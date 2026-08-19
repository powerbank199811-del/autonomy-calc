"""Расчёт потребности. Чистая функция: одинаковый вход — одинаковый выход.

Формулы:
    энергия позиции   = power_w * quantity * hours * duty_cycle
    непрерывная мощн. = sum(power_w * quantity) по шине
    полная мощность   = sum(power_w * quantity / power_factor)
    пуск              = max_i(startup_i) + мощность остальных
"""

from core.appliances import PowerBus
from core.errors import InvalidLoadItemError
from core.load import AutonomyTarget, LoadProfile
from core.policy import DEFAULT_POLICY, CalculationPolicy
from core.requirement import (
    AssumptionCode,
    EnergyRequirement,
    LoadContribution,
    RequirementFlag,
)
from core.units import Hours, VoltAmpere, Watt, WattHour, round_energy, round_power


def calculate_requirement(
    profile: LoadProfile,
    target: AutonomyTarget,
    policy: CalculationPolicy = DEFAULT_POLICY,
) -> EnergyRequirement:
    """Считает потребность в энергии и мощности за одно окно автономности."""
    energy_ac = 0.0
    energy_dc = 0.0
    power_ac = 0.0
    power_dc = 0.0
    apparent = 0.0
    flags: set[RequirementFlag] = set()
    assumptions: set[AssumptionCode] = set()
    switchover: int | None = None
    raw_contributions: list[tuple[str, float, float]] = []

    for item in profile.items:
        hours = item.hours if item.hours is not None else target.window_hours
        if hours > target.window_hours:
            raise InvalidLoadItemError(
                f"{item.appliance.code}: hours={hours} больше окна {target.window_hours}"
            )

        unit_power = item.effective_power_w
        group_power = unit_power * item.quantity
        energy = group_power * hours * item.effective_duty_cycle

        if item.override is not None:
            assumptions.add(AssumptionCode.USER_OVERRIDE_APPLIED)

        if item.appliance.bus is PowerBus.AC_230:
            energy_ac += energy
            power_ac += group_power
            apparent += group_power / item.appliance.power_factor
            if item.appliance.requires_pure_sine:
                flags.add(RequirementFlag.PURE_SINE_REQUIRED)
            if item.appliance.startup_factor >= 3.0:
                flags.add(RequirementFlag.HIGH_STARTUP)
            if item.appliance.max_switchover_ms is not None:
                flags.add(RequirementFlag.UPS_MODE_REQUIRED)
                switchover = (
                    item.appliance.max_switchover_ms
                    if switchover is None
                    else min(switchover, item.appliance.max_switchover_ms)
                )
        else:
            energy_dc += energy
            power_dc += group_power

        raw_contributions.append((item.appliance.code, energy, group_power))

    if power_ac == 0.0:
        flags.add(RequirementFlag.DC_ONLY)
    if policy.diversity_factor == 1.0:
        assumptions.add(AssumptionCode.NO_DIVERSITY_FACTOR)

    startup = _startup_power(profile, power_ac, policy)
    if policy.single_simultaneous_startup:
        assumptions.add(AssumptionCode.SINGLE_SIMULTANEOUS_STARTUP)

    total_energy = energy_ac + energy_dc
    breakdown = tuple(
        LoadContribution(
            appliance_code=code,
            energy_wh=round_energy(energy),
            share=(energy / total_energy) if total_energy > 0 else 0.0,
            peak_contribution_w=round_power(group_power),
        )
        for code, energy, group_power in raw_contributions
    )

    return EnergyRequirement(
        energy_ac_wh=round_energy(energy_ac * policy.diversity_factor),
        energy_dc_wh=round_energy(energy_dc * policy.diversity_factor),
        continuous_power_ac_w=round_power(power_ac * policy.diversity_factor),
        continuous_power_dc_w=round_power(power_dc * policy.diversity_factor),
        apparent_power_va=VoltAmpere(round(apparent * policy.diversity_factor)),
        startup_power_w=round_power(startup * policy.diversity_factor),
        window_hours=Hours(target.window_hours),
        flags=frozenset(flags),
        max_switchover_ms=switchover,
        breakdown=breakdown,
        assumptions=tuple(sorted(assumptions, key=lambda a: a.value)),
    )


def _startup_power(
    profile: LoadProfile, power_ac: float, policy: CalculationPolicy
) -> float:
    """Худший пуск: один двигатель стартует, остальные уже работают."""
    ac_items = [i for i in profile.items if i.appliance.bus is PowerBus.AC_230]
    if not ac_items:
        return 0.0
    if not policy.single_simultaneous_startup:
        return sum(
            i.effective_power_w * i.quantity * i.appliance.startup_factor
            for i in ac_items
        )
    return max(
        power_ac + (i.appliance.startup_factor - 1.0) * i.effective_power_w
        for i in ac_items
    )
