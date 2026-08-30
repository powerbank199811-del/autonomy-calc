"""Тесты разбора ссылки. Формат зафиксирован навсегда — он и проверяется.

Парсер — единственное место, где строка запроса превращается в намерение.
Ссылки уходят в мессенджеры и живут дольше кода, поэтому каждое правило
формата закрыто тестом: сломать его молча нельзя.
"""

from typing import Sequence

from api.query_params import (
    CalcQuery,
    DEFAULT_HOURS,
    DEFAULT_TARIFF_UAH_PER_KWH,
    parse_calc_query,
    to_query_string,
)

KNOWN = frozenset({"fridge_medium", "wifi_router_9v", "led_bulb_9w"})


def _parse(
    p: Sequence[str] | None,
    h: str | None = None,
    t: str | None = None,
    f: str | None = None,
) -> CalcQuery:
    return parse_calc_query(p, h, t, f, KNOWN)


def test_order_is_normalized() -> None:
    """?p=a,b и ?p=b,a — одна и та же страница."""
    first = _parse(["fridge_medium,wifi_router_9v"])
    second = _parse(["wifi_router_9v,fridge_medium"])
    assert first == second


def test_repeated_and_comma_forms_are_equivalent() -> None:
    """Сабмит формы (?p=a&p=b) и пересланная ссылка (?p=a,b) — одно и то же."""
    assert _parse(["fridge_medium", "wifi_router_9v"]) == _parse(
        ["fridge_medium,wifi_router_9v"]
    )


def test_quantity_parsed_and_duplicates_summed() -> None:
    assert _parse(["led_bulb_9w:3"]).items[0].quantity == 3
    assert _parse(["led_bulb_9w,led_bulb_9w"]).items[0].quantity == 2


def test_zero_quantity_drops_position() -> None:
    assert _parse(["led_bulb_9w:0"]).items == ()


def test_unknown_code_does_not_break_calculation() -> None:
    """Опечатка в пересланной ссылке не должна ронять расчёт целиком."""
    query = _parse(["fridge_medium,ghost_device"])
    assert [item.code for item in query.items] == ["fridge_medium"]
    assert query.unknown_codes == ("ghost_device",)


def test_broken_hours_fall_back_and_clamp() -> None:
    assert _parse(["fridge_medium"], h="abc").hours == DEFAULT_HOURS
    assert _parse(["fridge_medium"], h="0").hours == DEFAULT_HOURS
    assert _parse(["fridge_medium"], h="999").hours == 72.0


def test_tariff_default_is_marked() -> None:
    """Дефолтный тариф не попадает в ссылку — отсюда флаг."""
    default = _parse(["fridge_medium"])
    assert default.tariff_uah_per_kwh == DEFAULT_TARIFF_UAH_PER_KWH
    assert default.tariff_is_default is True
    assert _parse(["fridge_medium"], t="6.1").tariff_is_default is False


def test_no_fuel_price_by_default() -> None:
    """Цена топлива региональная, дефолта нет намеренно."""
    assert _parse(["fridge_medium"]).fuel_price_uah_per_l is None


def test_roundtrip_is_canonical_and_stable() -> None:
    """Сериализованная ссылка при повторном разборе даёт то же намерение."""
    query = _parse(["led_bulb_9w:3,fridge_medium"], h="8")
    url = to_query_string(query)
    assert url == "/?p=fridge_medium,led_bulb_9w:3&h=8"
    assert _parse([url.split("p=")[1].split("&")[0]], h="8") == query


def test_empty_query_is_not_an_error() -> None:
    """Пустой профиль — первый визит, не ошибка."""
    assert _parse(None).is_empty is True