"""Продукт каталога: бренд+модель+физика, без цены и продавца.

Разделение products/offers — обязательное решение проекта (см. план):
удаление одного продавца не должно трогать физическую спецификацию товара,
и один товар может иметь несколько офферов (когда появятся другие источники).
"""

from dataclasses import dataclass

from core.solution import SolutionSpec


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
