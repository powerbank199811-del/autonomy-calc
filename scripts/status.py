#!/usr/bin/env python3
"""Срез состояния проекта: каталог, файлы данных, тесты, git.

Назначение: не выяснять состояние вручную в начале каждой сессии.
Скрипт НИЧЕГО не меняет — только читает файлы и запускает внешние
команды на чтение (pytest, git). Слой инструментальный, вне
архитектурных границ: импортирует только catalog/ и core/, чтобы
использовать те же загрузчики, что и продакшн-код (ошибка №6 —
состояние каталога проверяется кодом, а не чтением YAML глазами).

Запуск:
    python scripts/status.py
    python scripts/status.py --no-tests   # без прогона pytest
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"

# Файлы данных, наличие которых проверяется. Часть из них ещё не создана —
# это ожидаемо, крестик здесь не ошибка, а факт.
EXPECTED_DATA_FILES: tuple[str, ...] = (
    "appliances.yaml",
    "components.yaml",
    "products.yaml",
    "sources.yaml",
    "devices.yaml",
    "scenarios.yaml",
    "accessories.yaml",
)

# Известные падения тестов, оставленные сознательно. Печатаются с пометкой,
# чтобы не путать их с новыми регрессиями.
KNOWN_FAILURES: dict[str, str] = {
    "lifan": "падение, оставлено как есть",
    "test_catalog_size": "хардкод размера каталога, ошибка №5",
    "test_real_components": "хардкод размера каталога, ошибка №5",
}


class OfferLike(Protocol):
    """Структурный тип оффера: CatalogOffer и ComponentOffer совпадают по этим полям.

    Номинальной общей базы у них нет и не должно быть — это разные сущности
    из разных слоёв каталога. Для подсчёта достаточно структурного совпадения.

    Поля объявлены через @property (read-only): оба оффера — frozen-датаклассы,
    изменяемому атрибуту в протоколе они не соответствуют.
    """

    @property
    def url(self) -> str | None: ...

    @property
    def in_stock(self) -> bool: ...

    @property
    def source(self) -> str: ...


@dataclass(frozen=True, slots=True)
class OfferStats:
    """Агрегат по офферам одного источника каталога."""

    total: int
    no_url: int
    out_of_stock: int
    domains: Counter[str]


def _header(title: str) -> None:
    """Печатает заголовок секции."""
    print(f"\n=== {title} ===")


def _collect_offer_stats(offers: Iterable[OfferLike]) -> OfferStats:
    """Считает офферы: всего, без url, не в наличии, домены продавцов."""
    total = 0
    no_url = 0
    out_of_stock = 0
    domains: Counter[str] = Counter()
    for offer in offers:
        total += 1
        if offer.url is None or not offer.url.strip():
            no_url += 1
        if not offer.in_stock:
            out_of_stock += 1
        domains[offer.source] += 1
    return OfferStats(total=total, no_url=no_url, out_of_stock=out_of_stock, domains=domains)


def _print_catalog() -> None:
    """Секция CATALOG: оба слоя каталога плюс справочник продавцов."""
    _header("CATALOG")

    from catalog.components_loader import load_components
    from catalog.products_loader import load_catalog
    from catalog.sources_loader import load_sources
    from core.solution import SolutionKind

    all_domains: Counter[str] = Counter()
    offers_total = 0
    no_url_total = 0
    out_of_stock_total = 0

    # --- products.yaml -------------------------------------------------
    try:
        products, offers = load_catalog(DATA / "products.yaml")
    except Exception as exc:  # noqa: BLE001 — диагностика, падать нельзя
        print(f"products.yaml: ОШИБКА ЗАГРУЗКИ — {type(exc).__name__}: {exc}")
        products, offers = (), ()

    if products:
        print("products.yaml по категориям:")
        for category, count in sorted(Counter(p.category for p in products).items()):
            print(f"  {category}: {count}")
        print(f"  всего продуктов: {len(products)}")

    product_stats = _collect_offer_stats(offers)
    offers_total += product_stats.total
    no_url_total += product_stats.no_url
    out_of_stock_total += product_stats.out_of_stock
    all_domains.update(product_stats.domains)

    # --- components.yaml -----------------------------------------------
    try:
        inverters, inverter_offers, batteries, battery_offers = load_components(
            DATA / "components.yaml"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"components.yaml: ОШИБКА ЗАГРУЗКИ — {type(exc).__name__}: {exc}")
        inverters, inverter_offers, batteries, battery_offers = (), (), (), ()

    print(f"components.yaml: інвертори {len(inverters)}, батареї {len(batteries)}")

    for stats in (_collect_offer_stats(inverter_offers), _collect_offer_stats(battery_offers)):
        offers_total += stats.total
        no_url_total += stats.no_url
        out_of_stock_total += stats.out_of_stock
        all_domains.update(stats.domains)

    # --- офферы суммарно -------------------------------------------------
    print(
        f"offers total: {offers_total} "
        f"(products {product_stats.total} + "
        f"inverters {len(inverter_offers)} + batteries {len(battery_offers)})"
    )
    print(f"offers без url: {no_url_total}")
    print(f"offers in_stock=False: {out_of_stock_total}")

    # --- честная ёмкость повербанков -------------------------------------
    powerbanks = [p for p in products if p.spec.kind is SolutionKind.POWERBANK]
    measured = sum(1 for p in powerbanks if p.spec.measured_wh is not None)
    print(f"повербанки з measured_wh: {measured}/{len(powerbanks)}")

    # --- sources.yaml ------------------------------------------------------
    try:
        sources = load_sources(DATA / "sources.yaml")
    except Exception as exc:  # noqa: BLE001
        print(f"sources.yaml: ОШИБКА ЗАГРУЗКИ — {type(exc).__name__}: {exc}")
        return

    print(f"sources.yaml: {len(sources)} доменів з seller_label")
    unknown = sorted(d for d in all_domains if d and d not in sources)
    if unknown:
        print(f"  домени офферів ПОЗА sources.yaml ({len(unknown)}): {', '.join(unknown)}")
    else:
        print("  всі домени офферів покриті seller_label")


def _print_data_files() -> None:
    """Секция DATA FILES: какие справочники существуют, какие нет."""
    _header("DATA FILES")
    for name in EXPECTED_DATA_FILES:
        path = DATA / name
        mark = "✓" if path.is_file() else "✗"
        size = f"  ({path.stat().st_size} B)" if path.is_file() else ""
        print(f"  {mark} data/{name}{size}")


def _annotate(test_id: str) -> str:
    """Дописывает пометку к известному падению, если оно узнаётся по имени."""
    for marker, note in KNOWN_FAILURES.items():
        if marker in test_id:
            return f"  [{note}]"
    return "  [НОВОЕ падение]"


def _print_tests() -> None:
    """Секция TESTS: краткий итог pytest и явные имена падающих тестов."""
    _header("TESTS")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no", "-rf"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError:
        print("pytest не найден в текущем интерпретаторе")
        return
    except subprocess.TimeoutExpired:
        print("pytest не завершился за 600 с")
        return

    lines = result.stdout.splitlines()
    summary = next(
        (ln for ln in reversed(lines) if " passed" in ln or " failed" in ln or " error" in ln),
        "итоговая строка pytest не распознана",
    )
    print(summary.strip())

    failed = [ln.split("FAILED ", 1)[1].strip() for ln in lines if ln.startswith("FAILED ")]
    if failed:
        print("падающие тесты:")
        for test_id in failed:
            print(f"  {test_id}{_annotate(test_id)}")


def _git(*args: str) -> str:
    """Выполняет git-команду на чтение, возвращает stdout без хвостовых пробелов."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.rstrip()


def _print_git() -> None:
    """Секция GIT: ветка, незакоммиченные пути списком, последний коммит."""
    _header("GIT")
    print(f"branch: {_git('rev-parse', '--abbrev-ref', 'HEAD') or '?'}")

    porcelain = _git("status", "--porcelain")
    changed = [ln for ln in porcelain.splitlines() if ln.strip()]
    if changed:
        print(f"uncommitted ({len(changed)}):")
        for line in changed:
            print(f"  {line}")
    else:
        print("uncommitted: рабочее дерево чистое")

    print(f"last commit: {_git('log', '-1', '--oneline') or '?'}")
    print(f"origin/main: {_git('log', 'origin/main', '-1', '--oneline') or 'не сверялся'}")


def main() -> int:
    """Печатает все секции. Возвращает 0 всегда: это диагностика, не проверка."""
    skip_tests = "--no-tests" in sys.argv
    print(f"autonomy-calc — состояние проекта ({ROOT})")
    _print_catalog()
    _print_data_files()
    if skip_tests:
        _header("TESTS")
        print("пропущено (--no-tests)")
    else:
        _print_tests()
    _print_git()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())