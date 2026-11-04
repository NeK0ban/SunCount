"""Создаёт CSV, годовые контрольные ряды и графики по 19 отдельным годам PVGIS.

python -m scripts.import_uploaded_pvgis
python -m scripts.generate_outputs --mode verified
"""
from __future__ import annotations
import argparse
import csv
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.energy.api import (BASE, CITIES, PORTRAITS, HOUR_MONTH, NIGHT,
                            HOUR_HOD, HOURS, build_profile, simulate, solar_hourly_by_year, solar_hourly)

PV_SIZES=(3,5,10)
YEAR_COLS=["profile_id","city","pv_kw","gen_kwh","load_kwh","self_kwh",
           "export_kwh","import_kwh","import_day_kwh","import_night_kwh",
           "self_share","coverage"]
MON_COLS=["profile_id","city","pv_kw","month","gen_kwh","load_kwh","self_kwh",
          "export_kwh","import_kwh","import_day_kwh","import_night_kwh",
          "self_share","coverage"]


def read_ref():
    with (BASE/"data"/"reference"/"monthly_load_2023.csv").open(encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    d={}
    for row in rows:
        k=(row["profile_id"],row["city"])
        d.setdefault(k,[None]*12)[int(row["month"])-1]=float(row["load_kwh"])
    assert len(d)==8 and all(len(x)==12 and all(v is not None for v in x) for x in d.values())
    return d


def write_csv(path:Path, fields:list[str], rows:list[dict]):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (round(v,9) if isinstance(v,float) else v) for k,v in row.items()})


def annual_record(mon_rows:list[dict]) -> dict:
    first=mon_rows[0]
    yearly={c:first[c] for c in ("profile_id","city","pv_kw")}
    for col in ("gen_kwh","load_kwh","self_kwh","export_kwh","import_kwh",
                "import_day_kwh","import_night_kwh"):
        yearly[col]=float(sum(float(r[col]) for r in mon_rows))
    yearly["self_share"]=100*yearly["self_kwh"]/yearly["gen_kwh"] if yearly["gen_kwh"] else 0.
    yearly["coverage"]=100*yearly["self_kwh"]/yearly["load_kwh"] if yearly["load_kwh"] else 0.
    return yearly


def make_graphs(loads, gens, mode):
    dst=BASE/"reports"/"charts"
    dst.mkdir(exist_ok=True,parents=True)
    city="krasnodar"
    for m,day,label in [(1,15,"winter"),(7,15,"summer")]:
        mask=np.array([dt.month==m and dt.day==day for dt in HOURS])
        x=np.arange(24)
        plt.figure(figsize=(10,4.6))
        plt.plot(x, loads[("day_absent",city)][mask],label="Семья отсутствует днём")
        plt.plot(x, loads[("home_all_day",city)][mask],label="Дома весь день")
        plt.plot(x, gens[(city,5)][mask],label="СЭС 5 кВт")
        plt.title(f"Краснодар | {'зимний' if label=='winter' else 'летний'} день | статус базы: {'DEMO' if mode=='demo' else 'PVGIS 2005–2023'}")
        plt.xlabel("Час (UTC+3)");plt.ylabel("кВт·ч за час")
        plt.xticks(np.arange(0,24,2));plt.legend();plt.grid(alpha=.25)
        plt.tight_layout();plt.savefig(dst/f"day_{label}.png",dpi=140);plt.close()


