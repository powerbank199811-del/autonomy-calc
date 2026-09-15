#!/usr/bin/env python3
"""Снимок выдачи по фиксированным профилям — для diff между сессиями.

Тот же путь, что прод: api.app._calculate. Не собирает свой расчёт —
иначе снимок мог бы разойтись с тем, что видит пользователь (принцип 1).

Для строки "найдешевше покриття" используются core.demand.calculate_requirement
и core.fit.evaluate_fit напрямую, в обход matching.engine._cost_key — это
намеренно: цель строки в том, чтобы показать разрыв с тем, что выбрал
_cost_key, а не повторить его выбор. Тариф на неё не влияет: самая дешёвая
покрывающая цена не зависит от LCOE. DEFAULT_POLICY и evaluate_fit
импортируются из core.policy/core.fit напрямую (исходные модули, не
matching.engine — там это re-export без __all__, mypy на нём падает).

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
from api.catalog_provider import load_all_candidates  # noqa: E402
from api.schemas import RecommendationRequest  # noqa: E402
from core.demand import calculate_requirement  # noqa: E402
from core.fit import SolutionFit, evaluate_fit  # noqa: E402
from core.load import AutonomyTarget  # noqa: E402
from core.policy import DEFAULT_POLICY  # noqa: E402
from core.solution import SolutionKind  # noqa: E402
from core.units import Hours  # noqa: E402
from matching.candidate import Candidate  # noqa: E402

#: Четыре профиля из S8 (без тарифа — унаследованное поведение исходного
#: файла, не трогаем) + пятый — профиль со скриншота владельца
#: (диагностика ранжирования, эта сессия). Пятому профилю тариф нужен
#: явно: дефект из Части 1 (кит дешевле кита проигрывает по LCOE)
#: проявляется только при grid_tariff_uah_per_kwh задан, иначе ownership
#: не считается вовсе и _cost_key сортирует по чистой цене — без тарифа
#: профиль 5 не воспроизводит найденную проблему.
#: Четвёртый элемент кортежа — tariff, None для первых четырёх профилей.
PROFILES: tuple[tuple[str, list[dict[str, object]], float, float | None], ...] = (
    ("fridge_medium_4h", [{"code": "fridge_medium"}], 4, None),
    (
        "boiler_light_house_router_8h",
        [
            {"code": "gas_boiler"},
            {"code": "led_bulb_9w"},
            {"code": "wifi_router_9v"},
        ],
        8,
        None,
    ),
    (
        "router_laptop_dc_4h",
        [
            {"code": "wifi_router_9v"},
            {"code": "laptop_usb_c_pd_65w"},
        ],
        4,
        None,
    ),
    (
        "fridge_boiler_4h",
        [{"code": "fridge_medium"}, {"code": "gas_boiler"}],
        4,
        None,
    ),
    (
        "pc_monitor_router_lamp_8h",
        [
            {"code": "desktop_pc_office"},
            {"code": "monitor_24"},
            {"code": "wifi_router_9v"},
            {"code": "led_bulb_9w"},
        ],
        8,
        4.32,
    ),
)

#: limit=20, не дефолт 5 — снимок должен видеть весь топ, а не то,
#: что попало в дефолтную выдачу (иначе снимок сам зависит от лимита,
#: который меняется независимо от каталога).
LIMIT = 20


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


def _cheapest_covering(
    appliances: list[dict[str, object]], hours: float
) -> tuple[str, str, float, float] | None:
    """Самое дешёвое решение, покрывающее окно — независимо от _cost_key.

    Тот же фильтр, что matching/engine.py делает до сортировки:
    in_stock, can_run, can_cover_window. Дальше — минимум по абсолютной
    цене, без dimension и без LCOE, поэтому от тарифа не зависит.
    Возвращает None, если каталог пуст для этого профиля (дыра каталога,
    не дефект ранжирования).
    """
    request = RecommendationRequest.model_validate(
        {"appliances": appliances, "autonomy_hours": hours, "limit_per_kind": LIMIT}
    )
    profile = _build_profile(request)
    requirement = calculate_requirement(
        profile, AutonomyTarget(window_hours=Hours(hours))
    )

    best: tuple[Candidate, SolutionFit] | None = None
    for candidate in load_all_candidates():
        if not candidate.in_stock:
            continue
        fit = evaluate_fit(requirement, candidate.solution, DEFAULT_POLICY)
        if not fit.can_run or not fit.can_cover_window:
            continue
        if best is None or candidate.price_uah < best[0].price_uah:
            best = (candidate, fit)

    if best is None:
        return None
    candidate, fit = best
    is_kit = candidate.component_offer_ids is not None
    kind = "KIT" if is_kit else candidate.solution.kind.name
    return (kind, candidate.offer_id, candidate.price_uah, fit.autonomy_hours)


def _print_profile(
    label: str,
    appliances: list[dict[str, object]],
    hours: float,
    tariff: float | None,
) -> None:
    payload: dict[str, object] = {
        "appliances": appliances,
        "autonomy_hours": hours,
        "limit_per_kind": LIMIT,
    }
    if tariff is not None:
        payload["grid_tariff_uah_per_kwh"] = tariff
    request = RecommendationRequest.model_validate(payload)
    response = _calculate(request)

    counts: dict[str, int] = {kind.name: 0 for kind in SolutionKind}
    rows: list[tuple[str, str, float, float]] = []
    for item in response.recommendations:
        kind = "KIT" if item.component_offer_ids else _kind_name(item)
        counts[kind] = counts.get(kind, 0) + 1
        rows.append((kind, item.offer_id, item.price_uah, item.fit.autonomy_hours))

    tariff_note = f" tariff={tariff}" if tariff is not None else ""
    print(f"# profile={label} hours={hours} limit={LIMIT}{tariff_note}")
    print(
        "# summary "
        + " ".join(f"{kind}={count}" for kind, count in sorted(counts.items()) if count)
    )

    if response.recommendations:
        first = response.recommendations[0]
        first_kind = "KIT" if first.component_offer_ids else _kind_name(first)
        print(
            f"# показано першим:     {first_kind}\t{first.price_uah:.2f}\t"
            f"{first.fit.autonomy_hours:.1f}\t{first.offer_id}"
        )
    else:
        print("# показано першим:     (порожня видача)")

    cheapest = _cheapest_covering(appliances, hours)
    if cheapest is not None:
        kind, offer_id, price, autonomy = cheapest
        print(f"# найдешевше покриття: {kind}\t{price:.2f}\t{autonomy:.1f}\t{offer_id}")
    else:
        print("# найдешевше покриття: (немає покриваючих кандидатів — дыра каталога)")

    rows.sort(key=lambda row: (row[0], row[1]))
    for kind, offer_id, price, autonomy in rows:
        print(f"{kind}\t{offer_id}\t{price:.2f}\t{autonomy:.1f}")
    print()


def main() -> None:
    for label, appliances, hours, tariff in PROFILES:
        _print_profile(label, appliances, hours, tariff)


if __name__ == "__main__":
    main()