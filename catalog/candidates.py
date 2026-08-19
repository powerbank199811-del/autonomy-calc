"""Склейка каталога с движком подбора: (products, offers) -> Candidate.

Это единственное место, где catalog встречается с matching. Направление
зависимости: catalog -> matching (не наоборот) — движок ничего не знает
про существование каталога, каталог знает про контракт движка.
"""

from core.errors import DomainError
from catalog.offers import CatalogOffer
from catalog.products import CatalogProduct
from matching.candidate import Candidate


class UnknownProductError(DomainError):
    """Оффер ссылается на продукт, которого нет в переданном списке."""


def build_candidates(
    products: tuple[CatalogProduct, ...], offers: tuple[CatalogOffer, ...]
) -> tuple[Candidate, ...]:
    """Строит кандидатов для matching.engine из каталога.

    Ссылочная целостность уже проверена загрузчиком (products_loader),
    но эта функция не полагается на это молча — защищается сама, чтобы
    остаться корректной, даже если products/offers собраны вручную в тесте.
    """
    by_id = {p.product_id: p for p in products}
    candidates: list[Candidate] = []
    for offer in offers:
        product = by_id.get(offer.product_id)
        if product is None:
            raise UnknownProductError(
                f"offer '{offer.offer_id}' ссылается на несуществующий "
                f"product_id '{offer.product_id}'"
            )
        candidates.append(
            Candidate(
                offer_id=offer.offer_id,
                solution=product.spec,
                price_uah=offer.price_uah,
                commission_rate=offer.commission_rate,
                expected_lifetime_wh=offer.expected_lifetime_wh,
                in_stock=offer.in_stock,
            )
        )
    return tuple(candidates)
