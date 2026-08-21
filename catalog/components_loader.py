"""Загрузка инверторов и АКБ (компонентов для сборки китов) из YAML."""

from pathlib import Path
from typing import Any

import yaml

from catalog.components import (
    BatterySpec,
    CatalogBattery,
    CatalogInverter,
    ComponentOffer,
    InverterSpec,
    InvalidComponentSpecError,
)
from core.solution import StorageChemistry, Waveform
from core.units import VoltAmpere, Volt, Watt, WattHour

_REQUIRED_KEYS = {"inverters", "inverter_offers", "batteries", "battery_offers"}


class ComponentsCatalogError(Exception):
    """Ошибка загрузки каталога компонентов: битый YAML, дубликаты, битые ссылки."""


def load_components(
    path: Path,
) -> tuple[
    tuple[CatalogInverter, ...],
    tuple[ComponentOffer, ...],
    tuple[CatalogBattery, ...],
    tuple[ComponentOffer, ...],
]:
    """Читает YAML и возвращает (inverters, inverter_offers, batteries, battery_offers)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not _REQUIRED_KEYS.issubset(raw):
        raise ComponentsCatalogError(f"{path}: ожидались ключи {sorted(_REQUIRED_KEYS)}")

    inverters = _load_inverters(raw["inverters"], path)
    inverter_offers = _load_offers(
        raw["inverter_offers"], path, {c.component_id for c in inverters}, "inverter"
    )
    batteries = _load_batteries(raw["batteries"], path)
    battery_offers = _load_offers(
        raw["battery_offers"], path, {c.component_id for c in batteries}, "battery"
    )
    return inverters, inverter_offers, batteries, battery_offers


def _load_inverters(raw_items: Any, path: Path) -> tuple[CatalogInverter, ...]:
    if not isinstance(raw_items, list):
        raise ComponentsCatalogError(f"{path}: 'inverters' должен быть списком")
    items: list[CatalogInverter] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items):
        inv = _parse_inverter(item, index, path)
        if inv.component_id in seen:
            raise ComponentsCatalogError(
                f"{path}: повторяющийся component_id '{inv.component_id}'"
            )
        seen.add(inv.component_id)
        items.append(inv)
    return tuple(items)


def _parse_inverter(item: dict[str, Any], index: int, path: Path) -> CatalogInverter:
    try:
        spec = InverterSpec(
            system_voltage_v=Volt(float(item["system_voltage_v"])),
            continuous_power_w=Watt(float(item["continuous_power_w"])),
            peak_power_w=Watt(float(item["peak_power_w"])),
            apparent_power_va=_optional_va(item.get("apparent_power_va")),
            inverter_efficiency=float(item.get("inverter_efficiency", 0.90)),
            idle_draw_w=Watt(float(item.get("idle_draw_w", 0.0))),
            waveform=Waveform(item.get("waveform", "pure_sine")),
            switchover_ms=item.get("switchover_ms"),
            dc_output_power_w=Watt(float(item.get("dc_output_power_w", 0.0))),
        )
        return CatalogInverter(
            component_id=str(item["component_id"]),
            name=str(item["name"]),
            brand=str(item["brand"]),
            model=str(item["model"]),
            spec=spec,
        )
    except KeyError as exc:
        raise ComponentsCatalogError(f"{path}: inverters[{index}] — нет поля {exc}") from exc
    except (ValueError, InvalidComponentSpecError) as exc:
        raise ComponentsCatalogError(f"{path}: inverters[{index}] — {exc}") from exc


def _load_batteries(raw_items: Any, path: Path) -> tuple[CatalogBattery, ...]:
    if not isinstance(raw_items, list):
        raise ComponentsCatalogError(f"{path}: 'batteries' должен быть списком")
    items: list[CatalogBattery] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items):
        bat = _parse_battery(item, index, path)
        if bat.component_id in seen:
            raise ComponentsCatalogError(
                f"{path}: повторяющийся component_id '{bat.component_id}'"
            )
        seen.add(bat.component_id)
        items.append(bat)
    return tuple(items)


def _parse_battery(item: dict[str, Any], index: int, path: Path) -> CatalogBattery:
    try:
        spec = BatterySpec(
            system_voltage_v=Volt(float(item["system_voltage_v"])),
            chemistry=StorageChemistry(item["chemistry"]),
            capacity_wh=WattHour(float(item["capacity_wh"])),
            cycle_life=item.get("cycle_life"),
            dc_output_efficiency=float(item.get("dc_output_efficiency", 0.95)),
            depth_of_discharge_override=(
                float(item["depth_of_discharge_override"])
                if item.get("depth_of_discharge_override") is not None
                else None
            ),
        )
        return CatalogBattery(
            component_id=str(item["component_id"]),
            name=str(item["name"]),
            brand=str(item["brand"]),
            model=str(item["model"]),
            spec=spec,
        )
    except KeyError as exc:
        raise ComponentsCatalogError(f"{path}: batteries[{index}] — нет поля {exc}") from exc
    except (ValueError, InvalidComponentSpecError) as exc:
        raise ComponentsCatalogError(f"{path}: batteries[{index}] — {exc}") from exc


def _load_offers(
    raw_items: Any, path: Path, known_ids: set[str], kind_label: str
) -> tuple[ComponentOffer, ...]:
    if not isinstance(raw_items, list):
        raise ComponentsCatalogError(f"{path}: '{kind_label}_offers' должен быть списком")
    items: list[ComponentOffer] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items):
        try:
            offer = ComponentOffer(
                offer_id=str(item["offer_id"]),
                component_id=str(item["component_id"]),
                price_uah=float(item["price_uah"]),
                commission_rate=float(item["commission_rate"]),
                source=str(item["source"]),
                url=None if item.get("url") is None else str(item["url"]),
                in_stock=bool(item.get("in_stock", True)),
            )
        except KeyError as exc:
            raise ComponentsCatalogError(
                f"{path}: {kind_label}_offers[{index}] — нет поля {exc}"
            ) from exc
        if offer.offer_id in seen:
            raise ComponentsCatalogError(f"{path}: повторяющийся offer_id '{offer.offer_id}'")
        if offer.component_id not in known_ids:
            raise ComponentsCatalogError(
                f"{path}: {kind_label}_offers[{index}] ссылается на "
                f"несуществующий component_id '{offer.component_id}'"
            )
        seen.add(offer.offer_id)
        items.append(offer)
    return tuple(items)


def _optional_va(value: Any) -> VoltAmpere | None:
    return None if value is None else VoltAmpere(float(value))
