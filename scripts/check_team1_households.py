"""Проверка № 5 данных команды 1 (поставка 04.11.2026): сценарная сверка пяти домохозяйств и гипотеза 1 по годам.

Что делает (всё пересчитывается независимо от кода команды 1):
  1. household_readings.csv — 5 семей × 336 часов, шаг 1 ч, без пропусков, дубликатов и отрицательных;
     суммы и суточные минимумы/максимумы совпадают с household_metadata.csv; разбиение 7 + 7 суток;
  2. household_components.csv — сумма приборов = total_device_kwh; показания = приборы × масштаб 0,998/1,002;
  3. household_validation_metrics.csv — все 20 сравнений (5 семей × 4 портрета города): MAE, MAPE, WAPE по часам
     и суткам, без калибровки и с калибровкой масштаба по первой неделе — пересчитаны по почасовым профилям 8760;
  4. hypothesis_equal_consumption_per_year.csv — минимумы по годам совпадают с нашим results/team1_hypothesis_by_years.csv.

Важно: все пять семей СМОДЕЛИРОВАНЫ командой 1 (так написано в их методике), это не показания счётчиков.
Критерий приёмки 4 мастер-ТЗ («профили сверены с данными не менее 3 семей») этим не закрывается.

Выход: results/team1_household_check.csv (по одной строке на сравнение: их и наши метрики, расхождение).
Запуск: python scripts/check_team1_households.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HV = ROOT / "data" / "household_validation"
SRC = ROOT / "docs" / "sources" / "team1" / "2026-11-04"
PROFILES = ROOT / "data" / "hourly_profiles"
OUT = ROOT / "results"
T0 = pd.Timestamp("2023-01-01T00:00:00+03:00")   # час 0 почасового профиля 8760 (UTC+3, календарь 2023)
METRICS = ["hourly_mae_kwh", "hourly_mape_pct", "hourly_wape_pct", "daily_mae_kwh", "daily_mape_pct"]


def read(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", **kw)


rd = read(HV / "household_readings.csv", parse_dates=["interval_start"])
meta = read(HV / "household_metadata.csv").set_index("family_id")
comp = read(HV / "household_components.csv", parse_dates=["interval_start"])
met = read(SRC / "household_validation_metrics.csv")

# ----------------------------------------------------------------- 1. полнота и согласованность
problems = []
assert len(rd) == 1680 and rd.family_id.nunique() == 5, "ожидалось 5 семей × 336 часов"
if rd.duplicated(["family_id", "interval_start"]).any() or (rd.consumption_kwh < 0).any():
    problems.append("дубликаты или отрицательные значения в показаниях")
for fid, g in rd.groupby("family_id"):
    g = g.sort_values("interval_start")
    m = meta.loc[fid]
    daily = g.set_index("interval_start").consumption_kwh.resample("D").sum()
    if set(g.interval_start.diff().dropna().dt.total_seconds()) != {3600.0} or len(g) != 336:
        problems.append(f"{fid}: шаг не 1 ч или не 336 часов")
    if abs(g.consumption_kwh.sum() - m.total_kwh) > 1e-6 or abs(daily.min() - m.min_daily_kwh) > 1e-6 \
            or abs(daily.max() - m.max_daily_kwh) > 1e-6:
        problems.append(f"{fid}: суммы не совпадают с household_metadata.csv")
    if g.partition.value_counts().to_dict() != {"calibration": 168, "validation": 168}:
        problems.append(f"{fid}: разбиение не 7 + 7 суток")

# ----------------------------------------------------------------- 2. приборный баланс
dev_cols = [c for c in comp.columns if c.endswith("_kwh") and c != "total_device_kwh"]
dev_err = float((comp[dev_cols].sum(axis=1) - comp.total_device_kwh).abs().max())
j = rd.merge(comp[["family_id", "interval_start", "total_device_kwh"]], on=["family_id", "interval_start"])
scale = j.groupby("family_id").apply(lambda g: g.consumption_kwh.sum() / g.total_device_kwh.sum(), include_groups=False)
if dev_err > 1e-9 or not all(min(abs(s - 0.998), abs(s - 1.002)) < 5e-4 for s in scale):
    problems.append("приборный баланс или масштаб учёта не сходится")

# ----------------------------------------------------------------- 3. пересчёт MAE / MAPE / WAPE
def metrics(actual: np.ndarray, pred: np.ndarray) -> list[float]:
    e = np.abs(pred - actual)
    pos = actual > 0
    da, dp = actual.reshape(7, 24).sum(1), pred.reshape(7, 24).sum(1)
    return [e.mean(), 100 * np.mean(e[pos] / actual[pos]), 100 * e.sum() / actual.sum(),
            np.abs(dp - da).mean(), 100 * np.mean(np.abs(dp - da) / da)]


rows = []
for _, r in met.iterrows():
    g = rd[rd.family_id == r.family_id].sort_values("interval_start")
    prof = read(PROFILES / f"{r.profile_id}_{r.city}_8760.csv").load_kwh.to_numpy()
    model = prof[((g.interval_start - T0).dt.total_seconds() // 3600).astype(int).to_numpy()]
    cal = (g.partition == "calibration").to_numpy()
    actual = g.consumption_kwh.to_numpy()
    k = actual[cal].sum() / model[cal].sum()                  # масштаб — только по первой неделе
    ours = {"calibration_scale_factor": k}
    for prefix, pred in (("raw_", model[~cal]), ("scaled_", model[~cal] * k)):
        ours.update({prefix + name: v for name, v in zip(METRICS, metrics(actual[~cal], pred))})
    diff = max(abs(ours[c] - r[c]) / max(abs(r[c]), 1e-9) for c in ours)
    rows.append({"family_id": r.family_id, "city": r.city, "profile_id": r.profile_id,
                 "primary": bool(r.primary_comparison), **{c: round(ours[c], 6) for c in ours},
                 "max_rel_diff_vs_team1": diff})
res = pd.DataFrame(rows)
if res.max_rel_diff_vs_team1.max() > 1e-9:
    problems.append("метрики команды 1 не воспроизводятся")

# ----------------------------------------------------------------- 4. гипотеза 1 по годам
hy = read(SRC / "hypothesis_equal_consumption_per_year.csv")
ratio_col = next(c for c in hy.columns if "ratio" in c)
yr = hy.groupby(["city", "pv_kw"])[ratio_col].agg(["min", "count", lambda s: int((s >= 1.5).sum())])
yr.columns = ["min", "years", "years_ge_1_5"]
ours_h = read(OUT / "team1_hypothesis_by_years.csv").set_index(["city", "pv_kw"])
yr = yr.join(ours_h.ratio_min_year)
if (yr["min"].round(4) - yr.ratio_min_year).abs().max() > 1e-4:
    problems.append("минимумы гипотезы по годам не совпадают с нашим пересчётом")

OUT.mkdir(exist_ok=True)
res.to_csv(OUT / "team1_household_check.csv", index=False, encoding="utf-8-sig")

prim = res[res.primary]
best = res.loc[res.groupby("family_id").raw_hourly_mae_kwh.idxmin()].set_index("family_id").profile_id
print(f"Показания: 1680 часов, 5 семей; приборный баланс до {dev_err:.0e} кВт·ч; масштаб учёта {sorted(float(s) for s in scale.round(3).unique())}")
print(f"Пересчитано сравнений: {len(res)} (основных {len(prim)}), "
      f"наибольшее расхождение с командой 1: {res.max_rel_diff_vs_team1.max():.0e}")
print(prim[["family_id", "profile_id", "raw_hourly_mae_kwh", "raw_hourly_wape_pct", "raw_daily_mape_pct",
            "calibration_scale_factor"]].round(3).to_string(index=False))
for fid, p in best.items():
    if p != prim.set_index("family_id").profile_id[fid]:
        print(f"  {fid}: по часовому MAE ближе портрет {p}, а не назначенный {prim.set_index('family_id').profile_id[fid]}")
print("Гипотеза 1 по годам:\n" + yr.round(4).to_string())
print("Замечаний нет" if not problems else "ЗАМЕЧАНИЯ:\n  " + "\n  ".join(problems))
print("Готово: results/team1_household_check.csv")
