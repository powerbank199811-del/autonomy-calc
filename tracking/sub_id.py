"""Сборка sub_id для партнёрской ссылки.

Формат: scenario_hash:source:position:click_id

Разделитель — двоеточие, а не вертикальная черта: `|` требует
URL-экранирования и часть CPA-сетей режет его при разборе постбека.
Двоеточие безопасно в query-параметре и читаемо в отчёте сети.

Все компоненты санитизируются: любой символ вне [a-z0-9_-] заменяется на
подчёркивание. Причина не в красоте, а в том, что sub_id возвращается
обратно постбеком, и сеть, которая его исказит, сделает атрибуцию
невосстановимой.
"""

import re

from tracking.click import Click

SEPARATOR = ":"
MAX_LENGTH = 100

_UNSAFE = re.compile(r"[^a-z0-9_-]+")


def sanitize(value: str) -> str:
    """Приводит компонент к безопасному для sub_id виду."""
    return _UNSAFE.sub("_", value.lower()).strip("_") or "na"


def build_sub_id(click: Click) -> str:
    """scenario_hash:source:position:click_id, обрезанный до 100 символов.

    Обрезка с конца: click_id стоит последним и генерируется нами, поэтому
    при переполнении теряется его хвост, а не идентификатор сценария или
    источника. Полный click_id всё равно лежит в нашем журнале — сопоставить
    урезанный префикс с записью можно, потерянный scenario_hash — нельзя.
    """
    parts = [
        sanitize(click.scenario_hash),
        sanitize(click.source),
        str(click.position),
        sanitize(click.click_id),
    ]
    return SEPARATOR.join(parts)[:MAX_LENGTH]
