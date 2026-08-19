"""Доменные ошибки. Без текстов для пользователя — только коды и детали."""


class DomainError(Exception):
    """Базовая ошибка домена. Всё, что ловит слой API, наследуется отсюда."""


class EmptyLoadProfileError(DomainError):
    """Пустой профиль нагрузки. Ноль Вт·ч — валидное число, за которым баг."""


class InvalidApplianceSpecError(DomainError):
    """Запись справочника нарушает физические инварианты."""


class InvalidLoadItemError(DomainError):
    """Позиция нагрузки невалидна: количество, часы, переопределения."""


class InvalidAutonomyTargetError(DomainError):
    """Цель автономности вне допустимых границ."""


class InvalidSolutionSpecError(DomainError):
    """Описание решения нарушает физические инварианты."""
