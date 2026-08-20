"""Сборка совместимых инвертор+АКБ в единый core.SolutionSpec 'на лету'.

Совместимость проверяется по КЛАССУ напряжения (12V/24V/48V), а не по
буквальному совпадению чисел. Так надо: LiFePO4-пакет на 4 ячейки маркетинг
называет "12V", а реальное номинальное напряжение — 12.8V; 16 ячеек —
"48V" при реальных 51.2V. Сравнение "inverter.v == battery.v" отбросило бы
почти все настоящие совместимые пары рынка.
"""

from core.solution import SolutionKind, SolutionSpec
from core.units import Volt
from catalog.components import BatterySpec, InverterSpec

#: Стандартные классы напряжения систем резервного питания.
_VOLTAGE_CLASSES: tuple[Volt, ...] = (Volt(12.0), Volt(24.0), Volt(48.0))
#: Допуск класса: LiFePO4 "12V" реально 12.8V — это 6.7%, берём с запасом.
_CLASS_TOLERANCE = 0.15


def _voltage_class(voltage: Volt) -> Volt | None:
    """Относит напряжение к ближайшему стандартному классу или None."""
    for cls in _VOLTAGE_CLASSES:
        if abs(voltage - cls) / cls <= _CLASS_TOLERANCE:
            return cls
    return None


def is_voltage_compatible(inverter: InverterSpec, battery: BatterySpec) -> bool:
    """Единственный жёсткий фильтр совместимости — класс напряжения системы.

    Более глубокая совместимость (протокол BMS, CAN/RS485 между конкретными
    моделями) — вне калькулятора, это ответственность продавца/монтажника.
    """
    inv_class = _voltage_class(inverter.system_voltage_v)
    bat_class = _voltage_class(battery.system_voltage_v)
    return inv_class is not None and inv_class == bat_class


def assemble_solution(inverter: InverterSpec, battery: BatterySpec) -> SolutionSpec:
    """Синтезирует core.SolutionSpec из совместимых инвертора и АКБ.

    Вызывать только после is_voltage_compatible() — эта функция сама
    совместимость не проверяет, остаётся чистой функцией трансформации.
    """
    return SolutionSpec(
        kind=SolutionKind.INVERTER_BATTERY,
        chemistry=battery.chemistry,
        capacity_wh=battery.capacity_wh,
        continuous_power_w=inverter.continuous_power_w,
        peak_power_w=inverter.peak_power_w,
        apparent_power_va=inverter.apparent_power_va,
        dc_output_power_w=inverter.dc_output_power_w,
        inverter_efficiency=inverter.inverter_efficiency,
        dc_output_efficiency=battery.dc_output_efficiency,
        idle_draw_w=inverter.idle_draw_w,
        waveform=inverter.waveform,
        switchover_ms=inverter.switchover_ms,
        cycle_life=battery.cycle_life,
        depth_of_discharge_override=battery.depth_of_discharge_override,
    )
