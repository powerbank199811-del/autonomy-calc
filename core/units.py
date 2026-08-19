"""Канонические единицы измерения домена.

Единственная каноническая единица энергии — ватт-час (Вт·ч).
NewType, а не голый float: mypy --strict поймает попытку сложить Вт с Вт·ч.
"""

from typing import Final, NewType

Watt = NewType("Watt", float)
WattHour = NewType("WattHour", float)
VoltAmpere = NewType("VoltAmpere", float)
Volt = NewType("Volt", float)
Hours = NewType("Hours", float)

#: Номинальное напряжение ячейки Li-ion, к которому производители приводят mAh.
NOMINAL_CELL_VOLTAGE: Final[Volt] = Volt(3.7)


def mah_to_wh(mah: float, voltage: Volt = NOMINAL_CELL_VOLTAGE) -> WattHour:
    """Переводит mAh в Вт·ч. Без напряжения mAh — не единица энергии."""
    if mah < 0:
        raise ValueError("mah не может быть отрицательным")
    return WattHour(mah * voltage / 1000.0)


def wh_to_mah(wh: WattHour, voltage: Volt = NOMINAL_CELL_VOLTAGE) -> float:
    """Обратный перевод. Нужен только для совместимости с карточками товара."""
    if voltage <= 0:
        raise ValueError("voltage должен быть положительным")
    return wh * 1000.0 / voltage


def round_energy(value: float) -> WattHour:
    """Округление энергии до 1 Вт·ч — на выходе ядра, один раз."""
    return WattHour(round(value))


def round_power(value: float) -> Watt:
    """Округление мощности до 1 Вт — на выходе ядра, один раз."""
    return Watt(round(value))
