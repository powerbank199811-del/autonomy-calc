"""Каталог приборов для UI: имя и категория поверх core.ApplianceSpec.

core ничего не знает про названия и категории (ядро без текстов для
пользователя). Этот модуль — тонкая обвязка над core.appliances и
принадлежит слою каталога: зависимость идёт core <- reference,
никогда наоборот.
"""

from dataclasses import dataclass

from core.appliances import ApplianceSpec


@dataclass(frozen=True, slots=True)
class CatalogAppliance:
    """Прибор в UI-справочнике: отображаемые данные + доменная спецификация."""

    code: str
    name_uk: str
    category: str
    spec: ApplianceSpec
