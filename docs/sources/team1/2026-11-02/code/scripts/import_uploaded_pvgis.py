"""Validate the original uploaded PVGIS JSON and build a 8760-hour typical solar year.

Use: python -m scripts.import_uploaded_pvgis
Then: python -m scripts.generate_outputs --mode verified
No internet required. The uploaded archive is shipped with this project.
"""
from __future__ import annotations
from collections import defaultdict, Counter
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlencode
import hashlib
import json
import zipfile
import numpy as np
from src.energy.api import BASE,CITIES,HOURS

YEARS=range(2005,2024)
RAW=BASE/'data/pvgis_raw/pvgis_2005_2023_original_upload.zip'
ENDPOINT='https://re.jrc.ec.europa.eu/api/v5_3/seriescalc'

def _expect(value,expected,name):
    if value!=expected: raise ValueError(f'{name}: obtained {value!r}, expected {expected!r}')

def import_archive(path:Path=RAW):
    if not path.is_file(): raise FileNotFoundError(path)
    zip_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    names={'krasnodar':'krasnodar_2005_2023.json','maykop':'maykop_2005_2023.json'}
    metas={}
    with zipfile.ZipFile(path) as z:
        if set(z.namelist())!=set(names.values()): raise ValueError('Archive must contain exactly the two city JSON files')
        for city, name in names.items():
            raw=z.read(name); d=json.loads(raw)
            inputs=d['inputs'];loc=inputs['location'];meteo=inputs['meteo_data'];fixed=inputs['mounting_system']['fixed'];pv=inputs['pv_module']
            lat,lon=CITIES[city]
            if abs(float(loc['latitude'])-lat)>1e-5 or abs(float(loc['longitude'])-lon)>1e-5: raise ValueError(f'{city}: coordinates mismatch')
            for v,e,k in [(meteo['radiation_db'],'PVGIS-SARAH3','radiation_db'),(meteo['meteo_db'],'ERA5','meteo_db'),(meteo['year_min'],2005,'startyear'),(meteo['year_max'],2023,'endyear'),(meteo['use_horizon'],True,'horizon'),(fixed['slope']['value'],30,'tilt'),(fixed['azimuth']['value'],0,'PVGIS aspect (south=0)'),(fixed['type'],'free-standing','mounting'),(pv['peak_power'],1,'kW'),(pv['system_loss'],14,'loss'),(pv['technology'],'c-Si','module')]:
                _expect(v,e,f'{city}:{k}')
            records=d['outputs']['hourly']
            expected_count=19*8760+4*24
            _expect(len(records),expected_count,f'{city}: raw records')
            accum=defaultdict(list); peryear=defaultdict(float); peryear_month=defaultdict(float)
            seen=set(); first=None; last=None; prev=None; negative=0
            for r in records:
                utc=datetime.strptime(r['time'],'%Y%m%d:%H%M')
                if utc.minute not in (0,10,20,30,40,50):raise ValueError('Unexpected minutes in timestamp')
                if prev is not None and utc-prev!=timedelta(hours=1):raise ValueError(f'{city}: hourly timestamp gap {prev} to {utc}')
                if utc in seen:raise ValueError(f'{city}: duplicate UTC time {utc}')
                seen.add(utc); prev=utc
                if first is None:first=utc
                last=utc
                power=float(r['P'])
                if not np.isfinite(power) or power<0:raise ValueError(f'{city}: negative / invalid PV power')
                local=utc+timedelta(hours=3)
                # Dec 31 last three UTC slots belong to next local year and are omitted;
                # first three local hours of 2005 aren't present. All are PV-night.
                if 2005<=local.year<=2023 and (local.month,local.day)!=(2,29):
                    v=power/1000.0
                    accum[(local.month,local.day,local.hour)].append(v)
                    peryear[local.year]+=v
                    peryear_month[(local.year,local.month)]+=v
            _expect(first,datetime(2005,1,1,0,10),f'{city}: first UTC record')
            _expect(last,datetime(2023,12,31,23,10),f'{city}: last UTC record')
            keys=[(dt.month,dt.day,dt.hour) for dt in HOURS]
            if set(accum)!=set(keys):raise ValueError(f'{city}: calendar coverage incomplete')
            counts=Counter(map(len,accum.values()))
            if counts!=Counter({19:8757,18:3}):raise ValueError(f'{city}: unexpected source hourly sample counts {counts}')
            series=np.asarray([np.mean(accum[k]) for k in keys],dtype=float)
            assert series.shape==(8760,) and np.isfinite(series).all() and (series>=0).all()
            dest=BASE/'data/solar_reference';dest.mkdir(parents=True,exist_ok=True)
            np.save(dest/f'solar_{city}_tilt30_az180_1kw.npy',series)
            args=dict(lat=lat,lon=lon,pvcalculation=1,peakpower=1,pvtechchoice='crystSi',mountingplace='free',loss=14,angle=30,aspect=0,usehorizon=1,raddatabase='PVGIS-SARAH3',startyear=2005,endyear=2023,outputformat='json')
            meta={
              'status':'PVGIS_SARAH3_2005_2023_MODELLED',
              'source':'USER_PROVIDED_PVGIS_JSON_VALIDATED_STRUCTURE',
              'file_name_in_zip':name,'raw_sha256':hashlib.sha256(raw).hexdigest(),
              'original_archive_sha256':zip_sha,
              'data_are_modelled_not_measured':True,
              'input_coordinates':[lat,lon], 'dataset':'PVGIS-SARAH3','meteo_db':'ERA5',
              'startyear':2005,'endyear':2023,'tilt_degrees':30,'azimuth_compass_degrees':180,
              'pvgis_azimuth_from_south':0,'pv_size_kw':1,'system_losses_percent':14,'horizon':True,
              'time_reference':'PVGIS timestamps UTC; regroup to fixed UTC+3',
              'timestamp_source_minutes':10,
              'year_basis':2023,'reference_calendar_only':True,
              'leap_rule':'discard local Feb29, preserving 8760-hour nonleap reference calendar',
              'mean_rule':'mean P for each local month-day-hour across 2005-2023',
              'hourly_sample_count_distribution':{str(k):v for k,v in sorted(counts.items())},
              'raw_records':len(records),'typical_hours':len(series),
              'reconstructed_api_url_not_original_request':ENDPOINT+'?'+urlencode(args),
              'yearly_1kw_kwh':float(series.sum()),
              'monthly_1kw_kwh':[float(series[[dt.month==m for dt in HOURS]].sum()) for m in range(1,13)],
              'peryear_total_1kw_kwh':{str(y):float(peryear[y]) for y in YEARS},
              'peryear_month_1kw_kwh':{str(y):[float(peryear_month[(y,m)]) for m in range(1,13)] for y in YEARS},
            }
            (dest/f'solar_{city}_tilt30_az180_1kw.meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
            metas[city]=meta
            print(f'{city}: {len(records)} source hours, {series.sum():.5f} kWh/1kWp; source sha256={meta["raw_sha256"][:16]}')
    return metas

if __name__=='__main__':import_archive()
