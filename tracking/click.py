"""Событие клика по партнёрской ссылке.

Отдельный слой, не часть core: расчёт автономности ничего не знает про
клики, а клики ничего не знают про ватт-часы. Единственное, что их
связывает — offer_id, и это строка.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


class InvalidClickError(ValueError):
    """Клик с пустым offer_id или отрицательной позицией."""


def _now() -> datetime:
    return datetime.now(UTC)


def _new_click_id() -> str:
    return uuid4().hex


@dataclass(frozen=True, slots=True)
class Click:
    """Один переход по /go/{offer_id}.

    click_id генерируется здесь, а не в БД: он уходит в sub_id партнёрской
    ссылки ДО того, как строка попадёт в хранилище. Ждать автоинкремента от
    базы значило бы сделать формирование ссылки зависимым от успеха записи.
    """

    offer_id: str
    source: str
    scenario_hash: str
    position: int
    click_id: str = field(default_factory=_new_click_id)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.offer_id:
            raise InvalidClickError("offer_id не может быть пустым")
        if self.position < 0:
            raise InvalidClickError("position не может быть отрицательной")
