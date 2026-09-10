"""Снимок выдачи по трём целевым профилям до правок matching/.

Точка сравнения для ADR-040. Считает тем же путём, что и прод:
api.app._calculate — общая функция для POST /api/v1/recommendations
и для SSR-страницы (см. её докстринг). Своей цепочки вызовов
не собирает намеренно: пересобранная цепочка перестаёт быть
доказательством того, что мерили прод.

Ничего не меняет, пишет в stdout.
"""

from __future__ import annotations

import json
from typing import Any

from api.app import _calculate
from api.catalog_provider import load_appliances
from api.schemas import ApplianceSelection, RecommendationRequest

GRID_TARIFF_UAH_PER_KWH = 4.32
FUEL_PRICE_UAH_PER_L = 58.0

#: (название, [(code, quantity)], часы окна)
PROFILES: list[tuple[str, list[tuple[str, int]], float]] = [
    ("1. холодильник, 4 год", [("fridge_medium", 1)], 4.0),
    (
        "2. котел + свiтло + iнтернет, 8 год",
        [("gas_boiler", 1), ("led_bulb_9w", 3), ("wifi_router_9v", 1)],
        8.0,
    ),
    (
        "3. роутер + ноутбук DC, 4 год",
        [("wifi_router_9v", 1), ("laptop_usb_c_pd_65w", 1)],
        4.0,
    ),
]

LIMITS: tuple[int, ...] = (5, 20)


def check_codes() -> None:
    """Падает громко, если код прибора отсутствует в справочнике."""
    known = set(load_appliances())
    used = {code for _, items, _ in PROFILES for code, _ in items}
    missing = sorted(used - known)
    if missing:
        raise SystemExit(f"НЕТ В СПРАВОЧНИКЕ: {missing}")
    print(f"коды профилей проверены по справочнику: {len(known)} приборов\n")


def run_profile(title: str, items: list[tuple[str, int]], hours: float, limit: int) -> None:
    """Печатает выдачу одного профиля при заданном limit."""
    request = RecommendationRequest(
        appliances=[
            ApplianceSelection(code=code, quantity=quantity) for code, quantity in items
        ],
        autonomy_hours=hours,
        grid_tariff_uah_per_kwh=GRID_TARIFF_UAH_PER_KWH,
        fuel_price_uah_per_l=FUEL_PRICE_UAH_PER_L,
        limit=limit,
    )
    response = _calculate(request)
    payload: dict[str, Any] = response.model_dump(mode="json")

    print("=" * 70)
    print(f"{title}   limit={limit}")
    print("=" * 70)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print()


def main() -> None:
    print(f"tariff={GRID_TARIFF_UAH_PER_KWH}  fuel={FUEL_PRICE_UAH_PER_L}\n")
    check_codes()
    for limit in LIMITS:
        for title, items, hours in PROFILES:
            run_profile(title, items, hours, limit)


if __name__ == "__main__":
    main()