"""Скрипт-конвертер CSV -> products.yaml: не должен молча портить данные."""

import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "csv_to_products_yaml.py"
TEMPLATE_CSV = Path(__file__).resolve().parent.parent / "data" / "products_template.csv"


def test_template_csv_converts_and_validates(tmp_path: Path) -> None:
    """Реальный шаблон конвертируется и проходит валидацию каталога."""
    output = tmp_path / "products.yaml"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(TEMPLATE_CSV), str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Валидация пройдена" in result.stdout
    assert output.exists()

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert len(data["products"]) == 8
    assert len(data["offers"]) == 8


def test_broken_physics_rejected_with_clear_error(tmp_path: Path) -> None:
    """peak_power_w < continuous_power_w — понятная ошибка, файл всё равно не молчит."""
    csv_content = (
        "product_id,name,brand,model,category,kind,chemistry,capacity_wh,"
        "continuous_power_w,peak_power_w,apparent_power_va,dc_output_power_w,"
        "inverter_efficiency,dc_output_efficiency,idle_draw_w,waveform,"
        "switchover_ms,fuel_rate_l_per_kwh,tank_l,cycle_life,image,offer_id,"
        "price_uah,commission_rate,source,url,in_stock,expected_lifetime_wh\n"
        "broken,Test,X,Y,Test,station,lifepo4,1000,2000,1000,,,,,,,,,,3000,,"
        "off1,10000,0.05,test,,так,\n"
    )
    csv_path = tmp_path / "broken.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    output = tmp_path / "out.yaml"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(csv_path), str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "peak_power_w" in result.stderr


def test_missing_offer_id_rejected(tmp_path: Path) -> None:
    """Пустой offer_id — явная ошибка на конкретной строке, не тихий пропуск."""
    csv_content = (
        "product_id,name,brand,model,category,kind,chemistry,capacity_wh,"
        "continuous_power_w,peak_power_w,apparent_power_va,dc_output_power_w,"
        "inverter_efficiency,dc_output_efficiency,idle_draw_w,waveform,"
        "switchover_ms,fuel_rate_l_per_kwh,tank_l,cycle_life,image,offer_id,"
        "price_uah,commission_rate,source,url,in_stock,expected_lifetime_wh\n"
        "p1,Test,X,Y,Test,powerbank,li_ion,74,,,,65,,,,,,,,500,,,2499,0.05,test,,так,\n"
    )
    csv_path = tmp_path / "no_offer_id.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    output = tmp_path / "out.yaml"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(csv_path), str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "offer_id" in result.stderr
