"""Движок подбора: жёсткие фильтры и ранжирование."""

import pytest

from core.appliances import ApplianceSpec
from core.demand import calculate_requirement
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.requirement import EnergyRequirement
from core.solution import SolutionKind, SolutionSpec, StorageChemistry, Waveform
from core.units import Hours, Watt, WattHour
from matching.candidate import Candidate, InvalidCandidateError
from matching.engine import select_recommendations


def _req(fridge: ApplianceSpec, hours: int = 4) -> EnergyRequirement:
    return calculate_requirement(
        LoadProfile(items=(LoadItem(appliance=fridge),)),
        AutonomyTarget(window_hours=Hours(hours)),
    )


def _station(
    offer_id: str, price: float, commission: float, capacity_wh: float = 1000,
    continuous_w: float = 1000, peak_w: float = 2000, in_stock: bool = True,
) -> Candidate:
    return Candidate(
        offer_id=offer_id, price_uah=price, commission_rate=commission, in_stock=in_stock,
        solution=SolutionSpec(
            kind=SolutionKind.STATION, chemistry=StorageChemistry.LIFEPO4,
            capacity_wh=WattHour(capacity_wh), continuous_power_w=Watt(continuous_w),
            peak_power_w=Watt(peak_w), waveform=Waveform.PURE_SINE, cycle_life=3000,
        ),
    )


def test_weak_inverter_excluded_entirely(fridge: ApplianceSpec) -> None:
    weak = _station("weak", price=10000, commission=0.15, continuous_w=300, peak_w=600)
    strong = _station("strong", price=25000, commission=0.05, continuous_w=1000, peak_w=2000)
    result = select_recommendations(_req(fridge), [weak, strong])
    offer_ids = [r.offer_id for r in result]
    assert "weak" not in offer_ids
    assert "strong" in offer_ids


def test_out_of_stock_excluded(fridge: ApplianceSpec) -> None:
    out = _station("out", price=5000, commission=0.2, in_stock=False)
    available = _station("available", price=25000, commission=0.05)
    result = select_recommendations(_req(fridge), [out, available])
    assert [r.offer_id for r in result] == ["available"]


def test_full_coverage_beats_partial_even_if_pricier(fridge: ApplianceSpec) -> None:
    partial = _station("partial", price=8000, commission=0.15, capacity_wh=300)
    full = _station("full", price=25000, commission=0.05, capacity_wh=2000)
    result = select_recommendations(_req(fridge, hours=8), [partial, full])
    assert result[0].offer_id == "full"
    assert result[0].fit.can_cover_window is True
    assert result[1].offer_id == "partial"
    assert result[1].fit.can_run is True
    assert result[1].fit.can_cover_window is False


def test_commission_never_overrides_primary_ranking(fridge: ApplianceSpec) -> None:
    cheap_low_commission = _station("cheap", price=15000, commission=0.03)
    expensive_high_commission = _station("expensive", price=30000, commission=0.25)
    result = select_recommendations(
        _req(fridge), [cheap_low_commission, expensive_high_commission],
        grid_tariff_uah_per_kwh=5.0,
    )
    assert result[0].offer_id == "cheap"


def test_commission_breaks_ties_only(fridge: ApplianceSpec) -> None:
    low_commission = _station("low_comm", price=20000, commission=0.02, capacity_wh=1000)
    high_commission = _station("high_comm", price=20000, commission=0.20, capacity_wh=1000)
    result = select_recommendations(_req(fridge), [low_commission, high_commission])
    assert result[0].offer_id == "high_comm"


def test_ownership_skipped_without_tariff(fridge: ApplianceSpec) -> None:
    candidate = _station("solo", price=20000, commission=0.1)
    result = select_recommendations(_req(fridge), [candidate])
    assert result[0].ownership is None


def test_ownership_present_with_tariff(fridge: ApplianceSpec) -> None:
    candidate = _station("solo", price=20000, commission=0.1)
    result = select_recommendations(_req(fridge), [candidate], grid_tariff_uah_per_kwh=5.0)
    assert result[0].ownership is not None
    assert result[0].ownership.cost_per_kwh_uah > 0


