"""Фикстуры приборов для тестов ядра."""

import pytest

from core.appliances import ApplianceSpec, PowerBus
from core.units import Watt


@pytest.fixture
def fridge() -> ApplianceSpec:
    """Холодильник No Frost: компрессор, пусковой ток, чистый синус."""
    return ApplianceSpec(
        code="fridge_no_frost_medium",
        power_w=Watt(150),
        duty_cycle=0.35,
        startup_factor=5.0,
        power_factor=0.7,
        bus=PowerBus.AC_230,
        requires_pure_sine=True,
    )


@pytest.fixture
def router() -> ApplianceSpec:
    """Роутер через блок питания 230 В: резистивная нагрузка, работает всегда."""
    return ApplianceSpec(code="router_wifi", power_w=Watt(12), duty_cycle=1.0)


@pytest.fixture
def led_lamp() -> ApplianceSpec:
    """LED-лампа 9 Вт."""
    return ApplianceSpec(code="led_lamp_9w", power_w=Watt(9))


@pytest.fixture
def phone() -> ApplianceSpec:
    """Смартфон по USB — шина DC, инвертор в цепи не участвует."""
    return ApplianceSpec(code="smartphone", power_w=Watt(10), bus=PowerBus.DC_USB)


@pytest.fixture
def gas_boiler() -> ApplianceSpec:
    """Газовый котёл: индуктивная нагрузка и требование к времени переключения."""
    return ApplianceSpec(
        code="gas_boiler",
        power_w=Watt(120),
        duty_cycle=0.5,
        startup_factor=3.0,
        power_factor=0.6,
        requires_pure_sine=True,
        max_switchover_ms=10,
    )
