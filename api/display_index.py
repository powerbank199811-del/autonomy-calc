"""Display-склейка: offer_id -> данные для карточки (ADR-038).

Здесь и только здесь каталожные поля (имя, бренд, картинка, продавец)
встречаются с ответом API. matching/ про них не знает и знать не должен:
движок ранжирует по цене и физике, бренд на ранг не влияет (ADR-021).

Индекс строится по ОТДЕЛЬНЫМ офферам обоих источников. Составной
kit__{inv}__{bat} собственной записи не имеет: у кита нет одной страницы
продавца (ADR-035), карточка кита собирается из двух записей индекса
по component_offer_ids.
"""

from dataclasses import dataclass

from catalog.components import CatalogBattery, CatalogInverter, ComponentOffer
from catalog.offers import CatalogOffer
from catalog.products import CapacitySource, CatalogProduct
from catalog.sources_loader import seller_label_for
from core.errors import DomainError


class UnknownOfferError(DomainError):
    """Запрошен offer_id, которого нет в display-индексе."""


@dataclass(frozen=True, slots=True)
class DisplayEntry:
    """Всё, что карточке нужно про ОДНУ покупку.

    image_url = None допустим и ошибкой не является (ADR-038): шаблон
    рисует плейсхолдер. Отсутствие seller_label, напротив, невозможно —
    оно падает раньше, на загрузке sources.yaml.
    """

    offer_id: str
    name: str
    brand: str
    image_url: str | None
    seller_label: str
    price_uah: float
    capacity_source: CapacitySource | None = None
    accepts_solar_input: bool = False


class DisplayIndex:
    """Плоский индекс offer_id -> DisplayEntry."""

    def __init__(self, entries: dict[str, DisplayEntry]) -> None:
        self._entries = entries

    def get(self, offer_id: str) -> DisplayEntry:
        """Запись по offer_id. Неизвестный id — ошибка, не пустая карточка."""
        entry = self._entries.get(offer_id)
        if entry is None:
            raise UnknownOfferError(
                f"offer_id '{offer_id}' отсутствует в display-индексе"
            )
        return entry

    def __len__(self) -> int:
        return len(self._entries)


def build_display_index(
    products: tuple[CatalogProduct, ...],
    offers: tuple[CatalogOffer, ...],
    inverters: tuple[CatalogInverter, ...],
    inverter_offers: tuple[ComponentOffer, ...],
    batteries: tuple[CatalogBattery, ...],
    battery_offers: tuple[ComponentOffer, ...],
    sources: dict[str, str],
) -> DisplayIndex:
    """Склеивает оба источника каталога в один индекс по offer_id."""
    entries: dict[str, DisplayEntry] = {}

    products_by_id = {p.product_id: p for p in products}
    for offer in offers:
        product = products_by_id.get(offer.product_id)
        if product is None:
            continue  # ссылочную целостность уже проверил products_loader
        entries[offer.offer_id] = DisplayEntry(
            offer_id=offer.offer_id,
            name=product.name,
            brand=product.brand,
            image_url=product.image,
            seller_label=seller_label_for(offer.source, sources),
            price_uah=offer.price_uah,
            capacity_source=product.capacity_source,
        )

    inverters_by_id = {c.component_id: c for c in inverters}
    for inv_offer in inverter_offers:
        inverter = inverters_by_id.get(inv_offer.component_id)
        if inverter is None:
            continue
        entries[inv_offer.offer_id] = DisplayEntry(
            offer_id=inv_offer.offer_id,
            name=inverter.name,
            brand=inverter.brand,
            image_url=inverter.image,
            seller_label=seller_label_for(inv_offer.source, sources),
            price_uah=inv_offer.price_uah,
            accepts_solar_input=inverter.spec.accepts_solar_input,
        )

    batteries_by_id = {c.component_id: c for c in batteries}
    for bat_offer in battery_offers:
        battery = batteries_by_id.get(bat_offer.component_id)
        if battery is None:
            continue
        entries[bat_offer.offer_id] = DisplayEntry(
            offer_id=bat_offer.offer_id,
            name=battery.name,
            brand=battery.brand,
            image_url=battery.image,
            seller_label=seller_label_for(bat_offer.source, sources),
            price_uah=bat_offer.price_uah,
            capacity_source=battery.capacity_source,
        )

    return DisplayIndex(entries)