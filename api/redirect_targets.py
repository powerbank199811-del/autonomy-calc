"""Резолвер цели редиректа: offer_id -> (url, source).

Собирает в один индекс офферы товаров и офферы компонентов. Для /go они
неразличимы: это две ссылки на две страницы двух продавцов, и то, что одна
из них — половина кита, редирект не касается.

Киты в индекс НЕ попадают (ADR-035): у составного kit__inv_X__bat_Y нет
одной целевой страницы, потому что это две покупки.
"""

from dataclasses import dataclass
from functools import lru_cache

from api.catalog_provider import DATA_DIR
from catalog.components_loader import load_components
from catalog.products_loader import load_catalog


@dataclass(frozen=True, slots=True)
class RedirectTarget:
    """Куда вести и от чьего имени считать комиссию."""

    url: str
    source: str


@lru_cache(maxsize=1)
def load_redirect_targets() -> dict[str, RedirectTarget]:
    """Индекс всех офферов, у которых есть URL.

    Оффер без URL в индекс не попадает: редирект в никуда хуже честного
    404, потому что клик будет записан, а пользователь никуда не уйдёт —
    и метрика CTR окажется завышенной.
    """
    targets: dict[str, RedirectTarget] = {}

    _, offers = load_catalog(DATA_DIR / "products.yaml")
    for offer in offers:
        if offer.url:
            targets[offer.offer_id] = RedirectTarget(url=offer.url, source=offer.source)

    _, inverter_offers, _, battery_offers = load_components(DATA_DIR / "components.yaml")
    for component_offer in (*inverter_offers, *battery_offers):
        if component_offer.url:
            targets[component_offer.offer_id] = RedirectTarget(
                url=component_offer.url, source=component_offer.source
            )

    return targets
