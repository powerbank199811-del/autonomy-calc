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
