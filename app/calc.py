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

from src.econ.api import capex_estimate, recommend  # noqa: E402
from src.econ.exchange import MonthlyMetrics, make_stub_monthly, read_csv  # noqa: E402
from src.econ.inputs import TariffPlan  # noqa: E402
from app.texts import TARIFFS  # noqa: E402

PV_SIZES = (3, 5, 10)
MONTHS_GEN = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
              "октябрь", "ноябрь", "декабрь"]


PORTRAIT_FILE = ROOT / "data" / "energy_metrics_monthly.csv"   # помесячные данные команды 1 (19 лет PVGIS)

# Приборы, дающие сниженный тариф (категория reduced), и диапазоны потребления для них:
# первый ключ — отопительный период (октябрь–апрель), второй — май–сентябрь (data/tariff_ranges_2026.csv)
HEATING_STOVE_RANGES = ("reduced_heating", "reduced_heating_stove")
HEATING_RANGES = ("reduced_heating", "reduced_heating_nostove")
STOVE_RANGES = ("reduced_stove",)


def get_plan(tariff_key: str, appliances=()) -> TariffPlan:
    """Тариф с учётом приборов (T4.2).

    Дом с электроотоплением и (или) электроплитой и в городе платит по сниженному тарифу — категория reduced,
    как у села (data/tariffs_2026.csv: «Разделы 2–8: сельское население; город с электроплитами/электроотоплением»).
    Вид тарифа (одноставочный или день/ночь) и название остаются теми, что выбрал пользователь; меняются
    категория и диапазоны потребления. Кондиционер и насос тариф не меняют.
    """
    plan = TARIFFS[tariff_key]["plan"]
    heating, stove = "el_heating" in appliances, "el_stove" in appliances
    if heating:
        ranges = HEATING_STOVE_RANGES if stove else HEATING_RANGES
    elif stove:
        ranges = STOVE_RANGES
    else:
        return plan
    return TariffPlan(plan.name, "reduced", plan.tariff_type, ranges, plan.date_from)


def reduced_by_appliances(tariff_key: str, appliances=()) -> bool:
    """True, если из-за приборов расчёт идёт по сниженному тарифу, хотя выбран городской."""
    return TARIFFS[tariff_key]["plan"].price_category == "base" and get_plan(tariff_key, appliances).price_category == "reduced"


@lru_cache(maxsize=1)
def _portrait_records() -> tuple:
    return tuple(read_csv(PORTRAIT_FILE, MonthlyMetrics)) if PORTRAIT_FILE.exists() else ()


def get_portrait_months(profile_id: str, city: str) -> dict[int, list[MonthlyMetrics]]:
    """Готовый портрет команды 1: {кВт: 12 помесячных записей}; {} — если данных нет (тогда расчёта не будет)."""
    by_kw: dict[int, list[MonthlyMetrics]] = {}
    for r in _portrait_records():
        if r.profile_id == profile_id and r.city == city:
            by_kw.setdefault(int(r.pv_kw), []).append(r)   # в файле pv_kw записан как 3.0
    by_kw = {kw: sorted(recs, key=lambda r: r.month) for kw, recs in by_kw.items()}
    if set(by_kw) != set(PV_SIZES) or any(len(v) != 12 for v in by_kw.values()):
        return {}
    return by_kw


def portrait_monthly_load(profile_id: str, city: str) -> float:
    """Среднее потребление портрета в месяц, кВт·ч (для фразы с выводом)."""
    months = get_portrait_months(profile_id, city)
    return sum(r.load_kwh for r in months[PV_SIZES[0]]) / 12 if months else float("nan")


def calculate_scenario(
    monthly_kwh,
    self_share_pct: float,
    city: str,
    tariff_key: str,
    profile_id: str | None = None,
    appliances=(),
    custom_capex: dict[int, float] | None = None,
) -> tuple[int, dict[int, dict]]:
    """
    Считает окупаемость для мощностей 3, 5 и 10 кВт. Возвращает (рекомендуемая_мощность, {кВт: показатели}).

    Режимы ввода (T4.2):
    - «Готовый портрет» (profile_id задан): помесячные данные команды 1 из data/energy_metrics_monthly.csv;
      доля самопотребления уже посчитана командой 1, self_share_pct и monthly_kwh не используются;
      у портрета el_heating тариф всегда сниженный (как приборы {"el_heating"});
    - «Свои данные»: monthly_kwh — одно среднее значение в месяц или список из 12 месячных значений
      (годовое потребление — их сумма, сезонность — сами значения: make_stub_monthly делит на их сумму);
      профиль условный (make_stub_monthly), долю самопотребления задаёт ползунок — до подключения модуля команды 1.
    appliances меняют тариф (get_plan); custom_capex = {кВт: ₽} — своя цена станции вместо базовой.

    Рекомендуемая мощность — по api.recommend: наименьший простой срок; сроки, различающиеся меньше
    чем на 0,05 года, считаются равными, и тогда берётся меньшая мощность. Если не окупается ни одна
    станция — мощность с наибольшим годовым эффектом (simple_payback у всех = inf).
    Показатели — поля api.Result: capex_rub, self_share, coverage, self_rub, export_rub, effect_rub,
    export_share, simple_payback, disc_payback, npv_rub, payback_low, payback_high.
    """
    appliances = set(appliances or ())
    if profile_id:
        if profile_id == "el_heating":
            appliances.add("el_heating")
        months_by_kw = get_portrait_months(profile_id, city)
        if not months_by_kw:
            raise ValueError(f"Нет данных команды 1 для портрета {profile_id!r}, город {city!r}")
    else:
        if isinstance(monthly_kwh, (list, tuple)):
            if len(monthly_kwh) != 12 or min(monthly_kwh) <= 0:
                raise ValueError("Потребление по месяцам: нужны все 12 значений больше нуля")
            load_kwh, load_shape = float(sum(monthly_kwh)), [float(v) for v in monthly_kwh]
        else:
            if monthly_kwh <= 0:
                raise ValueError("Потребление должно быть больше нуля")
            load_kwh, load_shape = float(monthly_kwh) * 12, None
        months_by_kw = {
            kw: make_stub_monthly(
                profile_id=f"stub_{int(self_share_pct)}",
                pv_kw=kw,
                load_kwh=load_kwh,
                self_share_pct=self_share_pct,
                city=city,
                load_shape=load_shape,
            )
            for kw in PV_SIZES
        }
    plan = get_plan(tariff_key, appliances)
    best_kw, results = recommend(months_by_kw, plan, capex_by_kw=dict(custom_capex) if custom_capex else None)
    return best_kw, {kw: r.as_dict() for kw, r in results.items()}


def base_capex() -> dict[int, float]:
    """Базовая цена станций из data/capex_estimate.csv — значения по умолчанию для поля «своя цена»."""
    return {kw: capex_estimate(kw) for kw in PV_SIZES}


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
