"""Разбор параметров GET-формы расчёта.

Формат ссылки зафиксирован и не пересматривается:

    /?p=fridge_medium,led_bulb_9w:3&h=4&t=4.32&f=58

Разделитель количества — двоеточие: оно легально в query по RFC 3986
и не является символом разметки в мессенджерах, в отличие от звёздочки.
Ссылки уходят в переписку навсегда, менять формат потом нельзя.

Модуль НЕ поднимает исключений ни на каком входе. Любой 4xx на пересланной
ссылке — потерянный человек, а битые ссылки при пересылке неизбежны.
Домен по-прежнему защищён валидацией на /api/v1/, где клиент программный.
"""

from dataclasses import dataclass
from typing import Iterable, Sequence

#: Тариф населения, однозонный счётчик. Дефолт живёт в api/, не в ядре:
#: ADR-009 запрещает дефолт в core, и он не нарушен — ядро по-прежнему
#: получает явное число, просто подставленное внешним слоем.
DEFAULT_TARIFF_UAH_PER_KWH = 4.32

#: Цены топлива по умолчанию нет намеренно: она региональная и меняется
#: быстрее, чем тариф. Без неё генератор показывается без блока экономики.
DEFAULT_HOURS = 4.0

MIN_HOURS = 1.0
MAX_HOURS = 72.0  # верхняя граница взята из RecommendationRequest.autonomy_hours
MIN_QUANTITY = 1
MAX_QUANTITY = 99


@dataclass(frozen=True, slots=True)
class SelectedAppliance:
    """Одна позиция профиля: код прибора и количество."""

    code: str
    quantity: int


@dataclass(frozen=True, slots=True)
class CalcQuery:
    """Намерение пользователя, восстановленное из строки запроса.

    items всегда отсортирован по code: ?p=a,b и ?p=b,a обязаны давать
    побайтово одинаковый HTML, иначе одна и та же ссылка в разном порядке
    выглядит как разные страницы.
    """

    items: tuple[SelectedAppliance, ...]
    hours: float
    tariff_uah_per_kwh: float
    fuel_price_uah_per_l: float | None
    unknown_codes: tuple[str, ...]
    tariff_is_default: bool

    @property
    def is_empty(self) -> bool:
        """Пустой профиль — не ошибка. Это первый визит, показываем форму."""
        return not self.items


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _parse_positive_float(raw: str | None) -> float | None:
    """Число больше нуля или None. Мусор молча становится None."""
    if raw is None:
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


def _parse_quantity(raw: str) -> int | None:
    """Количество из хвоста после двоеточия. None означает «позицию выбросить»."""
    try:
        value = int(raw)
    except ValueError:
        return MIN_QUANTITY
    if value < MIN_QUANTITY:
        return None
    return min(value, MAX_QUANTITY)


def _split_codes(values: Sequence[str]) -> list[str]:
    """Склеивает repeated-параметры и запятые в один плоский список.

    Форма с чекбоксами отправляет ?p=a&p=b, пересланная ссылка — ?p=a,b.
    Оба варианта означают одно и то же и обязаны разбираться одинаково.
    """
    tokens: list[str] = []
    for value in values:
        tokens.extend(part.strip() for part in value.split(","))
    return [token for token in tokens if token]


def parse_calc_query(
    p: Sequence[str] | None,
    h: str | None,
    t: str | None,
    f: str | None,
    known_codes: Iterable[str],
) -> CalcQuery:
    """Строка запроса -> намерение. Не бросает исключений, см. докстринг модуля."""
    known = frozenset(known_codes)
    quantities: dict[str, int] = {}
    unknown: list[str] = []

    for token in _split_codes(p or ()):
        code, _, raw_quantity = token.partition(":")
        code = code.strip()
        if code not in known:
            if code not in unknown:
                unknown.append(code)
            continue
        quantity = _parse_quantity(raw_quantity) if raw_quantity else MIN_QUANTITY
        if quantity is None:
            continue
        # Дубль кода складывается, а не порождает вторую позицию:
        # ?p=led_bulb_9w,led_bulb_9w и ?p=led_bulb_9w:2 — одно и то же.
        quantities[code] = min(quantities.get(code, 0) + quantity, MAX_QUANTITY)

    items = tuple(
        SelectedAppliance(code=code, quantity=quantities[code])
        for code in sorted(quantities)
    )

    hours_value = _parse_positive_float(h)
    hours = DEFAULT_HOURS if hours_value is None else _clamp(hours_value, MIN_HOURS, MAX_HOURS)

    tariff_value = _parse_positive_float(t)
    return CalcQuery(
        items=items,
        hours=hours,
        tariff_uah_per_kwh=(
            DEFAULT_TARIFF_UAH_PER_KWH if tariff_value is None else tariff_value
        ),
        fuel_price_uah_per_l=_parse_positive_float(f),
        unknown_codes=tuple(unknown),
        tariff_is_default=tariff_value is None,
    )


def _format_number(value: float) -> str:
    """Целое пишется без хвоста: h=4, а не h=4.0."""
    return str(int(value)) if value == int(value) else f"{value:g}"


def to_query_string(query: CalcQuery) -> str:
    """Каноническая сериализация. Единственный источник ссылок на расчёт.

    Обратная операция к parse_calc_query для валидного входа. Используется
    и для редиректа после сабмита формы, и для пресетов, и для ссылки
    «змінити тариф».
    """
    if not query.items:
        return "/"
    codes = ",".join(
        item.code if item.quantity == MIN_QUANTITY else f"{item.code}:{item.quantity}"
        for item in query.items
    )
    parts = [f"p={codes}", f"h={_format_number(query.hours)}"]
    if not query.tariff_is_default:
        parts.append(f"t={_format_number(query.tariff_uah_per_kwh)}")
    if query.fuel_price_uah_per_l is not None:
        parts.append(f"f={_format_number(query.fuel_price_uah_per_l)}")
    return "/?" + "&".join(parts)