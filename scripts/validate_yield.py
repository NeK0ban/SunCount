"""Проверка энергорасчёта выработки (src/config/pv_yield.py) против PVGIS.

Две независимые проверки для Краснодара и Майкопа, наклон 30°, юг (как у команды 1):
1. Модель: наш расчёт (отражение, слабый свет, температура модуля по NOCT, γ из паспорта, потери PVWatts,
   КПД инвертора) на тех же
   почасовых рядах PVGIS 2005–2023 (облучённость плоскости G(i), температура, ветер — архив команды 1),
   против выработки самого PVGIS (P, потери 14 %) по каждому году.
2. Погода: облучённость плоскости типичного метеогода (TMY, наш перенос на плоскость) против средней за
   2005–2023 гг. — насколько TMY представителен.

Выход: results/yield_validation.csv. Запуск: python scripts/validate_yield.py
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config.catalog import panels  # noqa: E402
from src.config.pv_yield import MOUNT_STANDOFF_IN, dc_power, plane_irradiance, specific_yield, system_loss  # noqa: E402

INV_EFF = 0.975
IAM_FACTOR = {c: float(plane_irradiance(c, 30.0, 180.0).effective.sum() / plane_irradiance(c, 30.0, 180.0).poa_global.sum())
              for c in ("krasnodar", "maykop")}
print("Доля облучённости после отражения от стекла (TMY, 30°, юг):", {c: round(v, 4) for c, v in IAM_FACTOR.items()})
rows = []
with zipfile.ZipFile(ROOT / "data" / "raw" / "team1_pvgis" / "pvgis_2005_2023_original_upload.zip") as z:
    for city in ("krasnodar", "maykop"):
        d = json.loads(z.read(f"{city}_2005_2023.json"))
        h = pd.DataFrame(d["outputs"]["hourly"])
        h["year"] = h["time"].str[:4].astype(int)
        for p in panels():
            t_cell = pvlib.temperature.noct_sam(h["G(i)"], h["T2m"], h["WS10m"], p.noct_c, p.eff_pct / 100,
                                                mount_standoff=MOUNT_STANDOFF_IN)
            # в рядах PVGIS есть только полная облучённость плоскости G(i), без деления на прямую и рассеянную, —
            # потери на отражение берём средней годовой долей из нашего расчёта на TMY (IAM_FACTOR)
            dc = dc_power(h["G(i)"] * IAM_FACTOR[city], t_cell, 1.0, p.gamma_pmax_pct_c)
            h["ours"] = np.clip(dc, 0, None) * (1 - system_loss()) * INV_EFF   # Вт·ч на 1 Вт = кВт·ч на 1 кВт за час
            y = h.groupby("year")[["ours", "P"]].sum()
            y["P"] /= 1000
            diff = 100 * (y.ours / y.P - 1)
            tmy_poa = plane_irradiance(city, 30.0, 180.0).poa_global.sum() / 1000
            mean_poa = h.groupby("year")["G(i)"].sum().mean() / 1000
            rows.append({
                "city": city, "panel_id": p.panel_id,
                "pvgis_kwh_per_kw_mean": round(y.P.mean(), 1), "ours_same_weather_kwh_per_kw": round(y.ours.mean(), 1),
                "diff_mean_pct": round(diff.mean(), 2), "diff_min_pct": round(diff.min(), 2),
                "diff_max_pct": round(diff.max(), 2),
                "poa_tmy_kwh_m2": round(tmy_poa, 1), "poa_mean_2005_2023_kwh_m2": round(mean_poa, 1),
                "tmy_vs_mean_pct": round(100 * (tmy_poa / mean_poa - 1), 2),
                "ours_tmy_kwh_per_kw": round(specific_yield(p, city, 30.0, 180.0, INV_EFF * 100), 1),
            })

out = pd.DataFrame(rows)
(ROOT / "results").mkdir(exist_ok=True)
out.to_csv(ROOT / "results" / "yield_validation.csv", index=False, encoding="utf-8-sig")
print(out.to_string(index=False))
