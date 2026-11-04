"""Generate five regional household scenarios and compare saved portraits.

python -m scripts.build_household_scenarios
The generator does not read the saved portraits or reference monthly totals.
Only the comparison stage reads those files. Provenance: docs/household_validation.md.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=3))
PROFILES = ('day_absent', 'home_all_day', 'ac', 'el_heating')
COMPONENTS = ('background', 'lighting', 'cooking', 'hot_water', 'electronics', 'laundry', 'dishwasher', 'misc', 'ac', 'heating')


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def add_event(power, start_hour, duration_hour, kw):
    """Integrate an arbitrary event into quarter-hour mean powers exactly."""
    if duration_hour < 0 or kw < 0:
        raise ValueError('Negative event duration or power')
    left = np.arange(len(power)) / 4
    overlap = np.maximum(0, np.minimum(left + .25, start_hour + duration_hour) - np.maximum(left, start_hour))
    power += kw * overlap / .25


def simulate(spec):
    rng = np.random.default_rng(spec['seed'])
    start = datetime.fromisoformat(spec['start']).replace(tzinfo=TZ)
    n = 14 * 96
    clock = np.array([(i % 96) / 4 for i in range(n)])
    power = {name: np.zeros(n) for name in COMPONENTS}
    presence = np.ones(n, dtype=bool)
    temperature = np.empty(n)
    day_weather = 0.0
    for day in range(14):
        day_start = start + timedelta(days=day)
        weekend = day_start.weekday() >= 5
        local = np.arange(96) / 4
        wake = float(np.clip(rng.normal(8.1 if weekend else 6.9, .4), 5.8, 10))
        leave = float(rng.normal(8.1, .25))
        arrive = float(rng.normal(18.0, .6))
        away = np.zeros(96, dtype=bool)
        if spec['presence'] == 'day_absent' and not weekend:
            away = (local >= leave) & (local < arrive)
        elif weekend and rng.random() < .6:
            away = (local >= 12.0) & (local < 12.0 + rng.uniform(1, 3))
        elif spec['presence'] == 'home_all_day' and rng.random() < .25:
            away = (local >= 14) & (local < 15.5)
        mask = slice(day * 96, (day + 1) * 96)
        presence[mask] = ~away
        day_weather = .7 * day_weather + rng.normal(0, spec['weather_daily_sd_c'])
        temperature[mask] = spec['outdoor_mean_c'] + day_weather + spec['outdoor_diurnal_c'] * np.cos(2 * np.pi * (local - 15) / 24)
        # Continuous background, including refrigerator cycles; powers are assumed.
        fridge = .115 * (np.sin(2 * np.pi * (local + rng.uniform(0, 1.8)) / 1.5) > .15)
        power['background'][mask] = spec['background_kw'] * rng.lognormal(0, .06, 96) + fridge
        dark = ((local < spec['daylight_start']) | (local >= spec['daylight_end']))
        awake = (local >= wake) & (local < 23.0)
        power['lighting'][mask] = (~away & dark & awake) * rng.uniform(.07, .14)
        d0 = day * 24
        # Cooking energy is integrated over real event durations, not whole-hour on/off.
        meals = [(wake + .3, rng.uniform(.18, .32), rng.uniform(1.1, 1.8)),
                 (arrive + .7 if not weekend else 18.8, rng.uniform(.35, .65), rng.uniform(1.4, 2.1))]
        if weekend or spec['presence'] == 'home_all_day':
            meals.append((rng.uniform(12.0, 13.5), rng.uniform(.25, .5), rng.uniform(1.2, 1.8)))
        for when, duration, kw in meals:
            add_event(power['cooking'], d0 + when, duration, kw)
            add_event(power['cooking'], d0 + when + .2, rng.uniform(.04, .08), 1.9)
        if spec['water_heater']:
            for when in [wake - .2, 19.5, 21.3]:
                add_event(power['hot_water'], d0 + when + rng.uniform(-.3, .3),
                          rng.uniform(.3, .55) * spec['persons'] / 3, 2.0)
        add_event(power['electronics'], d0 + 19 + rng.uniform(-.3, .3), rng.uniform(3.1, 4.0), .15)
        if spec['presence'] == 'home_all_day' or weekend:
            add_event(power['electronics'], d0 + 9.5, rng.uniform(3, 6), .12)
        if rng.random() < .48:
            washing = rng.uniform(10.0, 15.0) if weekend or spec['presence'] == 'home_all_day' else rng.uniform(19, 20)
            add_event(power['laundry'], d0 + washing, .35, 1.8)
            add_event(power['laundry'], d0 + washing + .35, 1.2, .10)
        if rng.random() < .70:
            when = rng.uniform(20.0, 21.5)
            add_event(power['dishwasher'], d0 + when, .35, 1.7)
            add_event(power['dishwasher'], d0 + when + 1.1, .20, 1.7)
            add_event(power['dishwasher'], d0 + when + .35, .75, .05)
        for _ in range(int(rng.integers(2, 5))):
            when = rng.choice([wake + .5, 18.5, 21.0]) + rng.uniform(-.2, .2)
            add_event(power['misc'], d0 + when, rng.uniform(.08, .20), rng.uniform(.15, .6))
        if weekend and rng.random() < .65:
            add_event(power['misc'], d0 + 11, .4, .75)

    # Thermal building model: weather is a scenario input, not historical meteorology.
    indoor = spec['indoor_initial_c']
    thermostat_on = False
    for i in range(n):
        internal_gain = .10 + (.10 if presence[i] else 0)
        solar_gain = spec['solar_gain_kw'] * max(0.0, np.sin(np.pi * (clock[i] - 7) / 13)) if 7 < clock[i] < 20 else 0.0
        hvac_heat = 0.0
        if spec['profile_id'] == 'ac':
            setpoint = 26.0 if presence[i] else 28.5
            if indoor > setpoint + .4:
                thermostat_on = True
            elif indoor < setpoint - .4:
                thermostat_on = False
            cooling = spec['ac_electric_kw'] if thermostat_on else 0.0
            power['ac'][i] = cooling + (.035 if presence[i] else 0.0)
            hvac_heat = -spec['ac_cop'] * cooling
        elif spec['profile_id'] == 'el_heating':
            setpoint = 21.0 if presence[i] else 18.0
            if indoor < setpoint - .35:
                thermostat_on = True
            elif indoor > setpoint + .35:
                thermostat_on = False
            power['heating'][i] = spec['heater_kw'] if thermostat_on else 0.0
            hvac_heat = power['heating'][i]
        indoor += .25 * (hvac_heat + internal_gain + solar_gain - spec['heat_loss_kw_per_c'] * (indoor - temperature[i])) / spec['thermal_capacity_kwh_per_c']

    total = sum(power.values())
    if np.max(total) > spec['connection_kw']:
        raise ValueError(f"Scenario {spec['family_id']} exceeds assumed connection capacity")
    hourly_components = {name: values.reshape(336, 4).sum(axis=1) * .25 for name, values in power.items()}
    energy = sum(hourly_components.values())
    readings = np.round(energy * spec['meter_gain'], 3)
    return start, readings, hourly_components, temperature.reshape(336, 4).mean(axis=1), presence.reshape(336, 4).mean(axis=1), float(np.max(total))


def metrics(actual, forecast):
    error = np.abs(actual - forecast)
    positive = actual > 0
    return {'mae_kwh': float(error.mean()), 'mape_pct': float(100 * np.mean(error[positive] / actual[positive])),
            'wape_pct': float(100 * error.sum() / actual.sum()), 'mape_excluded_zeros': int((~positive).sum())}


def read_portrait(profile, city):
    with (BASE / f'data/hourly_profiles/{profile}_{city}_8760.csv').open(encoding='utf-8-sig') as stream:
        return {datetime.fromisoformat(r['datetime_local']): float(r['load_kwh']) for r in csv.DictReader(stream)}


def build():
    data_dir = BASE / 'data/household_validation'
    config = json.loads((data_dir / 'scenario_parameters.json').read_text())
    all_readings, all_components, metadata, all_metrics, primary, predictions, daily = [], [], [], [], [], [], []
    for spec in config['households']:
        start, energy, components, outdoor, occupied, peak = simulate(spec)
        family, city = spec['family_id'], spec['city']
        dates = [start + timedelta(hours=i) for i in range(336)]
        for i, dt in enumerate(dates):
            all_readings.append({'family_id': family, 'city': city, 'profile_id': spec['profile_id'],
                'interval_start': dt.isoformat(), 'interval_end': (dt + timedelta(hours=1)).isoformat(),
                'consumption_kwh': float(energy[i]), 'occupied_fraction': float(occupied[i]),
                'partition': 'calibration' if i < 168 else 'validation'})
            all_components.append({'family_id': family, 'interval_start': dt.isoformat(),
                **{name + '_kwh': float(values[i]) for name, values in components.items()},
                'total_device_kwh': float(sum(values[i] for values in components.values())),
                'outdoor_temperature_c': float(outdoor[i])})
        metadata.append({'family_id': family, 'city': city, 'profile_id': spec['profile_id'],
            'persons': spec['persons'], 'area_m2': spec['area_m2'], 'start': start.isoformat(),
            'end_exclusive': (start + timedelta(days=14)).isoformat(), 'days': 14, 'hours': 336,
            'calibration_days': 7, 'validation_days': 7, 'total_kwh': float(energy.sum()),
            'min_daily_kwh': float(energy.reshape(14, 24).sum(axis=1).min()),
            'max_daily_kwh': float(energy.reshape(14, 24).sum(axis=1).max()), 'peak_15min_kw': peak})
        for profile in PROFILES:
            portrait = read_portrait(profile, city)
            raw = np.array([portrait[d] for d in dates])
            scale = float(energy[:168].sum() / raw[:168].sum())
            y, before, after = energy[168:], raw[168:], raw[168:] * scale
            a, b = metrics(y, before), metrics(y, after)
            row = {'family_id': family, 'city': city, 'profile_id': profile, 'primary_comparison': profile == spec['profile_id'],
                'validation_hours': 168, 'validation_days': 7, 'actual_validation_kwh': float(y.sum()),
                'raw_model_validation_kwh': float(before.sum()), 'calibration_scale_factor': scale,
                'scaled_model_validation_kwh': float(after.sum()),
                'raw_hourly_mae_kwh': a['mae_kwh'], 'raw_hourly_mape_pct': a['mape_pct'], 'raw_hourly_wape_pct': a['wape_pct'],
                'scaled_hourly_mae_kwh': b['mae_kwh'], 'scaled_hourly_mape_pct': b['mape_pct'], 'scaled_hourly_wape_pct': b['wape_pct'],
                'raw_daily_mae_kwh': metrics(y.reshape(7,24).sum(1), before.reshape(7,24).sum(1))['mae_kwh'],
                'raw_daily_mape_pct': metrics(y.reshape(7,24).sum(1), before.reshape(7,24).sum(1))['mape_pct'],
                'scaled_daily_mae_kwh': metrics(y.reshape(7,24).sum(1), after.reshape(7,24).sum(1))['mae_kwh'],
                'scaled_daily_mape_pct': metrics(y.reshape(7,24).sum(1), after.reshape(7,24).sum(1))['mape_pct'],
                'mape_excluded_zeros': a['mape_excluded_zeros']}
            all_metrics.append(row)
            if row['primary_comparison']:
                primary.append(row)
                for d in range(7):
                    daily.append({'family_id': family, 'city': city, 'profile_id': profile,
                        'date': dates[168 + d*24].date().isoformat(), 'consumption_kwh': float(y[d*24:(d+1)*24].sum()),
                        'raw_model_kwh': float(before[d*24:(d+1)*24].sum()), 'scaled_model_kwh': float(after[d*24:(d+1)*24].sum())})
            for i, dt in enumerate(dates[168:]):
                predictions.append({'family_id': family, 'city': city, 'profile_id': profile, 'interval_start': dt.isoformat(),
                    'consumption_kwh': float(y[i]), 'raw_model_kwh': float(before[i]), 'scaled_model_kwh': float(after[i])})
    write_csv(data_dir / 'household_readings.csv', all_readings)
    write_csv(data_dir / 'household_metadata.csv', metadata)
    write_csv(data_dir / 'household_components.csv', all_components)
    for name, rows in [('household_validation_metrics.csv',all_metrics), ('household_validation_primary.csv',primary),
                       ('household_validation_hourly.csv',predictions), ('household_validation_daily.csv',daily)]:
        write_csv(BASE / 'results' / name, rows)
    summary = {'status':'SCENARIO_COMPARISON_COMPLETED', 'household_count':5, 'hourly_rows':1680,
        'validation_unique_hours':840, 'comparison_count':20, 'primary_comparison_count':5,
        'days_per_household':14, 'calibration_days':7, 'validation_days':7, 'time_zone':'UTC+03:00',
        'generator':'independent_15_minute_appliance_events_and_thermal_balance',
        'matching':'exact local timestamps in fixed 2023 calendar', 'model_rows_modified':False,
        'generation_reads_reference_profiles':False, 'field_validation_completed':False,
        'all_csv_encoding':'utf-8-sig',
        'primary_raw_hourly_mae_range':[min(r['raw_hourly_mae_kwh'] for r in primary),max(r['raw_hourly_mae_kwh'] for r in primary)]}
    (BASE / 'results/household_validation_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    for row in primary:
        print(row['family_id'],row['city'],row['profile_id'],'raw_MAE',round(row['raw_hourly_mae_kwh'],4),'raw_MAPE',round(row['raw_hourly_mape_pct'],2),'scaled_MAE',round(row['scaled_hourly_mae_kwh'],4))


if __name__ == '__main__':
    build()
