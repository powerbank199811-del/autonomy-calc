"""Внутренний API: контракт, обе ветки ответа, обработка ошибок запроса.

Тесты идут через реальный каталог из data/, а не через подставные кандидаты:
API — точка склейки, и её ценность именно в том, что настоящие YAML,
настоящий движок и настоящая диагностика работают вместе.
"""

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)

URL = "/api/v1/recommendations"


def test_returns_recommendations_for_realistic_load() -> None:
    response = client.post(
        URL,
        json={
            "appliances": [
                {"code": "fridge_medium"},
                {"code": "wifi_router_9v"},
            ],
            "autonomy_hours": 6,
            "grid_tariff_uah_per_kwh": 4.32,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"], "реальный каталог должен что-то предложить"
    assert body["requirement"]["total_energy_wh"] > 0


def test_rejected_is_absent_when_recommendations_found() -> None:
    """Успешный расчёт не запускает диагностику — второго прохода нет (ADR-031)."""
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "wifi_router_9v"}],
            "autonomy_hours": 4,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"]
    assert body["rejected"] is None


def test_rejected_is_filled_when_nothing_fits() -> None:
    """Пустая выдача — не пустой ответ: клиент получает причины отказа.

    Нагрузка подобрана так, чтобы упереться именно в МОЩНОСТЬ: нехватка
    энергии дала бы частичное покрытие, а это выдача, а не отказ (ADR-019).
    """
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "fridge_large_no_frost", "quantity": 100}],
            "autonomy_hours": 24,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"] == []
    assert body["rejected"], "при пустой выдаче должны быть причины"
    assert all(item["blockers"] or item["out_of_stock"] for item in body["rejected"])


def test_partial_coverage_is_still_an_answer() -> None:
    """Нагрузка, которую тянут по мощности, но не покрывают по энергии.

    Такой кандидат остаётся в выдаче с can_cover_window=False, и диагностика
    не запускается — граница между «не подходит» и «подходит хуже».
    """
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "fridge_large_no_frost", "quantity": 60}],
            "autonomy_hours": 24,
        },
    )
    body = response.json()
    assert body["recommendations"]
    assert body["rejected"] is None
    assert all(not r["fit"]["can_cover_window"] for r in body["recommendations"])


def test_commission_never_appears_in_response() -> None:
    """Комиссии нет в ответе ни на одном уровне вложенности (ADR-017)."""
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "fridge_medium"}],
            "autonomy_hours": 5,
            "grid_tariff_uah_per_kwh": 4.32,
        },
    )
    assert "commission" not in response.text


def test_unknown_appliance_code_is_client_error() -> None:
    response = client.post(
        URL,
        json={"appliances": [{"code": "nonexistent_device"}], "autonomy_hours": 4},
    )
    assert response.status_code == 422
    assert "nonexistent_device" in response.json()["detail"]


def test_empty_appliance_list_rejected() -> None:
    response = client.post(URL, json={"appliances": [], "autonomy_hours": 4})
    assert response.status_code == 422


def test_zero_tariff_rejected_by_schema() -> None:
    """Нулевой тариф отсекается на границе, не доходя до движка (ADR-029)."""
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "fridge_medium"}],
            "autonomy_hours": 4,
            "grid_tariff_uah_per_kwh": 0,
        },
    )
    assert response.status_code == 422


def test_window_beyond_policy_limit_rejected() -> None:
    response = client.post(
        URL,
        json={"appliances": [{"code": "fridge_medium"}], "autonomy_hours": 100},
    )
    assert response.status_code == 422


def test_appliances_endpoint_lists_reference() -> None:
    response = client.get("/api/v1/appliances")
    assert response.status_code == 200
    appliances = response.json()["appliances"]
    assert len(appliances) == 47
    assert {"code", "name", "category"} == set(appliances[0])


def test_kit_recommendation_exposes_two_go_targets() -> None:
    """У кита component_offer_ids — две рабочие цели /go, не одна (ADR-035, ADR-037)."""
    response = client.post(
        URL,
        json={
            "appliances": [{"code": "electric_boiler_80l_full_heat"}],
            "autonomy_hours": 6,
        },
    )
    body = response.json()
    kits = [r for r in body["recommendations"] if r["offer_id"].startswith("kit__")]
    assert kits, "ожидался хотя бы один кит для мощной нагрузки"
    kit = kits[0]
    assert kit["component_offer_ids"] is not None
    assert len(kit["component_offer_ids"]) == 2
    assert all(part in kit["offer_id"] for part in kit["component_offer_ids"])


def test_simple_product_has_no_component_offer_ids() -> None:
    """Для лёгкой нагрузки киты часто дешевле и занимают верх выдачи — берём
    полный список (limit=20), а не полагаемся на позицию в топ-5."""
    response = client.post(
        URL,
        json={"appliances": [{"code": "wifi_router_9v"}], "autonomy_hours": 4, "limit": 20},
    )
    body = response.json()
    simple = [r for r in body["recommendations"] if not r["offer_id"].startswith("kit__")]
    assert simple, "в каталоге есть готовые станции — хотя бы одна должна попасть в выдачу"
    assert simple[0]["component_offer_ids"] is None
