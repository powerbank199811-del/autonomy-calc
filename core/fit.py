"""Проверка: потянет ли конкретное решение конкретную потребность."""

from dataclasses import dataclass
from enum import Enum

from core.policy import DEFAULT_POLICY, CalculationPolicy
from core.requirement import EnergyRequirement, RequirementFlag
from core.solution import SolutionKind, SolutionSpec, Waveform
from core.units import Hours, Watt, WattHour, round_energy


class FitBlocker(Enum):
    NO_AC_OUTPUT = "no_ac_output"
    INSUFFICIENT_CONTINUOUS_POWER = "insufficient_continuous_power"
    INSUFFICIENT_PEAK_POWER = "insufficient_peak_power"
    INSUFFICIENT_APPARENT_POWER = "insufficient_apparent_power"
    MODIFIED_SINE_NOT_ALLOWED = "modified_sine_not_allowed"
    SWITCHOVER_TOO_SLOW = "switchover_too_slow"
    INSUFFICIENT_DC_POWER = "insufficient_dc_power"


class FitFlag(Enum):
    USED_MEASURED_CAPACITY = "used_measured_capacity"
    USED_DECLARED_DERATING = "used_declared_derating"
    FUEL_LIMITED = "fuel_limited"
    IDLE_DRAW_SIGNIFICANT = "idle_draw_significant"


@dataclass(frozen=True, slots=True)
class LossBreakdown:
    inverter_loss_wh: WattHour
    dc_conversion_loss_wh: WattHour
    idle_loss_wh: WattHour
    unusable_by_dod_wh: WattHour


@dataclass(frozen=True, slots=True)
class SolutionFit:
    can_run: bool
    can_cover_window: bool
    blockers: tuple[FitBlocker, ...]
    usable_energy_wh: WattHour
    required_from_storage_wh: WattHour
    autonomy_hours: float
    energy_margin: float
    power_margin: float
    losses: LossBreakdown
    flags: frozenset[FitFlag]


def evaluate_fit(
    requirement: EnergyRequirement,
    solution: SolutionSpec,
    policy: CalculationPolicy = DEFAULT_POLICY,
) -> SolutionFit:
    blockers = _power_blockers(requirement, solution)
    flags: set[FitFlag] = set()

    needs_ac = requirement.continuous_power_ac_w > 0
    inverter_loss = 0.0
    if needs_ac:
        from_inverter = requirement.energy_ac_wh / solution.inverter_efficiency
        inverter_loss = from_inverter - requirement.energy_ac_wh
    else:
        from_inverter = 0.0

    from_dc = requirement.energy_dc_wh / solution.dc_output_efficiency
    dc_loss = from_dc - requirement.energy_dc_wh

    idle_loss = solution.idle_draw_w * requirement.window_hours if needs_ac else 0.0
    required_from_storage = from_inverter + from_dc + idle_loss

    usable, unusable, capacity_flags = _usable_energy(solution, policy)
    flags |= capacity_flags
    if idle_loss > 0 and idle_loss / max(required_from_storage, 1e-9) > 0.15:
        flags.add(FitFlag.IDLE_DRAW_SIGNIFICANT)

    energy_margin = (usable / required_from_storage - 1.0) if required_from_storage else 0.0
    autonomy_hours = (
        requirement.window_hours * min(usable / required_from_storage, 99.0)
        if required_from_storage > 0
        else 0.0
    )
    demand_power = max(
        requirement.continuous_power_ac_w, requirement.continuous_power_dc_w
    )
    available_power = (
        solution.continuous_power_w if needs_ac else solution.dc_output_power_w
    )
    power_margin = (
        available_power / demand_power - 1.0 if demand_power > 0 else 0.0
    )

    return SolutionFit(
        can_run=not blockers,
        can_cover_window=not blockers and autonomy_hours >= requirement.window_hours,
        blockers=tuple(sorted(blockers, key=lambda b: b.value)),
        usable_energy_wh=round_energy(usable),
        required_from_storage_wh=round_energy(required_from_storage),
        autonomy_hours=round(autonomy_hours, 1),
        energy_margin=round(energy_margin, 3),
        power_margin=round(power_margin, 3),
        losses=LossBreakdown(
            inverter_loss_wh=round_energy(inverter_loss),
            dc_conversion_loss_wh=round_energy(dc_loss),
            idle_loss_wh=round_energy(idle_loss),
            unusable_by_dod_wh=round_energy(unusable),
        ),
        flags=frozenset(flags),
    )


def _power_blockers(
    requirement: EnergyRequirement, solution: SolutionSpec
) -> set[FitBlocker]:
    blockers: set[FitBlocker] = set()
    needs_ac = requirement.continuous_power_ac_w > 0

    if needs_ac:
        if solution.continuous_power_w <= 0:
            blockers.add(FitBlocker.NO_AC_OUTPUT)
            return blockers
        if requirement.continuous_power_ac_w > solution.continuous_power_w:
            blockers.add(FitBlocker.INSUFFICIENT_CONTINUOUS_POWER)
        peak = solution.peak_power_w or solution.continuous_power_w
        if requirement.startup_power_w > peak:
            blockers.add(FitBlocker.INSUFFICIENT_PEAK_POWER)
        if (
            solution.apparent_power_va is not None
            and requirement.apparent_power_va > solution.apparent_power_va
        ):
            blockers.add(FitBlocker.INSUFFICIENT_APPARENT_POWER)
        if (
            RequirementFlag.PURE_SINE_REQUIRED in requirement.flags
            and solution.waveform is Waveform.MODIFIED
        ):
            blockers.add(FitBlocker.MODIFIED_SINE_NOT_ALLOWED)
        if requirement.max_switchover_ms is not None:
            if (
                solution.switchover_ms is None
                or solution.switchover_ms > requirement.max_switchover_ms
            ):
                blockers.add(FitBlocker.SWITCHOVER_TOO_SLOW)

    if (
        requirement.continuous_power_dc_w > 0
        and solution.dc_output_power_w > 0
        and requirement.continuous_power_dc_w > solution.dc_output_power_w
    ):
        blockers.add(FitBlocker.INSUFFICIENT_DC_POWER)

    return blockers


def _usable_energy(
    solution: SolutionSpec, policy: CalculationPolicy
) -> tuple[float, float, set[FitFlag]]:
    flags: set[FitFlag] = set()

    if solution.kind is SolutionKind.GENERATOR:
        assert solution.tank_l is not None and solution.fuel_rate_l_per_kwh is not None
        flags.add(FitFlag.FUEL_LIMITED)
        return solution.tank_l / solution.fuel_rate_l_per_kwh * 1000.0, 0.0, flags

    if solution.measured_wh is not None:
        gross = float(solution.measured_wh)
        flags.add(FitFlag.USED_MEASURED_CAPACITY)
    else:
        assert solution.capacity_wh is not None
        gross = float(solution.capacity_wh) * policy.declared_capacity_derating
        flags.add(FitFlag.USED_DECLARED_DERATING)

    dod = policy.dod_for(solution.chemistry)
    return gross * dod, gross * (1.0 - dod), flags
