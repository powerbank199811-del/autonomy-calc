"""Реальные данные data/components.yaml: загрузка и сборка китов."""

from pathlib import Path

from catalog.components_loader import load_components
from catalog.kit_candidates import build_kit_candidates
from catalog.products import FuelRateSource
from catalog.products_loader import load_catalog

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_real_components_load_and_validate() -> None:
    """9 инверторов + 6 АКБ грузятся и проходят валидацию core.solution."""
    inverters, inv_offers, batteries, bat_offers = load_components(
        DATA_DIR / "components.yaml"
    )
    assert len(inverters) == 9
    assert len(batteries) == 6


def test_real_kits_produce_compatible_pairs() -> None:
    """Реальные данные дают рабочие пары инвертор+АКБ, 24V остаётся без пары."""
    inverters, inv_offers, batteries, bat_offers = load_components(
        DATA_DIR / "components.yaml"
    )
    candidates = build_kit_candidates(inverters, inv_offers, batteries, bat_offers)
    assert len(candidates) == 24  # 8 совместимых инверторов x 3 АКБ 48V + 3 малых x 2 АКБ 12V

    offer_ids = {c.offer_id for c in candidates}
    # Deye SUN-5K + Deye SE-F5 Pro-C — оба 48V-класс, должны собраться
    assert any("inv_deye_sun5k" in oid and "bat_deye_sef5proc" in oid for oid in offer_ids)
    # 24V-вариант Sinus 600 не находит пары — все АКБ на 12.8V
    assert not any("sinus600_24v" in oid for oid in offer_ids)


def test_lifan_generator_flagged_as_estimated() -> None:
    """Lifan с derived_from_tank расходом — статус доверия сохранён в каталоге."""
    products, offers = load_catalog(DATA_DIR / "products.yaml")
    lifan = next(p for p in products if p.product_id == "generator_lifan_lf2800i_2")
    assert lifan.fuel_rate_source is FuelRateSource.DERIVED_FROM_TANK


def test_konner_generator_flagged_as_rated() -> None:
    """Konner&Sohnen с паспортным расходом — другой, более надёжный статус."""
    products, offers = load_catalog(DATA_DIR / "products.yaml")
    konner = next(
        p for p in products if p.product_id == "generator_konner_sohnen_ks_4000ie_s_ats"
    )
    assert konner.fuel_rate_source is FuelRateSource.RATED_SPECIFIC


def test_battery_with_dod_override_differs_from_class_default() -> None:
    """Must LP15 (80% DoD по паспорту) и LogicPower (без override, 90% по умолчанию для
    LiFePO4) дают разную полезную энергию на одинаковой заявленной ёмкости."""
    inverters, inv_offers, batteries, bat_offers = load_components(
        DATA_DIR / "components.yaml"
    )
    must = next(b for b in batteries if b.component_id == "bat_must_lp15_12100")
    logicpower = next(b for b in batteries if b.component_id == "bat_logicpower_lp24662")
    assert must.spec.depth_of_discharge_override == 0.80
    assert logicpower.spec.depth_of_discharge_override is None
