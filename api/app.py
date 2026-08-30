"""Внутренний API: единственный контракт для сайта и Telegram-бота.

Слой намеренно тонкий. Здесь нет ни одной строки, которая принимает решение
о подборе или считает энергию — только перевод HTTP <-> домен и обработка
доменных ошибок. Если сюда захочется добавить условие «а для генераторов
сделаем иначе» — это признак, что условие место в matching, а не тут.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from api.catalog_provider import (
    load_all_candidates,
    load_appliance_catalog,
    load_appliances,
    load_display_index,
)
from api.display_index import DisplayIndex
from api.schemas import (
    ComponentRole,
    FitOut,
    OwnershipOut,
    PurchaseOut,
    RecommendationOut,
    RecommendationRequest,
    RecommendationResponse,
    RejectionOut,
    RequirementOut,
)

from typing import Mapping

from reference.appliances import CatalogAppliance
from catalog.products import CapacitySource
from api.redirect import build_router
from core.demand import calculate_requirement
from core.errors import DomainError
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.requirement import EnergyRequirement
from core.units import Hours
from matching.engine import select_recommendations
from matching.recommendation import Recommendation
from matching.rejection import RejectionReason, explain_rejections
from tracking.sqlite_log import SqliteClickLog
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from api.query_params import CalcQuery, SelectedAppliance, parse_calc_query, to_query_string
from api.rejection_summary import RejectionSummary, summarize_rejections
from api.schemas import ApplianceSelection
from api.templating import get_environment


app = FastAPI(title="autonomy-calc", version="0.1.0")

#: Журнал кликов приложения. Единственное место, где выбрана конкретная
#: реализация порта ClickLog — композиционный корень (ADR-034).
CLICKS_DB = Path(__file__).resolve().parent.parent / "var" / "clicks.db"
click_log = SqliteClickLog(CLICKS_DB)
app.include_router(build_router(click_log))





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

def _purchases(
    recommendation: Recommendation, index: DisplayIndex
) -> tuple[tuple[PurchaseOut, ...], CapacitySource | None, bool | None]:
    """purchases + capacity_source + solar_optional одной сборкой.

    Роль в ките — по ПОЗИЦИИ в component_offer_ids (ADR-038): порядок
    (инвертор, АКБ) зафиксирован в kit_candidates. Парсить строку
    offer_id запрещено.
    """
    ids = recommendation.component_offer_ids
    if ids is None:
        entry = index.get(recommendation.offer_id)
        purchase = PurchaseOut(
            offer_id=entry.offer_id,
            role=ComponentRole.PRIMARY,
            name=entry.name,
            brand=entry.brand,
            image_url=entry.image_url,
            seller_label=entry.seller_label,
            price_uah=entry.price_uah,
        )
        return (purchase,), entry.capacity_source, None

    inverter = index.get(ids[0])
    battery = index.get(ids[1])
    purchases = (
        PurchaseOut(
            offer_id=inverter.offer_id,
            role=ComponentRole.INVERTER,
            name=inverter.name,
            brand=inverter.brand,
            image_url=inverter.image_url,
            seller_label=inverter.seller_label,
            price_uah=inverter.price_uah,
        ),
        PurchaseOut(
            offer_id=battery.offer_id,
            role=ComponentRole.BATTERY,
            name=battery.name,
            brand=battery.brand,
            image_url=battery.image_url,
            seller_label=battery.seller_label,
            price_uah=battery.price_uah,
        ),
    )
    # solar_optional имеет смысл только у кита: True = инвертор гибридный,
    # панели подключить МОЖНО, но они не обязательны (ADR-038).
    return purchases, battery.capacity_source, inverter.accepts_solar_input



def _recommendation_out(
    recommendation: Recommendation, index: DisplayIndex
) -> RecommendationOut:
    fit = recommendation.fit
    ownership = recommendation.ownership
    purchases, capacity_source, solar_optional = _purchases(recommendation, index)
    return RecommendationOut(
        offer_id=recommendation.offer_id,
        rank_position=recommendation.rank_position,
        price_uah=recommendation.price_uah,
        component_offer_ids=(
            None
            if recommendation.component_offer_ids is None
            else list(recommendation.component_offer_ids)
        ),
        purchases=purchases,
        capacity_source=capacity_source,
        solar_optional=solar_optional,
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


def _calculate(request: RecommendationRequest) -> RecommendationResponse:
    """Один путь расчёта для JSON-API и для SSR-страницы.

    Вынесено намеренно: два роута, считающие по-разному, — вопрос времени,
    а не вероятности. Диагностика отказов остаётся вторым проходом и только
    при пустой выдаче (ADR-031).
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

    display_index = load_display_index()
    return RecommendationResponse(
        requirement=_requirement_out(requirement),
        recommendations=[
            _recommendation_out(item, display_index) for item in recommendations
        ],
        rejected=rejected,
    )

@app.post("/api/v1/recommendations", response_model=RecommendationResponse)
def post_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    """Подбор решений под профиль нагрузки."""
    return _calculate(request)

    
#: Шесть позиций первого экрана. Отбор не по частотности — её нет, —
#: а по покрытию целевых формулировок проблем: холодильник, котёл, роутер.
TOP_APPLIANCE_CODES = (
    "fridge_medium",
    "gas_boiler",
    "wifi_router_9v",
    "led_bulb_9w",
    "tv_led_43",
    "smartphone_charge",
)

