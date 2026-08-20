"""Конвертер таблицы товаров (CSV) в data/products.yaml.

Зачем: заполнять 27 полей в YAML на 50 позиций руками — источник опечаток.
Проще заполнять плоскую таблицу (Excel/Google Sheets -> экспорт в CSV),
а этот скрипт сам собирает products.yaml и СРАЗУ проверяет каждую позицию
через core.solution.SolutionSpec — те же инварианты, что защищают ядро.

Использование:
    python scripts/csv_to_products_yaml.py data/products_template.csv data/products.yaml

Один продукт может встречаться в CSV несколько раз (несколько офферов
у разных продавцов на одну и ту же модель) — тогда product_id повторяется,
а offer_id у каждой строки свой. Данные о самом продукте берутся из
ПЕРВОГО встреченного ряда с этим product_id.
"""

import csv
import sys
from pathlib import Path
from typing import Any

import yaml

# Позволяет запускать скрипт напрямую, без pip install -e
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from catalog.candidates import build_candidates  # noqa: E402
from catalog.products_loader import ProductsCatalogError, load_catalog  # noqa: E402

PRODUCT_FIELDS = (
    "product_id", "name", "brand", "model", "category", "kind", "chemistry",
    "capacity_wh", "continuous_power_w", "peak_power_w", "apparent_power_va",
    "dc_output_power_w", "inverter_efficiency", "dc_output_efficiency",
    "idle_draw_w", "waveform", "switchover_ms", "fuel_rate_l_per_kwh",
    "tank_l", "cycle_life", "image", "depth_of_discharge_override", "fuel_rate_source",
)
NUMERIC_FIELDS = {
    "capacity_wh", "continuous_power_w", "peak_power_w", "apparent_power_va",
    "dc_output_power_w", "inverter_efficiency", "dc_output_efficiency",
    "idle_draw_w", "switchover_ms", "fuel_rate_l_per_kwh", "tank_l", "cycle_life",
    "depth_of_discharge_override",
}


def convert(csv_path: Path, yaml_path: Path) -> None:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    if not rows:
        raise SystemExit(f"{csv_path}: пустой файл или нет заголовка")

    products: dict[str, dict[str, Any]] = {}
    offers: list[dict[str, Any]] = []

    for line_number, row in enumerate(rows, start=2):  # 1 — заголовок
        product_id = row.get("product_id", "").strip()
        if not product_id:
            continue  # пустая строка — пропускаем молча

        if product_id not in products:
            products[product_id] = _row_to_product(row, line_number)

        offers.append(_row_to_offer(row, line_number))

    data = {"products": list(products.values()), "offers": offers}
    yaml_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"Записано: {len(products)} products, {len(offers)} offers -> {yaml_path}")

    _validate(yaml_path)


def _row_to_product(row: dict[str, str], line_number: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in PRODUCT_FIELDS:
        value = row.get(field, "").strip()
        if not value:
            continue
        result[field] = _to_number(value) if field in NUMERIC_FIELDS else value
    if "kind" not in result:
        raise SystemExit(f"CSV строка {line_number}: не заполнено обязательное поле 'kind'")
    return result


def _row_to_offer(row: dict[str, str], line_number: int) -> dict[str, Any]:
    offer_id = row.get("offer_id", "").strip()
    if not offer_id:
        raise SystemExit(f"CSV строка {line_number}: не заполнено обязательное поле 'offer_id'")

    price = row.get("price_uah", "").strip()
    commission = row.get("commission_rate", "").strip()
    source = row.get("source", "").strip()
    if not price or not commission or not source:
        raise SystemExit(
            f"CSV строка {line_number} ({offer_id}): нужны price_uah, "
            f"commission_rate и source"
        )

    result: dict[str, Any] = {
        "offer_id": offer_id,
        "product_id": row["product_id"].strip(),
        "price_uah": _to_number(price),
        "commission_rate": _to_number(commission),
        "source": source,
    }
    url = row.get("url", "").strip()
    if url:
        result["url"] = url
    in_stock = row.get("in_stock", "").strip().lower()
    result["in_stock"] = in_stock not in ("ні", "no", "false", "0")
    lifetime = row.get("expected_lifetime_wh", "").strip()
    if lifetime:
        result["expected_lifetime_wh"] = _to_number(lifetime)
    return result


def _to_number(value: str) -> float:
    return float(value.replace(",", "."))


def _validate(yaml_path: Path) -> None:
    """Сразу прогоняет результат через реальные проверки проекта."""
    try:
        products, offers = load_catalog(yaml_path)
        candidates = build_candidates(products, offers)
    except ProductsCatalogError as exc:
        raise SystemExit(f"ОШИБКА ВАЛИДАЦИИ: {exc}") from exc
    print(f"Валидация пройдена: {len(candidates)} кандидатов готовы для движка подбора.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "Использование: python scripts/csv_to_products_yaml.py <входной.csv> <выходной.yaml>"
        )
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
