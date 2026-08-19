"""Выходной контракт ядра: сколько энергии и мощности нужно НА РОЗЕТКЕ.

EnergyRequirement ничего не знает про батареи, химию и КПД инвертора.
Потери источника применяет к себе каждый кандидат в core.matching.
"""

from dataclasses import dataclass
from enum import Enum

from core.units import Hours, VoltAmpere, Watt, WattHour


class RequirementFlag(Enum):
    """Жёсткие требования к решению. Коды, не тексты: перевод — у клиента."""

    PURE_SINE_REQUIRED = "pure_sine_required"
    UPS_MODE_REQUIRED = "ups_mode_required"
    HIGH_STARTUP = "high_startup"
    DC_ONLY = "dc_only"


class AssumptionCode(Enum):
    """Допущения, применённые в расчёте. Показываются пользователю."""

    SINGLE_SIMULTANEOUS_STARTUP = "single_simultaneous_startup"
    NO_DIVERSITY_FACTOR = "no_diversity_factor"
    USER_OVERRIDE_APPLIED = "user_override_applied"


@dataclass(frozen=True, slots=True)
class LoadContribution:
    """Вклад одной позиции. Это продукт, а не отладка."""

    appliance_code: str
    energy_wh: WattHour
    share: float
    peak_contribution_w: Watt


@dataclass(frozen=True, slots=True)
class EnergyRequirement:
    """Потребность в энергии и мощности за одно окно автономности."""

    energy_ac_wh: WattHour
    energy_dc_wh: WattHour
    continuous_power_ac_w: Watt
    continuous_power_dc_w: Watt
    apparent_power_va: VoltAmpere
    startup_power_w: Watt
    window_hours: Hours
    flags: frozenset[RequirementFlag]
    max_switchover_ms: int | None
    breakdown: tuple[LoadContribution, ...]
    assumptions: tuple[AssumptionCode, ...]

    @property
    def total_energy_wh(self) -> WattHour:
        """Суммарная энергия по обеим шинам. Для показа пользователю."""
        return WattHour(self.energy_ac_wh + self.energy_dc_wh)
