#!/usr/bin/env python3
"""Снимок выдачи по фиксированным профилям — для diff между сессиями.

Тот же путь, что прод: api.app._calculate. Не собирает свой расчёт —
иначе снимок мог бы разойтись с тем, что видит пользователь (принцип 1).

Формат стабилен для diff: без временных меток, без путей с датами,
сортировка кандидатов внутри профиля детерминирована (kind, затем
offer_id) — порядок не зависит от порядка чтения YAML.

Запуск:
    python scripts/snapshot.py > var/snapshot_$(date +%F).txt
    diff var/snapshot_2026-09-01.txt var/snapshot_2026-09-11.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import _build_profile, _calculate  # noqa: E402
from api.schemas import RecommendationRequest  # noqa: E402
from core.solution import SolutionKind  # noqa: E402

#: Четыре профиля из S8 + четвёртый (S8-замер, давал пустую выдачу).
#: autonomy_hours и лимит зафиксированы здесь же, а не в вызывающем
#: коде — снимок должен быть воспроизводим без внешних параметров.
PROFILES: tuple[tuple[str, list[dict[str, object]], float], ...] = (
    ("fridge_medium_4h", [{"code": "fridge_medium"}], 4),
    (
        "boiler_light_house_router_8h",
        [
            {"code": "gas_boiler"},
            {"code": "led_bulb_9w"},
            {"code": "wifi_router_9v"},
        ],
        8,
    ),
    (
        "router_laptop_dc_4h",
        [
            {"code": "wifi_router_9v"},
            {"code": "laptop_usb_c_pd_65w"},
        ],
        4,
    ),
    (
        "fridge_boiler_4h",
        [{"code": "fridge_medium"}, {"code": "gas_boiler"}],
        4,
    ),
)

#: limit=20, не дефолт 5 — снимок должен видеть весь топ, а не то,
#: что попало в дефолтную выдачу (иначе снимок сам зависит от лимита,
#: который меняется независимо от каталога).
LIMIT = 20


def _print_profile(label: str, appliances: list[dict[str, object]], hours: float) -> None:
    request = RecommendationRequest.model_validate(
        {"appliances": appliances, "autonomy_hours": hours, "limit": LIMIT}
    )
    response = _calculate(request)

    counts: dict[str, int] = {kind.name: 0 for kind in SolutionKind}
    rows: list[tuple[str, str, float, float]] = []
    for item in response.recommendations:
        kind = "KIT" if item.component_offer_ids else _kind_name(item)
        counts[kind] = counts.get(kind, 0) + 1
        rows.append((kind, item.offer_id, item.price_uah, item.fit.autonomy_hours))

    rows.sort(key=lambda row: (row[0], row[1]))

    print(f"# profile={label} hours={hours} limit={LIMIT}")
    print(
        "# summary "
        + " ".join(f"{kind}={count}" for kind, count in sorted(counts.items()) if count)
    )
    for kind, offer_id, price, autonomy in rows:
        print(f"{kind}\t{offer_id}\t{price:.2f}\t{autonomy:.1f}")
    print()


def _kind_name(item: object) -> str:
    """Тип решения не-кита по префиксу offer_id.

    Явный обход: RecommendationOut не хранит SolutionKind (ADR-038,
    display-контракт не расширяет домен) — префикс offer_id единственный
    доступный признак на уровне api/. Соглашение об именовании нигде не
    зафиксировано как контракт, поэтому падаем на неизвестном префиксе,
    а не приписываем тип по умолчанию: тихая STATION была бы враньём
    в снимке, единственная ценность которого — доверенный diff.
    """
    offer_id = getattr(item, "offer_id", "")
    if offer_id.startswith("generator_"):
        return "GENERATOR"
    if offer_id.startswith("station_"):
        return "STATION"
    if offer_id.startswith("powerbank_"):
        return "POWERBANK"
    raise ValueError(f"неизвестный префикс offer_id, тип не определён: {offer_id!r}")


def main() -> None:
    for label, appliances, hours in PROFILES:
        _print_profile(label, appliances, hours)


if __name__ == "__main__":
    main()