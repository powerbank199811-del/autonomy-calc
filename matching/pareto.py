"""Граница Парето внутри одного типа решения (ADR-041).

Отбирает «остальные варианты», показываемые при раскрытии карточки типа.
Лицо типа передаётся отдельным параметром и не входит в отбираемый
список — его определяет _cost_key в engine.py (ADR-018/029/040), Парето
не может его вытолкнуть. Лицо ТАКЖЕ участвует как доминатор: иначе среди
альтернатив мог бы остаться вариант, строго худший, чем уже показанное
лицо.

Оси — сырая цена в гривнах и autonomy_hours (core/fit.py::SolutionFit).
Это НЕ метрика _cost_key и не конкурирует с ней: _cost_key решает
«что лучше» (в т.ч. по LCOE, ADR-029), Парето решает «между чем есть
осмысленный выбор» — вопрос, который _cost_key не задаёт.
"""

from collections.abc import Sequence

from core.economics import OwnershipCost
from core.fit import SolutionFit
from matching.candidate import Candidate

#: Дублирует форму _SortKey из engine.py намеренно: импорт создал бы
#: цикл (engine.py импортирует этот модуль), а типы должны совпадать
#: структурно, не по общему имени.
_SortKey = tuple[int, float, float]
_Row = tuple[_SortKey, Candidate, SolutionFit, OwnershipCost | None]


def _dominates(better: _Row, worse: _Row) -> bool:
    """Строгое доминирование: не хуже по обеим осям, лучше хотя бы по одной.

    Требование «хотя бы одно строго» обязательно: при полном совпадении
    цены и часов два кандидата доминировали бы друг друга взаимно,
    и оба исчезли бы из выдачи.
    """
    better_price = better[1].price_uah
    worse_price = worse[1].price_uah
    better_hours = better[2].autonomy_hours
    worse_hours = worse[2].autonomy_hours

    not_worse = better_price <= worse_price and better_hours >= worse_hours
    strictly_better = better_price < worse_price or better_hours > worse_hours
    return not_worse and strictly_better


def pareto_frontier(others: Sequence[_Row], face: _Row) -> list[_Row]:
    """Кандидаты из others, не доминируемые ни лицом типа, ни друг другом.

    face доминирует, но сам никогда не попадает в результат — его место
    в выдаче решает вызывающий код (engine.py), не эта функция.
    Порядок входа сохраняется — сортировка остаётся заботой engine.py.
    """
    frontier: list[_Row] = []
    for candidate in others:
        dominated_by_face = _dominates(face, candidate)
        dominated_by_rival = any(
            _dominates(rival, candidate) for rival in others if rival is not candidate
        )
        if not dominated_by_face and not dominated_by_rival:
            frontier.append(candidate)
    return frontier


def compress_frontier(frontier: Sequence[_Row]) -> list[_Row]:
    """Граница длиннее четырёх точек сжимается до трёх (ADR-041).

    Берутся самая дешёвая, самая долгая по автономности и одна средняя —
    ближайшая к середине ценового диапазона между ними. Середина по
    цене, а не по часам: человек мыслит «дешёвый / средний / дорогой».
    Граница из четырёх точек или меньше возвращается без изменений.
    """
    if len(frontier) <= 4:
        return list(frontier)

    cheapest = min(frontier, key=lambda row: row[1].price_uah)
    longest = max(frontier, key=lambda row: row[2].autonomy_hours)
    midpoint_price = (cheapest[1].price_uah + longest[1].price_uah) / 2.0

    remaining = [row for row in frontier if row is not cheapest and row is not longest]
    middle = min(
        remaining,
        key=lambda row: abs(row[1].price_uah - midpoint_price),
        default=None,
    )

    selected = [cheapest]
    if middle is not None:
        selected.append(middle)
    if longest is not cheapest:
        selected.append(longest)
    return selected