"""Кандидат для движка подбора: решение + цена + комиссия."""

from dataclasses import dataclass

from core.errors import DomainError
from core.solution import SolutionSpec
from core.units import WattHour


class InvalidCandidateError(DomainError):
    """Кандидат нарушает инварианты входа движка подбора."""


@dataclass(frozen=True, slots=True)
class Candidate:
    """Одно предложение: конкретный товар у конкретного продавца."""

    offer_id: str
    solution: SolutionSpec
    price_uah: float
    commission_rate: float
    expected_lifetime_wh: WattHour | None = None
    in_stock: bool = True

    def __post_init__(self) -> None:
        if not self.offer_id:
            raise InvalidCandidateError("offer_id не может быть пустым")
        if self.price_uah <= 0:
            raise InvalidCandidateError("price_uah должен быть > 0")
        if not 0.0 <= self.commission_rate <= 1.0:
            raise InvalidCandidateError("commission_rate должен быть в [0, 1]")
