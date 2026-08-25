"""Загрузка каталога с диска — один раз, а не на каждый запрос.

Здесь же собирается полный список кандидатов: готовые товары плюс киты
«инвертор + АКБ». Для движка подбора это однородный список Candidate —
он не знает и не должен знать, что часть из них собрана на лету.

Путь к data/ — единственное, что этот модуль знает про файловую систему.
Когда в фазе 2 появится PostgreSQL, заменяется только тело load_candidates:
ни схемы, ни обработчик, ни движок не трогаются.
"""

from functools import lru_cache
from pathlib import Path

from catalog.candidates import build_candidates
from catalog.components_loader import load_components
from catalog.kit_candidates import build_kit_candidates
from catalog.products_loader import load_catalog
from core.appliances import ApplianceSpec
from matching.candidate import Candidate
from reference.appliances import CatalogAppliance
from reference.appliances_loader import load_appliances_catalog
from api.display_index import DisplayIndex, build_display_index
from catalog.sources_loader import load_sources


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def load_appliance_catalog() -> tuple[CatalogAppliance, ...]:
    """Справочник целиком: коды, украинские названия, категории."""
    return load_appliances_catalog(DATA_DIR / "appliances.yaml")


def load_appliances() -> dict[str, ApplianceSpec]:
    """Справочник приборов по коду. Ключ — то, что присылает клиент."""
    return {entry.code: entry.spec for entry in load_appliance_catalog()}


@lru_cache(maxsize=1)
def load_all_candidates() -> tuple[Candidate, ...]:
    """Готовые товары + все совместимые пары инвертор/АКБ одним списком."""
    products, offers = load_catalog(DATA_DIR / "products.yaml")
    inverters, inverter_offers, batteries, battery_offers = load_components(
        DATA_DIR / "components.yaml"
    )
    return build_candidates(products, offers) + build_kit_candidates(
        inverters, inverter_offers, batteries, battery_offers
    )

    
@lru_cache(maxsize=1)
def load_display_index() -> DisplayIndex:
    """Display-индекс по обоим источникам каталога. Строится один раз."""
    products, offers = load_catalog(DATA_DIR / "products.yaml")
    inverters, inverter_offers, batteries, battery_offers = load_components(
        DATA_DIR / "components.yaml"
    )
    return build_display_index(
        products,
        offers,
        inverters,
        inverter_offers,
        batteries,
        battery_offers,
        load_sources(DATA_DIR / "sources.yaml"),
    )