"""Тесты конфигуратора src/config: каталог, энергорасчёт, цепочки панелей, смета, ограничения, экономика.

Запуск из корня репозитория: python -m pytest -q
"""
import math

import numpy as np
import pandas as pd
import pytest

from src.config import catalog
from src.config.configurator import (MICROGEN_LIMIT_KW, TIE_YEARS, House, bill_of_materials, candidates,
                                     configure, hourly_ac, layout, string_limits)
from src.config.pv_yield import panel_dc_w, specific_yield, system_loss
from src.config.weather import design_min_temp, tmy
from src.econ.api import evaluate
from src.econ.inputs import DATA, TariffPlan
from src.econ.model import Scenario

CITY_SINGLE = TariffPlan("Город, одноставочный", "base", "single", ("base",))
CITY_ZONES = TariffPlan("Город, день/ночь", "base", "two_zone", ("base",))
PVGIS_MEAN = {"krasnodar": 1224.0, "maykop": 1210.7}   # results/yield_validation.csv, 30°, юг, 2005–2023


def load(pid="day_absent", city="krasnodar"):
    return tuple(pd.read_csv(DATA / "hourly_profiles" / f"{pid}_{city}_8760.csv", encoding="utf-8-sig").load_kwh)


def house(**kw):
    base = dict(city="krasnodar", plan=CITY_SINGLE, load_8760=load(), profile_id="day_absent")
    base.update(kw)
    return House(**base)


# ----------------------------------------------------------------- каталог и погода
def test_catalog_complete():
    assert len(catalog.panels()) >= 3 and len(catalog.inverters()) >= 3
    for p in catalog.panels():
        assert p.price_rub > 0 and p.pmax_w > 0 and p.gamma_pmax_pct_c < 0 and p.area_m2 > 2
        assert p.datasheet_url.startswith("http")
    for i in catalog.inverters():
        assert i.price_rub > 0 and i.max_pv_kw >= i.ac_kw and i.mppt_min_v < i.mppt_max_v <= i.max_dc_v
        assert i.phases in (1, 3) and i.datasheet_url.startswith("http")


def test_prices_only_from_verified_sites_without_discounts():
    """Цены каталога — медиана обычных цен (без скидок) с сайтов из docs/equipment/equipment_sources.md."""
    offers = pd.read_csv(DATA / "equipment" / "offers.csv", encoding="utf-8-sig")
    sources = (DATA.parent / "docs" / "equipment" / "equipment_sources.md").read_text(encoding="utf-8")
    for _, o in offers.iterrows():
        domain = o.url.split("/")[2].removeprefix("www.")
        assert domain in sources or domain.startswith("xn--80aaabwwhjb3dj"), f"сайт {domain} не в списке проверенных"
        if not pd.isna(o.price_sale_rub):
            assert o.price_regular_rub > o.price_sale_rub   # в расчёт идёт цена до скидки
    used = offers[offers.used == "yes"]
    for item in list(catalog.panels()) + list(catalog.inverters()):
        cid = getattr(item, "panel_id", None) or item.inverter_id
        rows = used[used.catalog_id == cid]
        assert len(rows), f"{cid}: нет предложений с проверенных сайтов"
        per_seller = rows.groupby("seller").price_regular_rub.min()
        assert item.price_rub == pytest.approx(per_seller.median(), abs=1)


def test_weather():
    for city in ("krasnodar", "maykop"):
        w = tmy(city)
        assert len(w) == 8760 and w.ghi.max() < 1200 and (w.ghi >= 0).all()
        assert -40 < design_min_temp(city) < -5


# ----------------------------------------------------------------- энергорасчёт
@pytest.mark.parametrize("city", ["krasnodar", "maykop"])
def test_yield_close_to_pvgis(city):
    """30°, юг: удельная выработка на типичном метеогоде в пределах ±8 % от средней PVGIS за 2005–2023 гг."""
    for p in catalog.panels():
        assert abs(specific_yield(p, city, 30, 180) / PVGIS_MEAN[city] - 1) < 0.08


def test_orientation_and_tilt():
    p = catalog.panels()[0]
    south, east, west = (specific_yield(p, "krasnodar", 30, a) for a in (180, 90, 270))
    assert south > east and south > west
    assert specific_yield(p, "krasnodar", 0, 180) < south          # плоская крыша хуже наклона 30°
    assert 0 < system_loss("none") < system_loss("light") < 0.2


def test_hourly_shape():
    p = catalog.panels()[0]
    dc = panel_dc_w(p, "krasnodar", 30, 180)
    assert len(dc) == 8760 and dc.min() >= 0 and dc.max() <= p.pmax_w * 1.2
    hours = np.arange(8760) % 24
    assert dc[(hours < 4) | (hours > 21)].sum() == 0        # ночью (местное время) выработки нет


def test_inverter_limits_ac():
    p, inv = catalog.panel("jinko_590"), catalog.inverter("deye_5k_g04")
    strings = layout(p, 11, inv, "krasnodar")
    gen, clipped = hourly_ac(p, 11, inv, strings, house())
    assert gen.max() <= inv.ac_kw + 1e-9 and clipped >= 0


