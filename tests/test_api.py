"""Тесты единой точки входа src/econ/api.py (T1.4; набор test_api из T5.1 мастер-ТЗ + приёмка T1.4).

Запуск из корня репозитория: python -m pytest -q
Контрольная точка — PLAN.md («Решения команды», 31.10.2026; значения на 03.11.2026).
"""
import math
from dataclasses import replace

import pandas as pd
import pytest

from src.econ.api import TIE_YEARS, Result, evaluate, evaluate_tz, recommend
from src.econ.exchange import annual_from_monthly, make_stub_monthly
from src.econ.inputs import DATA, TariffPlan
from src.econ.model import Scenario

ROOT = DATA.parent
CITY_ZONES = TariffPlan("Город, день/ночь", "base", "two_zone", ("base",))
PLANS = [
    TariffPlan("Город, одноставочный", "base", "single", ("base",)),
    CITY_ZONES,
    TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",)),
    TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",)),
]


def stub(kw, load=6000, share=40, city="krasnodar"):
    return make_stub_monthly("s", kw, load, share, city)


# ----------------------------------------------------------------- набор test_api из T5.1
def test_recommend_min_simple_payback():
    best, res = recommend({kw: stub(kw) for kw in (3, 5, 10)}, CITY_ZONES)
    fastest = min(r.simple_payback for r in res.values())
    assert res[best].simple_payback - fastest < TIE_YEARS
    # при почти равных сроках — меньшая (более дешёвая) мощность
    assert best == min(kw for kw, r in res.items() if r.simple_payback - fastest < TIE_YEARS)


def test_own_buyback_zero_gives_no_export_income():
    r = evaluate(stub(5), CITY_ZONES, 5, buyback_rub_kwh=0)
    assert r.export_rub == 0
    assert r.effect_rub == pytest.approx(r.self_rub)


def test_own_capex():
    x = 250_000
    r = evaluate(stub(5), CITY_ZONES, 5, capex_rub=x)
    assert r.capex_rub == x
    assert r.simple_payback == pytest.approx(x / r.effect_rub)
    assert math.isnan(r.payback_low) and math.isnan(r.payback_high)   # границы — только для цены из таблицы


# ----------------------------------------------------------------- приёмка T1.4
def test_control_point():
    r = evaluate(stub(5), CITY_ZONES, 5)
    assert r.effect_rub == pytest.approx(51_394, abs=1)
    assert round(r.simple_payback, 1) == 5.7
    assert round(r.disc_payback, 1) == 6.4
    assert r.npv_rub == pytest.approx(484_002, abs=1)
    assert annual_from_monthly(stub(5)).gen_kwh == pytest.approx(6171.8, abs=0.1)


def test_matches_stub_payback_csv():
    """api даёт то же, что scripts/stub_payback.py, во всех строках results/stub_payback.csv."""
    df = pd.read_csv(ROOT / "results" / "stub_payback.csv", encoding="utf-8-sig")
    plans = {p.name: p for p in PLANS}
    for row in df.itertuples():
        r = evaluate(stub(row.pv_kw, share=row.self_share_target), plans[row.tariff], row.pv_kw)
        assert r.effect_rub == pytest.approx(row.effect_rub, abs=1)
        assert round(r.simple_payback, 1) == pytest.approx(row.simple_payback)
        assert round(r.disc_payback, 1) == pytest.approx(row.disc_payback)


def test_recommend_tie_prefers_smaller_station():
    """Сроки 5 и 10 кВт различаются меньше чем на 0,05 года — выбирается 5 кВт, хотя 10 кВт чуть быстрее."""
    plan = PLANS[3]
    best, res = recommend({kw: stub(kw, load=1200) for kw in (3, 5, 10)}, plan)
    assert res[10].simple_payback < res[5].simple_payback < res[10].simple_payback + TIE_YEARS
    assert best == 5


def test_recommend_none_pays_back_returns_max_effect():
    sc = replace(Scenario(), opex_rub=1e9)
    best, res = recommend({kw: stub(kw) for kw in (3, 5, 10)}, CITY_ZONES, scenario=sc)
    assert all(r.simple_payback == math.inf for r in res.values())
    assert best == max(res, key=lambda kw: res[kw].effect_rub)


def test_evaluate_tz_formula():
    m = annual_from_monthly(stub(5))
    r = evaluate_tz(m, tariff_rub=8.31, buyback_rub_kwh=4.44, capex_rub=291_000)
    assert r.self_rub == pytest.approx(m.self_kwh * 8.31)
    assert r.export_rub == pytest.approx(m.export_kwh * 4.44)
    assert r.simple_payback == pytest.approx(291_000 / r.effect_rub)


def test_result_plain_floats():
    d = evaluate(stub(5), CITY_ZONES, 5).as_dict()
    assert set(d) == {f for f in Result.__dataclass_fields__}
    assert all(type(v) is float for v in d.values())


@pytest.mark.parametrize("kwargs", [{"capex_rub": 0}, {"capex_rub": -1}, {"buyback_rub_kwh": -5},
                                    {"capex_level": "mid"}])
def test_bad_input_raises(kwargs):
    with pytest.raises(ValueError):
        evaluate(stub(5), CITY_ZONES, 5, **kwargs)


def test_bad_tariff_and_city_raise():
    with pytest.raises(ValueError):
        evaluate(stub(5), TariffPlan("x", "base", "three_zone"), 5)
    with pytest.raises(ValueError):
        stub(5, city="sochi")
    with pytest.raises(ValueError):
        recommend({}, CITY_ZONES)
    with pytest.raises(ValueError):
        recommend({5: stub(5)}, CITY_ZONES, capex_rub=300_000)
