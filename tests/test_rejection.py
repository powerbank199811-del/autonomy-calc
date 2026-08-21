"""explain_rejections: диагностика отказов, параллельная select_recommendations."""

from core.appliances import ApplianceSpec
from core.demand import calculate_requirement
from core.fit import FitBlocker
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.requirement import EnergyRequirement
from core.solution import SolutionKind, SolutionSpec, StorageChemistry, Waveform
from core.units import Hours, Watt, WattHour
from matching.candidate import Candidate
from matching.engine import select_recommendations
from matching.rejection import explain_rejections


def _req(fridge: ApplianceSpec, hours: int = 4) -> EnergyRequirement:
    return calculate_requirement(
        LoadProfile(items=(LoadItem(appliance=fridge),)),
        AutonomyTarget(window_hours=Hours(hours)),
    )


def _station(
    offer_id: str, capacity_wh: float = 1000, continuous_w: float = 1000,
    peak_w: float = 2000, in_stock: bool = True, waveform: Waveform = Waveform.PURE_SINE,
) -> Candidate:
    return Candidate(
        offer_id=offer_id, price_uah=25000, commission_rate=0.05, in_stock=in_stock,
        solution=SolutionSpec(
            kind=SolutionKind.STATION, chemistry=StorageChemistry.LIFEPO4,
            capacity_wh=WattHour(capacity_wh), continuous_power_w=Watt(continuous_w),
            peak_power_w=Watt(peak_w), waveform=waveform, cycle_life=3000,
        ),
    )


def test_weak_inverter_reported_with_blocker(fridge: ApplianceSpec) -> None:
    weak = _station("weak", continuous_w=50, peak_w=100)
    result = explain_rejections(_req(fridge), [weak])
    assert len(result) == 1
    assert result[0].offer_id == "weak"
    assert result[0].out_of_stock is False
    assert FitBlocker.INSUFFICIENT_CONTINUOUS_POWER in result[0].blockers


def test_out_of_stock_reported_without_blockers_when_fit_is_fine(
    fridge: ApplianceSpec,
) -> None:
    out = _station("out", in_stock=False)
    result = explain_rejections(_req(fridge), [out])
    assert len(result) == 1
    assert result[0].out_of_stock is True
    assert result[0].blockers == ()


def test_out_of_stock_and_unfit_both_reported_independently(fridge: ApplianceSpec) -> None:
    """Нет на складе И не подходит физически — оба факта видны одновременно."""
    both = _station("both", in_stock=False, continuous_w=50, peak_w=100)
    result = explain_rejections(_req(fridge), [both])
    assert result[0].out_of_stock is True
    assert FitBlocker.INSUFFICIENT_CONTINUOUS_POWER in result[0].blockers


def test_partial_coverage_is_not_a_rejection(fridge: ApplianceSpec) -> None:
    """can_run=True, can_cover_window=False — это выдача, а не отказ."""
    partial = _station("partial", capacity_wh=100)
    result = explain_rejections(_req(fridge, hours=8), [partial])
    assert result == ()


def test_fitting_in_stock_candidate_not_reported(fridge: ApplianceSpec) -> None:
    good = _station("good")
    result = explain_rejections(_req(fridge), [good])
    assert result == ()


def test_order_matches_input_order(fridge: ApplianceSpec) -> None:
    weak_a = _station("weak_a", continuous_w=50, peak_w=100)
    weak_b = _station("weak_b", continuous_w=60, peak_w=100)
    result = explain_rejections(_req(fridge), [weak_b, weak_a])
    assert [r.offer_id for r in result] == ["weak_b", "weak_a"]


def test_complements_select_recommendations_partition(fridge: ApplianceSpec) -> None:
    """Каждый кандидат либо в recommendations, либо в explain_rejections — не в обоих сразу."""
    good = _station("good")
    weak = _station("weak", continuous_w=50, peak_w=100)
    out = _station("out", in_stock=False)
    candidates = [good, weak, out]

    recommended = {r.offer_id for r in select_recommendations(_req(fridge), candidates)}
    rejected = {r.offer_id for r in explain_rejections(_req(fridge), candidates)}

    assert recommended == {"good"}
    assert rejected == {"weak", "out"}
    assert recommended.isdisjoint(rejected)
