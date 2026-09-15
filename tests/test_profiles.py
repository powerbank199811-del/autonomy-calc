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

Второй класс тестов ниже — property-тест на ранжирование (диагностика
дефекта ранжирования, сессия STATUS от этой даты): для каждого профиля
самое дешёвое покрывающее окно решение обязано присутствовать в выдаче
ПРИ ДЕФОЛТНОМ limit (api/schemas.py: default=5) — том же значении, что
получает пользователь без явного параметра. limit=20 здесь не годится:
при 20 в выдачу попадают все 15 покрывающих кандидатов сразу, и тест
становится тавтологией, ничего не проверяющей (первая версия этого
теста молчала именно по этой причине — исправлено). Без порогов и без
чисел из головы (ADR-041 отверг порог 75% именно потому, что 75% не из
чего вывести — здесь порог не придуман, а взят из уже существующего
дефолта схемы).

ЭТОТ ТЕСТ БУДЕТ КРАСНЫМ на профиле pc_monitor_router_lamp_8h — это его
работа (matching/engine.py:_cost_key не сравнивает абсолютную цену между
кандидатами с ownership и без). Не подгонять, не skip, не ослаблять —
починка в сессии "Реализация ранжирования" (ADR-041 её не покрывает,
ADR-041 работает над карточками внутри уже показанного типа, а не над
выбором типа по умолчанию).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import _build_profile, app
from api.catalog_provider import load_all_candidates
from api.schemas import RecommendationRequest
from core.demand import calculate_requirement
from core.economics import OwnershipCost
from core.fit import SolutionFit, evaluate_fit
from core.load import AutonomyTarget
from core.policy import DEFAULT_POLICY
from core.units import Hours
from matching.candidate import Candidate

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
        json={"appliances": appliances, "autonomy_hours": hours, "limit_per_kind": LIMIT},
    )
    body = response.json()
    present = _kinds_present(body["recommendations"])
    missing = expected_kinds - present
    assert not missing, (
        f"дыра каталога: не хватает типов {sorted(missing)}; "
        f"в выдаче есть только {sorted(present)}"
    )


def _cheapest_covering_offer_id(
    appliances: list[dict[str, object]], hours: float, tariff: float | None
) -> str | None:
    """Самое дешёвое решение, покрывающее окно — независимо от _cost_key.

    Тот же фильтр, что matching/engine.py делает до сортировки: in_stock,
    can_run, can_cover_window. Дальше — минимум по абсолютной цене, без
    dimension и без LCOE (не зависит от tariff по построению — tariff
    здесь только для сборки RecommendationRequest/профиля, тем же путём,
    что и в snapshot.py). None — каталог пуст для профиля, это дыра
    каталога (покрыта test_catalog_covers_every_solvable_kind), не предмет
    этого теста.
    """
    payload: dict[str, object] = {
        "appliances": appliances,
        "autonomy_hours": hours,
        "limit_per_kind": LIMIT,
    }
    if tariff is not None:
        payload["grid_tariff_uah_per_kwh"] = tariff
    request = RecommendationRequest.model_validate(payload)
    profile = _build_profile(request)
    requirement = calculate_requirement(
        profile, AutonomyTarget(window_hours=Hours(hours))
    )

    best: tuple[Candidate, SolutionFit] | None = None
    for candidate in load_all_candidates():
        if not candidate.in_stock:
            continue
        fit = evaluate_fit(requirement, candidate.solution, DEFAULT_POLICY)
        if not fit.can_run or not fit.can_cover_window:
            continue
        if best is None or candidate.price_uah < best[0].price_uah:
            best = (candidate, fit)

    if best is None:
        return None
    return best[0].offer_id


RANKING_PROFILES = [
    *[
        pytest.param(param.values[0], param.values[1], None, id=f"{param.id}__ranking")
        for param in PROFILES
    ],
    pytest.param(
        [
            {"code": "desktop_pc_office"},
            {"code": "monitor_24"},
            {"code": "wifi_router_9v"},
            {"code": "led_bulb_9w"},
        ],
        8,
        4.32,
        id="pc_monitor_router_lamp_8h__ranking",
    ),
]


@pytest.mark.parametrize("appliances, hours, tariff", RANKING_PROFILES)
def test_cheapest_covering_solution_is_shown(
    appliances: list[dict[str, object]], hours: float, tariff: float | None
) -> None:
    """Самое дешёвое покрывающее решение обязано быть в выдаче ПРИ ДЕФОЛТНОМ
    limit (api/schemas.py: default=5) — том, что видит пользователь без
    явного параметра.

    Поиск самого дешёвого ведётся без ограничения (см. _cheapest_covering_offer_id),
    а проверка присутствия — в ответе API БЕЗ переданного limit, то есть
    под дефолтом схемы. limit=20 для этой проверки не подходит: он вмещает
    весь набор покрывающих кандидатов профиля pc_monitor_router_lamp_8h
    (15 из 15, см. диагностику этой сессии) и тест был бы тавтологией.
    """
    cheapest_offer_id = _cheapest_covering_offer_id(appliances, hours, tariff)
    if cheapest_offer_id is None:
        pytest.skip("каталог не покрывает профиль — дыра каталога, не предмет этого теста")

    payload: dict[str, object] = {"appliances": appliances, "autonomy_hours": hours}
    if tariff is not None:
        payload["grid_tariff_uah_per_kwh"] = tariff
    response = client.post(URL, json=payload)
    body = response.json()
    shown_offer_ids = {item["offer_id"] for item in body["recommendations"]}

    assert cheapest_offer_id in shown_offer_ids, (
        f"самое дешёвое покрывающее решение ({cheapest_offer_id}) "
        f"не попало в выдачу (дефолтный limit); показаны: {sorted(shown_offer_ids)}"
    )