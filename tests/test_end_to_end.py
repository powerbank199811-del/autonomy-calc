"""Сквозной сценарий: справочник -> ядро -> каталог -> движок подбора.

Это интеграционный тест, не юнит: он не проверяет отдельную формулу,
а то, что все слои реально стыкуются друг с другом на реальных данных
проекта, а не только на фикстурах внутри тестов отдельных модулей.
"""

from pathlib import Path

from catalog.candidates import build_candidates
from catalog.products_loader import load_catalog
from core.demand import calculate_requirement
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.units import Hours
from matching.engine import select_recommendations
from reference.appliances_loader import load_appliances_catalog

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_full_pipeline_produces_ranked_recommendations() -> None:
    """Холодильник + роутер + Starlink на 6ч блэкаута -> список рекомендаций."""
    appliances = {
        e.code: e.spec for e in load_appliances_catalog(DATA_DIR / "appliances.yaml")
    }
    products, offers = load_catalog(DATA_DIR / "products.yaml")
    candidates = build_candidates(products, offers)

    profile = LoadProfile(
        items=(
            LoadItem(appliance=appliances["fridge_medium"]),
            LoadItem(appliance=appliances["wifi_router_9v"]),
            LoadItem(appliance=appliances["starlink_standard"]),
        )
    )
    requirement = calculate_requirement(profile, AutonomyTarget(window_hours=Hours(6)))

    recommendations = select_recommendations(
        requirement, candidates, grid_tariff_uah_per_kwh=4.32
    )

    assert len(recommendations) > 0
    # Инвариант ранжирования: полное покрытие всегда идёт раньше частичного.
    seen_partial = False
    for rec in recommendations:
        if not rec.fit.can_cover_window:
            seen_partial = True
        elif seen_partial:
            raise AssertionError("Частичное покрытие оказалось раньше полного")

    # rank_position идёт по порядку без пропусков
    assert [r.rank_position for r in recommendations] == list(
        range(1, len(recommendations) + 1)
    )


def test_full_pipeline_without_tariff_skips_ownership() -> None:
    """Без тарифа economics не считается нигде по всей цепочке."""
    appliances = {
        e.code: e.spec for e in load_appliances_catalog(DATA_DIR / "appliances.yaml")
    }
    products, offers = load_catalog(DATA_DIR / "products.yaml")
    candidates = build_candidates(products, offers)

    profile = LoadProfile(items=(LoadItem(appliance=appliances["led_bulb_9w"]),))
    requirement = calculate_requirement(profile, AutonomyTarget(window_hours=Hours(4)))

    recommendations = select_recommendations(requirement, candidates)
    assert all(r.ownership is None for r in recommendations)
