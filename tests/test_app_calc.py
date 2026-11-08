"""Тесты расчётной части веб-сервиса app/calc.py: тариф по приборам, потребление, вызов конфигуратора.

Запуск из корня репозитория: python -m pytest -q
"""
import pytest

from app.calc import average_day, get_plan, own_load, portrait_load, reduced_by_appliances, run_configurator
from app.texts import PORTRAITS, TARIFFS


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


def test_portraits_available():
    for pid in PORTRAITS:
        for city in ("krasnodar", "maykop"):
            assert len(portrait_load(pid, city)) == 8760
    assert portrait_load("pump_farm", "krasnodar") == ()


def test_own_load_keeps_monthly_sums():
    months = (900, 800, 600, 400, 300, 350, 450, 450, 300, 400, 600, 850)
    h = own_load(months, "home_all_day", ("el_heating",), "maykop")
    assert len(h) == 8760 and sum(h) == pytest.approx(sum(months), rel=1e-6)
    assert sum(own_load(500, "day_absent", (), "krasnodar")) == pytest.approx(6000, rel=1e-6)
    with pytest.raises(ValueError):
        own_load((500,) * 11, "day_absent", (), "krasnodar")


def test_presence_and_appliances_change_profile():
    """Режим присутствия и приборы меняют распределение по часам, а значит самопотребление (раньше — ползунок)."""
    a = run_configurator("krasnodar", "city_single", own_load(500, "day_absent", (), "krasnodar"))
    b = run_configurator("krasnodar", "city_single", own_load(500, "home_all_day", ("ac",), "krasnodar"))
    assert a["configs"][0]["self_share"] != b["configs"][0]["self_share"]


def test_run_configurator_output():
    r = run_configurator("maykop", "rural_zones", portrait_load("el_heating", "maykop"), ("el_heating",),
                         roof_area_m2=50, phases=3, goal="npv", profile_id="el_heating")
    best = r["configs"][0]
    assert r["constraint"]
    for key in ("panel", "n_panels", "kwp", "inverter", "strings", "capex_rub", "bom", "simple_payback",
                "disc_payback", "npv_rub", "self_share", "payback_low", "payback_high"):
        assert key in best
    assert best["capex_low_rub"] < best["capex_rub"] < best["capex_high_rub"]
    assert all(best["npv_rub"] >= c["npv_rub"] for c in r["configs"])
    with pytest.raises(ValueError):
        run_configurator("maykop", "rural_zones", portrait_load("ac", "maykop"), goal="cheapest")


def test_average_day_matches_station_month():
    """Средние сутки для графика лето/зима (T4.4): сумма × число дней = выработка и потребление месяца,
    самопотребление не больше выработки и потребления в каждый час."""
    load = portrait_load("day_absent", "krasnodar")
    best = run_configurator("krasnodar", "city_single", load)["configs"][0]
    july = average_day(best, "krasnodar", load, 7)
    jan = average_day(best, "krasnodar", load, 1)
    assert all(len(v) == 24 for v in july.values())
    assert sum(july["load"]) * 31 == pytest.approx(sum(load[4344:5088]), rel=1e-9)   # 1 июля 00:00 — час 4344
    assert all(s <= min(g, ld) + 1e-12 for s, g, ld in zip(july["self"], july["gen"], july["load"]))
    assert sum(july["gen"]) > 2 * sum(jan["gen"])        # летом выработка больше в разы
    assert max(range(24), key=lambda h: july["gen"][h]) in (11, 12, 13)   # пик около полудня по местному времени
    with pytest.raises(ValueError):
        average_day(best, "krasnodar", load, 13)
