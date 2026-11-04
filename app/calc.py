# app/calc.py
"""Расчёт окупаемости СЭС для веб-сервиса. НЕ импортирует streamlit — можно вызывать из теста или консоли.

Числа — только из модели, через единую точку входа src/econ/api.py (решение команды от 31.10.2026):
тот же расчёт, что в scripts/stub_payback.py и results/stub_payback.csv.
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

# Корень репозитория — чтобы видеть src/ и data/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.econ.api import recommend  # noqa: E402
from src.econ.exchange import make_stub_monthly  # noqa: E402
from app.texts import TARIFFS  # noqa: E402

PV_SIZES = (3, 5, 10)
MONTHS_GEN = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
              "октябрь", "ноябрь", "декабрь"]


def calculate_scenario(
    monthly_kwh: float,
    self_share_pct: float,
    city: str,
    tariff_key: str,
) -> tuple[int, dict[int, dict]]:
    """
    Считает окупаемость для мощностей 3, 5 и 10 кВт на условных данных (до подключения модуля команды 1).
    Возвращает (рекомендуемая_мощность, словарь {кВт: показатели}).

    Рекомендуемая мощность — по api.recommend: наименьший простой срок; сроки, различающиеся меньше
    чем на 0,05 года, считаются равными, и тогда берётся меньшая мощность. Если не окупается ни одна
    станция — мощность с наибольшим годовым эффектом (simple_payback у всех = inf).
    Показатели — поля api.Result: capex_rub, self_share, coverage, self_rub, export_rub, effect_rub,
    export_share, simple_payback, disc_payback, npv_rub, payback_low, payback_high.
    """
    plan = TARIFFS[tariff_key]["plan"]
    months_by_kw = {
        kw: make_stub_monthly(
            profile_id=f"stub_{int(self_share_pct)}",
            pv_kw=kw,
            load_kwh=monthly_kwh * 12,
            self_share_pct=self_share_pct,
            city=city,
        )
        for kw in PV_SIZES
    }
    best_kw, results = recommend(months_by_kw, plan)
    return best_kw, {kw: r.as_dict() for kw, r in results.items()}


@lru_cache(maxsize=1)
def data_versions() -> dict:
    """Какие данные лежат в основе расчёта — для подписи под результатом (берётся из файлов, не вручную)."""
    plan = next(iter(TARIFFS.values()))["plan"]
    y, m, d = plan.date_from.split("-")
    bb = pd.read_csv(ROOT / "data" / "buyback_by_category.csv", encoding="utf-8-sig").month.sort_values()
    first, last = bb.iloc[0], bb.iloc[-1]
    buyback = (f"{MONTHS_GEN[int(first[5:7]) - 1]}–{MONTHS_GEN[int(last[5:7]) - 1]} {last[:4]} г."
               if first[:4] == last[:4] else f"{first}–{last}")
    meteo = json.loads((ROOT / "data" / "raw" / "pvgis" / "krasnodar_pvcalc_1kw.json").read_text(encoding="utf-8"))
    meteo = meteo["inputs"]["meteo_data"]
    return {"tariffs_from": f"{d}.{m}.{y}", "buyback": buyback,
            "pvgis": f"среднее за {meteo['year_min']}–{meteo['year_max']} годы"}
