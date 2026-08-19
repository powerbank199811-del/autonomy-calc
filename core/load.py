"""Входной профиль нагрузки и цель автономности."""

from dataclasses import dataclass

from core.appliances import ApplianceSpec
from core.errors import (
    EmptyLoadProfileError,
    InvalidAutonomyTargetError,
    InvalidLoadItemError,
)
from core.policy import DEFAULT_POLICY
from core.units import Hours, Watt


@dataclass(frozen=True, slots=True)
class ApplianceOverride:
    """Пользователь уточнил параметры своей модели прибора."""

    power_w: Watt | None = None
    duty_cycle: float | None = None


@dataclass(frozen=True, slots=True)
class LoadItem:
    """Позиция нагрузки: прибор, количество и часы работы ВНУТРИ окна."""

    appliance: ApplianceSpec
    quantity: int = 1
    hours: Hours | None = None
    override: ApplianceOverride | None = None

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise InvalidLoadItemError(f"{self.appliance.code}: quantity < 1")
        if self.hours is not None and self.hours < 0:
            raise InvalidLoadItemError(f"{self.appliance.code}: hours < 0")

    @property
    def effective_power_w(self) -> Watt:
        """Мощность одной единицы с учётом переопределения пользователя."""
        if self.override is not None and self.override.power_w is not None:
            return self.override.power_w
        return self.appliance.power_w

    @property
    def effective_duty_cycle(self) -> float:
        """Доля времени под нагрузкой с учётом переопределения."""
        if self.override is not None and self.override.duty_cycle is not None:
            return self.override.duty_cycle
        return self.appliance.duty_cycle


@dataclass(frozen=True, slots=True)
class AutonomyTarget:
    """Цель: одно окно отключения заданной длительности.

    Фаза 0 считает ОДНО худшее окно. Пресеты «1..10 часов» — валидация
    на границе API, ядро принимает любое положительное число часов.
    """

    window_hours: Hours
    recharge_available: bool = False

    def __post_init__(self) -> None:
        if self.window_hours <= 0:
            raise InvalidAutonomyTargetError("window_hours должен быть > 0")
        if self.window_hours > DEFAULT_POLICY.max_window_hours:
            raise InvalidAutonomyTargetError("window_hours превышает 72 часа")


@dataclass(frozen=True, slots=True)
class LoadProfile:
    """Набор позиций нагрузки. Пустой профиль — ошибка, а не нулевой ответ."""

    items: tuple[LoadItem, ...]

    def __post_init__(self) -> None:
        if not self.items:
            raise EmptyLoadProfileError("профиль нагрузки пуст")
