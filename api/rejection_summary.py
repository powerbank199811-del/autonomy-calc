"""Перевод машинной диагностики отказов в одну человеческую фразу.

RejectionReason содержит offer_id и FitBlocker — это контракт matching/,
он не обязан знать украинский. Перевод — работа api/, как и seller_label.

Список из тридцати отказов человеку не нужен: он не выбирает между ними,
он хочет знать, что именно у него не влезло. Поэтому агрегат, не перечень.
"""

from dataclasses import dataclass
from typing import Sequence

from api.schemas import RejectionOut

#: Ключ — FitBlocker.value. Значение брать по .value, а не по объекту:
#: так модуль не зависит от состава перечисления и не падает, когда
#: в core/fit.py появится новый блокер.
_BLOCKER_TEXT: dict[str, str] = {
    "insufficient_continuous_power": (
        "не витримують постійну потужність ваших приладів"
    ),
    "insufficient_peak_power": "не витримують пусковий струм",
    "insufficient_energy": "не мають запасу енергії на це вікно",
    "waveform_mismatch": "дають модифікований синус, а вашим приладам потрібен чистий",
}
_BLOCKER_FALLBACK = "не підходять за технічними обмеженнями"


@dataclass(frozen=True, slots=True)
class RejectionSummary:
    """Готовые строки для шаблона. Шаблон не считает и не переводит."""

    total: int
    out_of_stock: int
    reasons: tuple[str, ...]


def summarize_rejections(rejections: Sequence[RejectionOut]) -> RejectionSummary:
    """Отказы -> агрегат. Один блокер = одна строка, независимо от числа офферов."""
    seen: list[str] = []
    out_of_stock = 0
    for rejection in rejections:
        if rejection.out_of_stock:
            out_of_stock += 1
        for blocker in rejection.blockers:
            key = getattr(blocker, "value", str(blocker))
            text = _BLOCKER_TEXT.get(key, _BLOCKER_FALLBACK)
            if text not in seen:
                seen.append(text)
    return RejectionSummary(
        total=len(rejections),
        out_of_stock=out_of_stock,
        reasons=tuple(seen),
    )