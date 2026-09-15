"""Результат движка подбора: одна карточка рекомендации."""

from dataclasses import dataclass

from core.economics import OwnershipCost
from core.fit import SolutionFit
from core.solution import SolutionKind


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Карточка рекомендации для клиента. Без commission_rate (ADR-017).

    kind — доменный факт, а не display-данные: api/ группирует выдачу
    по типу решения (ADR-039), не парся offer_id (запрещено ADR-037)
    и не обращаясь в catalog/.
    """

    offer_id: str
    fit: SolutionFit
    ownership: OwnershipCost | None
    price_uah: float
    rank_position: int
    kind: SolutionKind
    component_offer_ids: tuple[str, ...] | None = None