"""Проверка подбора решения под потребность: инварианты и золотые сценарии."""

import pytest

from core.appliances import ApplianceSpec
from core.demand import calculate_requirement
from core.fit import FitBlocker, FitFlag, evaluate_fit
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.requirement import EnergyRequirement
from core.solution import SolutionKind, SolutionSpec, StorageChemistry, Waveform
from core.units import Hours, VoltAmpere, Watt, WattHour


@pytest.fixture
def station_1000() -> SolutionSpec:
    return SolutionSpec(
        kind=SolutionKind.STATION,
        chemistry=StorageChemistry.LIFEPO4,
        capacity_wh=WattHour(1000),
        continuous_power_w=Watt(1000),
        peak_power_w=Watt(2000),
        dc_output_power_w=Watt(100),
        inverter_efficiency=0.90,
        idle_draw_w=Watt(8),
        waveform=Waveform.PURE_SINE,
        switchover_ms=20,
        cycle_life=3000,
    )


@pytest.fixture
def powerbank_20k() -> SolutionSpec:
    return SolutionSpec(
        kind=SolutionKind.POWERBANK,
        chemistry=StorageChemistry.LI_ION,
        capacity_wh=WattHour(74),
        measured_wh=WattHour(63),
        dc_output_power_w=Watt(65),
        cycle_life=500,
    )


def _req(items: tuple[LoadItem, ...], hours: int) -> EnergyRequirement:
    return calculate_requirement(
        LoadProfile(items=items), AutonomyTarget(window_hours=Hours(hours))
    )


def test_station_covers_blackout(
    station_1000: SolutionSpec,
    fridge: ApplianceSpec,
    led_lamp: ApplianceSpec,
    router: ApplianceSpec,
) -> None:
    req = _req(
        (
            LoadItem(appliance=fridge),
            LoadItem(appliance=led_lamp, quantity=3),
            LoadItem(appliance=router),
        ),
        4,
    )
    fit = evaluate_fit(req, station_1000)
    assert fit.can_run and fit.can_cover_window
    assert fit.required_from_storage_wh == 439.0
    assert fit.usable_energy_wh == 765.0
    assert fit.autonomy_hours == pytest.approx(7.0, abs=0.1)
    assert FitFlag.USED_DECLARED_DERATING in fit.flags


def test_measured_capacity_wins(powerbank_20k: SolutionSpec, phone: ApplianceSpec) -> None:
    req = _req((LoadItem(appliance=phone, hours=Hours(2)),), 10)
    fit = evaluate_fit(req, powerbank_20k)
    assert FitFlag.USED_MEASURED_CAPACITY in fit.flags
    assert fit.usable_energy_wh == float(round(63 * 0.85))


def test_powerbank_cannot_run_ac_load(
    powerbank_20k: SolutionSpec, fridge: ApplianceSpec
) -> None:
    fit = evaluate_fit(_req((LoadItem(appliance=fridge),), 4), powerbank_20k)
    assert not fit.can_run
    assert fit.blockers == (FitBlocker.NO_AC_OUTPUT,)


def test_startup_current_blocks_weak_inverter(fridge: ApplianceSpec) -> None:
    weak = SolutionSpec(
        kind=SolutionKind.STATION,
        chemistry=StorageChemistry.LIFEPO4,
        capacity_wh=WattHour(600),
        continuous_power_w=Watt(300),
        peak_power_w=Watt(600),
        waveform=Waveform.PURE_SINE,
    )
    fit = evaluate_fit(_req((LoadItem(appliance=fridge),), 4), weak)
    assert not fit.can_run
    assert FitBlocker.INSUFFICIENT_PEAK_POWER in fit.blockers
    assert FitBlocker.INSUFFICIENT_CONTINUOUS_POWER not in fit.blockers


