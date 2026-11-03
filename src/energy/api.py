"""API SunCount: 8760 потребления, PV-выработка, помесячные балансы.

Без накопителя. UTC+3 без сезонного перевода. Работает с локальным файлом
солнечной генерации, который создаёт scripts.fetch_pvgis или demo-сборка.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from src.econ.exchange import MonthlyMetrics

BASE = Path(__file__).resolve().parents[2]
REF_YEAR = 2023  # 365 дней (8760 ч); год-маска, не год метеоданных
HOURS = [datetime(REF_YEAR, 1, 1) + timedelta(hours=i) for i in range(8760)]
HOUR_MONTH = np.array([dt.month for dt in HOURS])
HOUR_DAY = np.array([dt.day for dt in HOURS])
HOUR_HOD = np.array([dt.hour for dt in HOURS])
HOUR_WEEKDAY = np.array([dt.weekday() for dt in HOURS])
NIGHT = (HOUR_HOD < 7) | (HOUR_HOD >= 23)

PORTRAITS: dict[str, str] = {
    "day_absent": "Семья отсутствует днём",
    "home_all_day": "Кто-то находится дома весь день",
    "ac": "Дом с кондиционером",
    "el_heating": "Дом с электроотоплением",
}
CITIES = {
    "krasnodar": (45.0355, 38.9753),
    "maykop": (44.6098, 40.1007),
}
APPLIANCES = {"ac", "el_heating", "pump", "el_stove"}


def _validate_city(city: str) -> None:
    if city not in CITIES:
        raise ValueError(f"Неизвестный город {city!r}; ожидается {list(CITIES)}")


def build_profile(monthly_kwh: list[float], presence: str,
                  appliances: set[str], city: str = "krasnodar") -> np.ndarray:
    """Вернуть 8760 кВт·ч за час, сгруппированных по местному UTC+3.

    Месячные объемы точны (с учетом float); распределение по часам —
    воспроизводимый синтетический профиль; это НЕ счётчики реальных семей.
    Приборы меняют распределение по времени, но не месячные суммы.
    """
    _validate_city(city)
    monthly = np.asarray(monthly_kwh, dtype=float)
    if monthly.shape != (12,) or not np.all(np.isfinite(monthly)) or np.any(monthly < 0):
        raise ValueError("monthly_kwh: ровно 12 конечных неотрицательных чисел")
    if presence not in {"day_absent", "home_all_day"}:
        raise ValueError("presence должен быть day_absent или home_all_day")
    appliances = set(appliances)
    if not appliances <= APPLIANCES:
        raise ValueError(f"Неизвестные приборы: {appliances - APPLIANCES}")

    h = HOUR_HOD
    weekend = HOUR_WEEKDAY >= 5
    # Плавная фоновая нагрузка, работа и бытовые пики.
    background = 0.43 + 0.11 * np.cos(2 * np.pi * (h - 21) / 24)
    breakfast = 1.5 * np.exp(-0.5 * ((h - 7.5) / 1.5)**2)
    dinner = 2.1 * np.exp(-0.5 * ((h - 20.0) / 2.1)**2)
    if presence == "day_absent":
        occupancy = np.where((h >= 9) & (h < 17) & ~weekend, 0.10, 0.38)
        breakfast *= 1.22
        dinner *= 1.20
    else:
        occupancy = np.where((h >= 9) & (h < 18), 1.65, 0.45)
        breakfast *= 0.92
        dinner *= 0.88
    weights = background + breakfast + dinner + occupancy
    # На выходных распределение (а не сумма месяца) меняется.
    weights += weekend * np.where((h >= 11) & (h <= 17), 0.48, 0.07)
    if "ac" in appliances:
        season = np.where(np.isin(HOUR_MONTH, [6, 7, 8]), 1.,
                          np.where(np.isin(HOUR_MONTH, [5, 9]), 0.42, 0.03))
        weights += 2.4 * season * np.exp(-0.5 * ((h - 15.5) / 3.4)**2)
    if "el_heating" in appliances:
        winter = np.where(np.isin(HOUR_MONTH, [11, 12, 1, 2]), 1.,
                          np.where(np.isin(HOUR_MONTH, [3, 4, 10]), 0.55, 0.03))
        weights += winter * (1.5 + 0.65 * np.cos(2*np.pi*(h - 4)/24))
    if "pump" in appliances:
        weights += 1.45 * (np.isin(h, [8, 9, 13, 17, 18]))
    if "el_stove" in appliances:
        weights += 1.5 * np.exp(-0.5 * ((h-12.5)/1.3)**2)
        weights += 1.9 * np.exp(-0.5 * ((h-19.5)/1.3)**2)
    if np.any(weights <= 0):
        raise AssertionError("Профиль мощности содержит неположительный вес")
    load = np.empty(8760, dtype=float)
    for month in range(1,13):
        idx = HOUR_MONTH == month
        w = weights[idx]
        load[idx] = w/w.sum() * monthly[month-1]
    return load


def solar_hourly(city: str, pv_kw: float, tilt: float = 30,
                 azimuth: float = 180) -> np.ndarray:
    """Локальный почасовой кэш 1 кВт; нельзя незаметно игнорировать угол.

    Для новой геометрии сначала запустить fetch_pvgis с её параметрами.
    """
    _validate_city(city)
    if not np.isfinite(pv_kw) or pv_kw <= 0:
        raise ValueError("pv_kw должно быть положительным конечным")
    if not 0 <= tilt <= 90 or not 0 <= azimuth < 360:
        raise ValueError("tilt: 0..90, azimuth: 0..360 (без 360)")
    filename = f"solar_{city}_tilt{tilt:g}_az{azimuth:g}_1kw.npy"
    path = BASE / "data" / "solar_reference" / filename
    if not path.exists():
        raise FileNotFoundError(f"Нет солнечной базы {path}. Сначала запустите fetch_pvgis.py")
    arr = np.load(path, allow_pickle=False)
    if arr.shape != (8760,) or not np.all(np.isfinite(arr)) or np.any(arr < 0):
        raise ValueError(f"Повреждён кэш солнечной выработки {path}")
    return arr.astype(float) * pv_kw


def simulate(load_8760: np.ndarray, pv_kw: float, city: str,
             tilt: float = 30, azimuth: float = 180) -> tuple[list[MonthlyMetrics], np.ndarray, np.ndarray]:
    """12 MonthlyMetrics + 8760 нагрузки + 8760 выработки (кВт·ч/час).

    profile_id='custom' (в сигнатуре нет profile_id); для готовых портретов
    экспортер заменяет его через dataclasses.replace.
    """
    load = np.asarray(load_8760, dtype=float)
    if load.shape != (8760,) or not np.all(np.isfinite(load)) or np.any(load < 0):
        raise ValueError("load_8760: 8760 конечных неотрицательных значений")
    gen = solar_hourly(city, pv_kw, tilt, azimuth)
    self_use = np.minimum(gen, load)
    grid_import = load - self_use
    grid_export = gen - self_use
    out = []
    for month in range(1, 13):
        idx = HOUR_MONTH == month
        g = float(gen[idx].sum())
        l = float(load[idx].sum())
        s = float(self_use[idx].sum())
        imp = float(grid_import[idx].sum())
        exp = float(grid_export[idx].sum())
        day_imp = float(grid_import[idx & ~NIGHT].sum())
        night_imp = float(grid_import[idx & NIGHT].sum())
        out.append(MonthlyMetrics(
            profile_id="custom", city=city, pv_kw=float(pv_kw), month=month,
            gen_kwh=g, load_kwh=l, self_kwh=s,
            export_kwh=exp, import_kwh=imp,
            import_day_kwh=day_imp, import_night_kwh=night_imp,
            self_share=100*s/g if g else 0.0,
            coverage=100*s/l if l else 0.0,
        ))
    if not np.allclose(load, self_use + grid_import, atol=1e-10):
        raise AssertionError("Нарушен баланс потребления")
    if not np.allclose(gen, self_use + grid_export, atol=1e-10):
        raise AssertionError("Нарушен баланс генерации")
    return out, load.copy(), gen