def test_recommendation_never_exposes_commission(fridge: ApplianceSpec) -> None:
    candidate = _station("solo", price=20000, commission=0.1)
    result = select_recommendations(_req(fridge), [candidate])
    assert not hasattr(result[0], "commission_rate")


def test_limit_truncates(fridge: ApplianceSpec) -> None:
    candidates = [_station(f"c{i}", price=10000 + i * 100, commission=0.1) for i in range(10)]
    result = select_recommendations(_req(fridge), candidates, limit=3)
    assert len(result) == 3


def test_empty_when_nothing_fits(fridge: ApplianceSpec) -> None:
    weak = _station("weak", price=5000, commission=0.1, continuous_w=100, peak_w=150)
    result = select_recommendations(_req(fridge), [weak])
    assert result == ()


def test_rank_position_is_sequential_from_one(fridge: ApplianceSpec) -> None:
    candidates = [_station(f"c{i}", price=10000 + i * 1000, commission=0.1) for i in range(4)]
    result = select_recommendations(_req(fridge), candidates)
    assert [r.rank_position for r in result] == [1, 2, 3, 4]


def test_generator_needs_expected_lifetime_for_ownership(fridge: ApplianceSpec) -> None:
    generator = Candidate(
        offer_id="gen", price_uah=20000, commission_rate=0.1,
        solution=SolutionSpec(
            kind=SolutionKind.GENERATOR, continuous_power_w=Watt(2000), peak_power_w=Watt(2500),
            fuel_rate_l_per_kwh=0.4, tank_l=4.0, waveform=Waveform.PURE_SINE,
        ),
    )
    result = select_recommendations(
        _req(fridge), [generator], grid_tariff_uah_per_kwh=5.0, fuel_price_uah_per_l=55.0,
    )
    assert result[0].ownership is None
    assert result[0].fit.can_run is True


def test_invalid_candidate_rejected() -> None:
    with pytest.raises(InvalidCandidateError):
        Candidate(
            offer_id="bad", price_uah=-100, commission_rate=0.1,
            solution=SolutionSpec(
                kind=SolutionKind.STATION, chemistry=StorageChemistry.LIFEPO4,
                capacity_wh=WattHour(1000), continuous_power_w=Watt(1000),
            ),
        )


def _station_without_cycle_life(offer_id: str, price: float, capacity_wh: float) -> Candidate:
    """Станция без cycle_life: экономику для неё посчитать нечем."""
    return Candidate(
        offer_id=offer_id, price_uah=price, commission_rate=0.0,
        solution=SolutionSpec(
            kind=SolutionKind.STATION, chemistry=StorageChemistry.LIFEPO4,
            capacity_wh=WattHour(capacity_wh), continuous_power_w=Watt(1000),
            peak_power_w=Watt(2000), waveform=Waveform.PURE_SINE,
        ),
    )


def test_cost_metric_never_compares_across_dimensions(fridge: ApplianceSpec) -> None:
    """Кандидат с LCOE не может проиграть кандидату с ценой по величине числа.

    Числа подобраны намеренно вырожденными: у станции with_lcoe ресурс циклов
    занижен так, что её LCOE (грн/кВт·ч) численно ПРЕВЫШАЕТ цену (грн) второй
    станции. Пока метрика стоимости лежала в кортеже без указания размерности,
    такое сравнение решало порядок выдачи. Теперь размерность идёт в ключе
    раньше значения, и сравнение между разными размерностями невозможно.
    """
    with_lcoe = Candidate(
        offer_id="with_lcoe", price_uah=40000, commission_rate=0.0,
        solution=SolutionSpec(
            kind=SolutionKind.STATION, chemistry=StorageChemistry.LIFEPO4,
            capacity_wh=WattHour(2000), continuous_power_w=Watt(1000),
            peak_power_w=Watt(2000), waveform=Waveform.PURE_SINE, cycle_life=5,
        ),
    )
    without_lcoe = _station_without_cycle_life("without_lcoe", price=8000, capacity_wh=2000)

    result = select_recommendations(
        _req(fridge), [without_lcoe, with_lcoe], grid_tariff_uah_per_kwh=4.32
    )

    assert result[0].ownership is not None
    assert result[0].ownership.cost_per_kwh_uah > without_lcoe.price_uah
    assert [r.offer_id for r in result] == ["with_lcoe", "without_lcoe"]


