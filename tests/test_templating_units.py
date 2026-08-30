"""Тесты форматирования единиц. Ошибка в них видна пользователю как ложь."""

from api.templating import format_kwh, format_wh_as_kwh


def test_watt_hours_are_converted_not_just_relabelled() -> None:
    """450 Вт·год — это 0,5 кВт·год, а не 450 кВт·год.

    Регресс на реальный баг: фильтр kwh применялся к total_energy_wh,
    и страница показывала месячное потребление дома вместо полкиловатта.
    """
    assert format_wh_as_kwh(450) == format_kwh(0.45)
    assert "450" not in format_wh_as_kwh(450)


def test_large_values_round_to_whole_kwh() -> None:
    assert format_wh_as_kwh(250_000) == format_kwh(250)