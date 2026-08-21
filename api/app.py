"""Внутренний API: единственный контракт для сайта и Telegram-бота.

Слой намеренно тонкий. Здесь нет ни одной строки, которая принимает решение
о подборе или считает энергию — только перевод HTTP <-> домен и обработка
доменных ошибок. Если сюда захочется добавить условие «а для генераторов
сделаем иначе» — это признак, что условие место в matching, а не тут.
"""

from fastapi import FastAPI, HTTPException

from api.catalog_provider import (
    load_all_candidates,
    load_appliance_catalog,
    load_appliances,
)
from api.schemas import (
    FitOut,
    OwnershipOut,
    RecommendationOut,
    RecommendationRequest,
    RecommendationResponse,
    RejectionOut,
    RequirementOut,
)
from core.demand import calculate_requirement
from core.errors import DomainError
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.requirement import EnergyRequirement
from core.units import Hours
from matching.engine import select_recommendations
from matching.recommendation import Recommendation
from matching.rejection import RejectionReason, explain_rejections

app = FastAPI(title="autonomy-calc", version="0.1.0")


def _build_profile(request: RecommendationRequest) -> LoadProfile:
    """Коды приборов -> доменный профиль нагрузки.

    Неизвестный код — 422 с указанием конкретного кода: клиент прислал то,
    чего нет в справочнике, и это ошибка запроса, а не сбой сервера.
    """
    appliances = load_appliances()
    items: list[LoadItem] = []
    for selection in request.appliances:
        spec = appliances.get(selection.code)
        if spec is None:
            raise HTTPException(
                status_code=422, detail=f"неизвестный код прибора: {selection.code}"
            )
        items.append(
            LoadItem(
                appliance=spec,
                quantity=selection.quantity,
                hours=None if selection.hours is None else Hours(selection.hours),
            )
        )
    return LoadProfile(items=tuple(items))


def _requirement_out(requirement: EnergyRequirement) -> RequirementOut:
    return RequirementOut(
        energy_ac_wh=requirement.energy_ac_wh,
        energy_dc_wh=requirement.energy_dc_wh,
        total_energy_wh=requirement.total_energy_wh,
        continuous_power_ac_w=requirement.continuous_power_ac_w,
        startup_power_w=requirement.startup_power_w,
        window_hours=requirement.window_hours,
    )


def _recommendation_out(recommendation: Recommendation) -> RecommendationOut:
    fit = recommendation.fit
    ownership = recommendation.ownership
    return RecommendationOut(
        offer_id=recommendation.offer_id,
        rank_position=recommendation.rank_position,
        price_uah=recommendation.price_uah,
        fit=FitOut(
            can_cover_window=fit.can_cover_window,
            autonomy_hours=fit.autonomy_hours,
            usable_energy_wh=fit.usable_energy_wh,
            energy_margin=fit.energy_margin,
            power_margin=fit.power_margin,
            flags=sorted(fit.flags, key=lambda flag: flag.value),
        ),
        ownership=None
        if ownership is None
        else OwnershipOut(
            cost_per_kwh_uah=ownership.cost_per_kwh_uah,
            lifetime_energy_kwh=ownership.lifetime_energy_kwh,
            fuel_opex_per_kwh_uah=ownership.fuel_opex_per_kwh_uah,
            cheaper_than_grid=ownership.cheaper_than_grid,
            payback_energy_kwh=ownership.payback_energy_kwh,
        ),
    )


def _rejection_out(reason: RejectionReason) -> RejectionOut:
    return RejectionOut(
        offer_id=reason.offer_id,
        out_of_stock=reason.out_of_stock,
        blockers=list(reason.blockers),
    )


@app.post("/api/v1/recommendations", response_model=RecommendationResponse)
def post_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    """Подбор решений под профиль нагрузки.

    Диагностика отказов считается вторым проходом и только при пустой
    выдаче (ADR-031): на успешном расчёте клиенту она не нужна.
    """
    profile = _build_profile(request)
    try:
        requirement = calculate_requirement(
            profile, AutonomyTarget(window_hours=Hours(request.autonomy_hours))
        )
        candidates = load_all_candidates()
        recommendations = select_recommendations(
            requirement,
            candidates,
            grid_tariff_uah_per_kwh=request.grid_tariff_uah_per_kwh,
            fuel_price_uah_per_l=request.fuel_price_uah_per_l,
            limit=request.limit,
        )
    except DomainError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    rejected: list[RejectionOut] | None = None
    if not recommendations:
        rejected = [
            _rejection_out(reason)
            for reason in explain_rejections(requirement, candidates)
        ]

    return RecommendationResponse(
        requirement=_requirement_out(requirement),
        recommendations=[_recommendation_out(item) for item in recommendations],
        rejected=rejected,
    )


@app.get("/api/v1/appliances")
def get_appliances() -> dict[str, list[dict[str, str]]]:
    """Справочник приборов для выпадающего списка на фронте."""
    return {
        "appliances": [
            {"code": entry.code, "name": entry.name_uk, "category": entry.category}
            for entry in load_appliance_catalog()
        ]
    }
