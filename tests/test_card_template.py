"""Шаблон карточки: инварианты разметки и контракта, не внешний вид.

Что тут НЕ проверяется намеренно: ширина, отступы, цвета. Тест вёрстки
на 380px — это глаз в браузере, автоматизировать его нечем и незачем.
Проверяется то, что ломается молча: число кнопок, адрес перехода,
schema.org-разметка, поведение при image_url = None и полнота словарей
подписей относительно доменных enum'ов.

in_stock тут не фигурирует и фигурировать не может: недоступный кандидат
отсеян в matching/engine.py до ранжирования (ADR-019), до шаблона он не
доезжает. Поэтому availability=InStock в разметке безусловен и не лжёт.
"""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.schemas import (
    ComponentRole,
    FitOut,
    OwnershipOut,
    PurchaseOut,
    RecommendationOut,
)
from api.templating import (
    CAPACITY_SOURCE_LABELS,
    FIT_FLAG_LABELS,
    format_uah_per_kwh,
    render_card,
)
from catalog.products import CapacitySource
from core.fit import FitFlag

client = TestClient(app)


def _fit(can_cover: bool = True) -> FitOut:
    return FitOut(
        can_cover_window=can_cover,
        autonomy_hours=6.2,
        usable_energy_wh=900.0,
        energy_margin=0.24,
        power_margin=0.40,
        flags=[],
    )


def _purchase(
    offer_id: str = "offer_a",
    role: ComponentRole = ComponentRole.PRIMARY,
    image_url: str | None = None,
) -> PurchaseOut:
    return PurchaseOut(
        offer_id=offer_id,
        role=role,
        name="Тестова станція 600",
        brand="Ecoflow",
        image_url=image_url,
        seller_label="MOYO",
        price_uah=12499.0,
    )


def _simple(**kwargs: object) -> RecommendationOut:
    defaults: dict[str, object] = {
        "offer_id": "offer_a",
        "rank_position": 1,
        "price_uah": 12499.0,
        "fit": _fit(),
        "ownership": None,
        "purchases": (_purchase(),),
    }
    defaults.update(kwargs)
    return RecommendationOut(**defaults)  # type: ignore[arg-type]


def _kit() -> RecommendationOut:
    return RecommendationOut(
        offer_id="kit__inv_1__bat_1",
        rank_position=2,
        price_uah=31000.0,
        fit=_fit(),
        ownership=None,
        component_offer_ids=["inv_1", "bat_1"],
        purchases=(
            _purchase("inv_1", ComponentRole.INVERTER),
            _purchase("bat_1", ComponentRole.BATTERY),
        ),
    )


def test_simple_product_has_exactly_one_buy_link() -> None:
    """Один товар — одна кнопка, ведущая на /go/{offer_id}."""
    html = render_card(_simple())
    assert html.count('class="ac-btn"') == 1
    assert 'href="/go/offer_a' in html


def test_kit_has_two_buy_links_in_component_order() -> None:
    """Кит — две покупки, порядок инвертор→АКБ по позиции (ADR-037/038)."""
    html = render_card(_kit())
    assert html.count('class="ac-btn"') == 2
    assert html.index("/go/inv_1") < html.index("/go/bat_1")
    assert "Інвертор" in html and "Акумулятор" in html


def test_kit_is_item_list_not_single_product() -> None:
    """У кита нет одной страницы продавца (ADR-035) — Product на каждый товар."""
    html = render_card(_kit())
    assert "schema.org/ItemList" in html
    assert html.count("schema.org/Product") == 2
    assert html.count("schema.org/Offer") == 2


def test_missing_image_renders_placeholder_not_broken_img() -> None:
    """image_url = None — не ошибка (ADR-038): плейсхолдер вместо <img>."""
    html = render_card(_simple())
    assert "<img" not in html
    assert 'class="ac-card__thumb"' in html
    assert "EC" in html  # инициалы бренда вместо пустого квадрата


def test_present_image_is_marked_up_and_has_alt() -> None:
    html = render_card(_simple(purchases=(_purchase(image_url="/img/x.webp"),)))
    assert 'itemprop="image"' in html
    assert 'alt="Тестова станція 600"' in html


def test_offer_markup_carries_price_currency_and_availability() -> None:
    """Разметка Offer восстанавливается вместо той, что уйдёт со старым сайтом."""
    html = render_card(_simple())
    assert 'itemprop="priceCurrency" content="UAH"' in html
    assert 'itemprop="price" content="12499"' in html
    assert 'href="https://schema.org/InStock"' in html


def test_affiliate_link_is_not_followed() -> None:
    """Партнёрская ссылка не передаёт вес и помечена как sponsored."""
    html = render_card(_simple())
    assert 'rel="nofollow sponsored noopener"' in html


def test_solar_note_shown_only_when_solar_optional_is_true() -> None:
    """Массовое заблуждение зимней аудитории — текст обязателен, но только там,
    где он правдив: solar_optional False/None означает не гибридный кит."""
    assert "Сонячні панелі не обов'язкові" in render_card(_simple(solar_optional=True))
    assert "Сонячні панелі" not in render_card(_simple(solar_optional=False))
    assert "Сонячні панелі" not in render_card(_simple())


