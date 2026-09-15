"""Одноразовая диагностика ранжирования: все кандидаты, покрывающие окно.

Повторяет цикл matching/engine.py:49-73 дословно, но без обрезки по limit
и без сортировки по ключу — печатает всех, отсортированных по абсолютной
цене, и отмечает, на каком месте каждый оказался в реальной выдаче.

Приватные функции _cost_key/_build_ownership_input берутся из
matching.engine намеренно: так исключено расхождение между тем, что мерит
диагностика, и тем, что делает продакшн-путь. DEFAULT_POLICY,
evaluate_fit и calculate_ownership_cost импортируются из их исходных
модулей (core.policy, core.fit, core.economics), а не через matching.engine
— это re-export, не место определения, и mypy требует явного __all__
для импорта оттуда.

Статус после сессии реализации ADR-039/041 (14.09.2026): механизм 2
(кандидат без cycle_life обходил станцию по размерности, не по цене)
закрыт партиционированием структурно — станция и кит физически не
попадают в одну партицию для сравнения, воспроизвести через этот скрипт
больше нельзя. Механизм 1 (кит с лучшим LCOE обходит кит с более низкой
сырой ценой без верхней границы на неё, ADR-029) остаётся открытым,
отложен на «за релиз» (STATUS.md). Колонка "вим" (dimension) в выводе
по-прежнему показывает его: сравните строки INVERTER_BATTERY — 79498₴
(вим=0, LCOE 6.76) ранжируется выше 75498₴ (вим=0, LCOE 7.71), хотя
дороже по сырой цене. Скрипт актуален для диагностики именно этого
случая, держать не как исторический артефакт.
"""

from __future__ import annotations

from api.app import _build_profile
from api.catalog_provider import load_all_candidates
from api.schemas import ApplianceSelection, RecommendationRequest
from core.demand import calculate_requirement
from core.economics import OwnershipCost, calculate_ownership_cost
from core.fit import SolutionFit, evaluate_fit
from core.load import AutonomyTarget
from core.policy import DEFAULT_POLICY
from core.units import Hours
from matching.candidate import Candidate
from matching.engine import (
    _build_ownership_input,
    _cost_key,
    select_recommendations,
)

PROFILE_CODES: tuple[str, ...] = (
    "desktop_pc_office",
    "monitor_24",
    "wifi_router_9v",
    "led_bulb_9w",
)
HOURS: float = 8.0
TARIFF: float = 4.32
FUEL_PRICE: float | None = None  # как в URL со скриншота: параметра &f= нет
LIMIT: int = 20


def main() -> None:
    """Печатает потребность, полную таблицу покрывающих кандидатов и итог."""
    request = RecommendationRequest(
        appliances=[ApplianceSelection(code=code) for code in PROFILE_CODES],
        autonomy_hours=HOURS,
        grid_tariff_uah_per_kwh=TARIFF,
        fuel_price_uah_per_l=FUEL_PRICE,
        limit_per_kind=LIMIT,
    )
    profile = _build_profile(request)
    requirement = calculate_requirement(
        profile, AutonomyTarget(window_hours=Hours(HOURS))
    )
    print("ПОТРЕБНОСТЬ")
    print(requirement)
    print()

    candidates = load_all_candidates()
    print(f"кандидатов в каталоге всего: {len(candidates)}")

    rows: list[tuple[Candidate, SolutionFit, OwnershipCost | None, int]] = []
    skipped_stock = 0
    skipped_run = 0
    skipped_window = 0

    for candidate in candidates:
        if not candidate.in_stock:
            skipped_stock += 1
            continue
        fit = evaluate_fit(requirement, candidate.solution, DEFAULT_POLICY)
        if not fit.can_run:
            skipped_run += 1
            continue
        if not fit.can_cover_window:
            skipped_window += 1
            continue

        ownership: OwnershipCost | None = None
        ownership_input = _build_ownership_input(
            candidate, fit, TARIFF, FUEL_PRICE
        )
        if ownership_input is not None:
            ownership = calculate_ownership_cost(ownership_input, DEFAULT_POLICY)

        dimension, _ = _cost_key(candidate, ownership)
        rows.append((candidate, fit, ownership, dimension))

    print(
        f"отсеяно: in_stock={skipped_stock}, "
        f"can_run={skipped_run}, can_cover_window={skipped_window}"
    )
    print(f"покрывают окно: {len(rows)}")
    print()

    ranked = select_recommendations(
        requirement,
        candidates,
        grid_tariff_uah_per_kwh=TARIFF,
        fuel_price_uah_per_l=FUEL_PRICE,
        limit_per_kind=LIMIT,
    )
    positions = {rec.offer_id: rec.rank_position for rec in ranked}

    rows.sort(key=lambda row: row[0].price_uah)

    header = (
        f"{'поз':>4} {'вим':>4} {'kind':<18} {'ціна':>10} "
        f"{'год':>7} {'грн/кВт·год':>12}  offer_id"
    )
    print(header)
    print("-" * len(header))
    for candidate, fit, ownership, dimension in rows:
        position = positions.get(candidate.offer_id)
        lcoe = f"{ownership.cost_per_kwh_uah:.2f}" if ownership is not None else "—"
        print(
            f"{position if position is not None else '-':>4} "
            f"{dimension:>4} "
            f"{candidate.solution.kind.name:<18} "
            f"{candidate.price_uah:>10.0f} "
            f"{fit.autonomy_hours:>7.1f} "
            f"{lcoe:>12}  "
            f"{candidate.offer_id}"
        )

    print()
    print(f"в выдаче при limit={LIMIT}: {len(positions)} из {len(rows)}")


if __name__ == "__main__":
    main()