"""Инварианты расчёта потребности. Каждый инвариант — отдельный тест."""

import pytest

from core.appliances import ApplianceSpec
from core.demand import calculate_requirement
from core.errors import EmptyLoadProfileError, InvalidLoadItemError
from core.load import AutonomyTarget, LoadItem, LoadProfile
from core.requirement import RequirementFlag
from core.units import Hours, Watt


def _profile(*items: LoadItem) -> LoadProfile:
    return LoadProfile(items=items)


def test_empty_profile_raises() -> None:
    """Пустой профиль — ошибка, а не нулевой результат."""
    with pytest.raises(EmptyLoadProfileError):
        LoadProfile(items=())


def test_hours_beyond_window_raises(router: ApplianceSpec) -> None:
    """Прибор не может работать дольше окна автономности."""
    profile = _profile(LoadItem(appliance=router, hours=Hours(10)))
    with pytest.raises(InvalidLoadItemError):
        calculate_requirement(profile, AutonomyTarget(window_hours=Hours(8)))


def test_startup_not_less_than_continuous(fridge: ApplianceSpec, router: ApplianceSpec) -> None:
    """Инвариант: пусковая мощность >= непрерывной."""
    req = calculate_requirement(
        _profile(LoadItem(appliance=fridge), LoadItem(appliance=router)),
        AutonomyTarget(window_hours=Hours(8)),
    )
    assert req.startup_power_w >= req.continuous_power_ac_w


def test_apparent_not_less_than_active(fridge: ApplianceSpec) -> None:
    """Инвариант: полная мощность (ВА) >= активной (Вт) при cos φ < 1."""
    req = calculate_requirement(
        _profile(LoadItem(appliance=fridge)), AutonomyTarget(window_hours=Hours(8))
    )
    assert req.apparent_power_va > req.continuous_power_ac_w


def test_breakdown_sums_to_total(fridge: ApplianceSpec, phone: ApplianceSpec) -> None:
    """Инвариант: сумма разбивки равна суммарной энергии."""
    req = calculate_requirement(
        _profile(LoadItem(appliance=fridge), LoadItem(appliance=phone, quantity=2)),
        AutonomyTarget(window_hours=Hours(8)),
    )
    assert abs(sum(c.energy_wh for c in req.breakdown) - req.total_energy_wh) <= 1.0
    assert abs(sum(c.share for c in req.breakdown) - 1.0) < 1e-6


def test_ac_and_dc_are_separated(router: ApplianceSpec, phone: ApplianceSpec) -> None:
    """Шины AC и DC не смешиваются: у них разные цепочки потерь."""
    req = calculate_requirement(
        _profile(LoadItem(appliance=router), LoadItem(appliance=phone)),
        AutonomyTarget(window_hours=Hours(5)),
    )
    assert req.energy_ac_wh > 0 and req.energy_dc_wh > 0
    assert req.continuous_power_dc_w == 10


def test_dc_only_flag(phone: ApplianceSpec) -> None:
    """Только USB-нагрузка — инвертор не нужен."""
    req = calculate_requirement(
        _profile(LoadItem(appliance=phone)), AutonomyTarget(window_hours=Hours(4))
    )
    assert RequirementFlag.DC_ONLY in req.flags


def test_boiler_sets_ups_flag(gas_boiler: ApplianceSpec) -> None:
    """Котёл требует режима ИБП и задаёт максимальное время переключения."""
    req = calculate_requirement(
        _profile(LoadItem(appliance=gas_boiler)), AutonomyTarget(window_hours=Hours(8))
    )
    assert RequirementFlag.UPS_MODE_REQUIRED in req.flags
    assert RequirementFlag.PURE_SINE_REQUIRED in req.flags
    assert req.max_switchover_ms == 10


def test_determinism(fridge: ApplianceSpec, router: ApplianceSpec) -> None:
    """Одинаковый вход — одинаковый выход."""
    profile = _profile(LoadItem(appliance=fridge), LoadItem(appliance=router))
    target = AutonomyTarget(window_hours=Hours(6))
    assert calculate_requirement(profile, target) == calculate_requirement(profile, target)


@pytest.mark.parametrize("hours", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_energy_monotonic_by_hours(router: ApplianceSpec, hours: int) -> None:
    """Монотонность: рост окна не уменьшает энергию. Пресеты 1..10 часов."""
    req = calculate_requirement(
        _profile(LoadItem(appliance=router)), AutonomyTarget(window_hours=Hours(hours))
    )
    assert req.energy_ac_wh == 12 * hours


def test_energy_monotonic_by_quantity(led_lamp: ApplianceSpec) -> None:
    """Монотонность по количеству приборов."""
    target = AutonomyTarget(window_hours=Hours(8))
    one = calculate_requirement(_profile(LoadItem(appliance=led_lamp)), target)
    three = calculate_requirement(_profile(LoadItem(appliance=led_lamp, quantity=3)), target)
    assert three.energy_ac_wh == 3 * one.energy_ac_wh


def test_override_changes_power(router: ApplianceSpec) -> None:
    """Переопределение мощности пользователем применяется и помечается."""
    from core.load import ApplianceOverride
    from core.requirement import AssumptionCode

    req = calculate_requirement(
        _profile(LoadItem(appliance=router, override=ApplianceOverride(power_w=Watt(30)))),
        AutonomyTarget(window_hours=Hours(4)),
    )
    assert req.continuous_power_ac_w == 30
    assert AssumptionCode.USER_OVERRIDE_APPLIED in req.assumptions
