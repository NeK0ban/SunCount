"""Проверка данных команды 1 (задача T1.5): формат, балансы, выработка и метод «типичного года».

Вход:
  data/energy_metrics.csv, data/energy_metrics_monthly.csv — файлы команды 1 (формат обмена v1.0);
  data/hourly_profiles/<портрет>_<город>_8760.csv — почасовое потребление команды 1;
  data/raw/team1_pvgis/pvgis_2005_2023_original_upload.zip — исходные почасовые ряды PVGIS (2005–2023, 30°, юг, 14 %).
Выход:
  results/team1_typical_year_check.csv — доля самопотребления: как в файле команды 1 (по усреднённому по часам
    «типичному году») и в среднем по реальным годам 2006–2023;
  results/team1_hypothesis_by_years.csv — гипотеза команды 1 при равном потреблении 3500 кВт·ч/год по тем же годам.

Почему так: min(выработка, нагрузка) — вогнутая функция, поэтому самопотребление по усреднённому ряду
(каждый час — среднее за 19 лет, без пасмурных и ясных дней) выше, чем среднее самопотребление реальных лет.
Протокол — docs/team1_data_check.md, проверка № 3.

Запуск: python scripts/check_team1_data.py
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ.exchange import MonthlyMetrics, read_csv  # noqa: E402

DATA, OUT = ROOT / "data", ROOT / "results"
RAW_ZIP = DATA / "raw" / "team1_pvgis" / "pvgis_2005_2023_original_upload.zip"
PROFILES = ("day_absent", "home_all_day", "ac", "el_heating")
SIZES = (3, 5, 10)
EQUAL_LOAD = 3500.0     # кВт·ч/год — как в проверке гипотезы командой 1


def pvgis_years(city: str) -> dict[int, np.ndarray]:
    """Почасовая выработка 1 кВт по годам, местное время UTC+3, без 29 февраля; только полные годы (8760 ч)."""
    with zipfile.ZipFile(RAW_ZIP) as z:
        rows = json.loads(z.read(f"{city}_2005_2023.json"))["outputs"]["hourly"]
    t = pd.to_datetime([r["time"] for r in rows], format="%Y%m%d:%H%M") + pd.Timedelta(hours=3)
    s = pd.Series(np.array([r["P"] for r in rows]) / 1000.0, index=t)
    s = s[~((s.index.month == 2) & (s.index.day == 29))]
    years = {y: s[s.index.year == y].to_numpy() for y in sorted(set(s.index.year))}
    return {y: v for y, v in years.items() if len(v) == 8760}


def load_profile(profile: str, city: str) -> np.ndarray:
    return pd.read_csv(DATA / "hourly_profiles" / f"{profile}_{city}_8760.csv").load_kwh.to_numpy()


annual = read_csv(DATA / "energy_metrics.csv")
monthly = read_csv(DATA / "energy_metrics_monthly.csv", MonthlyMetrics)
print(f"Формат: {len(annual)} годовых и {len(monthly)} помесячных записей прочитаны и проверены read_csv")

rows, hyp = [], []
for city in ("krasnodar", "maykop"):
    years = pvgis_years(city)
    typical = np.mean(list(years.values()), axis=0)
    for profile in PROFILES:
        load = load_profile(profile, city)
        for kw in SIZES:
            rec = next(r for r in annual if r.profile_id == profile and r.city == city and int(r.pv_kw) == kw)
            per_year = [100 * np.minimum(g * kw, load).sum() / (g * kw).sum() for g in years.values()]
            typ = 100 * np.minimum(typical * kw, load).sum() / (typical * kw).sum()
            rows.append({"city": city, "profile_id": profile, "pv_kw": kw, "self_share_file": round(rec.self_share, 2),
                         "self_share_typical_recomputed": round(typ, 2),
                         "self_share_mean_of_years": round(float(np.mean(per_year)), 2),
                         "self_share_min_year": round(float(np.min(per_year)), 2),
                         "self_share_max_year": round(float(np.max(per_year)), 2),
                         "overstatement_pp": round(rec.self_share - float(np.mean(per_year)), 2),
                         "years": f"{min(years)}–{max(years)}"})
    la = load_profile("day_absent", city) * EQUAL_LOAD / load_profile("day_absent", city).sum()
    lh = load_profile("home_all_day", city) * EQUAL_LOAD / load_profile("home_all_day", city).sum()
    for kw in SIZES:
        self_a = np.mean([np.minimum(g * kw, la).sum() for g in years.values()])
        self_h = np.mean([np.minimum(g * kw, lh).sum() for g in years.values()])
        hyp.append({"city": city, "pv_kw": kw, "equal_annual_load_kwh": EQUAL_LOAD,
                    "self_share_ratio_by_years": round(self_h / self_a, 4),
                    "hypothesis_ge_1_5": bool(self_h / self_a >= 1.5)})

OUT.mkdir(exist_ok=True)
pd.DataFrame(rows).to_csv(OUT / "team1_typical_year_check.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(hyp).to_csv(OUT / "team1_hypothesis_by_years.csv", index=False, encoding="utf-8-sig")
d = pd.DataFrame(rows)
print(f"Завышение доли самопотребления методом типичного года: {d.overstatement_pp.min():.1f}–{d.overstatement_pp.max():.1f} п. п.")
print(pd.DataFrame(hyp).to_string(index=False))
print("Готово: results/team1_typical_year_check.csv, results/team1_hypothesis_by_years.csv")
