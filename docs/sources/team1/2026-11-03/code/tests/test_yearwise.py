"""Independent regression checks for year-wise energy accounting."""
import csv
import json
import unittest
from pathlib import Path
import numpy as np
from src.energy.api import (BASE, CITIES, HOUR_MONTH, NIGHT, build_profile,
                            solar_hourly, solar_hourly_by_year, simulate)
from scripts.generate_outputs import read_ref


class TestYearwise(unittest.TestCase):
    def test_pvgis_years_cache_shape_and_missing_night(self):
        for city in CITIES:
            year = solar_hourly_by_year(city, 1)
            mean = solar_hourly(city, 1)
            self.assertEqual(year.shape, (19, 8760))
            self.assertTrue(np.array_equal(year[0, :3], [0, 0, 0]))
            self.assertTrue(np.isfinite(year).all())
            self.assertTrue((year >= 0).all())
            np.testing.assert_allclose(mean, year.mean(axis=0), atol=1e-11)
            meta=json.loads((BASE/'data/solar_reference'/f'solar_{city}_tilt30_az180_1kw.meta.json').read_text())
            self.assertEqual(meta['missing_hours_by_year_before_imputation']['2005'], 3)
            self.assertTrue(all(meta['missing_hours_by_year_before_imputation'][str(y)] == 0 for y in range(2006,2024)))

    def test_simulate_is_average_of_yearwise_sums_not_mean_year_min(self):
        for city in CITIES:
            values = read_ref()[('home_all_day', city)]
            load = build_profile(values, 'home_all_day', set(), city)
            monthly, loadout, mean = simulate(load, 3, city)
            years = solar_hourly_by_year(city, 3)
            used = np.minimum(years, load[None,:])
            old = np.minimum(years.mean(axis=0), load)
            self.assertGreater(old.sum(), used.mean(axis=0).sum())
            for m, item in enumerate(monthly, 1):
                mask = HOUR_MONTH == m
                self.assertAlmostEqual(item.self_kwh, float(used[:,mask].sum(axis=1).mean()), places=8)
                self.assertAlmostEqual(item.gen_kwh, float(years[:,mask].sum(axis=1).mean()), places=8)
                self.assertAlmostEqual(item.import_day_kwh,
                    float((load[None,mask & ~NIGHT] - used[:,mask & ~NIGHT]).sum(axis=1).mean()), places=8)
                self.assertAlmostEqual(item.self_share,
                    100 * item.self_kwh/item.gen_kwh, places=8)
            np.testing.assert_allclose(loadout,load)
            np.testing.assert_allclose(mean,years.mean(axis=0))

    def test_hypothesis_all_six_and_contract(self):
        with (BASE/'results/hypothesis_equal_consumption.csv').open() as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(float(r['self_share_ratio']) > 1.5 for r in rows))
        self.assertTrue(all(r['hypothesis_ge_1_5'] == 'True' for r in rows))
        self.assertTrue(all(abs(float(r['equal_annual_load_kwh'])-3500) < 1e-6 for r in rows))

    def test_audit_exports_counts_and_bias(self):
        with (BASE/'results/energy_metrics_per_year.csv').open() as f:
            y=list(csv.DictReader(f))
        with (BASE/'results/energy_metrics_monthly_per_year.csv').open() as f:
            m=list(csv.DictReader(f))
        with (BASE/'results/team1_typical_year_check.csv').open() as f:
            diffs=list(csv.DictReader(f))
        self.assertEqual(len(y), 24 * 19)
        self.assertEqual(len(m), 24 * 19 * 12)
        self.assertEqual(len(diffs),24)
        self.assertTrue(all(float(r['self_share_overestimate_pp']) >= 0 for r in diffs))
        self.assertGreater(max(float(r['self_share_overestimate_pp']) for r in diffs), 6.3)
        self.assertTrue(all(abs(float(r['gen_kwh'])-float(r['self_kwh'])-float(r['export_kwh']))<1e-6 for r in m))
        self.assertTrue(all(abs(float(r['import_kwh'])-float(r['import_day_kwh'])-float(r['import_night_kwh']))<1e-6 for r in m))

if __name__=='__main__':unittest.main()