HOUR_OPTIONS = (2.0, 4.0, 8.0, 12.0, 24.0)

#: Пресеты — это <a href>, а не сущность. scenarios.yaml здесь ни при чём.
PRESETS = (
    ("Мінімум", "/?p=led_bulb_9w:3,smartphone_charge,wifi_router_9v&h=4"),
    ("Холодильник + інтернет", "/?p=fridge_medium,led_bulb_9w:2,wifi_router_9v&h=4"),
    ("Опалення", "/?p=gas_boiler,led_bulb_9w:2,wifi_router_9v&h=8"),
)


@app.get("/", response_class=HTMLResponse, response_model=None)
def index(
    request: Request,
    p: list[str] | None = Query(default=None),
    h: str | None = None,
    t: str | None = None,
    f: str | None = None,
) -> HTMLResponse | RedirectResponse:
    """Форма расчёта и результат на одной странице.

    Форма отправляет repeated-параметры (?p=a&p=b) — это всё, что умеет
    нативный HTML. Каноническая ссылка — с запятыми. Поэтому неканоническая
    строка запроса получает 302: в мессенджер уходит уже нормализованный URL,
    а сам он редиректа не вызывает.
    """
    catalog = load_appliance_catalog()
    query = parse_calc_query(p, h, t, f, (entry.code for entry in catalog))

    canonical = to_query_string(query)
    current = request.url.path + (("?" + request.url.query) if request.url.query else "")
    if not query.is_empty and current != canonical:
        return RedirectResponse(canonical, status_code=302)

    by_code = {entry.code: entry for entry in catalog}
    selected_codes = {item.code for item in query.items}
    top = [by_code[code] for code in TOP_APPLIANCE_CODES if code in by_code]
    top_codes = {entry.code for entry in top}

    rest: dict[str, list[CatalogAppliance]] = {}
    for entry in catalog:
        if entry.code not in top_codes:
            rest.setdefault(entry.category, []).append(entry)

    # Категория с выбранным прибором раскрыта: человек пришёл по ссылке
    # и должен видеть свой выбор, не открывая аккордеоны вручную.
        categories = [
        {
            "title": category,
            "appliances": items,
            "has_selected": any(item.code in selected_codes for item in items),
            # Счётчик виден в свёрнутом виде: человек, который сам закрыл
            # категорию, не должен разворачивать её, чтобы вспомнить выбор.
            "selected_count": sum(1 for item in items if item.code in selected_codes),
        }
        for category, items in rest.items()
    ]

    # Чекбокс прибора существует ровно в одном месте. Дублировать выбранное
    # наверх нельзя: два <input name="p"> с одним value дадут при сабмите
    # p=code дважды, парсер сложит количества, и человек получит расчёт
    # на два холодильника. Вместо дубля — текстовая сводка.
    selected_names = [
        by_code[item.code].name_uk for item in query.items if item.code in by_code
    ]

    context: dict[str, object] = {
        "query": query,
        "top_appliances": top,
        "categories": categories,
        "selected_codes": selected_codes,
        "selected_names": selected_names,
        "hour_options": HOUR_OPTIONS,
        "presets": [{"title": title, "url": url} for title, url in PRESETS],
        "recommendations": [],
        "requirement": None,
        "rejections": RejectionSummary(total=0, out_of_stock=0, reasons=()),
        "profile_text": "",
    }

    if not query.is_empty:
        response = _calculate(
            RecommendationRequest(
                appliances=[
                    ApplianceSelection(code=item.code, quantity=item.quantity)
                    for item in query.items
                ],
                autonomy_hours=query.hours,
                grid_tariff_uah_per_kwh=query.tariff_uah_per_kwh,
                fuel_price_uah_per_l=query.fuel_price_uah_per_l,
            )
        )
        context["recommendations"] = response.recommendations
        context["requirement"] = response.requirement
        context["rejections"] = summarize_rejections(response.rejected or [])
        context["profile_text"] = _profile_text(query, by_code)

    html = get_environment().get_template("index.html").render(**context)
    return HTMLResponse(html)


def _profile_text(query: CalcQuery, by_code: "Mapping[str, CatalogAppliance]") -> str:
    """«Холодильник середній + Wi-Fi роутер, 4 години».

    Нужен не для красоты: человек открыл присланную другом ссылку и должен
    видеть, из чего считалось, не разбирая параметры в адресной строке.
    """
    parts = []
    for item in query.items:
        entry = by_code[item.code]
        name = entry.name_uk
        parts.append(name if item.quantity == 1 else f"{name} ×{item.quantity}")
    hours = int(query.hours) if query.hours == int(query.hours) else query.hours
    return " + ".join(parts) + f", {hours} год"

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    """Запрещает индексацию партнёрских редиректов.

    /go/* и так помечен X-Robots-Tag в самом ответе (двойная защита: поисковик
    может проиндексировать ссылку раньше, чем перейдёт по ней и увидит
    заголовок). robots.txt — первый рубеж, заголовок — второй.
    """
    return "User-agent: *\nDisallow: /go/\n"


@app.get("/api/v1/appliances")
def get_appliances() -> dict[str, list[dict[str, str]]]:
    """Справочник приборов для выпадающего списка на фронте."""
    return {
        "appliances": [
            {"code": entry.code, "name": entry.name_uk, "category": entry.category}
            for entry in load_appliance_catalog()
        ]
    }
