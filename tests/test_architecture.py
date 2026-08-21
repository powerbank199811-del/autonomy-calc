"""Тест границы модуля: ядро импортирует только stdlib и само себя.

Это единственный механизм, которым правило направления зависимостей
переживёт три месяца разработки.
"""

import ast
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "core"
ALLOWED = set(sys.stdlib_module_names) | {"core"}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_core_imports_only_stdlib() -> None:
    """В core/ не должно быть ни pydantic, ни sqlalchemy, ни httpx."""
    violations: dict[str, set[str]] = {}
    for path in CORE_DIR.rglob("*.py"):
        external = _imported_roots(path) - ALLOWED
        if external:
            violations[path.name] = external
    assert not violations, f"Ядро тянет внешние зависимости: {violations}"


REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
REFERENCE_ALLOWED = set(sys.stdlib_module_names) | {"core", "reference", "yaml"}


def test_reference_imports_only_core_and_declared_libs() -> None:
    """reference/ зависит от core и yaml — не от FastAPI, БД, HTTP."""
    violations: dict[str, set[str]] = {}
    for path in REFERENCE_DIR.rglob("*.py"):
        external = _imported_roots(path) - REFERENCE_ALLOWED
        if external:
            violations[path.name] = external
    assert not violations, f"reference/ тянет лишние зависимости: {violations}"


MATCHING_DIR = Path(__file__).resolve().parent.parent / "matching"
MATCHING_ALLOWED = set(sys.stdlib_module_names) | {"core", "matching"}


def test_matching_imports_only_core() -> None:
    """matching/ зависит от core — не от reference, не от FastAPI, не от БД."""
    violations: dict[str, set[str]] = {}
    for path in MATCHING_DIR.rglob("*.py"):
        external = _imported_roots(path) - MATCHING_ALLOWED
        if external:
            violations[path.name] = external
    assert not violations, f"matching/ тянет лишние зависимости: {violations}"


CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"
CATALOG_ALLOWED = set(sys.stdlib_module_names) | {"core", "matching", "catalog", "yaml"}


def test_catalog_imports_only_core_matching_and_declared_libs() -> None:
    """catalog/ — единственный слой, которому разрешено знать и core, и matching.

    Это точка склейки: products/offers превращаются в Candidate для движка.
    reference/ и matching/ не должны знать про catalog/ — только наоборот.
    """
    violations: dict[str, set[str]] = {}
    for path in CATALOG_DIR.rglob("*.py"):
        external = _imported_roots(path) - CATALOG_ALLOWED
        if external:
            violations[path.name] = external
    assert not violations, f"catalog/ тянет лишние зависимости: {violations}"

API_DIR = Path(__file__).resolve().parent.parent / "api"
API_ALLOWED = set(sys.stdlib_module_names) | {
    "api",
    "catalog",
    "core",
    "fastapi",
    "matching",
    "pydantic",
    "reference",
    "tracking",
}


def test_api_is_the_outermost_layer() -> None:
    """api/ знает про все внутренние слои — и ни один из них не знает про api/.

    Это внешний слой: сюда можно тянуть fastapi и pydantic, но проверка
    односторонняя, поэтому её дополняет test_inner_layers_never_import_api.
    """
    violations: dict[str, set[str]] = {}
    for path in API_DIR.rglob("*.py"):
        external = _imported_roots(path) - API_ALLOWED
        if external:
            violations[path.name] = external
    assert not violations, f"api/ тянет лишние зависимости: {violations}"


def test_inner_layers_never_import_api() -> None:
    """Ни core, ни reference, ни matching, ни catalog не знают, что API существует.

    Удаление api/ целиком не должно ломать ни один внутренний слой: HTTP —
    деталь доставки, а не часть домена.
    """
    root = Path(__file__).resolve().parent.parent
    violations: dict[str, set[str]] = {}
    for layer in ("core", "reference", "matching", "catalog", "tracking"):
        for path in (root / layer).rglob("*.py"):
            if "api" in _imported_roots(path):
                violations[f"{layer}/{path.name}"] = {"api"}
    assert not violations, f"внутренний слой импортирует api/: {violations}"



TRACKING_DIR = Path(__file__).resolve().parent.parent / "tracking"
TRACKING_ALLOWED = set(sys.stdlib_module_names) | {"tracking"}


def test_tracking_is_a_leaf_layer() -> None:
    """tracking/ не знает ни про расчёт, ни про каталог, ни про HTTP.

    Клик — это offer_id, источник и время. Ватт-часы, цены и пригодность
    решения к нему отношения не имеют, и связь между слоями — одна строка
    offer_id. Если сюда попадёт импорт catalog или matching, значит журналу
    начали приписывать знание о товаре, которое место в каталоге.
    """
    violations: dict[str, set[str]] = {}
    for path in TRACKING_DIR.rglob("*.py"):
        external = _imported_roots(path) - TRACKING_ALLOWED
        if external:
            violations[path.name] = external
    assert not violations, f"tracking/ тянет лишние зависимости: {violations}"
