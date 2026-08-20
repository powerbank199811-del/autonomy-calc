"""Сборка инвертор+АКБ 'на лету': совместимость по напряжению и синтез."""

import pytest

from core.appliances import ApplianceSpec
from core.demand import calculate_requirement
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.solution import SolutionKind, StorageChemistry, Waveform
from core.units import Hours, VoltAmpere, Volt, Watt, WattHour
from catalog.components import (
    BatterySpec,
    CatalogBattery,
    CatalogInverter,
    ComponentOffer,
    InverterSpec,
    InvalidComponentSpecError,
)
from catalog.kit_candidates import build_kit_candidates
from catalog.kits import assemble_solution, is_voltage_compatible
from matching.engine import select_recommendations


def _deye_48v() -> InverterSpec:
    """Deye SUN-5K: 48V система, 5000 Вт непрерывно."""
    return InverterSpec(
        system_voltage_v=Volt(48.0),
        continuous_power_w=Watt(5000),
        peak_power_w=Watt(10000),
        inverter_efficiency=0.95,
        waveform=Waveform.PURE_SINE,
    )


def _logicpower_battery_48v() -> BatterySpec:
    """LogicPower 16S LiFePO4: маркетинг пишет '48V', реально 51.2V."""
    return BatterySpec(
        system_voltage_v=Volt(51.2),
        chemistry=StorageChemistry.LIFEPO4,
        capacity_wh=WattHour(5120),
        cycle_life=6000,
    )


def _battery_12v() -> BatterySpec:
    """АКБ на 12V-класс (LiFePO4 4S, реально 12.8V) — другой класс системы."""
    return BatterySpec(
        system_voltage_v=Volt(12.8),
        chemistry=StorageChemistry.LIFEPO4,
        capacity_wh=WattHour(1280),
        cycle_life=6000,
    )


def test_marketing_rounded_voltage_is_compatible() -> None:
    """'48V' инвертор + '48V' АКБ (реально 51.2V) — совместимы по классу."""
    assert is_voltage_compatible(_deye_48v(), _logicpower_battery_48v()) is True


def test_different_voltage_class_is_incompatible() -> None:
    """48V инвертор и 12V АКБ физически не соединяются — исключаем."""
    assert is_voltage_compatible(_deye_48v(), _battery_12v()) is False


def test_unclassifiable_voltage_is_incompatible() -> None:
    """Странное напряжение (не 12/24/48) не относится ни к одному классу."""
    weird = InverterSpec(
        system_voltage_v=Volt(36.0), continuous_power_w=Watt(1000), peak_power_w=Watt(2000)
    )
    assert is_voltage_compatible(weird, _logicpower_battery_48v()) is False


def test_assembled_solution_has_battery_energy_and_inverter_power() -> None:
    """Синтез берёт ёмкость от АКБ, мощность от инвертора — не путает местами."""
    solution = assemble_solution(_deye_48v(), _logicpower_battery_48v())
    assert solution.kind is SolutionKind.INVERTER_BATTERY
    assert solution.capacity_wh == 5120.0
    assert solution.continuous_power_w == 5000.0
    assert solution.chemistry is StorageChemistry.LIFEPO4


def test_incompatible_inverter_rejected_by_core() -> None:
    """Инвертор с peak < continuous не пройдёт даже до сборки — падает раньше."""
    with pytest.raises(InvalidComponentSpecError):
        InverterSpec(
            system_voltage_v=Volt(48.0), continuous_power_w=Watt(5000), peak_power_w=Watt(1000)
        )


