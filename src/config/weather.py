"""Погода для энергорасчёта: типичный метеорологический год (TMY) PVGIS 5.3 (SARAH3 + ERA5, 2005–2023).

TMY — 12 реальных месяцев из разных лет, выбранных как самые типичные; часы не усредняются, поэтому облачные
и ясные дни сохраняются (в отличие от «типичного года», усреднённого по часам, который завышал самопотребление —
docs/team1/team1_data_check.md, проверка № 4). Исходные файлы: data/raw/pvgis/<город>_tmy.json (scripts/fetch_tmy.py).

Часы приводятся к местному времени UTC+3 и к календарю 2023 года, как почасовые профили команды 1
(data/hourly_profiles/*_8760.csv): элемент i — час i от 01.01 00:00 местного времени.
"""
import json
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
CITIES = {"krasnodar": (45.0355, 38.9753), "maykop": (44.6098, 40.1007)}   # координаты команды 1
UTC_OFFSET_H = 3


def _check(city: str) -> None:
    if city not in CITIES:
        raise ValueError(f"Город: одно из {sorted(CITIES)}, получено {city!r}")


@lru_cache(maxsize=4)
def tmy(city: str) -> pd.DataFrame:
    """8760 часов в UTC (как в PVGIS): время для расчёта положения солнца, GHI, DNI, DHI, температура, ветер."""
    _check(city)
    d = json.loads((RAW / "pvgis" / f"{city}_tmy.json").read_text(encoding="utf-8"))
    rows = d["outputs"]["tmy_hourly"]
    offset_h = float(d["inputs"]["location"].get("irradiance_time_offset", 0.0))
    t = pd.to_datetime([r["time(UTC)"] for r in rows], format="%Y%m%d:%H%M", utc=True)
    df = pd.DataFrame({
        "ghi": [r["G(h)"] for r in rows], "dni": [r["Gb(n)"] for r in rows], "dhi": [r["Gd(h)"] for r in rows],
        "temp_air": [r["T2m"] for r in rows], "wind_speed": [r["WS10m"] for r in rows],
    })
    # момент, к которому относится часовая облучённость PVGIS (сдвиг irradiance_time_offset), — для положения солнца
    df.index = t + pd.to_timedelta(offset_h, unit="h")
    if len(df) != 8760:
        raise ValueError(f"{city}: в TMY {len(df)} часов вместо 8760")
    return df


def to_local(values: np.ndarray) -> np.ndarray:
    """Часы UTC (01.01 00:00 UTC …) → местное время UTC+3 (01.01 00:00 местного …), календарь без 29 февраля."""
    return np.roll(np.asarray(values, dtype=float), UTC_OFFSET_H)


@lru_cache(maxsize=1)
def local_calendar() -> pd.DataFrame:
    """Месяц и час местного времени для каждого из 8760 часов (как в профилях команды 1, 2023 год)."""
    idx = pd.date_range("2023-01-01", periods=8760, freq="h")
    return pd.DataFrame({"month": idx.month, "hour": idx.hour})


@lru_cache(maxsize=4)
def design_min_temp(city: str) -> float:
    """Минимальная температура воздуха за 2005–2023 гг. (почасовые ряды PVGIS из поставки команды 1) — для проверки
    напряжения цепочки панелей в мороз. Если архива нет — минимум TMY."""
    _check(city)
    z = RAW / "team1_pvgis" / "pvgis_2005_2023_original_upload.zip"
    if z.exists():
        with zipfile.ZipFile(z) as f:
            d = json.loads(f.read(f"{city}_2005_2023.json"))
        return float(min(r["T2m"] for r in d["outputs"]["hourly"]))
    return float(tmy(city).temp_air.min())
