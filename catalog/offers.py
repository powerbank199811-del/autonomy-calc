"""Оффер каталога: цена и продавец для конкретного продукта."""

from dataclasses import dataclass

from core.units import WattHour


@dataclass(frozen=True, slots=True)
class CatalogOffer:
    """Предложение купить product_id у конкретного продавца за price_uah."""

    offer_id: str
    product_id: str
    price_uah: float
    commission_rate: float
    source: str
    url: str | None = None
    in_stock: bool = True
    #: Только для генераторов без cycle_life (см. core.economics).
    expected_lifetime_wh: WattHour | None = None
