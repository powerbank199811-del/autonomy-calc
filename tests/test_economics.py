"""Экономика владения: золотые сценарии и инварианты."""

import pytest

from core.economics import (
    EconomicsAssumption,
    OwnershipInput,
    calculate_ownership_cost,
)
from core.errors import InvalidOwnershipInputError
from core.units import WattHour


def test_station_lcoe_and_payback() -> None:
    """Станция: 15000 грн, 750 Вт·ч полезных за цикл, ресурс 2000 циклов.

    Эффективный ресурс: 2000 * 0.5 = 1000 циклов.
    Срок службы: 0.75 * 1000 = 750 кВт·ч.
    LCOE: 15000 / 750 = 20.0 грн/кВт·ч.
    Окупаемость по тарифу 5.0: 15000 / 5.0 = 3000.0 кВт·ч.
    """
    inp = OwnershipInput(
        price_uah=15000.0,
        grid_tariff_uah_per_kwh=5.0,
        usable_energy_per_cycle_wh=WattHour(750),
        cycle_life=2000,
    )
    cost = calculate_ownership_cost(inp)
    assert cost.lifetime_energy_kwh == 750.0
    assert cost.cost_per_kwh_uah == 20.0
    assert cost.cheaper_than_grid is False
    assert cost.payback_energy_kwh == 3000.0
    assert EconomicsAssumption.CYCLE_LIFE_DERATED in cost.assumptions


def test_generator_never_pays_back_on_cheap_grid() -> None:
    """Генератор: топливо 55 грн/л, расход 0.4 л/кВт·ч → 22 грн/кВт·ч опекс.

    При тарифе сети 4.32 грн/кВт·ч генератор дороже сети даже без капекса —
    окупаемости при таком тарифе не существует.
    """
    inp = OwnershipInput(
        price_uah=20000.0,
        grid_tariff_uah_per_kwh=4.32,
        expected_lifetime_wh=WattHour(5_000_000),
        fuel_price_uah_per_l=55.0,
        fuel_rate_l_per_kwh=0.4,
    )
    cost = calculate_ownership_cost(inp)
    assert cost.fuel_opex_per_kwh_uah == 22.0
    assert cost.payback_energy_kwh is None
    assert cost.cheaper_than_grid is False
    assert EconomicsAssumption.NEVER_PAYS_BACK_AT_TARIFF in cost.assumptions
    assert EconomicsAssumption.FUEL_OPEX_INCLUDED in cost.assumptions


def test_generator_pays_back_when_fuel_cheaper_than_grid() -> None:
    """Если топливный опекс дешевле тарифа — окупаемость существует и конечна."""
    inp = OwnershipInput(
        price_uah=10000.0,
        grid_tariff_uah_per_kwh=10.0,
        expected_lifetime_wh=WattHour(5_000_000),
        fuel_price_uah_per_l=10.0,
        fuel_rate_l_per_kwh=0.4,
    )
    cost = calculate_ownership_cost(inp)
    assert cost.fuel_opex_per_kwh_uah == 4.0
    # savings_per_kwh = 10.0 - 4.0 = 6.0; payback = 10000 / 6.0
    assert cost.payback_energy_kwh == pytest.approx(1666.7, abs=0.1)


def test_missing_lifetime_data_raises() -> None:
    """Без cycle_life и без expected_lifetime_wh — считать нечего."""
    with pytest.raises(InvalidOwnershipInputError):
        OwnershipInput(price_uah=1000.0, grid_tariff_uah_per_kwh=5.0)


def test_zero_tariff_raises() -> None:
    """Тариф обязателен и должен быть положительным — не дефолт, а ошибка."""
    with pytest.raises(InvalidOwnershipInputError):
        OwnershipInput(
            price_uah=1000.0,
            grid_tariff_uah_per_kwh=0.0,
            expected_lifetime_wh=WattHour(1000),
        )


def test_partial_fuel_params_raises() -> None:
    """Цена топлива и расход задаются только вместе."""
    with pytest.raises(InvalidOwnershipInputError):
        OwnershipInput(
            price_uah=1000.0,
            grid_tariff_uah_per_kwh=5.0,
            expected_lifetime_wh=WattHour(1000),
            fuel_price_uah_per_l=50.0,
        )


def test_cost_per_kwh_never_negative() -> None:
    """Инвариант: LCOE не может быть отрицательным."""
    inp = OwnershipInput(
        price_uah=5000.0,
        grid_tariff_uah_per_kwh=5.0,
        usable_energy_per_cycle_wh=WattHour(500),
        cycle_life=1000,
    )
    assert calculate_ownership_cost(inp).cost_per_kwh_uah > 0


def test_payback_none_means_not_a_bug() -> None:
    """None у payback — валидный ответ 'не окупается', не ошибка расчёта."""
    inp = OwnershipInput(
        price_uah=100000.0,
        grid_tariff_uah_per_kwh=1.0,
        expected_lifetime_wh=WattHour(1_000_000),
        fuel_price_uah_per_l=100.0,
        fuel_rate_l_per_kwh=0.5,
    )
    cost = calculate_ownership_cost(inp)
    assert cost.payback_energy_kwh is None
    assert cost.cost_per_kwh_uah > 0
