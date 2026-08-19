"""Все допущения расчёта — в одном месте.

Правило: если в формуле появляется магическое число, оно переезжает сюда.
Policy передаётся параметром, а не читается из глобали: ядро остаётся чистым,
а тесты могут проверить поведение при других коэффициентах.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CalculationPolicy:
    """Коэффициенты и допущения, применяемые к расчёту потребности."""

    #: Одновременно запускается только один двигатель (см. ADR-002).
    single_simultaneous_startup: bool = True
    #: Коэффициент одновременности нагрузок. 1.0 = все приборы включены разом.
    diversity_factor: float = 1.0
    #: Верхняя граница окна автономности, часов.
    max_window_hours: float = 72.0

    def __post_init__(self) -> None:
        if not 0.0 < self.diversity_factor <= 1.0:
            raise ValueError("diversity_factor должен быть в (0, 1]")
        if self.max_window_hours <= 0:
            raise ValueError("max_window_hours должен быть положительным")


DEFAULT_POLICY = CalculationPolicy()