# ----------------------------------------------------------------- цепочки панелей
def test_string_voltage_rules():
    p = catalog.panel("jinko_590")
    for inv in catalog.inverters():
        l_min, l_max = string_limits(p, inv, "krasnodar")
        t_min = design_min_temp("krasnodar")
        assert l_max * p.voc_v * (1 + p.beta_voc_pct_c / 100 * (t_min - 25)) <= inv.max_dc_v
        assert l_min * p.vmp_v * (1 + p.beta_voc_pct_c / 100 * 45) >= inv.mppt_min_v
    assert layout(p, 1, catalog.inverter("deye_10k_g06p3"), "krasnodar") is None   # 43 В — ниже порога MPPT 120 В
    s = layout(p, 11, catalog.inverter("deye_5k_g04"), "krasnodar")
    assert sum(s) == 11 and len(s) == 2


# ----------------------------------------------------------------- смета
def test_bill_of_materials():
    p, inv = catalog.panel("resun_590"), catalog.inverter("deye_3k_g04p1")
    rows, base, low, high = bill_of_materials(p, 5, inv, (5,))
    assert math.isclose(sum(r[4] for r in rows), base)
    assert low < base < high
    names = [r[0] for r in rows]
    assert {"Панели", "Инвертор", "Монтаж и пусконаладка", "Подключение к сети"} <= set(names)
    grid = rows[names.index("Подключение к сети")][4]
    assert grid == min(21183, 11470 * inv.ac_kw)


def test_capex_near_installer_quote():
    """≈3 кВт: смета конфигуратора близка к КП Экопроект-Энерго с монтажом и подключением (193 683–208 683 ₽)."""
    p, inv = catalog.panel("resun_590"), catalog.inverter("deye_3k_g04p1")
    _, base, low, high = bill_of_materials(p, 5, inv, (5,))
    assert 0.8 * 193_683 < base < 1.2 * 208_683


# ----------------------------------------------------------------- ограничения и подбор
def test_constraints_respected():
    h = house(roof_area_m2=20, phases=1, allowed_kw=4, budget_rub=300_000)
    cs = candidates(h)
    assert cs
    for c in cs:
        assert c.area_m2 <= 20 and c.inverter.phases == 1 and c.inverter.ac_kw <= 4 and c.capex_rub <= 300_000
        assert c.kwp <= c.inverter.max_pv_kw
    assert all(c.inverter.ac_kw <= MICROGEN_LIMIT_KW for c in candidates(house(phases=3, allowed_kw=150)))


def test_no_three_phase_inverter_on_single_phase():
    assert all(c.inverter.phases == 1 for c in candidates(house(phases=1, roof_area_m2=100)))
    assert any(c.inverter.phases == 3 for c in candidates(house(phases=3, roof_area_m2=100)))


def test_own_needs_goal():
    """По умолчанию — станция для своих нужд: выработка за год не больше потребления дома."""
    for pid in ("day_absent", "el_heating"):
        h = house(load_8760=load(pid), roof_area_m2=80, phases=3)
        best = configure(h)[0]
        assert best.gen_kwh <= sum(h.load_8760)
        free = configure(House(**{**h.__dict__, "goal": "payback"}))[0]   # без ограничения — не меньше
        assert free.kwp >= best.kwp


def test_bigger_house_bigger_station():
    small = configure(house(load_8760=tuple(np.asarray(load()) * 0.5), phases=3, roof_area_m2=80))[0]
    big = configure(house(load_8760=tuple(np.asarray(load()) * 3), phases=3, roof_area_m2=80))[0]
    assert big.kwp > small.kwp


def test_recommendation_is_best_payback():
    h = house(roof_area_m2=60, phases=3, plan=CITY_ZONES, goal="payback")
    res = configure(h)
    best = res[0]
    assert all(best.result["simple_payback"] <= c.result["simple_payback"] + TIE_YEARS for c in res)


def test_npv_goal_picks_max_npv():
    res = configure(house(roof_area_m2=60, phases=3, goal="npv"))
    assert all(res[0].result["npv_rub"] >= c.result["npv_rub"] for c in res)


def test_economics_same_as_api():
    """Экономика варианта — та же модель src/econ: результат совпадает с api.evaluate на его помесячных записях."""
    c = configure(house())[0]
    r = evaluate(c.months, CITY_SINGLE, c.kwp, capex_rub=c.capex_rub,
                 scenario=Scenario(inverter_cost_rub=c.inverter.price_rub))
    for k in ("simple_payback", "disc_payback", "npv_rub", "effect_rub", "self_share"):
        assert c.result[k] == pytest.approx(getattr(r, k))


def test_monthly_balance():
    c = configure(house())[0]
    assert sum(m.gen_kwh for m in c.months) == pytest.approx(c.gen_kwh, rel=1e-4)
    assert sum(m.load_kwh for m in c.months) == pytest.approx(sum(load()), rel=1e-4)
    for m in c.months:
        assert m.self_kwh <= min(m.gen_kwh, m.load_kwh) + 0.1


def test_bad_house():
    with pytest.raises(ValueError):
        house(load_8760=(1.0,) * 100)
    with pytest.raises(ValueError):
        house(phases=2)
    with pytest.raises(ValueError):
        house(goal="fastest")
    assert configure(house(budget_rub=60_000)) == []   # на 60 тыс. ₽ станции нет
