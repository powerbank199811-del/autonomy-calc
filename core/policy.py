"""Все допущения расчёта — в одном месте.

Правило: если в формуле появляется магическое число, оно переезжает сюда.
Policy передаётся параметром, а не читается из глобали: ядро остаётся чистым,
а тесты могут проверить поведение при других коэффициентах.
"""

from dataclasses import dataclass, field

from core.solution import StorageChemistry


@dataclass(frozen=True)
class CalculationPolicy:
    """Коэффициенты и допущения, применяемые к расчёту потребности."""

    single_simultaneous_startup: bool = True
    diversity_factor: float = 1.0
    max_window_hours: float = 72.0
    depth_of_discharge: dict[StorageChemistry, float] = field(
        default_factory=lambda: {
            StorageChemistry.LIFEPO4: 0.90,
            StorageChemistry.LI_ION: 0.85,
            StorageChemistry.AGM: 0.50,
            StorageChemistry.NONE: 1.00,
        }
    )
    declared_capacity_derating: float = 0.85
    #: Реальный ресурс циклов = паспортный * этот коэффициент (см. ADR-011).
    cycle_life_derating: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 < self.diversity_factor <= 1.0:
            raise ValueError("diversity_factor должен быть в (0, 1]")
        if self.max_window_hours <= 0:
            raise ValueError("max_window_hours должен быть положительным")
        if not 0.0 < self.declared_capacity_derating <= 1.0:
            raise ValueError("declared_capacity_derating вне (0, 1]")
        if not 0.0 < self.cycle_life_derating <= 1.0:
            raise ValueError("cycle_life_derating вне (0, 1]")
        if not 0.0 < self.cycle_life_derating <= 1.0:
            raise ValueError("cycle_life_derating вне (0, 1]")
        for chemistry, dod in self.depth_of_discharge.items():
            if not 0.0 < dod <= 1.0:
                raise ValueError(f"глубина разряда {chemistry.value} вне (0, 1]")

    def dod_for(self, chemistry: StorageChemistry) -> float:
        """Глубина разряда для химии. Отсутствие записи — ошибка конфигурации."""
        try:
            return self.depth_of_discharge[chemistry]
        except KeyError as exc:
            raise ValueError(f"нет глубины разряда для {chemistry}") from exc


DEFAULT_POLICY = CalculationPolicy()
