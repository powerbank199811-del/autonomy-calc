"""Строит Candidate для всех физически совместимых пар инвертор+АКБ.

Один Candidate = одна пара конкретных офферов. Это фактически ДВЕ отдельные
продажи (инвертор у одного продавца, АКБ у другого), поэтому commission_rate
не берётся напрямую с одного из компонентов — считается средневзвешенным
по цене: это и есть реальная суммарная выручка как доля от общей цены пары.
"""

from catalog.components import CatalogBattery, CatalogInverter, ComponentOffer
from catalog.kits import assemble_solution, is_voltage_compatible
from matching.candidate import Candidate


def build_kit_candidates(
    inverters: tuple[CatalogInverter, ...],
    inverter_offers: tuple[ComponentOffer, ...],
    batteries: tuple[CatalogBattery, ...],
    battery_offers: tuple[ComponentOffer, ...],
) -> tuple[Candidate, ...]:
    """Перебирает все пары (инвертор-оффер x АКБ-оффер), фильтрует по
    совместимости напряжения, для совместимых — собирает Candidate."""
    inverters_by_id = {c.component_id: c for c in inverters}
    batteries_by_id = {c.component_id: c for c in batteries}

    candidates: list[Candidate] = []
    for inv_offer in inverter_offers:
        inverter = inverters_by_id.get(inv_offer.component_id)
        if inverter is None:
            continue
        for bat_offer in battery_offers:
            battery = batteries_by_id.get(bat_offer.component_id)
            if battery is None:
                continue
            if not is_voltage_compatible(inverter.spec, battery.spec):
                continue

            total_price = inv_offer.price_uah + bat_offer.price_uah
            combined_commission = (
                inv_offer.price_uah * inv_offer.commission_rate
                + bat_offer.price_uah * bat_offer.commission_rate
            ) / total_price

            candidates.append(
                Candidate(
                    offer_id=f"kit__{inv_offer.offer_id}__{bat_offer.offer_id}",
                    solution=assemble_solution(inverter.spec, battery.spec),
                    price_uah=total_price,
                    commission_rate=combined_commission,
                    in_stock=inv_offer.in_stock and bat_offer.in_stock,
                    component_offer_ids=(inv_offer.offer_id, bat_offer.offer_id),
                )
            )
    return tuple(candidates)
