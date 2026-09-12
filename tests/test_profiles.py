"""Критерий достаточности каталога: для каждого профиля — все физически
возможные типы решений присутствуют в выдаче (не количество товаров —
ошибка №5, а сам факт наличия типа).

Список ожидаемых типов свой для каждого профиля, не все четыре везде:
POWERBANK не может нести AC-нагрузку с пусковым током и чистым синусом
(холодильник, котёл) — требовать его там означало бы требовать
невозможного по физике, а не проверять дыру каталога.

ЭТОТ ТЕСТ КРАСНЫЙ СРАЗУ на 3 из 4 профилей. Не подгонять под текущее
состояние, не skip, не xfail (см. обсуждение в STATUS.md этой сессии) —
падение должно быть видно в обычном прогоне.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)
URL = "/api/v1/recommendations"

#: limit=20, не дефолт — тест про достаточность каталога, не про
#: ранжирование (то же решение, что в snapshot.py и в соседних тестах
#: api/, например test_simple_product_has_no_component_offer_ids).
LIMIT = 20


def _kinds_present(recommendations: list[dict[str, object]]) -> set[str]:
    """Тип решения по данным ответа API.

    component_offer_ids не None -> кит -> INVERTER_BATTERY (отдельного
    SolutionKind.KIT нет, кит собирается на лету из инвертора+АКБ).
    Иначе — по префиксу offer_id: RecommendationOut не хранит SolutionKind
    напрямую (ADR-038, display-контракт не расширяет домен), префикс —
    единственный доступный признак на уровне api/. Тот же приём, что
    в scripts/snapshot.py. Незнакомый префикс — падение теста, не тихий
    пропуск: если появится новый тип товара без префикса в этом списке,
    тест должен об этом сказать явно.
    """
    kinds: set[str] = set()
    for item in recommendations:
        if item["component_offer_ids"]:
            kinds.add("INVERTER_BATTERY")
            continue
        offer_id = str(item["offer_id"])
        if offer_id.startswith("generator_"):
            kinds.add("GENERATOR")
        elif offer_id.startswith("station_"):
            kinds.add("STATION")
        elif offer_id.startswith("powerbank_"):
            kinds.add("POWERBANK")
        else:
            raise AssertionError(f"неизвестный префикс offer_id: {offer_id!r}")
    return kinds


PROFILES = [
    pytest.param(
        [{"code": "fridge_medium"}],
        4,
        {"STATION", "INVERTER_BATTERY", "GENERATOR"},
        id="fridge_4h",
    ),
    pytest.param(
        [
            {"code": "gas_boiler"},
            {"code": "led_bulb_9w"},
            {"code": "wifi_router_9v"},
        ],
        8,
        {"STATION", "INVERTER_BATTERY", "GENERATOR"},
        id="boiler_light_router_8h",
    ),
    pytest.param(
        [
            {"code": "wifi_router_9v"},
            {"code": "laptop_usb_c_pd_65w"},
        ],
        4,
        {"POWERBANK", "STATION"},
        id="router_laptop_dc_4h",
    ),
    pytest.param(
        [{"code": "fridge_medium"}, {"code": "gas_boiler"}],
        4,
        {"STATION", "INVERTER_BATTERY", "GENERATOR"},
        id="fridge_boiler_4h",
    ),
]


@pytest.mark.parametrize("appliances, hours, expected_kinds", PROFILES)
def test_catalog_covers_every_solvable_kind(
    appliances: list[dict[str, object]], hours: float, expected_kinds: set[str]
) -> None:
    response = client.post(
        URL,
        json={"appliances": appliances, "autonomy_hours": hours, "limit": LIMIT},
    )
    body = response.json()
    present = _kinds_present(body["recommendations"])
    missing = expected_kinds - present
    assert not missing, (
        f"дыра каталога: не хватает типов {sorted(missing)}; "
        f"в выдаче есть только {sorted(present)}"
    )