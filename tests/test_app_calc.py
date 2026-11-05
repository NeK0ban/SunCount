"""Тесты расчётной части веб-сервиса app/calc.py — ввод данных по ТЗ (T4.2).

Запуск из корня репозитория: python -m pytest -q
"""
import math

import pandas as pd
import pytest

from app.calc import (PV_SIZES, base_capex, calculate_scenario, get_plan, get_portrait_months,
                      reduced_by_appliances)
from app.texts import PORTRAITS, TARIFFS
from src.econ.api import evaluate, recommend
from src.econ.exchange import make_stub_monthly
from src.econ.inputs import DATA

ROOT = DATA.parent


@pytest.mark.parametrize("appliances, category, ranges", [
    (set(), "base", ("base",)),
    ({"ac", "pump"}, "base", ("base",)),
    ({"el_stove"}, "reduced", ("reduced_stove",)),
    ({"el_heating"}, "reduced", ("reduced_heating", "reduced_heating_nostove")),
    ({"el_heating", "el_stove"}, "reduced", ("reduced_heating", "reduced_heating_stove")),
])
def test_plan_by_appliances_city(appliances, category, ranges):
    """Электроотопление и электроплита и в городе дают сниженный тариф; вид тарифа и название — как выбрал пользователь."""
    for key in ("city_single", "city_zones"):
        plan = get_plan(key, appliances)
        assert (plan.price_category, plan.range_keys) == (category, ranges)
        assert plan.tariff_type == TARIFFS[key]["plan"].tariff_type
        assert plan.name == TARIFFS[key]["plan"].name
        assert reduced_by_appliances(key, appliances) == (category == "reduced")


def test_plan_rural_heating_ranges():
    plan = get_plan("rural_zones", {"el_heating"})
    assert plan.price_category == "reduced" and plan.range_keys == ("reduced_heating", "reduced_heating_nostove")
    assert not reduced_by_appliances("rural_zones", {"el_heating"})   # село и так по сниженному — пометка не нужна


def test_custom_mode_unchanged():
    """«Свои данные» без приборов и своей цены — тот же расчёт, что и до T4.2 (api.recommend на условном профиле)."""
    best, res = calculate_scenario(500, 40, "krasnodar", "city_single")
    months = {kw: make_stub_monthly("stub_40", kw, 6000, 40, "krasnodar") for kw in PV_SIZES}
    best_api, res_api = recommend(months, TARIFFS["city_single"]["plan"])
    assert best == best_api
    assert all(res[kw] == res_api[kw].as_dict() for kw in PV_SIZES)


def test_monthly_input_equal_months_same_as_average():
    """12 одинаковых месяцев = одно среднее значение; сумма месяцев = годовое потребление."""
    assert calculate_scenario(tuple([700] * 12), 50, "maykop", "rural_zones") == \
        calculate_scenario(700, 50, "maykop", "rural_zones")


def test_monthly_input_shape_used():
    """Сезонность из 12 значений меняет результат при той же годовой сумме."""
    winter = (1500, 1400, 1000, 600, 300, 250, 250, 250, 300, 600, 1000, 1550)
    flat = sum(winter) / 12
    assert calculate_scenario(winter, 40, "krasnodar", "city_single", appliances={"el_heating"}) != \
        calculate_scenario(flat, 40, "krasnodar", "city_single", appliances={"el_heating"})


def test_bad_input():
    with pytest.raises(ValueError):
        calculate_scenario((500,) * 11, 40, "krasnodar", "city_single")
    with pytest.raises(ValueError):
        calculate_scenario((500,) * 11 + (0,), 40, "krasnodar", "city_single")
    with pytest.raises(ValueError):
        calculate_scenario(None, 40, "krasnodar", "city_single", profile_id="pump_farm")


def test_portraits_available():
    """Все 4 портрета команды 1 есть для обоих городов и всех мощностей, по 12 месяцев."""
    for pid in PORTRAITS:
        for city in ("krasnodar", "maykop"):
            by_kw = get_portrait_months(pid, city)
            assert sorted(by_kw) == list(PV_SIZES)
            assert all([r.month for r in recs] == list(range(1, 13)) for recs in by_kw.values())


def test_portrait_matches_real_payback():
    """«Готовый портрет» даёт те же сроки и рекомендацию, что расчёт на реальных профилях (T1.6, real_payback.csv).
    Портрет el_heating и при городском тарифе считается по сниженному — как «сельский» тариф того же вида."""
    real = pd.read_csv(ROOT / "results" / "real_payback.csv", encoding="utf-8-sig")
    label = {v["label"]: k for k, v in TARIFFS.items()}
    checked = 0
    for (pid, city, tariff), g in real.groupby(["profile_id", "city", "tariff"]):
        keys = [label[tariff]]
        if pid == "el_heating":   # городской тариф того же вида должен дать то же самое
            keys.append(label[tariff].replace("rural", "city"))
        for key in keys:
            best, res = calculate_scenario(None, 40, city, key, profile_id=pid)
            for _, row in g.iterrows():
                kw = int(row.pv_kw)
                assert res[kw]["simple_payback"] == pytest.approx(row.simple_payback, abs=1e-4)
                assert res[kw]["effect_rub"] == pytest.approx(row.effect_rub, abs=1)
                assert (kw == best) == bool(row.recommended)
            checked += 1
    assert checked == 28 + 4   # 28 троек из real_payback + el_heating на городских тарифах


def test_custom_capex():
    """Своя цена станции идёт в evaluate(capex_rub=...) для каждой мощности; границы цены — nan."""
    prices = {3: 150_000, 5: 240_000, 10: 700_000}
    best, res = calculate_scenario(500, 40, "krasnodar", "city_zones", custom_capex=prices)
    plan = TARIFFS["city_zones"]["plan"]
    for kw in PV_SIZES:
        ref = evaluate(make_stub_monthly("stub_40", kw, 6000, 40, "krasnodar"), plan, kw, capex_rub=prices[kw])
        assert res[kw]["capex_rub"] == prices[kw]
        assert res[kw]["simple_payback"] == pytest.approx(ref.simple_payback)
        assert math.isnan(res[kw]["payback_low"]) and math.isnan(res[kw]["payback_high"])
    assert best == min(PV_SIZES, key=lambda kw: (res[kw]["simple_payback"], kw))


def test_base_capex_defaults():
    assert base_capex() == {3: 193_000, 5: 291_000, 10: 584_000}
