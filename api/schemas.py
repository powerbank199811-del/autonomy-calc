"""Контракт внутреннего API. Единственное место, где домен встречается с HTTP.

Доменные enum'ы (FitBlocker, FitFlag) используются напрямую, а не дублируются
строковыми константами: pydantic сериализует их по .value, и единственным
источником правды остаётся core. Дублирование списка блокеров здесь означало
бы, что при добавлении нового блокера в ядро API молча отдавал бы старый набор.

commission_rate тут отсутствует не потому, что его выкинули при сборке ответа,
а потому что его нет в Recommendation (ADR-017) — собрать его тут физически
не из чего.
"""

from enum import Enum

from pydantic import BaseModel, Field

from catalog.products import CapacitySource
from core.fit import FitBlocker, FitFlag


class ApplianceSelection(BaseModel):
    """Один выбранный прибор: код из справочника, количество, часы работы."""

    code: str
    quantity: int = Field(default=1, ge=1)
    hours: float | None = Field(default=None, ge=0)


class RecommendationRequest(BaseModel):
    """Вход расчёта. Тариф опционален: без него экономика не считается (ADR-009)."""

    appliances: list[ApplianceSelection] = Field(min_length=1)
    autonomy_hours: float = Field(gt=0, le=72)
    grid_tariff_uah_per_kwh: float | None = Field(default=None, gt=0)
    fuel_price_uah_per_l: float | None = Field(default=None, gt=0)
    limit: int = Field(default=5, ge=1, le=20)


class RequirementOut(BaseModel):
    """Сколько энергии и мощности нужно — до подбора решений."""

    energy_ac_wh: float
    energy_dc_wh: float
    total_energy_wh: float
    continuous_power_ac_w: float
    startup_power_w: float
    window_hours: float


class FitOut(BaseModel):
    """Как решение справляется с этой потребностью."""

    can_cover_window: bool
    autonomy_hours: float
    usable_energy_wh: float
    energy_margin: float
    power_margin: float
    flags: list[FitFlag]


class OwnershipOut(BaseModel):
    """Экономика владения. None в ответе = не хватило данных, а не ноль."""

    cost_per_kwh_uah: float
    lifetime_energy_kwh: float
    fuel_opex_per_kwh_uah: float
    cheaper_than_grid: bool
    payback_energy_kwh: float | None


class ComponentRole(str, Enum):
    """Роль offer_id внутри purchases (ADR-038).

    PRIMARY  — простой товар, единственная покупка.
    INVERTER — кит, элемент 0 component_offer_ids.
    BATTERY  — кит, элемент 1 component_offer_ids.
    """

    PRIMARY = "primary"
    INVERTER = "inverter"
    BATTERY = "battery"


class PurchaseOut(BaseModel):
    """Одна покупка внутри рекомендации: то, что реально уходит в карточку.

    image_url = None допустим и не является ошибкой (ADR-038): шаблон
    рисует плейсхолдер. seller_label, напротив, обязателен — отсутствие
    домена в sources.yaml падает раньше, на загрузке.
    """

    offer_id: str
    role: ComponentRole
    name: str
    brand: str
    image_url: str | None
    seller_label: str
    price_uah: float


class RecommendationOut(BaseModel):
    """Карточка рекомендации.

    component_offer_ids: None — один переход, ведёт по offer_id. Не None —
    составной продукт (кит): список offer_id, по каждому свой /go/{id},
    своя страница продавца, своя покупка (ADR-035, ADR-037).
    """

    offer_id: str
    rank_position: int
    price_uah: float
    fit: FitOut
    ownership: OwnershipOut | None
    component_offer_ids: list[str] | None = None
    #: len==1 простой товар, len==2 кит — инвариант, не Optional (ADR-038).
    purchases: tuple[PurchaseOut, ...] = ()
    #: None — ёмкости нет (генератор).
    capacity_source: CapacitySource | None = None
    #: True только у кита с гибридным инвертором: панели можно подключить,
    #: но они НЕ обязательны.
    solar_optional: bool | None = None


class RejectionOut(BaseModel):
    """Почему кандидат не попал в выдачу. Обе причины независимы (ADR-030)."""

    offer_id: str
    out_of_stock: bool
    blockers: list[FitBlocker]


class RecommendationResponse(BaseModel):
    """Ответ расчёта.

    rejected заполняется ТОЛЬКО когда recommendations пуст (ADR-031): при
    непустой выдаче диагностика клиенту не нужна, а второй проход по каталогу
    не бесплатен. None и [] тут значат разное: None — диагностика не
    запускалась, [] — запускалась и не нашла ни одного отклонённого.
    """

    requirement: RequirementOut
    recommendations: list[RecommendationOut]
    rejected: list[RejectionOut] | None = None
