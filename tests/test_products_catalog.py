"""Каталог products/offers: загрузка, целостность, склейка с движком."""

from pathlib import Path

import pytest

from catalog.candidates import UnknownProductError, build_candidates
from catalog.offers import CatalogOffer
from catalog.products import CatalogProduct
from catalog.products_loader import ProductsCatalogError, load_catalog
from core.solution import SolutionKind, SolutionSpec, StorageChemistry, Waveform
from core.units import Watt, WattHour

MINIMAL_YAML = """
products:
  - product_id: p1
    name: "Тестова станція"
    brand: "TestBrand"
    model: "T100"
    category: "Портативні станції"
    kind: station
    chemistry: lifepo4
    capacity_wh: 1000
    continuous_power_w: 1000
    peak_power_w: 2000
    waveform: pure_sine
    cycle_life: 3000

offers:
  - offer_id: o1
    product_id: p1
    price_uah: 25000
    commission_rate: 0.05
    source: "власний магазин"
"""


def test_minimal_catalog_loads(tmp_path: Path) -> None:
    """Минимальный валидный каталог грузится, product и offer связаны."""
    f = tmp_path / "catalog.yaml"
    f.write_text(MINIMAL_YAML, encoding="utf-8")
    products, offers = load_catalog(f)
    assert len(products) == 1
    assert len(offers) == 1
    assert offers[0].product_id == products[0].product_id


def test_offer_pointing_to_unknown_product_raises(tmp_path: Path) -> None:
    """Оффер на несуществующий product_id — ошибка при загрузке, не потом."""
    bad = MINIMAL_YAML.replace("product_id: p1\n    price_uah", "product_id: GHOST\n    price_uah")
    f = tmp_path / "bad.yaml"
    f.write_text(bad, encoding="utf-8")
    with pytest.raises(ProductsCatalogError, match="несуществующий"):
        load_catalog(f)


def test_duplicate_product_id_raises(tmp_path: Path) -> None:
    """Дубликат product_id — явная ошибка."""
    doubled = MINIMAL_YAML.replace(
        "offers:", MINIMAL_YAML.split("offers:")[0].split("products:\n")[1] + "offers:"
    )
    f = tmp_path / "dup.yaml"
    f.write_text(doubled, encoding="utf-8")
    with pytest.raises(ProductsCatalogError, match="повторяющийся product_id"):
        load_catalog(f)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    """Нет обязательного поля 'kind' — понятная ошибка с номером записи."""
    bad = MINIMAL_YAML.replace("    kind: station\n", "")
    f = tmp_path / "bad.yaml"
    f.write_text(bad, encoding="utf-8")
    with pytest.raises(ProductsCatalogError, match="kind"):
        load_catalog(f)


def test_missing_top_level_keys_raises(tmp_path: Path) -> None:
    """YAML без 'products'/'offers' — понятная ошибка, не KeyError где-то внутри."""
    f = tmp_path / "bad.yaml"
    f.write_text("just_a_list:\n  - 1\n", encoding="utf-8")
    with pytest.raises(ProductsCatalogError, match="products"):
        load_catalog(f)


def test_build_candidates_joins_product_and_offer() -> None:
    """Склейка: Candidate получает solution от product, цену и комиссию от offer."""
    product = CatalogProduct(
        product_id="p1", name="Тест", brand="B", model="M", category="C",
        spec=SolutionSpec(
            kind=SolutionKind.STATION, chemistry=StorageChemistry.LIFEPO4,
            capacity_wh=WattHour(1000), continuous_power_w=Watt(1000),
            peak_power_w=Watt(2000), waveform=Waveform.PURE_SINE, cycle_life=3000,
        ),
    )
    offer = CatalogOffer(
        offer_id="o1", product_id="p1", price_uah=25000, commission_rate=0.05,
        source="власний магазин",
    )
    candidates = build_candidates((product,), (offer,))
    assert len(candidates) == 1
    assert candidates[0].offer_id == "o1"
    assert candidates[0].price_uah == 25000
    assert candidates[0].solution is product.spec


def test_build_candidates_raises_on_dangling_offer() -> None:
    """Защита build_candidates не полагается молча на проверку загрузчика."""
    offer = CatalogOffer(
        offer_id="o1", product_id="GHOST", price_uah=1000, commission_rate=0.05, source="x",
    )
    with pytest.raises(UnknownProductError):
        build_candidates((), (offer,))