def test_build_kit_candidates_only_compatible_pairs() -> None:
    """Из 2 инверторов x 2 АКБ (разные классы) — только совместимые пары."""
    inv_48 = CatalogInverter(
        component_id="inv48", name="Deye 48V", brand="Deye", model="X", spec=_deye_48v()
    )
    inv_12 = CatalogInverter(
        component_id="inv12",
        name="Small 12V",
        brand="X",
        model="Y",
        spec=InverterSpec(
            system_voltage_v=Volt(12.8), continuous_power_w=Watt(300), peak_power_w=Watt(600)
        ),
    )
    bat_48 = CatalogBattery(
        component_id="bat48", name="LP 48V", brand="LP", model="X", spec=_logicpower_battery_48v()
    )
    bat_12 = CatalogBattery(
        component_id="bat12", name="LP 12V", brand="LP", model="Y", spec=_battery_12v()
    )

    inv_offers = (
        ComponentOffer(offer_id="io1", component_id="inv48", price_uah=75000,
                        commission_rate=0.03, source="vencon.ua"),
        ComponentOffer(offer_id="io2", component_id="inv12", price_uah=2600,
                        commission_rate=0.05, source="rozetka"),
    )
    bat_offers = (
        ComponentOffer(offer_id="bo1", component_id="bat48", price_uah=45999,
                        commission_rate=0.04, source="climagroup.ua"),
        ComponentOffer(offer_id="bo2", component_id="bat12", price_uah=12480,
                        commission_rate=0.05, source="gurkit.ua"),
    )

    candidates = build_kit_candidates((inv_48, inv_12), inv_offers, (bat_48, bat_12), bat_offers)

    # 2x2=4 комбинации, но только 2 совпадают по классу напряжения (48+48, 12+12)
    assert len(candidates) == 2
    offer_ids = {c.offer_id for c in candidates}
    assert "kit__io1__bo1" in offer_ids
    assert "kit__io2__bo2" in offer_ids
    assert "kit__io1__bo2" not in offer_ids  # 48V инвертор + 12V АКБ


def test_kit_commission_is_price_weighted_average() -> None:
    """Комиссия кита — средневзвешенная по цене, реальная суммарная выручка."""
    inv = CatalogInverter(
        component_id="inv", name="X", brand="X", model="X", spec=_deye_48v()
    )
    bat = CatalogBattery(
        component_id="bat", name="X", brand="X", model="X", spec=_logicpower_battery_48v()
    )
    inv_offer = ComponentOffer(
        offer_id="io", component_id="inv", price_uah=75000, commission_rate=0.02, source="s"
    )
    bat_offer = ComponentOffer(
        offer_id="bo", component_id="bat", price_uah=25000, commission_rate=0.10, source="s"
    )
    candidates = build_kit_candidates((inv,), (inv_offer,), (bat,), (bat_offer,))
    # (75000*0.02 + 25000*0.10) / 100000 = (1500 + 2500) / 100000 = 0.04
    assert candidates[0].commission_rate == pytest.approx(0.04)
    assert candidates[0].price_uah == 100000


def test_out_of_stock_component_excludes_kit() -> None:
    """Если хотя бы один компонент нет в наличии — весь кит не в наличии."""
    inv = CatalogInverter(component_id="inv", name="X", brand="X", model="X", spec=_deye_48v())
    bat = CatalogBattery(
        component_id="bat", name="X", brand="X", model="X", spec=_logicpower_battery_48v()
    )
    inv_offer = ComponentOffer(
        offer_id="io", component_id="inv", price_uah=75000, commission_rate=0.02,
        source="s", in_stock=False,
    )
    bat_offer = ComponentOffer(
        offer_id="bo", component_id="bat", price_uah=25000, commission_rate=0.10, source="s"
    )
    candidates = build_kit_candidates((inv,), (inv_offer,), (bat,), (bat_offer,))
    assert candidates[0].in_stock is False


def test_kit_candidate_works_in_matching_engine(fridge: ApplianceSpec) -> None:
    """Главная проверка: matching.engine НЕ ЗНАЕТ, что Candidate собран из
    двух компонентов — обрабатывает его совершенно так же, как обычный товар."""
    inv = CatalogInverter(component_id="inv", name="X", brand="X", model="X", spec=_deye_48v())
    bat = CatalogBattery(
        component_id="bat", name="X", brand="X", model="X", spec=_logicpower_battery_48v()
    )
    inv_offer = ComponentOffer(
        offer_id="io", component_id="inv", price_uah=75000, commission_rate=0.02, source="s"
    )
    bat_offer = ComponentOffer(
        offer_id="bo", component_id="bat", price_uah=25000, commission_rate=0.10, source="s"
    )
    candidates = build_kit_candidates((inv,), (inv_offer,), (bat,), (bat_offer,))

    requirement = calculate_requirement(
        LoadProfile(items=(LoadItem(appliance=fridge),)), AutonomyTarget(window_hours=Hours(6))
    )
    recommendations = select_recommendations(requirement, candidates, grid_tariff_uah_per_kwh=4.32)

    assert len(recommendations) == 1
    assert recommendations[0].fit.can_run is True
    assert recommendations[0].ownership is not None
