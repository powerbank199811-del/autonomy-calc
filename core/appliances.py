"""Тип записи справочника приборов.

Ядро определяет ТИП. Сам справочник (YAML) грузит адаптер
adapters/appliances_yaml/ — зависимость идёт внутрь, к ядру.
"""

from dataclasses import dataclass
from enum import Enum

from core.errors import InvalidApplianceSpecError
from core.units import Watt


class PowerBus(Enum):
    """Шина питания. Определяет, участвует ли инвертор в цепочке потерь."""

    AC_230 = "ac_230"
    DC_USB = "dc_usb"


@dataclass(frozen=True, slots=True)
class ApplianceSpec:
    """Прибор из справочника: физика потребления, без цен и товаров."""

    code: str
    power_w: Watt
    duty_cycle: float = 1.0
    startup_factor: float = 1.0
    power_factor: float = 1.0
    bus: PowerBus = PowerBus.AC_230
    requires_pure_sine: bool = False
    max_switchover_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise InvalidApplianceSpecError("code не может быть пустым")
        if self.power_w <= 0:
            raise InvalidApplianceSpecError(f"{self.code}: power_w должен быть > 0")
        if not 0.0 < self.duty_cycle <= 1.0:
            raise InvalidApplianceSpecError(f"{self.code}: duty_cycle вне (0, 1]")
        if self.startup_factor < 1.0:
            raise InvalidApplianceSpecError(f"{self.code}: startup_factor < 1")
        if not 0.0 < self.power_factor <= 1.0:
            raise InvalidApplianceSpecError(f"{self.code}: power_factor вне (0, 1]")
        if self.max_switchover_ms is not None and self.max_switchover_ms <= 0:
            raise InvalidApplianceSpecError(f"{self.code}: max_switchover_ms <= 0")
