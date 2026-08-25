"""Компоненты для 'сборки на лету': инвертор и АКБ по отдельности.

core.solution ничего про них не знает. InverterSpec/BatterySpec заведомо
неполные (инвертор без ёмкости, АКБ без мощности) и core.fit оценить их
сами по себе не может. Полноценный core.SolutionSpec появляется только
после сборки совместимой пары (catalog.kits.assemble_solution).
"""

from dataclasses import dataclass

from catalog.products import CapacitySource
from core.errors import DomainError
from core.solution import StorageChemistry, Waveform
from core.units import VoltAmpere, Volt, Watt, WattHour


class InvalidComponentSpecError(DomainError):
    """Компонент (инвертор или АКБ) нарушает физические инварианты."""


@dataclass(frozen=True, slots=True)
class InverterSpec:
    """Инвертор без АКБ: преобразует DC системы в AC, ёмкости не имеет."""

    system_voltage_v: Volt
    continuous_power_w: Watt
    peak_power_w: Watt
    apparent_power_va: VoltAmpere | None = None
    inverter_efficiency: float = 0.90
    idle_draw_w: Watt = Watt(0.0)
    waveform: Waveform = Waveform.PURE_SINE
    switchover_ms: int | None = None
    dc_output_power_w: Watt = Watt(0.0)
    #: Гибридный инвертор принимает вход с солнечных панелей. Физический
    #: факт о железе, не витринный текст (ADR-038). Панели НЕ обязательны
    #: для работы кита — это поле только про совместимость, не требование.
    accepts_solar_input: bool = False

    def __post_init__(self) -> None:
        if self.system_voltage_v <= 0:
            raise InvalidComponentSpecError("system_voltage_v должен быть > 0")
        if self.continuous_power_w <= 0:
            raise InvalidComponentSpecError("continuous_power_w должен быть > 0")
        if self.peak_power_w < self.continuous_power_w:
            raise InvalidComponentSpecError("peak_power_w меньше continuous_power_w")
        if not 0.0 < self.inverter_efficiency <= 1.0:
            raise InvalidComponentSpecError("inverter_efficiency вне (0, 1]")


@dataclass(frozen=True, slots=True)
class BatterySpec:
    """АКБ без инвертора: хранит энергию, AC сама по себе не отдаёт."""

    system_voltage_v: Volt
    chemistry: StorageChemistry
    capacity_wh: WattHour
    cycle_life: int | None = None
    dc_output_efficiency: float = 0.95
    #: Переопределяет policy.dod_for(chemistry), когда есть даташит на
    #: конкретный товар (см. ADR-025).
    depth_of_discharge_override: float | None = None

    def __post_init__(self) -> None:
        if self.system_voltage_v <= 0:
            raise InvalidComponentSpecError("system_voltage_v должен быть > 0")
        if self.capacity_wh <= 0:
            raise InvalidComponentSpecError("capacity_wh должен быть > 0")
        if not 0.0 < self.dc_output_efficiency <= 1.0:
            raise InvalidComponentSpecError("dc_output_efficiency вне (0, 1]")
        if self.depth_of_discharge_override is not None:
            if not 0.0 < self.depth_of_discharge_override <= 1.0:
                raise InvalidComponentSpecError("depth_of_discharge_override вне (0, 1]")


@dataclass(frozen=True, slots=True)
class CatalogInverter:
    """Инвертор в каталоге: бренд+модель+физика, без цены."""

    component_id: str
    name: str
    brand: str
    model: str
    spec: InverterSpec
    image: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogBattery:
    """АКБ в каталоге: бренд+модель+физика, без цены."""

    component_id: str
    name: str
    brand: str
    model: str
    spec: BatterySpec
    image: str | None = None
    capacity_source: CapacitySource | None = None


@dataclass(frozen=True, slots=True)
class ComponentOffer:
    """Цена и продавец для конкретного компонента (инвертора или АКБ)."""

    offer_id: str
    component_id: str
    price_uah: float
    commission_rate: float
    source: str
    url: str | None = None
    in_stock: bool = True