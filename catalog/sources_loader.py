"""Загрузчик data/sources.yaml: домен продавца → человекочитаемое имя.

Отдельный источник правды для seller_label (ADR-038). Не путать
CatalogOffer.source/ComponentOffer.source (технический домен, остаётся
как есть) с этим словарём (только отображение).
"""

from pathlib import Path

import yaml

from core.errors import DomainError


class UnknownSourceDomainError(DomainError):
    """Оффер ссылается на домен, которого нет в data/sources.yaml.

    Умышленно фатально (ADR-038): молчаливый fallback на сырой домен
    маскирует пропуск в данных так же, как пустой url (ошибка №4).
    """


def load_sources(path: Path) -> dict[str, str]:
    """Читает data/sources.yaml, возвращает {domain: seller_label}."""
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise UnknownSourceDomainError(f"{path}: ожидался словарь domain -> label")
    return {str(k): str(v) for k, v in raw.items()}


def seller_label_for(domain: str, sources: dict[str, str]) -> str:
    """Возвращает seller_label или падает, если домена нет в справочнике."""
    label = sources.get(domain)
    if label is None:
        raise UnknownSourceDomainError(
            f"домен '{domain}' отсутствует в data/sources.yaml"
        )
    return label