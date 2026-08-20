"""Нейтральное описание решения: повербанк, станция, инвертор+АКБ, генератор.

Здесь физика ИСТОЧНИКА: химия, КПД, холостое потребление, форма сигнала.
Ни цен, ни продавцов, ни брендов — это слой каталога, а не ядра.
"""

from dataclasses import dataclass
from enum import Enum

from core.errors import InvalidSolutionSpecError
from core.units import VoltAmpere, Watt, WattHour


class SolutionKind(Enum):
    """Тип решения. Определяет, откуда берётся полезная энергия."""

    POWERBANK = "powerbank"
    STATION = "station"
    INVERTER_BATTERY = "inverter_battery"
    GENERATOR = "generator"


class StorageChemistry(Enum):
    """Химия накопителя. Задаёт допустимую глубину разряда."""

    LIFEPO4 = "lifepo4"
    LI_ION = "li_ion"
    AGM = "agm"
    NONE = "none"


class Waveform(Enum):
    """Форма выходного сигнала инвертора."""

    PURE_SINE = "pure_sine"
    MODIFIED = "modified"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class SolutionSpec:
    """Физические характеристики решения.

    capacity_wh — заявленная ёмкость, measured_wh — измеренная на FNB24P.
    Если есть измеренная, считаем по ней и ставим флаг.
    """

    kind: SolutionKind
    chemistry: StorageChemistry = StorageChemistry.NONE
    capacity_wh: WattHour | None = None
    measured_wh: WattHour | None = None
    continuous_power_w: Watt = Watt(0.0)
    peak_power_w: Watt = Watt(0.0)
    apparent_power_va: VoltAmpere | None = None
    dc_output_power_w: Watt = Watt(0.0)
    inverter_efficiency: float = 0.90
    dc_output_efficiency: float = 0.95
    idle_draw_w: Watt = Watt(0.0)
    waveform: Waveform = Waveform.NONE
    switchover_ms: int | None = None
    fuel_rate_l_per_kwh: float | None = None
    tank_l: float | None = None
    cycle_life: int | None = None
    #: Переопределяет policy.dod_for(chemistry), когда есть даташит на
    #: конкретный товар (см. ADR-025). None — используется дефолт по химии.
    depth_of_discharge_override: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 < self.inverter_efficiency <= 1.0:
            raise InvalidSolutionSpecError("inverter_efficiency вне (0, 1]")
        if not 0.0 < self.dc_output_efficiency <= 1.0:
            raise InvalidSolutionSpecError("dc_output_efficiency вне (0, 1]")
        if self.peak_power_w and self.peak_power_w < self.continuous_power_w:
            raise InvalidSolutionSpecError("peak_power_w меньше continuous_power_w")
        if self.kind is SolutionKind.GENERATOR:
            if not self.fuel_rate_l_per_kwh or not self.tank_l:
                raise InvalidSolutionSpecError("генератору нужны fuel_rate и tank_l")
        elif self.capacity_wh is None and self.measured_wh is None:
            raise InvalidSolutionSpecError("накопителю нужна ёмкость")
        for value in (self.capacity_wh, self.measured_wh):
            if value is not None and value <= 0:
                raise InvalidSolutionSpecError("ёмкость должна быть > 0")
        if self.depth_of_discharge_override is not None:
            if not 0.0 < self.depth_of_discharge_override <= 1.0:
                raise InvalidSolutionSpecError("depth_of_discharge_override вне (0, 1]")