"""Экономика владения: во сколько обходится 1 кВт·ч и когда решение окупается.

Два разных вопроса, два разных числа:

    cost_per_kwh_uah    — LCOE: полная стоимость (капекс + топливо) размазанная
                           на ВЕСЬ паспортный срок службы. Для сравнения решений
                           между собой.
    payback_energy_kwh  — сколько кВт·ч нужно РЕАЛЬНО получить от решения, чтобы
                           экономия на тарифе окупила капекс. Не требует
                           дожития до конца паспортного ресурса.

Окупаемость считается в кВт·ч, а не в месяцах: без предположения о частоте
отключений в месяц время не является осмысленной единицей (см. ADR-010).
"""

from dataclasses import dataclass
from enum import Enum

from core.errors import InvalidOwnershipInputError
from core.policy import DEFAULT_POLICY, CalculationPolicy
from core.units import WattHour


class EconomicsAssumption(Enum):
    """Допущения расчёта экономики. Показываются пользователю."""

    CYCLE_LIFE_DERATED = "cycle_life_derated"
    LIFETIME_FROM_EXPLICIT_ESTIMATE = "lifetime_from_explicit_estimate"
    FUEL_OPEX_INCLUDED = "fuel_opex_included"
    NEVER_PAYS_BACK_AT_TARIFF = "never_pays_back_at_tariff"


@dataclass(frozen=True, slots=True)
class OwnershipInput:
    """Вход для расчёта экономики.

    Тариф — обязательный параметр без дефолта (ADR-009): UI не должен
    подставлять "среднюю по Украине" цифру от имени пользователя.
    """

    price_uah: float
    grid_tariff_uah_per_kwh: float
    usable_energy_per_cycle_wh: WattHour | None = None
    cycle_life: int | None = None
    expected_lifetime_wh: WattHour | None = None
    fuel_price_uah_per_l: float | None = None
    fuel_rate_l_per_kwh: float | None = None

    def __post_init__(self) -> None:
        if self.price_uah <= 0:
            raise InvalidOwnershipInputError("price_uah должен быть > 0")
        if self.grid_tariff_uah_per_kwh <= 0:
            raise InvalidOwnershipInputError("grid_tariff_uah_per_kwh должен быть > 0")
        has_cycle_data = (
            self.usable_energy_per_cycle_wh is not None and self.cycle_life is not None
        )
        if not has_cycle_data and self.expected_lifetime_wh is None:
            raise InvalidOwnershipInputError(
                "нужны либо (usable_energy_per_cycle_wh и cycle_life), "
                "либо expected_lifetime_wh"
            )
        if (self.fuel_price_uah_per_l is None) != (self.fuel_rate_l_per_kwh is None):
            raise InvalidOwnershipInputError(
                "fuel_price_uah_per_l и fuel_rate_l_per_kwh задаются только вместе"
            )


@dataclass(frozen=True, slots=True)
class OwnershipCost:
    """Результат: LCOE и точка окупаемости капекса."""

    lifetime_energy_kwh: float
    fuel_opex_per_kwh_uah: float
    cost_per_kwh_uah: float
    cheaper_than_grid: bool
    payback_energy_kwh: float | None
    assumptions: tuple[EconomicsAssumption, ...]


def calculate_ownership_cost(
    inp: OwnershipInput, policy: CalculationPolicy = DEFAULT_POLICY
) -> OwnershipCost:
    """Считает LCOE (грн/кВт·ч) и окупаемость капекса в кВт·ч."""
    assumptions: set[EconomicsAssumption] = set()

    if inp.usable_energy_per_cycle_wh is not None and inp.cycle_life is not None:
        # Паспортный ресурс циклов режем вдвое — реальная эксплуатация (ADR-011).
        effective_cycles = inp.cycle_life * policy.cycle_life_derating
        lifetime_kwh = (inp.usable_energy_per_cycle_wh / 1000.0) * effective_cycles
        assumptions.add(EconomicsAssumption.CYCLE_LIFE_DERATED)
    else:
        assert inp.expected_lifetime_wh is not None
        lifetime_kwh = inp.expected_lifetime_wh / 1000.0
        assumptions.add(EconomicsAssumption.LIFETIME_FROM_EXPLICIT_ESTIMATE)

    fuel_opex = 0.0
    if inp.fuel_price_uah_per_l is not None and inp.fuel_rate_l_per_kwh is not None:
        fuel_opex = inp.fuel_price_uah_per_l * inp.fuel_rate_l_per_kwh
        assumptions.add(EconomicsAssumption.FUEL_OPEX_INCLUDED)

    capex_per_kwh = inp.price_uah / lifetime_kwh
    cost_per_kwh = capex_per_kwh + fuel_opex

    # Окупаемость — по МАРЖИНАЛЬНОЙ стоимости (топливо), капекс не размазан:
    # это отвечает на вопрос "когда накопленная экономия на тарифе покроет
    # цену покупки", а не "выгодно ли это на всём паспортном ресурсе".
    savings_per_kwh = inp.grid_tariff_uah_per_kwh - fuel_opex
    payback_energy_kwh: float | None
    if savings_per_kwh > 0:
        payback_energy_kwh = round(inp.price_uah / savings_per_kwh, 1)
    else:
        payback_energy_kwh = None
        assumptions.add(EconomicsAssumption.NEVER_PAYS_BACK_AT_TARIFF)

    return OwnershipCost(
        lifetime_energy_kwh=round(lifetime_kwh, 2),
        fuel_opex_per_kwh_uah=round(fuel_opex, 3),
        cost_per_kwh_uah=round(cost_per_kwh, 3),
        cheaper_than_grid=cost_per_kwh < inp.grid_tariff_uah_per_kwh,
        payback_energy_kwh=payback_energy_kwh,
        assumptions=tuple(sorted(assumptions, key=lambda a: a.value)),
    )
