"""Результат движка подбора: одна карточка рекомендации."""

from dataclasses import dataclass

from core.economics import OwnershipCost
from core.fit import SolutionFit


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Карточка рекомендации для клиента. Без commission_rate (ADR-017)."""

    offer_id: str
    fit: SolutionFit
    ownership: OwnershipCost | None
    price_uah: float
    rank_position: int
