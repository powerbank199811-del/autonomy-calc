#!/usr/bin/env python3
"""Превью карточек в браузере: реальный каталог -> один HTML-файл.

Инструментальный слой, вне архитектуры (тот же статус, что у status.py).
Нужен, чтобы проверить вёрстку на 380px до того, как появится страница на
корне: роут GET / — это S5, и заводить его в S4 значит начать чужую сессию.

Ничего не меняет, только читает каталог и пишет var/preview.html.
Тариф обязателен и без дефолта (ADR-009): выдуманное число тут превратится
в ₴/кВт·год на экране, а числа мы не выдумываем.

Запуск:
    python scripts/preview_card.py --tariff 4.32
    python scripts/preview_card.py --tariff 4.32 --appliances fridge_medium,gas_boiler
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PAGE = """<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Превью карток — autonomy-calc</title>
{styles}
<style>
body {{ margin: 0; background: #eef0f3; font: 16px/1.4 -apple-system, sans-serif; }}
.wrap {{ max-width: {width}px; margin: 0 auto; padding: 12px; }}
.meta {{ font-size: 13px; color: #5b6672; padding: 8px 0 12px; }}
</style>
</head>
<body>
<div class="wrap">
<p class="meta">{meta}</p>
{cards}
</div>
</body>
</html>
"""


def main() -> int:
    """Собирает превью. Импорты проекта — внутри, как в status.py."""
    from api.app import _recommendation_out
    from api.catalog_provider import (
        load_all_candidates,
        load_appliances,
        load_display_index,
    )
    from api.templating import render_card, render_card_styles
    from core.demand import calculate_requirement
    from core.load import AutonomyTarget, LoadItem, LoadProfile
    from core.units import Hours
    from matching.engine import select_recommendations

    parser = argparse.ArgumentParser(description="Превью карточек рекомендаций")
    parser.add_argument("--tariff", type=float, required=True, help="₴ за кВт·год")
    parser.add_argument("--appliances", default="fridge_medium,wifi_router_12v")
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--open", action="store_true", help="открыть в браузере")
    parser.add_argument(
        "--width", type=int, default=380, help="ширина колонки, px (380 = мобильный)"
    )
    args = parser.parse_args()

    appliances = load_appliances()
    items: list[LoadItem] = []
    for code in (c.strip() for c in args.appliances.split(",") if c.strip()):
        spec = appliances.get(code)
        if spec is None:
            print(f"неизвестный код прибора: {code}", file=sys.stderr)
            return 2
        items.append(LoadItem(appliance=spec, quantity=1, hours=Hours(args.hours)))

    requirement = calculate_requirement(
        LoadProfile(items=tuple(items)),
        AutonomyTarget(window_hours=Hours(args.hours)),
    )
    recommendations = select_recommendations(
        requirement,
        load_all_candidates(),
        grid_tariff_uah_per_kwh=args.tariff,
        limit=args.limit,
    )
    index = load_display_index()
    cards = "\n".join(
        render_card(_recommendation_out(item, index)) for item in recommendations
    )
    meta = (
        f"{args.appliances} · {args.hours:g} год · тариф {args.tariff:g} ₴/кВт·год · "
        f"рекомендацій: {len(recommendations)} · колонка {args.width}px"
    )

    out = ROOT / "var" / "preview.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        PAGE.format(
            styles=render_card_styles(), cards=cards, meta=meta, width=args.width
        ),
        encoding="utf-8",
    )
    print(f"записано: {out}")
    print(f"рекомендаций: {len(recommendations)}")
    if args.open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
