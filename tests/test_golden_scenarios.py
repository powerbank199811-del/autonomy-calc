"""Золотые сценарии: цифры посчитаны руками и зафиксированы.

Если тест упал — сначала пересчитай руками, потом правь код.
"""

from core.appliances import ApplianceSpec
from core.demand import calculate_requirement
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.units import Hours


def test_blackout_4h_fridge_light_router(
    fridge: ApplianceSpec, led_lamp: ApplianceSpec, router: ApplianceSpec
) -> None:
    """Типовое отключение 4 часа: холодильник + 3 лампы + роутер.

    Энергия: 150*4*0.35 = 210; 9*3*4 = 108; 12*4 = 48 → 366 Вт·ч.
    Непрерывная: 150 + 27 + 12 = 189 Вт.
    Пуск: 189 + (5-1)*150 = 789 Вт.
    """
    req = calculate_requirement(
        LoadProfile(
            items=(
                LoadItem(appliance=fridge),
                LoadItem(appliance=led_lamp, quantity=3),
                LoadItem(appliance=router),
            )
        ),
        AutonomyTarget(window_hours=Hours(4)),
    )
    assert req.energy_ac_wh == 366.0
    assert req.continuous_power_ac_w == 189.0
    assert req.startup_power_w == 789.0
    assert req.breakdown[0].share > 0.5


def test_boiler_8h(gas_boiler: ApplianceSpec) -> None:
    """Котёл 8 часов: 120*8*0.5 = 480 Вт·ч, полная мощность 120/0.6 = 200 ВА."""
    req = calculate_requirement(
        LoadProfile(items=(LoadItem(appliance=gas_boiler),)),
        AutonomyTarget(window_hours=Hours(8)),
    )
    assert req.energy_ac_wh == 480.0
    assert req.apparent_power_va == 200.0


def test_phones_only_10h(phone: ApplianceSpec) -> None:
    """Только USB: 2 телефона по 10 Вт, по 2 часа зарядки внутри окна 10 ч."""
    req = calculate_requirement(
        LoadProfile(items=(LoadItem(appliance=phone, quantity=2, hours=Hours(2)),)),
        AutonomyTarget(window_hours=Hours(10)),
    )
    assert req.energy_dc_wh == 40.0
    assert req.energy_ac_wh == 0.0