def generate(mode:str):
    if mode != "verified":
        raise ValueError("Для сдачи поддерживается только verified, с отдельными годами 2005-2023")
    for city in CITIES:
        p=BASE/"data"/"solar_reference"/f"solar_{city}_tilt30_az180_1kw.meta.json"
        if not p.exists():
            raise FileNotFoundError(f"Нет PVGIS кэша: {p}. Запустите python -m scripts.fetch_pvgis")
        meta=json.loads(p.read_text(encoding="utf-8"))
        if meta.get("status")!="PVGIS_SARAH3_2005_2023_MODELLED":
            raise ValueError(f"{city}: входная база не подтверждена как PVGIS 2005–2023")
        pv_years=solar_hourly_by_year(city,1)
        if not np.allclose(pv_years.mean(axis=0),solar_hourly(city,1),atol=1e-12):
            raise ValueError(f"{city}: типичный год не соответствует среднему отдельных лет")
    load_ref=read_ref()
    loads={}; gens={}
    for city in CITIES:
        for kw in PV_SIZES:
            # вычисление PV без нагрузки: генерация пропорциональна мощности
            gen=solar_hourly(city,kw)
            gens[(city,kw)]=gen
            write_csv(BASE/"data"/"hourly_solar"/f"solar_{city}_{kw}kw.csv",
                      ["datetime_local","gen_kwh"],
                      [{"datetime_local":f"{dt:%Y-%m-%d %H:%M}:00+03:00", "gen_kwh":float(v)}
                       for dt,v in zip(HOURS,gen)])
        for portrait in PORTRAITS:
            presence="home_all_day" if portrait=="home_all_day" else "day_absent"
            devices={"ac"} if portrait=="ac" else ({"el_heating"} if portrait=="el_heating" else set())
            load=build_profile(load_ref[(portrait,city)],presence,devices,city)
            loads[(portrait,city)]=load
            write_csv(BASE/"data"/"hourly_profiles"/f"{portrait}_{city}_8760.csv",
                      ["datetime_local","load_kwh"],
                      [{"datetime_local":f"{dt:%Y-%m-%d %H:%M}:00+03:00","load_kwh":float(v)}
                       for dt,v in zip(HOURS,load)])
    mon_all=[]; yearly=[]
    for city in CITIES:
        for portrait in PORTRAITS:
            for kw in PV_SIZES:
                monthly,_,_=simulate(loads[(portrait,city)],kw,city)
                entries=[asdict(replace(o,profile_id=portrait)) for o in monthly]
                mon_all.extend(entries)
                yearly.append(annual_record(entries))
    # Честная проверка гипотезы: одинаковые 3500 кВт·ч/год, всё остальное не меняется.
    hypothesis=[]
    equal_year=3500.
    for city in CITIES:
        annual_profiles={}
        for profile in ("day_absent","home_all_day"):
            arr=loads[(profile,city)]
            annual_profiles[profile]=arr*(equal_year/arr.sum())
        for kw in PV_SIZES:
            res={}
            for profile in ("day_absent","home_all_day"):
                met,_,_=simulate(annual_profiles[profile],kw,city)
                total=annual_record([asdict(replace(m,profile_id=profile)) for m in met])
                res[profile]=total
            p=res["home_all_day"];d=res["day_absent"]
            ratio=p["self_share"]/d["self_share"] if d["self_share"] else 0.
            coverage_ratio=p["coverage"]/d["coverage"] if d["coverage"] else 0.
            hypothesis.append({
                "city":city,"pv_kw":kw,"equal_annual_load_kwh":equal_year,
                "self_share_day_absent_pct":d["self_share"],
                "self_share_home_all_day_pct":p["self_share"],
                "self_share_ratio":ratio,"coverage_day_absent_pct":d["coverage"],
                "coverage_home_all_day_pct":p["coverage"],
                "coverage_ratio":coverage_ratio,
                "hypothesis_ge_1_5":bool(ratio>=1.5),
            })
    out=BASE/"results"
    write_csv(out/"energy_metrics.csv",YEAR_COLS,yearly)
    write_csv(out/"energy_metrics_monthly.csv",MON_COLS,mon_all)
    write_csv(out/"hypothesis_equal_consumption.csv",
              list(hypothesis[0].keys()),hypothesis)

    # Полный аудит: 19 отдельных лет для каждого портрета / города / мощности;
    # проверяем отдельно поквартальные балансы и величину смещения от старого метода.
    year_cols = ["profile_id","city","pv_kw","year"] + [
        "gen_kwh","load_kwh","self_kwh","export_kwh","import_kwh",
        "import_day_kwh","import_night_kwh","self_share","coverage"]
    mon_year_cols = ["profile_id","city","pv_kw","year","month"] + year_cols[4:]
    per_year = []
    per_year_month = []
    typical_comparison = []
    for row in yearly:
        p,city,kw = row["profile_id"],row["city"],row["pv_kw"]
        load=loads[(p,city)]
        pv_years=solar_hourly_by_year(city,kw)
        used=np.minimum(pv_years,load[np.newaxis,:])
        imported=load[np.newaxis,:]-used
        exported=pv_years-used
        for i, year in enumerate(range(2005,2024)):
            mon_subset=[]
            for month in range(1,13):
                mask=HOUR_MONTH==month
                g=float(pv_years[i,mask].sum())
                l=float(load[mask].sum())
                u=float(used[i,mask].sum())
                imp=float(imported[i,mask].sum())
                exp=float(exported[i,mask].sum())
                di=float(imported[i,mask & ~NIGHT].sum())
                ni=float(imported[i,mask & NIGHT].sum())
                rec={"profile_id":p,"city":city,"pv_kw":kw,"year":year,"month":month,
                     "gen_kwh":g,"load_kwh":l,"self_kwh":u,"export_kwh":exp,"import_kwh":imp,
                     "import_day_kwh":di,"import_night_kwh":ni,
                     "self_share":100*u/g if g else 0.,"coverage":100*u/l if l else 0.}
                per_year_month.append(rec)
                mon_subset.append(rec)
            ann=annual_record(mon_subset)
            per_year.append({**ann,"year":year})
        avg_rows=[r for r in per_year if (r['profile_id'],r['city'],r['pv_kw'])==(p,city,kw)]
        for key in ["gen_kwh","load_kwh","self_kwh","import_kwh","export_kwh",
                    "import_day_kwh","import_night_kwh"]:
            assert abs(float(row[key])-np.mean([r[key] for r in avg_rows])) < 1e-7
        typical_use=float(np.minimum(gens[(city,kw)],load).sum())
        typical_share=100*typical_use/row["gen_kwh"] if row["gen_kwh"] else 0.
        typical_coverage=100*typical_use/row["load_kwh"] if row["load_kwh"] else 0.
        typical_comparison.append({
            "profile_id":p,"city":city,"pv_kw":kw,
            "self_kwh_typical_first":typical_use,
            "self_kwh_by_year_first":row["self_kwh"],
            "self_kwh_overestimate":typical_use-row["self_kwh"],
            "self_share_typical_pct":typical_share,
            "self_share_by_year_pct":row["self_share"],
            "self_share_overestimate_pp":typical_share-row["self_share"],
            "coverage_typical_pct":typical_coverage,
            "coverage_by_year_pct":row["coverage"],
            "coverage_overestimate_pp":typical_coverage-row["coverage"],
        })
    write_csv(out/"energy_metrics_per_year.csv",year_cols,per_year)
    write_csv(out/"energy_metrics_monthly_per_year.csv",mon_year_cols,per_year_month)
    write_csv(out/"team1_typical_year_check.csv",list(typical_comparison[0]),typical_comparison)
    assert len(per_year)==456 and len(per_year_month)==5472 and len(typical_comparison)==24
    assert all(r['self_share_overestimate_pp']>=-1e-9 for r in typical_comparison)

    # График теста гипотезы по всем шести комбинациям.
    xs=np.arange(len(hypothesis))
    plt.figure(figsize=(9.4,4.4))
    plt.bar(xs, [h["self_share_ratio"] for h in hypothesis])
    plt.axhline(1.5, linestyle="--", label="Порог гипотезы 1,5")
    plt.xticks(xs, [f"{('Кр' if h['city']=='krasnodar' else 'Мк')} {h['pv_kw']} кВт" for h in hypothesis])
    plt.ylabel("Отношение долей самопотребления")
    plt.title(f"Одинаковый годовой расход: 3500 кВт·ч | {'DEMO' if mode=='demo' else 'PVGIS 2005–2023'}")
    plt.legend();plt.grid(alpha=.2,axis="y");plt.tight_layout()
    plt.savefig(BASE/"reports"/"charts"/"hypothesis_ratio.png",dpi=140)
    plt.close()
    # Проверяем несмещённый почасовой баланс и год-месяц; контракт без скрытых 2023 данных.
    for a in yearly:
        mons=[r for r in mon_all if (r["profile_id"],r["city"],r["pv_kw"])==(a["profile_id"],a["city"],a["pv_kw"])]
        assert len(mons)==12
        for k in ("gen_kwh","load_kwh","self_kwh","export_kwh","import_kwh","import_day_kwh","import_night_kwh"):
            assert abs(float(a[k])-sum(float(r[k]) for r in mons))<1e-8
        assert abs(a["load_kwh"]-a["self_kwh"]-a["import_kwh"])<1e-8
        assert abs(a["gen_kwh"]-a["self_kwh"]-a["export_kwh"])<1e-8
        assert abs(a["import_kwh"]-a["import_day_kwh"]-a["import_night_kwh"])<1e-8
    make_graphs(loads,gens,mode)
    info={"status":mode.upper(),"PVGIS_2005_2023_verified":mode=="verified",
          "calculation_method":"min(load, PV) per each of 19 independent years, monthly sums averaged across years, then percentages calculated",
          "yearwise_rows":len(per_year),"yearwise_monthly_rows":len(per_year_month),
          "typical_year_check_rows":len(typical_comparison),
          "self_share_overestimate_pp_min":min(r['self_share_overestimate_pp'] for r in typical_comparison),
          "self_share_overestimate_pp_max":max(r['self_share_overestimate_pp'] for r in typical_comparison),
          "year":2023,"reference_calendar_only":True,"time_zone":"UTC+03:00",
          "profile_type":"SYNTHETIC, NOT METER MEASUREMENTS",
          "portrait_count":len(PORTRAITS),"city_count":len(CITIES),
          "annual_rows":len(yearly),"monthly_rows":len(mon_all),"hourly_profiles":8,
          "hours_per_profile":8760,
          "annual_generation_1kw_kwh":{city:float(gens[(city,5)].sum()/5) for city in CITIES},
          "hypothesis":hypothesis,
          "source_meta":{city:json.loads((BASE/"data"/"solar_reference"/f"solar_{city}_tilt30_az180_1kw.meta.json").read_text()) for city in CITIES}}
    (out/"validation_report.json").write_text(json.dumps(info,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Status={mode}; annual={len(yearly)} monthly={len(mon_all)} hourly_profiles={len(loads)}")
    for x in hypothesis:
        print(f"{x['city']} {x['pv_kw']}kW share ratio: {x['self_share_ratio']:.3f}; coverage ratio: {x['coverage_ratio']:.3f}; >=1.5: {x['hypothesis_ge_1_5']}")
    return info


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["verified"],default="verified")
    a=p.parse_args()
    generate(a.mode)

if __name__=="__main__":main()
