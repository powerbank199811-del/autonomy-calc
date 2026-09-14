"""Загрузка справочника приборов: реальные данные и обработка ошибок."""

from pathlib import Path

import pytest

from core.appliances import PowerBus
from reference.appliances_loader import AppliancesCatalogError, load_appliances_catalog

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "appliances.yaml"


def test_real_catalog_loads_and_is_in_scope() -> None:
    """Реальный справочник грузится и укладывается в 40-60 позиций (план проекта)."""
    catalog = load_appliances_catalog(DATA_PATH)
    assert 40 <= len(catalog) <= 60


def test_real_catalog_codes_are_unique() -> None:
    """Инвариант: code не повторяется — на него будут ссылаться сохранённые расчёты."""
    catalog = load_appliances_catalog(DATA_PATH)
    codes = [e.code for e in catalog]
    assert len(codes) == len(set(codes))


def test_real_catalog_has_expected_categories() -> None:
    """Проверка, что ключевые категории для блэкаута на месте."""
    catalog = load_appliances_catalog(DATA_PATH)
    categories = {e.category for e in catalog}
    assert "Холодильне обладнання" in categories
    assert "Опалення та вода" in categories
    assert "Зв'язок та охорона" in categories


def test_fridge_medium_matches_golden_scenario() -> None:
    """Значения holodilnik_medium совпадают с золотым сценарием test_fit.py."""
    catalog = load_appliances_catalog(DATA_PATH)
    fridge = next(e for e in catalog if e.code == "fridge_medium")
    assert fridge.spec.power_w == 150.0
    assert fridge.spec.duty_cycle == 0.35
    assert fridge.spec.startup_factor == 5.0
    assert fridge.spec.requires_pure_sine is True


def test_no_appliance_declares_switchover_requirement() -> None:
    """Рамка ADR-042: справочник не требует времени переключения ни у одного прибора.

    Продукт отвечает на плановое отключение по графику, а не на бесперебойность.
    Заполненное max_switchover_ms снова включит ветку core/fit.py:139-142,
    которая отбрасывает каждое решение с незаполненным switchover_ms —
    это все 10 инверторов и 15 продуктов из 21.
    """
    catalog = load_appliances_catalog(DATA_PATH)
    offenders = [e.code for e in catalog if e.spec.max_switchover_ms is not None]
    assert not offenders, (
        f"ADR-042: max_switchover_ms не заполняется в справочнике, "
        f"найдено у {sorted(offenders)}"
    )   


def test_dc_bus_items_are_marked() -> None:
    """Зарядка через USB (повербанк) помечена отдельной шиной, не смешана с AC."""
    catalog = load_appliances_catalog(DATA_PATH)
    phone = next(e for e in catalog if e.code == "smartphone_charge")
    assert phone.spec.bus is PowerBus.DC_USB


def test_missing_required_field_raises_clear_error(tmp_path: Path) -> None:
    """Отсутствие power_w — понятная ошибка с номером записи, не KeyError."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        "- code: broken\n  name_uk: 'Сломанный'\n  category: 'Тест'\n", encoding="utf-8"
    )
    with pytest.raises(AppliancesCatalogError, match="power_w"):
        load_appliances_catalog(bad_yaml)


def test_duplicate_code_raises(tmp_path: Path) -> None:
    """Дубликат code — явная ошибка, а не молчаливая перезапись."""
    bad_yaml = tmp_path / "dup.yaml"
    bad_yaml.write_text(
        "- code: dup\n  name_uk: 'A'\n  category: 'X'\n  power_w: 10\n"
        "- code: dup\n  name_uk: 'B'\n  category: 'X'\n  power_w: 20\n",
        encoding="utf-8",
    )
    with pytest.raises(AppliancesCatalogError, match="повторяющийся"):
        load_appliances_catalog(bad_yaml)


def test_negative_power_raises(tmp_path: Path) -> None:
    """Отрицательная мощность — доменная ошибка ApplianceSpec всплывает наверх."""
    bad_yaml = tmp_path / "negative.yaml"
    bad_yaml.write_text(
        "- code: negative\n  name_uk: 'Плохой'\n  category: 'Тест'\n  power_w: -5\n",
        encoding="utf-8",
    )
    with pytest.raises(AppliancesCatalogError):
        load_appliances_catalog(bad_yaml)


def test_not_a_list_raises(tmp_path: Path) -> None:
    """YAML верхнего уровня должен быть списком, не словарём или строкой."""
    bad_yaml = tmp_path / "not_list.yaml"
    bad_yaml.write_text("code: not_a_list\n", encoding="utf-8")
    with pytest.raises(AppliancesCatalogError, match="ожидался список"):
        load_appliances_catalog(bad_yaml)
