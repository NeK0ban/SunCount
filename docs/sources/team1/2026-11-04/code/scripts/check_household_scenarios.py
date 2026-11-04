"""Check data consistency, event energy, held-out metrics and unchanged core."""
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from scripts.build_household_scenarios import add_event, simulate

BASE = Path(__file__).resolve().parents[1]


def read(name):
    with (BASE / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def check():
    # An event straddling quarter-hours must preserve kWh, not round duration up.
    event = np.zeros(8)
    add_event(event, .20, .35, 2.0)
    assert abs(float(event.sum()) * .25 - .70) < 1e-12
    assert np.allclose(event[:3], [.4, 2.0, .4])
    config = json.loads((BASE / 'data/household_validation/scenario_parameters.json').read_text())
    records = read('data/household_validation/household_readings.csv')
    components = read('data/household_validation/household_components.csv')
    meta = read('data/household_validation/household_metadata.csv')
    primary = read('results/household_validation_primary.csv')
    scores = read('results/household_validation_metrics.csv')
    predicted = read('results/household_validation_hourly.csv')
    assert len(records) == len(components) == 1680 and len(meta) == len(primary) == 5
    assert len(scores) == 20 and len(predicted) == 3360
    assert len({(r['family_id'],r['interval_start']) for r in records}) == 1680
    grouped = defaultdict(list)
    for row in records:
        grouped[row['family_id']].append(row)
        dt, end = datetime.fromisoformat(row['interval_start']), datetime.fromisoformat(row['interval_end'])
        assert dt.utcoffset() == timedelta(hours=3) and dt.year == 2023
        assert end - dt == timedelta(hours=1)
        assert math.isfinite(float(row['consumption_kwh'])) and float(row['consumption_kwh']) >= 0
    component_map = {(r['family_id'],r['interval_start']): r for r in components}
    for spec in config['households']:
        rows = grouped[spec['family_id']]
        assert len(rows) == 336 and sum(r['partition']=='calibration' for r in rows) == 168
        assert sum(r['partition']=='validation' for r in rows) == 168
        assert all(datetime.fromisoformat(b['interval_start'])-datetime.fromisoformat(a['interval_start']) == timedelta(hours=1) for a,b in zip(rows,rows[1:]))
        replay = simulate(spec)[1]
        assert np.array_equal(replay,np.array([float(r['consumption_kwh']) for r in rows])), 'Replay differs'
        for row in rows:
            part = component_map[(spec['family_id'],row['interval_start'])]
            total = math.fsum(float(v) for k,v in part.items() if k.endswith('_kwh') and k!='total_device_kwh')
            assert abs(total-float(part['total_device_kwh'])) < 1e-10
            assert abs(float(row['consumption_kwh'])-total*spec['meter_gain']) <= .000500001
    record_map={(r['family_id'],r['interval_start']):r for r in records}
    pgroup=defaultdict(list)
    for row in predicted:
        original=record_map[(row['family_id'],row['interval_start'])]
        assert original['partition']=='validation'
        assert float(original['consumption_kwh'])==float(row['consumption_kwh'])
        pgroup[(row['family_id'],row['city'],row['profile_id'])].append(row)
    for metric in scores:
        family,city,profile=metric['family_id'],metric['city'],metric['profile_id']
        test=pgroup[(family,city,profile)]
        assert len(test)==168
        lookup={r['datetime_local']:float(r['load_kwh']) for r in read(f'data/hourly_profiles/{profile}_{city}_8760.csv')}
        lookup={datetime.fromisoformat(k):v for k,v in lookup.items()}
        cal=[r for r in grouped[family] if r['partition']=='calibration']
        factor=math.fsum(float(r['consumption_kwh']) for r in cal)/math.fsum(lookup[datetime.fromisoformat(r['interval_start'])] for r in cal)
        assert abs(factor-float(metric['calibration_scale_factor']))<1e-11
        for row in test:
            assert abs(float(row['raw_model_kwh'])-lookup[datetime.fromisoformat(row['interval_start'])])<1e-12
            assert abs(float(row['scaled_model_kwh'])-float(row['raw_model_kwh'])*factor)<1e-10
        for prefix,col in [('raw','raw_model_kwh'),('scaled','scaled_model_kwh')]:
            ae=[abs(float(r[col])-float(r['consumption_kwh'])) for r in test]
            mae=math.fsum(ae)/168
            rel=[err/float(r['consumption_kwh']) for err,r in zip(ae,test) if float(r['consumption_kwh'])>0]
            assert abs(mae-float(metric[f'{prefix}_hourly_mae_kwh']))<1e-10
            assert abs(100*math.fsum(rel)/len(rel)-float(metric[f'{prefix}_hourly_mape_pct']))<1e-8
    for name,expected in json.loads((BASE/'data/household_validation/previous_core_sha256.json').read_text()).items():
        assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==expected, name
    assert all(p.read_bytes().startswith(b'\xef\xbb\xbf') for p in BASE.rglob('*.csv'))
    print('PASS: 5 households, 1680 hourly records, 15-minute energy conservation, deterministic replay, device-energy reconciliation, 7+7 split, 20 MAE/MAPE comparisons, unchanged core and UTF-8 BOM')


if __name__=='__main__':
    check()
