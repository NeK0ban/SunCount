"""Получение ФАКТИЧЕСКОЙ почасовой многолетней базы PVGIS-SARAH3 2005–2023.

Команда: python -m scripts.fetch_pvgis
На компьютере с доступом к https://re.jrc.ec.europa.eu .
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np

from src.energy.api import BASE, CITIES, HOURS

URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"


def fetch(city: str, tilt: float = 30, azimuth: float = 180,
          startyear: int = 2005, endyear: int = 2023):
    lat, lon = CITIES[city]
    args = dict(lat=lat, lon=lon, pvcalculation=1, peakpower=1,
                loss=14, angle=tilt, aspect=azimuth-180,
                mountingplace="free", usehorizon=1,
                raddatabase="PVGIS-SARAH3", startyear=startyear,
                endyear=endyear, outputformat="json")
    url = URL + "?" + urlencode(args)
    req = Request(url,headers={"User-Agent": "SunCount-research/1.0 (PVGIS open data)"})
    print(f"PVGIS: {city}, {startyear}–{endyear} ...",flush=True)
    with urlopen(req, timeout=240) as r:
        raw = r.read()
    obj = json.loads(raw)
    hourly = obj.get("outputs",{}).get("hourly",[])
    if len(hourly) < (endyear-startyear+1)*8700:
        raise RuntimeError(f"PVGIS выдал только {len(hourly)} часовых записей: {str(obj)[:500]}")
    buckets = defaultdict(list)
    count_samples = 0
    for rec in hourly:
        # PVGIS время UTC: локальное время = UTC + 3; минутные метки опускаем
        utc = datetime.strptime(rec["time"], "%Y%m%d:%H%M")
        local = utc.replace(minute=0) + timedelta(hours=3)
        if not startyear <= local.year <= endyear:
            continue
        if local.month == 2 and local.day == 29:
            continue  # стандартный невисокосный год 8760
        p = max(0., float(rec["P"])/1000.)  # P в W; 1 час => кВт·ч
        buckets[(local.month, local.day, local.hour)].append(p)
        count_samples += 1
    # Среднее по одинаковому локальному часу/дате за 19 лет.
    keys = {(dt.month,dt.day,dt.hour) for dt in HOURS}
    if set(buckets) != keys:
        missing=sorted(keys-set(buckets))
        raise RuntimeError(f"Отсутствуют календарные часы PVGIS: {missing[:10]}")
    solar = np.asarray([np.mean(buckets[(d.month,d.day,d.hour)]) for d in HOURS], dtype=float)
    droot=BASE / "data"
    (droot/"solar_reference").mkdir(exist_ok=True,parents=True)
    (droot/"pvgis_raw").mkdir(exist_ok=True,parents=True)
    rawpath=droot/"pvgis_raw"/f"pvgis_{city}_{startyear}_{endyear}_t{tilt:g}_a{azimuth:g}.json"
    rawpath.write_bytes(raw)
    out=droot/"solar_reference"/f"solar_{city}_tilt{tilt:g}_az{azimuth:g}_1kw.npy"
    np.save(out,solar)
    manifest={
        "status":"PVGIS_SARAH3_2005_2023_MODELLED",
        "city":city,"latitude":lat,"longitude":lon,
        "source_url":url,"api":"PVGIS 5.3 / seriescalc",
        "dataset":"PVGIS-SARAH3; meteorology via PVGIS (ERA5)",
        "startyear":startyear,"endyear":endyear,
        "tilt_degrees":tilt,"azimuth_degrees_clockwise_from_north":azimuth,
        "pvgis_aspect_from_south":azimuth-180,"system_losses_percent":14,
        "horizon":True,"mountingplace":"free","pvtechchoice":"crystSi",
        "timezone":"UTC+03:00, fixed","reference_calendar_year":2023,
        "temporal_method":"mean hourly P for each local month/day/hour (excluding Feb 29)",
        "number_of_hourly_records":len(hourly),
        "number_of_samples_kept":count_samples,
        "yearly_1kw_kwh":float(solar.sum()),
        "monthly_1kw_kwh":[float(solar[[d.month==m for d in HOURS]].sum()) for m in range(1,13)],
        "raw_sha256":hashlib.sha256(raw).hexdigest(),
        "source_data_are_not_household_meter_measurements": True,
    }
    meta_path=droot/"solar_reference"/f"solar_{city}_tilt{tilt:g}_az{azimuth:g}_1kw.meta.json"
    meta_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Готово {city}: {solar.sum():.2f} кВт·ч/кВт за типовой год")
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--tilt",type=float,default=30)
    parser.add_argument("--azimuth",type=float,default=180)
    parser.add_argument("--startyear",type=int,default=2005)
    parser.add_argument("--endyear",type=int,default=2023)
    a=parser.parse_args()
    if a.startyear!=2005 or a.endyear!=2023:
        raise ValueError("Для сопоставимости с ТЗ требуются 2005–2023 годы")
    for city in CITIES:
        fetch(city,a.tilt,a.azimuth,a.startyear,a.endyear)

if __name__=="__main__": main()
