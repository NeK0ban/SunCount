"""Проверка данных команды 1 (задача T1.5): формат, балансы и независимый пересчёт по годам PVGIS.

Вход:
  data/energy_metrics.csv, data/energy_metrics_monthly.csv — файлы команды 1 (формат обмена v1.0; с 03.11.2026 —
    самопотребление по каждому году PVGIS 2005–2023 отдельно, затем среднее помесячных энергий);
  data/hourly_profiles/<портрет>_<город>_8760.csv — почасовое потребление команды 1;
  data/raw/team1_pvgis/pvgis_2005_2023_original_upload.zip — исходные почасовые ряды PVGIS (2005–2023, 30°, юг, 14 %).
Выход:
  results/team1_yearwise_check.csv — по каждому сочетанию «портрет × город × мощность»: доля самопотребления в файле
    и в нашем пересчёте по годам, наибольшее расхождение помесячных объёмов, доля по «типичному году» (метод первой
    версии) и его завышение, разброс доли по отдельным годам;
  results/team1_hypothesis_by_years.csv — гипотеза команды 1 при равном потреблении 3500 кВт·ч/год: отношение долей
    самопотребления home_all_day / day_absent у команды 1, в нашем пересчёте и минимум по отдельным годам.

Метод (как у команды 1, docs/sources/team1/2026-11-03/methodology.md): UTC → UTC+3, 29 февраля отбрасывается,
три ночных часа 01.01.2005, которых нет в исходных рядах, — ноль; для каждого года почасово
self = min(выработка, нагрузка), покупка днём (7:00–22:59) и ночью; помесячные энергии усредняются по 19 годам,
доли — из средних энергий. «Типичный год» (каждый час усреднён по годам) завышает самопотребление, потому что
min() — вогнутая функция; первая версия данных (02.11) была посчитана так.
Протокол — docs/team1_data_check.md, проверки № 3 и 4.

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
TEAM1_HYP = ROOT / "docs" / "sources" / "team1" / "2026-11-03" / "hypothesis_equal_consumption.csv"
PROFILES = ("day_absent", "home_all_day", "ac", "el_heating")
SIZES = (3, 5, 10)
YEARS = range(2005, 2024)
EQUAL_LOAD = 3500.0     # кВт·ч/год — как в проверке гипотезы командой 1
COLS = ["gen_kwh", "self_kwh", "import_day_kwh", "import_night_kwh"]


def pvgis_years(city: str) -> tuple[dict[int, np.ndarray], np.ndarray, np.ndarray]:
    """Почасовая выработка 1 кВт по годам (8760 ч, UTC+3, без 29 февраля) + месяц и «день» для каждого часа."""
    with zipfile.ZipFile(RAW_ZIP) as z:
        rows = json.loads(z.read(f"{city}_2005_2023.json"))["outputs"]["hourly"]
    t = pd.to_datetime([r["time"] for r in rows], format="%Y%m%d:%H%M").floor("h") + pd.Timedelta(hours=3)
    s = pd.Series(np.array([r["P"] for r in rows]) / 1000.0, index=t)
    years = {}
    for y in YEARS:
        idx = pd.date_range(f"{y}-01-01", f"{y}-12-31 23:00", freq="h")
        idx = idx[~((idx.month == 2) & (idx.day == 29))]
        years[y] = s.reindex(idx, fill_value=0.0).to_numpy()
    return years, idx.month.to_numpy(), (idx.hour >= 7) & (idx.hour <= 22)


def load_profile(profile: str, city: str) -> np.ndarray:
    return pd.read_csv(DATA / "hourly_profiles" / f"{profile}_{city}_8760.csv").load_kwh.to_numpy()


def monthly(gen: np.ndarray, load: np.ndarray, month: np.ndarray, day: np.ndarray) -> np.ndarray:
    """Помесячные gen, self, покупка днём, покупка ночью: массив 12 × 4."""
    s = np.minimum(gen, load)
    imp = load - s
    return np.array([[gen[k].sum(), s[k].sum(), imp[k & day].sum(), imp[k & ~day].sum()]
                     for k in (month == m for m in range(1, 13))])


annual = read_csv(DATA / "energy_metrics.csv")
mon = read_csv(DATA / "energy_metrics_monthly.csv", MonthlyMetrics)
print(f"Формат: {len(annual)} годовых и {len(mon)} помесячных записей прочитаны и проверены read_csv")
mdf = pd.read_csv(DATA / "energy_metrics_monthly.csv").set_index(["profile_id", "city", "pv_kw", "month"]).sort_index()

rows, hyp = [], []
for city in ("krasnodar", "maykop"):
    years, month, day = pvgis_years(city)
    typical = np.mean(list(years.values()), axis=0)
    for profile in PROFILES:
        load = load_profile(profile, city)
        for kw in SIZES:
            per_year = [monthly(g * kw, load, month, day) for g in years.values()]
            mean = np.mean(per_year, axis=0)
            f = mdf.loc[(profile, city, float(kw))][COLS].to_numpy()
            share = 100 * mean[:, 1].sum() / mean[:, 0].sum()
            typ = 100 * np.minimum(typical * kw, load).sum() / (typical * kw).sum()
            by_year = [100 * m[:, 1].sum() / m[:, 0].sum() for m in per_year]
            rec = next(r for r in annual if r.profile_id == profile and r.city == city and int(r.pv_kw) == kw)
            rows.append({"city": city, "profile_id": profile, "pv_kw": kw,
                         "self_share_file": round(rec.self_share, 3), "self_share_recomputed": round(share, 3),
                         "max_abs_diff_kwh": float(f"{np.abs(f - mean).max():.2e}"),
                         "self_share_typical_year": round(typ, 2), "typical_bias_pp": round(typ - share, 2),
                         "self_share_min_year": round(min(by_year), 2), "self_share_max_year": round(max(by_year), 2)})
    la = load_profile("day_absent", city) * EQUAL_LOAD / load_profile("day_absent", city).sum()
    lh = load_profile("home_all_day", city) * EQUAL_LOAD / load_profile("home_all_day", city).sum()
    team1 = pd.read_csv(TEAM1_HYP)
    for kw in SIZES:
        sa = [np.minimum(g * kw, la).sum() for g in years.values()]
        sh = [np.minimum(g * kw, lh).sum() for g in years.values()]
        ratio = np.mean(sh) / np.mean(sa)
        hyp.append({"city": city, "pv_kw": kw, "equal_annual_load_kwh": EQUAL_LOAD,
                    "ratio_team1": round(float(team1[(team1.city == city) & (team1.pv_kw == kw)].self_share_ratio.iloc[0]), 4),
                    "ratio_recomputed": round(float(ratio), 4),
                    "ratio_min_year": round(float(min(h / a for h, a in zip(sh, sa))), 4),
                    "hypothesis_ge_1_5": bool(ratio >= 1.5)})

OUT.mkdir(exist_ok=True)
d, h = pd.DataFrame(rows), pd.DataFrame(hyp)
d.to_csv(OUT / "team1_yearwise_check.csv", index=False, encoding="utf-8-sig")
h.to_csv(OUT / "team1_hypothesis_by_years.csv", index=False, encoding="utf-8-sig")
print(f"Пересчёт по годам против файла: max |разница| помесячных объёмов {d.max_abs_diff_kwh.max():.1e} кВт·ч, "
      f"доли самопотребления {(d.self_share_file - d.self_share_recomputed).abs().max():.3f} п. п.")
print(f"Метод «типичного года» (первая версия данных) завышал долю на "
      f"{d.typical_bias_pp.min():.2f}–{d.typical_bias_pp.max():.2f} п. п.")
print(h.to_string(index=False))
print("Готово: results/team1_yearwise_check.csv, results/team1_hypothesis_by_years.csv")
