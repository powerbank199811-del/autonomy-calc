"""Продукт каталога: бренд+модель+физика, без цены и продавца.

Разделение products/offers — обязательное решение проекта (см. план):
удаление одного продавца не должно трогать физическую спецификацию товара,
и один товар может иметь несколько офферов (когда появятся другие источники).
"""

from dataclasses import dataclass
from enum import Enum

from core.solution import SolutionSpec


class FuelRateSource(Enum):
    """Насколько надёжен fuel_rate_l_per_kwh — не всё равнозначно.

    rated_specific    — прямое значение г/кВт·ч или л/кВт·ч из паспорта.
    derived_from_tank  — вычислено из объёма бака и предположения о нагрузке,
                          погрешность может достигать 30-40%.
    measured            — собственный замер на стенде.
    """

    RATED_SPECIFIC = "rated_specific"
    DERIVED_FROM_TANK = "derived_from_tank"
    MEASURED = "measured"


@dataclass(frozen=True, slots=True)
class CatalogProduct:
    """Товар: что это такое физически, безотносительно того, где его купить."""

    product_id: str
    name: str
    brand: str
    model: str
    category: str
    spec: SolutionSpec
    image: str | None = None
    #: Статус доверия к fuel_rate_l_per_kwh внутри spec. None — не применимо
    #: (не генератор) или статус не указан.
    fuel_rate_source: FuelRateSource | None = None
