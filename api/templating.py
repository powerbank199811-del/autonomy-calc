"""Рендер HTML: единственное место, где RecommendationOut становится разметкой.

Шаблон получает ТОЛЬКО RecommendationOut. Прямой доступ в catalog/ и
matching/ запрещён: если карточке не хватает поля, это дефект контракта
и повод вернуться к ADR-038, а не обойти границу через импорт в шаблоне.

undefined=StrictUndefined выбран сознательно: опечатка в имени поля должна
падать на рендере, а не тихо рисовать пустое место. Тот же принцип, что
уже применён к неизвестному домену в sources.yaml — валидация на входе,
а не молчаливый fallback.

Подписи enum'ов живут здесь, а не в core/: FitFlag.FUEL_LIMITED — доменный
факт, "Обмежено запасом пального" — витрина. Ядро не знает украинского.
"""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from api.schemas import ComponentRole, OwnershipOut, RecommendationOut
from catalog.products import CapacitySource
from core.fit import FitFlag

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

#: Неразрывный пробел: "12 499 ₴" не должно переноситься на две строки.
NBSP = "\u00a0"

CAPACITY_SOURCE_LABELS: dict[CapacitySource, str] = {
    CapacitySource.RATED: "Ємність — з паспорта виробника, ми її не перевіряли",
    CapacitySource.THIRD_PARTY: "Ємність — за незалежним заміром, не нашим",
    CapacitySource.MEASURED: "Ємність ми виміряли самі",
}

COMPONENT_ROLE_LABELS: dict[ComponentRole, str] = {
    ComponentRole.INVERTER: "Інвертор",
    ComponentRole.BATTERY: "Акумулятор",
}

FIT_FLAG_LABELS: dict[FitFlag, str] = {
    FitFlag.USED_MEASURED_CAPACITY: "Рахували за реальним заміром ємності, а не за паспортом",
    FitFlag.USED_DECLARED_DERATING: (
        "Паспортну ємність зменшили на 15% — виробники її завищують"
    ),
    FitFlag.USED_PRODUCT_DOD_OVERRIDE: (
        "Глибину розряду взяли з даташита саме цього акумулятора"
    ),
    FitFlag.FUEL_LIMITED: "Час обмежений запасом пального в баку, а не потужністю",
    FitFlag.IDLE_DRAW_SIGNIFICANT: "Пристрій помітно споживає сам на себе — це враховано",
}


def format_uah(value: float) -> str:
    """Ціна без копійок, з нерозривними пробілами: 12 499 ₴."""
    whole = f"{round(value):,}".replace(",", NBSP)
    return f"{whole}{NBSP}₴"


def format_uah_per_kwh(value: float) -> str:
    """Вартість кіловат-години: дві цифри після коми.

    Отдельный фильтр, а не format_uah: цена товара без копеек читается
    лучше, а 7,80 ₴/кВт·год, округлённые до 8, убивают саму метрику —
    это ниша, ради которой проект и делается.
    """
    return f"{value:.2f}".replace(".", ",") + f"{NBSP}₴/кВт·год"


def format_hours(value: float) -> str:
    """Години словом і зі склінням: 1 година, 3 години, 14 годин, 6,2 години.

    Скорочення "год" не використовуємо навмисно: російськомовний читач
    бачить у ньому "рік". Двозначність на вітрині коштує дорожче,
    ніж кілька зайвих символів.
    """
    if value < 10:
        return f"{value:.1f}".replace(".", ",") + f"{NBSP}години"
    whole = round(value)
    if whole % 10 == 1 and whole % 100 != 11:
        word = "година"
    elif whole % 10 in (2, 3, 4) and whole % 100 not in (12, 13, 14):
        word = "години"
    else:
        word = "годин"
    return f"{whole}{NBSP}{word}"


def format_kwh(value: float) -> str:
    """Кіловат-години: одиниця окупності (ADR-010), не місяці."""
    if value >= 100:
        return f"{round(value)}{NBSP}кВт·год"
    return f"{value:.1f}".replace(".", ",") + f"{NBSP}кВт·год"

def format_wh_as_kwh(value: float) -> str:
    """Ватт-години -> кіловат-години. Домен рахує у Вт·год (ADR-008).

    Окремий фільтр, а не ділення в шаблоні: одиниці вимірювання —
    робота форматування, а не вёрстки. format_kwh лишається для тих,
    хто вже має кіловат-години (картка, економіка).
    """
    return format_kwh(value / 1000)

def capacity_source_label(source: CapacitySource | None) -> str | None:
    """None = ёмкости нет вообще (генератор) — подписи тоже нет."""
    if source is None:
        return None
    return CAPACITY_SOURCE_LABELS[source]


def role_label(role: ComponentRole) -> str | None:
    """PRIMARY подписи не имеет: один товар — одна покупка, пояснять нечего."""
    return COMPONENT_ROLE_LABELS.get(role)


def flag_label(flag: FitFlag) -> str:
    return FIT_FLAG_LABELS[flag]


def pays_back_within_life(ownership: OwnershipOut) -> bool:
    """Окупится ли решение раньше, чем выработает свой ресурс.

    Сравнение двух независимых чисел (ADR-012), а не одного порога:
    payback_energy_kwh может быть больше lifetime_energy_kwh — тогда
    решение не окупается НИКОГДА, и обещать окупаемость на карточке
    значит врать. Резервное питание против сети обычно и не окупается;
    честный текст здесь сильнее красивого.
    """
    if ownership.payback_energy_kwh is None:
        return False
    return ownership.payback_energy_kwh <= ownership.lifetime_energy_kwh


def brand_initials(brand: str) -> str:
    """Заглушка вместо картинки: две буквы бренда вместо пустого квадрата."""
    cleaned = brand.strip()
    if not cleaned:
        return "?"
    return cleaned[:2].upper()


@lru_cache(maxsize=1)
def get_environment() -> Environment:
    """Окружение строится один раз, не на каждый запрос."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["uah"] = format_uah
    env.filters["uah_per_kwh"] = format_uah_per_kwh
    env.filters["hours"] = format_hours
    env.filters["kwh"] = format_kwh
    env.filters["capacity_source_label"] = capacity_source_label
    env.filters["role_label"] = role_label
    env.filters["flag_label"] = flag_label
    env.filters["initials"] = brand_initials
    env.filters["pays_back"] = pays_back_within_life
    env.filters["wh_as_kwh"] = format_wh_as_kwh
    return env


def render_card(recommendation: RecommendationOut) -> str:
    """HTML одной карточки. Стили сюда не входят — они один раз на страницу."""
    module = get_environment().get_template("card.html").make_module()
    card = module.card  # type: ignore[attr-defined]
    result: str = card(recommendation)
    return result


def render_card_styles() -> str:
    """Блок <style> карточки. Вставляется один раз, независимо от числа карточек."""
    module = get_environment().get_template("card.html").make_module()
    styles = module.card_styles  # type: ignore[attr-defined]
    result: str = styles()
    return result
