"""Движок подбора: жёсткие фильтры + ранжирование."""

from collections.abc import Sequence

from core.economics import OwnershipCost, OwnershipInput, calculate_ownership_cost
from core.errors import InvalidOwnershipInputError
from core.fit import SolutionFit, evaluate_fit
from core.policy import DEFAULT_POLICY, CalculationPolicy
from core.requirement import EnergyRequirement
from core.solution import SolutionKind
from matching.candidate import Candidate
from matching.recommendation import Recommendation

#: (покрытие, размерность метрики, значение метрики, -комиссия). См. ADR-029.
_SortKey = tuple[int, int, float, float]


def _cost_key(candidate: Candidate, ownership: OwnershipCost | None) -> tuple[int, float]:
    """Метрика стоимости вместе с её размерностью.

    Первый элемент — размерность: 0 для грн/кВт·ч, 1 для грн. Он идёт в
    сортировочный кортеж ПЕРЕД самим значением, поэтому числа в разных
    размерностях никогда не попадают в одно сравнение (ADR-029).
    """
    if ownership is not None:
        return (0, ownership.cost_per_kwh_uah)
    return (1, candidate.price_uah)


def select_recommendations(
    requirement: EnergyRequirement,
    candidates: Sequence[Candidate],
    *,
    grid_tariff_uah_per_kwh: float | None = None,
    fuel_price_uah_per_l: float | None = None,
    policy: CalculationPolicy = DEFAULT_POLICY,
    limit: int = 5,
) -> tuple[Recommendation, ...]:
    """Фильтрует и ранжирует кандидатов под конкретную потребность."""
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if grid_tariff_uah_per_kwh is not None and grid_tariff_uah_per_kwh <= 0:
        raise ValueError("grid_tariff_uah_per_kwh должен быть > 0 или None")
    if fuel_price_uah_per_l is not None and fuel_price_uah_per_l <= 0:
        raise ValueError("fuel_price_uah_per_l должен быть > 0 или None")

    scored: list[tuple[_SortKey, Candidate, SolutionFit, OwnershipCost | None]] = []

    for candidate in candidates:
        if not candidate.in_stock:
            continue

        fit = evaluate_fit(requirement, candidate.solution, policy)
        if not fit.can_run:
            continue

        ownership: OwnershipCost | None = None
        if grid_tariff_uah_per_kwh is not None:
            ownership_input = _build_ownership_input(
                candidate, fit, grid_tariff_uah_per_kwh, fuel_price_uah_per_l
            )
            if ownership_input is not None:
                ownership = calculate_ownership_cost(ownership_input, policy)

        cost_dimension, cost_value = _cost_key(candidate, ownership)
        key: _SortKey = (
            0 if fit.can_cover_window else 1,
            cost_dimension,
            cost_value,
            -candidate.commission_rate,
        )
        scored.append((key, candidate, fit, ownership))

    scored.sort(key=lambda row: row[0])

    return tuple(
        Recommendation(
            offer_id=candidate.offer_id,
            fit=fit,
            ownership=ownership,
            price_uah=candidate.price_uah,
            rank_position=position,
            component_offer_ids=candidate.component_offer_ids,
        )
        for position, (_, candidate, fit, ownership) in enumerate(scored[:limit], start=1)
    )


def _build_ownership_input(
    candidate: Candidate,
    fit: SolutionFit,
    grid_tariff: float,
    fuel_price: float | None,
) -> OwnershipInput | None:
    spec = candidate.solution
    try:
        if spec.kind is SolutionKind.GENERATOR:
            if fuel_price is None or spec.fuel_rate_l_per_kwh is None:
                return None
            if candidate.expected_lifetime_wh is None:
                return None
            return OwnershipInput(
                price_uah=candidate.price_uah,
                grid_tariff_uah_per_kwh=grid_tariff,
                expected_lifetime_wh=candidate.expected_lifetime_wh,
                fuel_price_uah_per_l=fuel_price,
                fuel_rate_l_per_kwh=spec.fuel_rate_l_per_kwh,
            )
        if spec.cycle_life is None:
            return None
        return OwnershipInput(
            price_uah=candidate.price_uah,
            grid_tariff_uah_per_kwh=grid_tariff,
            usable_energy_per_cycle_wh=fit.usable_energy_wh,
            cycle_life=spec.cycle_life,
        )
    except InvalidOwnershipInputError:
        return None