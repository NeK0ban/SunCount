"""Загрузка входных данных из data/: тарифы с диапазонами, помесячная цена выкупа, сезонность выработки.

Все функции читают только файлы проекта (у каждого значения в CSV есть источник и дата).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HEATING_MONTHS = {10, 11, 12, 1, 2, 3, 4}  # отопительный период 01.10–30.04 (ТНС энерго Кубань)
DAY_HOURS = range(7, 23)                  # дневная зона 7–23 (2-зонный тариф)


# ----------------------------------------------------------------- тарифы
@dataclass(frozen=True)
class TariffPlan:
    """Тариф домохозяйства.

    price_category: 'base' (раздел 1, город с газом) или 'reduced' (село; электроплита/электроотопление)
    tariff_type:    'single' (одноставочный) или 'two_zone' (день/ночь)
    range_keys:     ключи из data/tariff_ranges_2026.csv; для домов с электроотоплением —
                    (ключ отопительного периода, ключ неотопительного)
    owner_category: ценовая категория для цены выкупа: 'flat' (1-я ЦК) или 'zones' (2-я ЦК)
    """
    name: str
    price_category: str
    tariff_type: str
    range_keys: tuple[str, ...] = ("base",)
    date_from: str = "2026-10-01"

    @property
    def owner_category(self) -> str:
        return "zones" if self.tariff_type == "two_zone" else "flat"


@lru_cache
def _tariffs() -> pd.DataFrame:
    return pd.read_csv(DATA / "tariffs_2026.csv", encoding="utf-8-sig")


@lru_cache
def _ranges() -> pd.DataFrame:
    return pd.read_csv(DATA / "tariff_ranges_2026.csv", encoding="utf-8-sig")


def zone_prices(plan: TariffPlan) -> dict[str, dict[str, float]]:
    """{'I': {'day': p, 'night': p}, 'II': ..., 'III': ...}, ₽/кВт·ч."""
    t = _tariffs()
    t = t[(t.date_from == plan.date_from) & (t.category == plan.price_category) & (t.tariff_type == plan.tariff_type)]
    out = {}
    for rng in ("I", "II", "III"):
        r = t[t.range == rng]
        if plan.tariff_type == "single":
            p = float(r.price_rub_kwh.iloc[0])
            out[rng] = {"day": p, "night": p}
        else:
            out[rng] = {z: float(r[r.zone == z].price_rub_kwh.iloc[0]) for z in ("day", "night")}
    return out


def range_bounds(plan: TariffPlan, month: int) -> tuple[float, float]:
    """Границы I и II диапазонов, кВт·ч/мес, для данного месяца."""
    r = _ranges()
    if len(plan.range_keys) == 1:
        key = plan.range_keys[0]
    else:
        key = plan.range_keys[0] if month in HEATING_MONTHS else plan.range_keys[1]
    row = r[r.category == key].iloc[0]
    return float(row.range_I_max_kwh_month), float(row.range_II_max_kwh_month)


def monthly_bill(plan: TariffPlan, month: int, day_kwh: float, night_kwh: float) -> float:
    """Счёт за месяц с учётом диапазонов: объём сверх границы диапазона оплачивается по ставке
    следующего диапазона; день/ночь распределяются по диапазонам пропорционально."""
    total = day_kwh + night_kwh
    if total <= 0:
        return 0.0
    b1, b2 = range_bounds(plan, month)
    bands = {"I": min(total, b1), "II": min(max(total - b1, 0), b2 - b1), "III": max(total - b2, 0)}
    s_day = day_kwh / total
    prices = zone_prices(plan)
    return sum(v * (s_day * prices[k]["day"] + (1 - s_day) * prices[k]["night"]) for k, v in bands.items())


# ----------------------------------------------------------------- цена выкупа
@lru_cache
def buyback_monthly(owner_category: str) -> dict[int, float]:
    """Цена выкупа по месяцам (1–12), ₽/кВт·ч, для владельца на тарифе 'flat' или 'zones'.

    Уровень — среднее восстановленной цены категории за май–сентябрь 2026 (data/buyback_by_category.csv).
    Сезонность — индекс средневзвешенной цены ТНС по календарным месяцам 2024–2026
    (data/buyback_prices.csv), нормированный так, что среднее за май–сентябрь = 1.
    """
    cat = pd.read_csv(DATA / "buyback_by_category.csv", encoding="utf-8-sig")
    level = float(cat["flat_rub_kwh" if owner_category == "flat" else "zones_day_rub_kwh"].mean())
    avg = pd.read_csv(DATA / "buyback_prices.csv", encoding="utf-8-sig")
    avg["m"] = avg.month.str[5:7].astype(int)
    by_m = avg.groupby("m").price_rub_kwh.mean()
    base = by_m.loc[[5, 6, 7, 8, 9]].mean()
    return {m: level * float(by_m.loc[m]) / base for m in range(1, 13)}


# ----------------------------------------------------------------- выработка
@lru_cache
def pv_monthly_kwh_per_kw(city: str) -> dict[int, float]:
    """Выработка 1 кВт СЭС по месяцам, кВт·ч (PVGIS-SARAH3 2005–2023, оптимальный угол, потери 14 %)."""
    d = json.loads((DATA / "raw" / "pvgis" / f"{city}_pvcalc_1kw.json").read_text(encoding="utf-8"))
    return {x["month"]: float(x["E_m"]) for x in d["outputs"]["monthly"]["fixed"]}
