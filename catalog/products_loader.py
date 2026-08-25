"""Загрузка каталога products/offers из YAML.

Один YAML, два списка: products и offers. Ссылочная целостность
(offer.product_id существует среди products) проверяется здесь, при
загрузке — не в момент использования где-то в API, где такая ошибка
превратится в невнятный 500-й ответ вместо понятной ошибки при старте.
"""

from pathlib import Path
from typing import Any

import yaml

from catalog.offers import CatalogOffer
from catalog.products import CapacitySource, CatalogProduct, FuelRateSource
from core.errors import InvalidSolutionSpecError
from core.solution import SolutionKind, SolutionSpec, StorageChemistry, Waveform
from core.units import VoltAmpere, Watt, WattHour


class ProductsCatalogError(Exception):
    """Ошибка загрузки каталога: битый YAML, дубликаты, битые ссылки."""


def load_catalog(path: Path) -> tuple[tuple[CatalogProduct, ...], tuple[CatalogOffer, ...]]:
    """Читает YAML и возвращает валидированные (products, offers)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "products" not in raw or "offers" not in raw:
        raise ProductsCatalogError(f"{path}: ожидался словарь с ключами 'products' и 'offers'")

    products = _load_products(raw["products"], path)
    offers = _load_offers(raw["offers"], path, known_product_ids={p.product_id for p in products})
    return products, offers


def _load_products(raw_items: Any, path: Path) -> tuple[CatalogProduct, ...]:
    if not isinstance(raw_items, list):
        raise ProductsCatalogError(f"{path}: 'products' должен быть списком")

    items: list[CatalogProduct] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_items):
        product = _parse_product(item, index=index, path=path)
        if product.product_id in seen_ids:
            raise ProductsCatalogError(
                f"{path}: повторяющийся product_id '{product.product_id}'"
            )
        seen_ids.add(product.product_id)
        items.append(product)
    return tuple(items)


def _parse_product(item: dict[str, Any], *, index: int, path: Path) -> CatalogProduct:
    try:
        product_id = str(item["product_id"])
        spec = SolutionSpec(
            kind=SolutionKind(item["kind"]),
            chemistry=StorageChemistry(item.get("chemistry", "none")),
            capacity_wh=_optional_wh(item.get("capacity_wh")),
            continuous_power_w=Watt(float(item.get("continuous_power_w", 0.0))),
            peak_power_w=Watt(float(item.get("peak_power_w", 0.0))),
            apparent_power_va=_optional_va(item.get("apparent_power_va")),
            dc_output_power_w=Watt(float(item.get("dc_output_power_w", 0.0))),
            inverter_efficiency=float(item.get("inverter_efficiency", 0.90)),
            dc_output_efficiency=float(item.get("dc_output_efficiency", 0.95)),
            idle_draw_w=Watt(float(item.get("idle_draw_w", 0.0))),
            waveform=Waveform(item.get("waveform", "none")),
            switchover_ms=item.get("switchover_ms"),
            fuel_rate_l_per_kwh=item.get("fuel_rate_l_per_kwh"),
            tank_l=item.get("tank_l"),
            cycle_life=item.get("cycle_life"),
            depth_of_discharge_override=_optional_float(item.get("depth_of_discharge_override")),
        )
        capacity_source = (
            CapacitySource(item["capacity_source"])
            if item.get("capacity_source")
            else None
        )
        fuel_rate_source = (
            FuelRateSource(item["fuel_rate_source"])
            if item.get("fuel_rate_source")
            else None
        )
        return CatalogProduct(
            product_id=product_id,
            name=str(item["name"]),
            brand=str(item["brand"]),
            model=str(item["model"]),
            category=str(item["category"]),
            spec=spec,
            image=item.get("image"),
            fuel_rate_source=fuel_rate_source,
            capacity_source=capacity_source,
        )
    except KeyError as exc:
        raise ProductsCatalogError(
            f"{path}: products[{index}] — отсутствует обязательное поле {exc}"
        ) from exc
    except (ValueError, InvalidSolutionSpecError) as exc:
        raise ProductsCatalogError(
            f"{path}: products[{index}] ({item.get('product_id')}) — {exc}"
        ) from exc


def _load_offers(
    raw_items: Any, path: Path, *, known_product_ids: set[str]
) -> tuple[CatalogOffer, ...]:
    if not isinstance(raw_items, list):
        raise ProductsCatalogError(f"{path}: 'offers' должен быть списком")

    items: list[CatalogOffer] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_items):
        offer = _parse_offer(item, index=index, path=path)
        if offer.offer_id in seen_ids:
            raise ProductsCatalogError(f"{path}: повторяющийся offer_id '{offer.offer_id}'")
        if offer.product_id not in known_product_ids:
            raise ProductsCatalogError(
                f"{path}: offers[{index}] ({offer.offer_id}) ссылается на "
                f"несуществующий product_id '{offer.product_id}'"
            )
        seen_ids.add(offer.offer_id)
        items.append(offer)
    return tuple(items)


def _parse_offer(item: dict[str, Any], *, index: int, path: Path) -> CatalogOffer:
    try:
        return CatalogOffer(
            offer_id=str(item["offer_id"]),
            product_id=str(item["product_id"]),
            price_uah=float(item["price_uah"]),
            commission_rate=float(item["commission_rate"]),
            source=str(item["source"]),
            url=item.get("url"),
            in_stock=bool(item.get("in_stock", True)),
            expected_lifetime_wh=_optional_wh(item.get("expected_lifetime_wh")),
        )
    except KeyError as exc:
        raise ProductsCatalogError(
            f"{path}: offers[{index}] — отсутствует обязательное поле {exc}"
        ) from exc
    except ValueError as exc:
        raise ProductsCatalogError(
            f"{path}: offers[{index}] ({item.get('offer_id')}) — {exc}"
        ) from exc


def _optional_wh(value: Any) -> WattHour | None:
    return None if value is None else WattHour(float(value))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_va(value: Any) -> VoltAmpere | None:
    return None if value is None else VoltAmpere(float(value))