def test_modified_sine_blocked_for_boiler(gas_boiler: ApplianceSpec) -> None:
    cheap = SolutionSpec(
        kind=SolutionKind.INVERTER_BATTERY,
        chemistry=StorageChemistry.AGM,
        capacity_wh=WattHour(1200),
        continuous_power_w=Watt(1000),
        peak_power_w=Watt(2000),
        apparent_power_va=VoltAmpere(1000),
        waveform=Waveform.MODIFIED,
        switchover_ms=200,
    )
    fit = evaluate_fit(_req((LoadItem(appliance=gas_boiler),), 8), cheap)
    assert not fit.can_run
    assert FitBlocker.MODIFIED_SINE_NOT_ALLOWED in fit.blockers
    assert FitBlocker.SWITCHOVER_TOO_SLOW in fit.blockers


def test_agm_loses_half_the_capacity(router: ApplianceSpec) -> None:
    agm = SolutionSpec(
        kind=SolutionKind.INVERTER_BATTERY,
        chemistry=StorageChemistry.AGM,
        capacity_wh=WattHour(1200),
        continuous_power_w=Watt(800),
        peak_power_w=Watt(1600),
        waveform=Waveform.PURE_SINE,
    )
    fit = evaluate_fit(_req((LoadItem(appliance=router),), 8), agm)
    assert fit.usable_energy_wh == 510.0
    assert fit.losses.unusable_by_dod_wh == 510.0


def test_generator_energy_from_fuel(fridge: ApplianceSpec) -> None:
    generator = SolutionSpec(
        kind=SolutionKind.GENERATOR,
        continuous_power_w=Watt(2000),
        peak_power_w=Watt(2500),
        fuel_rate_l_per_kwh=0.40,
        tank_l=4.0,
        waveform=Waveform.PURE_SINE,
        inverter_efficiency=1.0,
    )
    fit = evaluate_fit(_req((LoadItem(appliance=fridge),), 8), generator)
    assert FitFlag.FUEL_LIMITED in fit.flags
    assert fit.usable_energy_wh == 10000.0
    assert fit.can_cover_window


def test_idle_draw_flagged_on_small_load(router: ApplianceSpec) -> None:
    station = SolutionSpec(
        kind=SolutionKind.STATION,
        chemistry=StorageChemistry.LIFEPO4,
        capacity_wh=WattHour(500),
        continuous_power_w=Watt(500),
        peak_power_w=Watt(1000),
        idle_draw_w=Watt(8),
        waveform=Waveform.PURE_SINE,
    )
    fit = evaluate_fit(_req((LoadItem(appliance=router),), 8), station)
    assert FitFlag.IDLE_DRAW_SIGNIFICANT in fit.flags
    assert fit.losses.idle_loss_wh == 64.0


def test_dc_load_ignores_idle_draw(
    station_1000: SolutionSpec, phone: ApplianceSpec
) -> None:
    fit = evaluate_fit(_req((LoadItem(appliance=phone, hours=Hours(2)),), 4), station_1000)
    assert fit.losses.idle_loss_wh == 0.0
    assert fit.losses.inverter_loss_wh == 0.0


def test_losses_only_increase_demand(
    station_1000: SolutionSpec, fridge: ApplianceSpec
) -> None:
    req = _req((LoadItem(appliance=fridge),), 6)
    fit = evaluate_fit(req, station_1000)
    assert fit.required_from_storage_wh > req.total_energy_wh


def test_usable_never_exceeds_capacity(station_1000: SolutionSpec, router: ApplianceSpec) -> None:
    fit = evaluate_fit(_req((LoadItem(appliance=router),), 8), station_1000)
    assert station_1000.capacity_wh is not None
    assert fit.usable_energy_wh <= station_1000.capacity_wh


def test_determinism(station_1000: SolutionSpec, fridge: ApplianceSpec) -> None:
    req = _req((LoadItem(appliance=fridge),), 5)
    assert evaluate_fit(req, station_1000) == evaluate_fit(req, station_1000)
