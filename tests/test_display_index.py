"""Display-контракт ADR-038: purchases в ответе API и построение индекса.

Первые два теста идут через реальный каталог (как test_api.py) — ценность
именно в том, что настоящие YAML и настоящая сборка _purchases работают
вместе. Третий строит объекты вручную: он проверяет отказ на плохих данных,
а не то, что данные хорошие.
"""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.catalog_provider import DATA_DIR
from api.display_index import build_display_index
from catalog.offers import CatalogOffer
from catalog.products import CatalogProduct
from catalog.sources_loader import UnknownSourceDomainError, load_sources
from core.solution import SolutionKind, SolutionSpec
from core.units import WattHour

client = TestClient(app)

URL = "/api/v1/recommendations"


def test_simple_product_has_single_primary_purchase() -> None:
    """Простой товар (не кит) — одна покупка с ролью primary."""
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "wifi_router_9v"}],
            "autonomy_hours": 4,
            "limit": 20,
        },
    )
    body = response.json()
    simple = [
        r for r in body["recommendations"] if r["component_offer_ids"] is None
    ]
    assert simple, "в каталоге есть готовые станции — хотя бы одна должна попасть в выдачу"
    recommendation = simple[0]

    assert len(recommendation["purchases"]) == 1
    assert recommendation["purchases"][0]["role"] == "primary"
    assert recommendation["solar_optional"] is None


def test_kit_exposes_inverter_then_battery_in_order() -> None:
    """Роль в ките — по ПОЗИЦИИ в component_offer_ids, не парсингом строки."""
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "electric_boiler_80l_full_heat"}],
            "autonomy_hours": 6,
        },
    )
    body = response.json()
    kits = [r for r in body["recommendations"] if r["component_offer_ids"] is not None]
    assert kits, "ожидался хотя бы один кит для мощной нагрузки"
    kit = kits[0]

    assert len(kit["purchases"]) == 2
    assert kit["purchases"][0]["role"] == "inverter"
    assert kit["purchases"][1]["role"] == "battery"
    assert kit["purchases"][0]["offer_id"] == kit["component_offer_ids"][0]
    assert kit["purchases"][1]["offer_id"] == kit["component_offer_ids"][1]


def test_unknown_domain_fails_loudly() -> None:
    """Оффер ссылается на домен, которого нет в справочнике sources — падает.

    ADR-038: молчаливый fallback на сырой домен запрещён так же, как
    молчаливый fallback на пустой url.
    """
    product = CatalogProduct(
        product_id="prod_1",
        name="Тестовая станция",
        brand="TestBrand",
        model="T-1",
        category="station",
        spec=SolutionSpec(kind=SolutionKind.STATION, capacity_wh=WattHour(500)),
    )
    offer = CatalogOffer(
        offer_id="offer_1",
        product_id="prod_1",
        price_uah=10000,
        commission_rate=0.05,
        source="unknown-shop.example",
        url="https://unknown-shop.example/prod_1",
    )

    with pytest.raises(UnknownSourceDomainError):
        build_display_index(
            products=(product,),
            offers=(offer,),
            inverters=(),
            inverter_offers=(),
            batteries=(),
            battery_offers=(),
            sources={},
        )


def test_seller_label_is_human_readable_not_raw_domain() -> None:
    """seller_label — склейка с data/sources.yaml, а не сырой CatalogOffer.source.

    Простая проверка «не оканчивается на .ua/.com/.biz» ложно падает на
    реальных данных: пара продавцов (Мотоблок.biz, TI.ua) намеренно носит
    такое имя, и это законный seller_label, а не пропущенная склейка.
    Поэтому сверяемся с настоящим data/sources.yaml: seller_label обязан
    быть одним из его ЗНАЧЕНИЙ и не может совпадать ни с одним сырым
    доменом-КЛЮЧОМ. Если бы seller_label_for() молча возвращал домен
    как есть, метка совпала бы с ключом, а не со значением, и тест
    поймал бы это; на пустом sources.yaml сам /go-индекс не построится
    (test_unknown_domain_fails_loudly), так что тест не может пройти
    бесполезно.
    """
    sources = load_sources(DATA_DIR / "sources.yaml")
    raw_domains = set(sources.keys())
    human_labels = set(sources.values())

    response = client.post(
        URL,
        json={
            "appliances": [{"code": "fridge_medium"}, {"code": "wifi_router_9v"}],
            "autonomy_hours": 6,
            "limit": 20,
        },
    )
    body = response.json()
    assert body["recommendations"], "реальный каталог должен что-то предложить"

    purchases = [
        purchase
        for recommendation in body["recommendations"]
        for purchase in recommendation["purchases"]
    ]
    assert purchases, "в выдаче должна быть хотя бы одна покупка"

    for purchase in purchases:
        label = purchase["seller_label"]
        assert label, "seller_label обязателен (ADR-038)"
        assert label not in raw_domains, (
            f"seller_label '{label}' — сырой домен, склейка не произошла"
        )
        assert label in human_labels, (
            f"seller_label '{label}' не найден среди значений data/sources.yaml"
        )
