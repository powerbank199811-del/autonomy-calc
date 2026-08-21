"""Диагностика: почему конкретный кандидат не попал в рекомендации.

Отдельная функция, а не расширение select_recommendations (ADR-030).
Экономика (LCOE, окупаемость) сюда не передаётся: она никогда не блокирует
кандидата, только сортирует прошедших (ADR-018), поэтому объяснению отказа
она не нужна.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from core.fit import FitBlocker, evaluate_fit
from core.policy import DEFAULT_POLICY, CalculationPolicy
from core.requirement import EnergyRequirement
from matching.candidate import Candidate


@dataclass(frozen=True, slots=True)
class RejectionReason:
    """Почему один кандидат не попал в select_recommendations.

    out_of_stock и blockers независимы: даже при отсутствии на складе
    физическая пригодность проверяется и возвращается — это два разных
    сообщения для клиента, и одно не должно маскировать другое.
    """

    offer_id: str
    out_of_stock: bool
    blockers: tuple[FitBlocker, ...]


def explain_rejections(
    requirement: EnergyRequirement,
    candidates: Sequence[Candidate],
    policy: CalculationPolicy = DEFAULT_POLICY,
) -> tuple[RejectionReason, ...]:
    """Возвращает причину отказа для каждого кандидата, не прошедшего фильтр.

    Кандидат считается отказанным, если select_recommendations не включил бы
    его в выдачу: нет на складе ИЛИ не прошёл evaluate_fit.can_run. Частичное
    покрытие окна (can_run=True, can_cover_window=False) — не отказ, такой
    кандидат в основной выдаче, просто ниже по рангу; сюда он не попадает.

    Порядок совпадает с порядком входного candidates — функция не ранжирует.
    """
    reasons: list[RejectionReason] = []
    for candidate in candidates:
        fit = evaluate_fit(requirement, candidate.solution, policy)
        if candidate.in_stock and fit.can_run:
            continue
        reasons.append(
            RejectionReason(
                offer_id=candidate.offer_id,
                out_of_stock=not candidate.in_stock,
                blockers=fit.blockers,
            )
        )
    return tuple(reasons)
