"""Энергорасчёт выработки СЭС по паспорту панели (метаданным) и погоде — почасово, на типичный метеогод.

Цепочка расчёта для каждого часа:
1. Положение солнца (pvlib.solarposition) для координат города.
2. Облучённость плоскости панелей при заданных наклоне и азимуте: прямая + рассеянная (модель Хэя — Дэвиса)
   + отражённая от земли (альбедо 0,2) — pvlib.irradiance.get_total_irradiance.
3. Потери на отражение от стекла при косом падении прямого света — физическая модель IAM (pvlib.iam.physical).
4. Температура модуля по паспортной NOCT, КПД модуля и ветру — модель NOCT SAM (pvlib.temperature.noct_sam).
5. Мощность постоянного тока одной панели: P = Pmax × G_эфф / 1000 × η_слабый_свет(G_эфф) × (1 + γ × (T_модуля − 25)),
   γ — температурный коэффициент мощности из паспорта (как в модели PVWatts); η_слабый_свет — снижение КПД
   кристаллического кремния при слабом свете по модели Хульда (её использует PVGIS; Huld et al., 2011,
   коэффициенты c-Si из pvlib.pvarray.huld) при 25 °C.
6. Потери системы (загрязнение, рассогласование, провода, деградация первого часа, паспортный допуск,
   доступность) — по умолчаниям NREL PVWatts; затенение — по выбору пользователя.
7. Переменный ток: КПД инвертора (евро-КПД из паспорта) и ограничение номинальной мощностью инвертора.

Тыловая сторона двусторонних панелей не учитывается: на скатной крыше прирост мал (консервативно).
Результат — кВт·ч за каждый из 8760 часов в местном времени (src/config/weather.py: to_local).
Проверка модели против почасовых рядов PVGIS — scripts/validate_yield.py, results/yield_validation.csv.
"""
from functools import lru_cache

import numpy as np
import pandas as pd
import pvlib

from .catalog import Inverter, Panel
from .weather import CITIES, tmy, to_local

ALBEDO = 0.20
MOUNT_STANDOFF_IN = 3.0   # зазор между панелью и кровлей ~7–8 см (рейки) — поправка NOCT SAM +2 °C
# Потери системы, доли (NREL PVWatts v5, умолчания; Dobos, NREL/TP-6A20-62641, 2014)
LOSSES = {"soiling": 0.02, "mismatch": 0.02, "wiring": 0.02, "connections": 0.005, "lid": 0.015,
          "nameplate": 0.01, "availability": 0.03}
SHADING = {"none": 0.0, "light": 0.03}   # 3 % — умолчание PVWatts для затенения


def system_loss(shading: str = "none") -> float:
    if shading not in SHADING:
        raise ValueError(f"Затенение: одно из {sorted(SHADING)}, получено {shading!r}")
    keep = np.prod([1 - v for v in LOSSES.values()]) * (1 - SHADING[shading])
    return float(1 - keep)


def _check_geometry(tilt: float, azimuth: float) -> None:
    if not 0 <= tilt <= 90:
        raise ValueError(f"Наклон панелей 0–90°, получено {tilt}")
    if not 0 <= azimuth <= 360:
        raise ValueError(f"Азимут 0–360° (180 — юг), получено {azimuth}")


def low_light_factor(g_eff) -> np.ndarray:
    """Относительный КПД при облучённости G (Вт/м²) и 25 °C по модели Хульда для c-Si: 1 при 1000 Вт/м², ниже при
    слабом свете. Температурную часть модели не берём — её даёт паспортный γ."""
    g = np.asarray(g_eff, dtype=float)
    rel = np.asarray(pvlib.pvarray.huld(np.where(g > 0, g, 1.0), 25.0, 1.0, cell_type="csi"), dtype=float)
    return np.where(g > 0, rel / (np.where(g > 0, g, 1.0) / 1000), 0.0)


