"""Import user PVGIS-SARAH3 JSON into BOTH 19 x 8760 yearly arrays and a
8760-hour mean calendar used only for plotting. Does not use the network.

Run: python -m scripts.import_uploaded_pvgis
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
import hashlib
import json
import zipfile
import numpy as np
from src.energy.api import BASE, CITIES, HOURS

YEARS = tuple(range(2005, 2024))
RAW = BASE / 'data/pvgis_raw/pvgis_2005_2023_original_upload.zip'
ENDPOINT = 'https://re.jrc.ec.europa.eu/api/v5_3/seriescalc'
CALENDAR = {(dt.month, dt.day, dt.hour): i for i, dt in enumerate(HOURS)}


def _expect(v, exp, msg):
    if v != exp:
        raise ValueError(f'{msg}: {v!r} != {exp!r}')


def import_archive(path: Path = RAW):
    if not path.is_file():
        raise FileNotFoundError(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    names = {city: f'{city}_2005_2023.json' for city in CITIES}
    metas = {}
    with zipfile.ZipFile(path) as z:
        if set(z.namelist()) != set(names.values()):
            raise ValueError('Archive must contain exactly two city JSON files')
        for city, fname in names.items():
            raw = z.read(fname)
            d = json.loads(raw)
            info = d['inputs']
            loc, meteo = info['location'], info['meteo_data']
            fixed, pv = info['mounting_system']['fixed'], info['pv_module']
            lat, lon = CITIES[city]
            if abs(float(loc['latitude'])-lat)>1e-5 or abs(float(loc['longitude'])-lon)>1e-5:
                raise ValueError(f'{city}: coordinates mismatch')
            for actual, expected, field in [
                (meteo['radiation_db'], 'PVGIS-SARAH3', 'radiation_db'),
                (meteo['meteo_db'], 'ERA5', 'meteo_db'),
                (meteo['year_min'], 2005, 'startyear'),
                (meteo['year_max'], 2023, 'endyear'),
                (meteo['use_horizon'], True, 'use_horizon'),
                (fixed['slope']['value'], 30, 'tilt'),
                (fixed['azimuth']['value'], 0, 'PVGIS azimuth south=0'),
                (fixed['type'], 'free-standing', 'mounting'),
                (pv['peak_power'], 1, 'peak_power'),
                (pv['system_loss'], 14, 'loss'),
                (pv['technology'], 'c-Si', 'technology'),
            ]:
                _expect(actual, expected, f'{city}:{field}')
            recs = d['outputs']['hourly']
            _expect(len(recs), 19 * 8760 + 4 * 24, f'{city}: source hours')
            matrix = np.full((len(YEARS), 8760), np.nan, dtype=np.float64)
            first = prev = None
            for rec in recs:
                utc = datetime.strptime(rec['time'], '%Y%m%d:%H%M')
                if first is None:
                    first = utc
                if prev is not None and utc - prev != timedelta(hours=1):
                    raise ValueError(f'{city}: irregular timestamp {prev} -> {utc}')
                prev = utc
                v = float(rec['P']) / 1000
                if not np.isfinite(v) or v < 0:
                    raise ValueError(f'{city}: invalid PV power')
                local = utc + timedelta(hours=3)
                if local.year not in YEARS or (local.month, local.day) == (2, 29):
                    continue
                row = local.year - YEARS[0]
                index = CALENDAR[(local.month, local.day, local.hour)]
                if np.isfinite(matrix[row, index]):
                    raise ValueError(f'{city}: duplicate year-local-hour')
                matrix[row, index] = v
            _expect(first, datetime(2005, 1, 1, 0, 10), f'{city}: first UTC hour')
            _expect(prev, datetime(2023, 12, 31, 23, 10), f'{city}: last UTC hour')
            missing = np.isnan(matrix)
            missing_counts = [int(v) for v in missing.sum(axis=1)]
            if missing_counts != [3] + [0]*18:
                raise ValueError(f'{city}: unexpected gaps by year: {missing_counts}')
            if set(np.flatnonzero(missing[0])) != {0, 1, 2}:
                raise ValueError(f'{city}: missing hours do not match initial night 2005')
            matrix[0, :3] = 0.0  # Explicit documented convention; never impute daylight
            assert np.isfinite(matrix).all() and (matrix >= 0).all()
            typical = matrix.mean(axis=0)
            dest = BASE / 'data' / 'solar_reference'
            dest.mkdir(parents=True, exist_ok=True)
            np.save(dest / f'solar_{city}_tilt30_az180_1kw_by_year.npy', matrix)
            np.save(dest / f'solar_{city}_tilt30_az180_1kw.npy', typical)
            sums = matrix.sum(axis=1)
            months = np.array([dt.month for dt in HOURS])
            monthly_by_year = np.stack([matrix[:, months == m].sum(axis=1) for m in range(1, 13)], axis=1)
            # Counts in original typical-year implementation (3 first hours of 2005 missing)
            sample_counts = Counter({18: 3, 19: 8757})
            args = dict(lat=lat,lon=lon,pvcalculation=1,peakpower=1,pvtechchoice='crystSi',
                        mountingplace='free',loss=14,angle=30,aspect=0,usehorizon=1,
                        raddatabase='PVGIS-SARAH3',startyear=2005,endyear=2023,outputformat='json')
            meta = {
                'status': 'PVGIS_SARAH3_2005_2023_MODELLED',
                'source': 'USER_PROVIDED_PVGIS_JSON_VALIDATED_STRUCTURE',
                'file_name_in_zip': fname,
                'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'original_archive_sha256': sha,
                'data_are_modelled_not_measured': True,
                'input_coordinates': [lat, lon], 'dataset': 'PVGIS-SARAH3',
                'meteo_db': 'ERA5', 'startyear': 2005, 'endyear': 2023,
                'tilt_degrees': 30, 'azimuth_compass_degrees': 180,
                'pvgis_azimuth_from_south': 0, 'pv_size_kw': 1,
                'system_losses_percent': 14, 'horizon': True,
                'time_reference': 'PVGIS UTC timestamps at minute 10; local fixed UTC+3 hour bins',
                'timestamp_source_minutes': 10,
                'year_basis': 2023, 'reference_calendar_only': True,
                'leap_rule': 'discard local Feb29, align month/day/hour to 8760-hour calendar',
                '2005_missing_rule': 'fill local Jan 1 00:00, 01:00, 02:00 with 0 kWh (night)',
                'mean_rule': 'PV-only typical hourly year is for visualisation, NOT for energy balances',
                'balance_rule': 'compute min(load, PV) separately on each year then mean monthly sums',
                'raw_records': len(recs), 'typical_hours': 8760,
                'hourly_sample_count_distribution': {'18': 3, '19': 8757},
                'by_year_array_shape': list(matrix.shape),
                'missing_hours_by_year_before_imputation': dict(zip(map(str, YEARS), missing_counts)),
                'reconstructed_api_url_not_original_request': ENDPOINT+'?'+urlencode(args),
                'yearly_1kw_kwh': float(typical.sum()),
                'monthly_1kw_kwh': [float(v) for v in monthly_by_year.mean(axis=0)],
                'peryear_total_1kw_kwh': {str(y): float(v) for y,v in zip(YEARS, sums)},
                'peryear_month_1kw_kwh': {str(y): [float(v) for v in row] for y,row in zip(YEARS,monthly_by_year)},
            }
            (dest / f'solar_{city}_tilt30_az180_1kw.meta.json').write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            metas[city] = meta
            print(f'{city}: {len(recs):,} source hours; {matrix.shape}; mean={typical.sum():.5f} kWh/kWp; 2005 initial 3h filled with 0')
    return metas


if __name__ == '__main__':
    import_archive()
