import unittest
import numpy as np
from src.energy.api import (build_profile,simulate,CITIES,HOUR_MONTH,NIGHT)
from scripts.generate_outputs import read_ref


class TestEnergy(unittest.TestCase):
    def test_profile_monthly_totals(self):
        target=list(range(120,132))
        load=build_profile(target,"home_all_day",{"ac","pump"})
        self.assertEqual(len(load),8760)
        self.assertTrue((load>=0).all())
        self.assertTrue(np.allclose([load[HOUR_MONTH==m].sum() for m in range(1,13)],target))

    def test_pv_balance(self):
        for city in CITIES:
            for profile in ("day_absent","home_all_day"):
                arr=build_profile(read_ref()[(profile,city)],profile,set(),city)
                for k in (3,5,10):
                    met,load,gen=simulate(arr,k,city)
                    self.assertEqual(len(met),12)
                    self.assertEqual(gen.shape,(8760,))
                    self.assertTrue(np.allclose(arr,load))
                    for x in met:
                        self.assertAlmostEqual(x.load_kwh,x.self_kwh+x.import_kwh,places=7)
                        self.assertAlmostEqual(x.gen_kwh,x.self_kwh+x.export_kwh,places=7)
                        self.assertAlmostEqual(x.import_kwh,x.import_day_kwh+x.import_night_kwh,places=7)

    def test_validation(self):
        with self.assertRaises(ValueError):build_profile([2.]*11,"day_absent",set())
        with self.assertRaises(ValueError):build_profile([2.]*12,"wrong",set())
        with self.assertRaises(ValueError):build_profile([2.]*12,"day_absent",{"madeup"})
        with self.assertRaises(ValueError):simulate(np.ones(8759),3,"krasnodar")
        with self.assertRaises(FileNotFoundError):simulate(np.ones(8760),3,"krasnodar",tilt=45)

    def test_different_day_night(self):
        a=build_profile([200]*12,"day_absent",set())
        b=build_profile([200]*12,"home_all_day",set())
        self.assertTrue(b[~NIGHT].sum()>a[~NIGHT].sum())

if __name__=="__main__": unittest.main()