def dc_power(g_eff, t_cell, pmax_w: float, gamma_pct_c: float) -> np.ndarray:
    """Мощность постоянного тока панели, Вт: паспортные Pmax и γ, слабый свет по Хульду."""
    g = np.clip(np.asarray(g_eff, dtype=float), 0, None)
    return pmax_w * g / 1000 * low_light_factor(g) * (1 + gamma_pct_c / 100 * (np.asarray(t_cell, dtype=float) - 25))


@lru_cache(maxsize=64)
def plane_irradiance(city: str, tilt: float, azimuth: float) -> pd.DataFrame:
    """Облучённость плоскости панелей, Вт/м² (UTC, как TMY): poa_global, эффективная (с IAM), температура, ветер."""
    _check_geometry(tilt, azimuth)
    w = tmy(city)
    lat, lon = CITIES[city]
    sp = pvlib.solarposition.get_solarposition(w.index, lat, lon)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt, surface_azimuth=azimuth, solar_zenith=sp.apparent_zenith, solar_azimuth=sp.azimuth,
        dni=w.dni, ghi=w.ghi, dhi=w.dhi, dni_extra=pvlib.irradiance.get_extra_radiation(w.index),
        model="haydavies", albedo=ALBEDO)
    aoi = pvlib.irradiance.aoi(tilt, azimuth, sp.apparent_zenith, sp.azimuth)
    iam = pvlib.iam.physical(aoi).fillna(0.0)
    diffuse = poa.poa_sky_diffuse.fillna(0) + poa.poa_ground_diffuse.fillna(0)
    effective = (poa.poa_direct.fillna(0) * iam + diffuse).clip(lower=0)
    return pd.DataFrame({"poa_global": poa.poa_global.fillna(0).clip(lower=0), "effective": effective,
                         "temp_air": w.temp_air, "wind_speed": w.wind_speed})


@lru_cache(maxsize=256)
def panel_dc_w(panel: Panel, city: str, tilt: float, azimuth: float) -> np.ndarray:
    """Мощность постоянного тока одной панели, Вт, 8760 часов в местном времени — до потерь системы."""
    p = plane_irradiance(city, tilt, azimuth)
    t_cell = pvlib.temperature.noct_sam(
        poa_global=p.poa_global, temp_air=p.temp_air, wind_speed=p.wind_speed, noct=panel.noct_c,
        module_efficiency=panel.eff_pct / 100, effective_irradiance=p.effective,
        mount_standoff=MOUNT_STANDOFF_IN)
    dc = dc_power(p.effective, t_cell, panel.pmax_w, panel.gamma_pmax_pct_c)
    out = to_local(np.clip(np.nan_to_num(np.asarray(dc, dtype=float)), 0, None))
    out.flags.writeable = False
    return out


def ac_kwh(panel: Panel, n_panels: int, inverter: Inverter, city: str, tilt: float = 30, azimuth: float = 180,
           shading: str = "none") -> np.ndarray:
    """Выработка станции на выходе инвертора, кВт·ч за каждый из 8760 часов (местное время)."""
    if n_panels < 1:
        raise ValueError("Число панелей должно быть не меньше 1")
    dc = panel_dc_w(panel, city, tilt, azimuth) * n_panels * (1 - system_loss(shading))
    ac = np.minimum(dc * inverter.euro_eff_pct / 100, inverter.ac_kw * 1000)
    return ac / 1000


def specific_yield(panel: Panel, city: str, tilt: float = 30, azimuth: float = 180, inverter_eff_pct: float = 97.5,
                   shading: str = "none") -> float:
    """Годовая выработка на 1 кВт панелей без ограничения инвертором, кВт·ч/кВт — для сравнения с PVGIS."""
    dc = panel_dc_w(panel, city, tilt, azimuth) * (1 - system_loss(shading))
    return float(dc.sum() * inverter_eff_pct / 100 / panel.pmax_w)
