"""Тесты файлов передачи, включая страховку от подмены DEMO за PVGIS."""
import csv
import json
import unittest
import numpy as np
from pathlib import Path
from src.energy.api import BASE, CITIES, PORTRAITS
from scripts.generate_outputs import generate


class TestDelivery(unittest.TestCase):
    def test_csv_contracts(self):
        with (BASE/'results'/'energy_metrics.csv').open(encoding='utf-8') as f:
            annual=list(csv.DictReader(f))
        with (BASE/'results'/'energy_metrics_monthly.csv').open(encoding='utf-8') as f:
            monthly=list(csv.DictReader(f))
        self.assertEqual(len(annual),24)
        self.assertEqual(len(monthly),288)
        akeys={(r['profile_id'],r['city'],float(r['pv_kw'])) for r in annual}
        mkeys={(r['profile_id'],r['city'],float(r['pv_kw']),int(r['month'])) for r in monthly}
        self.assertEqual(len(akeys),24)
        self.assertEqual(len(mkeys),288)
        for r in annual:
            matches=[m for m in monthly if (m['profile_id'],m['city'],float(m['pv_kw']))==(r['profile_id'],r['city'],float(r['pv_kw']))]
            self.assertEqual(len(matches),12)
            for metric in ('gen_kwh','load_kwh','self_kwh','import_kwh','export_kwh','import_day_kwh','import_night_kwh'):
                self.assertAlmostEqual(float(r[metric]),sum(float(m[metric]) for m in matches),places=5)
            self.assertAlmostEqual(float(r['load_kwh']),float(r['self_kwh'])+float(r['import_kwh']),places=6)
            self.assertAlmostEqual(float(r['gen_kwh']),float(r['self_kwh'])+float(r['export_kwh']),places=6)

    def test_hourly_profile_lengths(self):
        for city in CITIES:
            for port in PORTRAITS:
                p=BASE/'data'/'hourly_profiles'/f'{port}_{city}_8760.csv'
                with p.open(encoding='utf-8') as f:
                    rows=list(csv.DictReader(f))
                self.assertEqual(len(rows),8760)
                self.assertTrue(all(float(r['load_kwh'])>=0 for r in rows))

    def test_verified_source_is_uploaded_pvgis(self):
        report=json.loads((BASE/'results'/'validation_report.json').read_text())
        self.assertTrue(report['PVGIS_2005_2023_verified'])
        self.assertEqual(report['status'], 'VERIFIED')
        for city in CITIES:
            meta=report['source_meta'][city]
            self.assertEqual(meta['status'],'PVGIS_SARAH3_2005_2023_MODELLED')
            self.assertEqual(meta['source'],'USER_PROVIDED_PVGIS_JSON_VALIDATED_STRUCTURE')
            self.assertEqual(meta['raw_records'],166536)
            self.assertEqual(meta['typical_hours'],8760)
            self.assertTrue(meta['data_are_modelled_not_measured'])
            self.assertEqual(meta['hourly_sample_count_distribution'],{'18':3,'19':8757})

    def test_uploaded_archive_hash_and_data(self):
        from zipfile import ZipFile
        import hashlib
        archive=BASE/'data/pvgis_raw/pvgis_2005_2023_original_upload.zip'
        with ZipFile(archive) as z:
            for city in CITIES:
                name=f'{city}_2005_2023.json'
                raw=z.read(name)
                meta=json.loads((BASE/'data/solar_reference'/f'solar_{city}_tilt30_az180_1kw.meta.json').read_text())
                self.assertEqual(hashlib.sha256(raw).hexdigest(),meta['raw_sha256'])
                solar=np.load(BASE/'data/solar_reference'/f'solar_{city}_tilt30_az180_1kw.npy')
                self.assertEqual(solar.shape,(8760,))
                self.assertAlmostEqual(float(solar.sum()),meta['yearly_1kw_kwh'],places=6)

    def test_3_5_10kw_generation_scales(self):
        with (BASE/'results/energy_metrics.csv').open(encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        for city in CITIES:
            for kw in (3,5,10):
                gen={round(float(r['gen_kwh']),6) for r in rows if r['city']==city and float(r['pv_kw'])==kw}
                self.assertEqual(len(gen),1)
                self.assertAlmostEqual(next(iter(gen)),
                    float(np.load(BASE/'data/solar_reference'/f'solar_{city}_tilt30_az180_1kw.npy').sum())*kw,places=5)

if __name__=='__main__': unittest.main()
