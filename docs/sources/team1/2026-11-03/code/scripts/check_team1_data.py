"""Cross-check the yearwise CSV exports and the declared 19 x 8760 PV arrays.

python -m scripts.check_team1_data
"""
from __future__ import annotations
import csv
from pathlib import Path
import numpy as np
from src.energy.api import BASE, CITIES, PORTRAITS, solar_hourly_by_year

NUMS=['gen_kwh','load_kwh','self_kwh','export_kwh','import_kwh','import_day_kwh','import_night_kwh']

def read(filename):
    with (BASE/'results'/filename).open(encoding='utf8',newline='') as f:
        return list(csv.DictReader(f))


def check():
    annual=read('energy_metrics.csv')
    monthly=read('energy_metrics_monthly.csv')
    year=read('energy_metrics_per_year.csv')
    bymonth=read('energy_metrics_monthly_per_year.csv')
    comparison=read('team1_typical_year_check.csv')
    hypothesis=read('hypothesis_equal_consumption.csv')
    assert (len(annual),len(monthly),len(year),len(bymonth),len(comparison),len(hypothesis)) == (24,288,456,5472,24,6)
    assert len({(x['profile_id'],x['city'],x['pv_kw'],x['month']) for x in monthly})==288
    assert len({(x['profile_id'],x['city'],x['pv_kw'],x['year'],x['month']) for x in bymonth})==5472
    for city in CITIES:
        assert solar_hourly_by_year(city,1).shape == (19,8760)
    for r in annual:
        k=(r['profile_id'],r['city'],r['pv_kw'])
        mr=[m for m in monthly if (m['profile_id'],m['city'],m['pv_kw'])==k]
        yr=[m for m in year if (m['profile_id'],m['city'],m['pv_kw'])==k]
        assert len(mr)==12 and len(yr)==19
        for col in NUMS:
            assert abs(float(r[col])-sum(float(m[col]) for m in mr))<1e-6
            assert abs(float(r[col])-np.mean([float(m[col]) for m in yr]))<1e-6
        assert abs(float(r['self_share'])-100*float(r['self_kwh'])/float(r['gen_kwh']))<1e-7
        assert abs(float(r['coverage'])-100*float(r['self_kwh'])/float(r['load_kwh']))<1e-7
    for r in bymonth:
        assert abs(float(r['gen_kwh'])-float(r['self_kwh'])-float(r['export_kwh']))<1e-6
        assert abs(float(r['load_kwh'])-float(r['self_kwh'])-float(r['import_kwh']))<1e-6
        assert abs(float(r['import_kwh'])-float(r['import_day_kwh'])-float(r['import_night_kwh']))<1e-6
    assert all(float(r['self_share_overestimate_pp'])>=-1e-9 for r in comparison)
    assert all(float(r['self_share_ratio'])>=1.5 for r in hypothesis)
    print('PASS: 24 annual, 288 monthly, 456 per-year, 5472 per-year-month, 24 bias checks, 6 hypothesis tests')

if __name__ == '__main__':check()
