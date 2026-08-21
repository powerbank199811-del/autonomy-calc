"""Кандидат для движка подбора: решение + цена + комиссия."""

from dataclasses import dataclass

from core.errors import DomainError
from core.solution import SolutionSpec
from core.units import WattHour


class InvalidCandidateError(DomainError):
    """Кандидат нарушает инварианты входа движка подбора."""


@dataclass(frozen=True, slots=True)
class Candidate:
    """Одно предложение: конкретный товар у конкретного продавца.

    component_offer_ids — None для простого товара (одна кнопка перехода,
    её цель — сам offer_id). Для составного продукта (кит) — кортеж offer_id
    его частей, каждая ведёт к своему продавцу своим /go (ADR-035, ADR-037).
    matching и api не парсят offer_id, чтобы получить эти части: строка
    "kit__X__Y" — деталь catalog, а не контракт, который можно разбирать
    снаружи слоя, который её собрал.
    """

    offer_id: str
    solution: SolutionSpec
    price_uah: float
    commission_rate: float
    expected_lifetime_wh: WattHour | None = None
    in_stock: bool = True
    component_offer_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.offer_id:
            raise InvalidCandidateError("offer_id не может быть пустым")
        if self.price_uah <= 0:
            raise InvalidCandidateError("price_uah должен быть > 0")
        if not 0.0 <= self.commission_rate <= 1.0:
            raise InvalidCandidateError("commission_rate должен быть в [0, 1]")
        if self.component_offer_ids is not None:
            if len(self.component_offer_ids) < 2:
                raise InvalidCandidateError(
                    "component_offer_ids должен содержать хотя бы 2 части "
                    "или быть None для простого товара"
                )
            if any(not part for part in self.component_offer_ids):
                raise InvalidCandidateError("component_offer_ids не может содержать пустую строку")