def test_candidate_without_economics_ranks_below_one_with_it(fridge: ApplianceSpec) -> None:
    """При равном покрытии посчитанная экономика важнее непосчитанной.

    Отсутствие данных не даёт преимущества: дешёвая позиция без cycle_life
    не обгоняет дорогую с полными данными. Клиент видит это в ownership=None
    и может объяснить пользователю, почему экономика не показана.
    """
    cheap_no_data = _station_without_cycle_life("cheap_no_data", price=9000, capacity_wh=2000)
    pricey_with_data = _station("pricey_with_data", price=30000, commission=0.0, capacity_wh=2000)

    result = select_recommendations(
        _req(fridge), [cheap_no_data, pricey_with_data], grid_tariff_uah_per_kwh=4.32
    )

    assert [r.offer_id for r in result] == ["pricey_with_data", "cheap_no_data"]
    assert result[0].ownership is not None
    assert result[1].ownership is None


def test_without_tariff_all_candidates_share_one_dimension(fridge: ApplianceSpec) -> None:
    """Без тарифа экономики нет ни у кого — сравнение снова однородное, по цене."""
    cheap = _station_without_cycle_life("cheap", price=9000, capacity_wh=2000)
    pricey = _station("pricey", price=30000, commission=0.0, capacity_wh=2000)

    result = select_recommendations(_req(fridge), [cheap, pricey])

    assert [r.offer_id for r in result] == ["cheap", "pricey"]
    assert all(r.ownership is None for r in result)


def test_non_positive_tariff_rejected(fridge: ApplianceSpec) -> None:
    """Нулевой тариф — ошибка ввода, а не повод молча не считать экономику."""
    station = _station("s", price=30000, commission=0.0)
    with pytest.raises(ValueError):
        select_recommendations(_req(fridge), [station], grid_tariff_uah_per_kwh=0.0)


def test_non_positive_fuel_price_rejected(fridge: ApplianceSpec) -> None:
    """То же для цены топлива: нулевая цена сделала бы генератор бесплатным."""
    station = _station("s", price=30000, commission=0.0)
    with pytest.raises(ValueError):
        select_recommendations(
            _req(fridge), [station], grid_tariff_uah_per_kwh=4.32, fuel_price_uah_per_l=0.0
        )

def test_candidate_rejects_single_component_offer_id() -> None:
    """component_offer_ids должен либо быть None, либо содержать >= 2 частей."""
    with pytest.raises(InvalidCandidateError):
        Candidate(
            offer_id="s",
            solution=_station("s2", 1000, 0.0).solution,
            price_uah=1000,
            commission_rate=0.0,
            component_offer_ids=("only_one",),
        )


def test_candidate_rejects_empty_part_in_component_offer_ids() -> None:
    with pytest.raises(InvalidCandidateError):
        Candidate(
            offer_id="s",
            solution=_station("s2", 1000, 0.0).solution,
            price_uah=1000,
            commission_rate=0.0,
            component_offer_ids=("inv_x", ""),
        )


def test_simple_candidate_component_offer_ids_is_none(fridge: ApplianceSpec) -> None:
    station = _station("simple", price=30000, commission=0.05)
    assert station.component_offer_ids is None

    result = select_recommendations(_req(fridge), [station])
    assert result[0].component_offer_ids is None


def test_kit_candidate_component_offer_ids_propagates_to_recommendation(
    fridge: ApplianceSpec,
) -> None:
    kit = Candidate(
        offer_id="kit__inv_a__bat_b",
        solution=_station("x", 1000, 0.0).solution,
        price_uah=40000,
        commission_rate=0.03,
        component_offer_ids=("inv_a", "bat_b"),
    )
    result = select_recommendations(_req(fridge), [kit])
    assert result[0].component_offer_ids == ("inv_a", "bat_b")
