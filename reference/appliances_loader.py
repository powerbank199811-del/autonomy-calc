"""Загрузка справочника приборов из YAML в core.ApplianceSpec.

Это не внешний источник (не Rozetka, не AliExpress) — собственный
курируемый справочник. Но направление зависимости то же: этот модуль
импортирует core, core о нём не знает.
"""

from pathlib import Path
from typing import Any

import yaml

from core.appliances import ApplianceSpec, PowerBus
from core.errors import InvalidApplianceSpecError
from core.units import Watt
from reference.appliances import CatalogAppliance


class AppliancesCatalogError(Exception):
    """Ошибка загрузки справочника: битый YAML, дубликат кода, плохие данные."""


def load_appliances_catalog(path: Path) -> tuple[CatalogAppliance, ...]:
    """Читает YAML и возвращает валидированный справочник приборов."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise AppliancesCatalogError(f"{path}: ожидался список приборов")

    entries: list[CatalogAppliance] = []
    seen_codes: set[str] = set()
    for index, item in enumerate(raw):
        entry = _parse_entry(item, index=index, path=path)
        if entry.code in seen_codes:
            raise AppliancesCatalogError(f"{path}: повторяющийся code '{entry.code}'")
        seen_codes.add(entry.code)
        entries.append(entry)
    return tuple(entries)


def _parse_entry(item: dict[str, Any], *, index: int, path: Path) -> CatalogAppliance:
    try:
        code = str(item["code"])
        name_uk = str(item["name_uk"])
        category = str(item["category"])
        bus = PowerBus(item.get("bus", "ac_230"))
        spec = ApplianceSpec(
            code=code,
            power_w=Watt(float(item["power_w"])),
            duty_cycle=float(item.get("duty_cycle", 1.0)),
            startup_factor=float(item.get("startup_factor", 1.0)),
            power_factor=float(item.get("power_factor", 1.0)),
            bus=bus,
            requires_pure_sine=bool(item.get("requires_pure_sine", False)),
            max_switchover_ms=item.get("max_switchover_ms"),
        )
    except KeyError as exc:
        raise AppliancesCatalogError(
            f"{path}: запись #{index} — отсутствует обязательное поле {exc}"
        ) from exc
    except (ValueError, InvalidApplianceSpecError) as exc:
        raise AppliancesCatalogError(
            f"{path}: запись #{index} ({item.get('code')}) — {exc}"
        ) from exc

    return CatalogAppliance(code=code, name_uk=name_uk, category=category, spec=spec)
