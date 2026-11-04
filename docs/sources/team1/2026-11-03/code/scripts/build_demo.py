"""Создаёт ИСКЛЮЧИТЕЛЬНО предварительный сценарий: не выдавать за PVGIS 19-летние данные."""
from __future__ import annotations
from datetime import date
import json
import math
import numpy as np
from src.energy.api import BASE, CITIES, HOURS

# Выработка PVGIS за ОДИН 2023 год, ранее переданная команде №2, кВт·ч/кВт.
PV_2023 = {
    "krasnodar": [85.87166,42.86078,74.81442,97.03055,123.64693,142.80058,
                  157.79833,160.31448,140.74278,110.06092,49.76179,36.14255],
    "maykop": [98.23410,50.09826,79.56734,101.97163,124.47739,136.73655,
               148.89077,157.90408,137.72269,107.55696,53.99275,42.29799],
}
# Команда №2 сообщила ТОЛЬКО 3 подтверждённых среднемноголетних месяца Краснодара.
TEAM2_KR_MONTHS = {1:48.8,2:66.7,12:49.9}
TEAM2_KR_TOTAL = 1240.0  # округлено командой №2 до целого кВт·ч


def preview_months(city: str) -> np.ndarray:
    raw=np.array(PV_2023[city],dtype=float)
    if city!="krasnodar":
        return raw  # НЕТ данных о многолетнем среднем Майкопа; оставлено 2023!
    out=raw.copy()
    for m,value in TEAM2_KR_MONTHS.items(): out[m-1]=value
    unknown=[i for i in range(12) if (i+1) not in TEAM2_KR_MONTHS]
    remainder=TEAM2_KR_TOTAL-sum(TEAM2_KR_MONTHS.values())
    out[unknown]*=remainder / raw[unknown].sum()
    return out


def make_demo():
    for city,(lat,lon) in CITIES.items():
        monthly=preview_months(city)
        arr=np.zeros(8760,dtype=float)
        # Иллюстративный гладкий суточный профиль солнца, а не PVGIS hourly.
        for j,dt in enumerate(HOURS):
            n=dt.timetuple().tm_yday
            dec=math.radians(23.44)*math.sin(2*math.pi*(284+n)/365)
            phi=math.radians(lat)
            daylen=24/math.pi*math.acos(max(-1.,min(1.,-math.tan(phi)*math.tan(dec))))
            solar_noon=12.15 if city=="krasnodar" else 12.08
            x=abs(dt.hour+0.5-solar_noon)/(daylen/2)
            arr[j]=max(0.,math.cos(x*math.pi/2))**1.65 if x<=1 else 0.
        for m in range(1,13):
            ids=np.array([d.month==m for d in HOURS])
            arr[ids]*=monthly[m-1]/arr[ids].sum()
        path=BASE/"data"/"solar_reference"/f"solar_{city}_tilt30_az180_1kw.npy"
        np.save(path,arr)
        meta={
            "status":"DEMO_NOT_VERIFIED_MULTYEAR_PVGIS",
            "city":city,"coordinates":[lat,lon],"year_calendar":2023,
            "angle":30,"azimuth":180,"loss_percent":14,
            "method":"illustrative daylight profile adjusted to monthly totals",
            "notes":("Krasnodar: Jan/Feb/Dec from team 2, total 1240; "
                     "other 9 months reweighted from 2023; NOT actual PVGIS 19-year data" if city=="krasnodar"
                     else "Maykop: 2023 monthly totals only, NOT multiyear PVGIS"),
            "monthly_kwh_1kw":monthly.tolist(),"annual_kwh_1kw":float(arr.sum()),
            "may_not_be_presented_as_final_pvgis":True,
        }
        path.with_suffix(".meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print("DEMO solar caches generated; NOT official multi-year data.")

if __name__=="__main__":make_demo()