def test_capacity_source_note_shown_only_when_known() -> None:
    html = render_card(_simple(capacity_source=CapacitySource.MEASURED))
    assert CAPACITY_SOURCE_LABELS[CapacitySource.MEASURED] in html
    assert "Ємність" not in render_card(_simple())


def test_cost_per_kwh_keeps_kopecks() -> None:
    """7,80 ₴/кВт·год, округлённые до 8 ₴, убивают саму метрику."""
    ownership = OwnershipOut(
        cost_per_kwh_uah=7.8,
        lifetime_energy_kwh=1200.0,
        fuel_opex_per_kwh_uah=0.0,
        cheaper_than_grid=False,
        payback_energy_kwh=None,
    )
    html = render_card(_simple(ownership=ownership))
    assert format_uah_per_kwh(7.8) in html
    assert "7,80" in html


def test_short_autonomy_is_stated_not_hidden() -> None:
    """Решение, не закрывающее окно, в выдаче остаётся — но помечено честно."""
    html = render_card(_simple(fit=_fit(can_cover=False)))
    assert "менше, ніж ви просили" in html


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (6.2, "6,2 години"),
        (14.0, "14 годин"),
        (21.0, "21 година"),
        (22.0, "22 години"),
    ],
)
def test_hours_are_spelled_out_not_abbreviated(value: float, expected: str) -> None:
    """Скорочення "год" читається як "рік" російськомовним відвідувачем."""
    from api.templating import format_hours

    assert format_hours(value).replace("\u00a0", " ") == expected


@pytest.mark.parametrize("flag", list(FitFlag))
def test_every_fit_flag_has_a_label(flag: FitFlag) -> None:
    """Новый флаг в ядре обязан получить украинскую подпись здесь.

    Тест существует, чтобы это выяснилось в CI, а не на живой карточке:
    flag_label падает KeyError, молчаливого fallback нет (тот же принцип,
    что у неизвестного домена в sources.yaml).
    """
    assert flag in FIT_FLAG_LABELS


@pytest.mark.parametrize("source", list(CapacitySource))
def test_every_capacity_source_has_a_label(source: CapacitySource) -> None:
    assert source in CAPACITY_SOURCE_LABELS


def test_real_recommendations_render_without_undefined_errors() -> None:
    """Реальные данные через реальный API: StrictUndefined ловит опечатки в полях.

    Смысл именно в сквозном прогоне: ручные объекты выше не докажут, что
    _purchases в app.py заполняет то, что шаблон читает.
    """
    response = client.post(
        "/api/v1/recommendations",
        json={
            "appliances": [{"code": "fridge_medium", "hours": 4}],
            "autonomy_hours": 4,
            "grid_tariff_uah_per_kwh": 4.32,
            "limit": 5,
        },
    )
    assert response.status_code == 200
    recommendations = response.json()["recommendations"]
    assert recommendations, "каталог не дал ни одной рекомендации — проверять нечего"
    for item in recommendations:
        html = render_card(RecommendationOut.model_validate(item))
        assert "/go/" in html


def test_payback_not_promised_when_unreachable() -> None:
    """Окупаемость дальше ресурса — это "не окупится никогда", не цель.

    payback_energy_kwh 4228 при lifetime 2937 (реальные числа каталога на
    28.08.2026) означает, что решение выработает ресурс раньше, чем отобьёт
    цену. Обещать окупаемость в этом случае — обман, ADR-012 разводит эти
    два числа именно затем, чтобы их можно было сравнить.
    """
    unreachable = OwnershipOut(
        cost_per_kwh_uah=6.22,
        lifetime_energy_kwh=2937.0,
        fuel_opex_per_kwh_uah=0.0,
        cheaper_than_grid=False,
        payback_energy_kwh=4228.0,
    )
    html = render_card(_simple(ownership=unreachable))
    assert "не окупиться" in html
    assert "Проти мережі окупиться" not in html


def test_payback_shown_when_within_lifetime() -> None:
    reachable = OwnershipOut(
        cost_per_kwh_uah=2.10,
        lifetime_energy_kwh=5000.0,
        fuel_opex_per_kwh_uah=0.0,
        cheaper_than_grid=True,
        payback_energy_kwh=1200.0,
    )
    html = render_card(_simple(ownership=reachable))
    assert "Проти мережі окупиться" in html
    assert "не окупиться" not in html


def test_kit_explains_why_two_purchases() -> None:
    """Без объяснения кит выглядит как ошибка выдачи: две кнопки без причины."""
    html = render_card(_kit())
    assert "Інвертор + акумулятор" in html
    assert "Поодинці жоден із них не працює" in html
    assert html.index("Інвертор + акумулятор") < html.index("годин")


def test_disclosures_are_below_the_answer() -> None:
    """Оговорки расчёта идут после цены и кнопок, а не липнут к названию."""
    html = render_card(
        _simple(capacity_source=CapacitySource.RATED, fit=_fit()),
    )
    assert html.index("ac-btn") < html.index("Як ми це порахували")
