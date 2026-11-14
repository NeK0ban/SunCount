"""Тесты расчётной части веб-сервиса app/calc.py: тариф по приборам, потребление, вызов конфигуратора.

Запуск из корня репозитория: python -m pytest -q
"""
import pytest

import numpy as np

from app.calc import (average_day, get_plan, own_load, portrait_load, reduced_by_appliances, run_configurator,
                      shift_load_to_day, tips, why_nothing_fits)
from app.charts import day_figures
from app.texts import PORTRAITS, TARIFFS, hint_no_payback


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


def test_shift_load_to_day_keeps_daily_sums():
    """Сценарий подсказки T4.5: с 19–22 снято не больше 2 кВт·ч в сутки, столько же добавлено на 11–14,
    суточное потребление не изменилось, отрицательных часов нет."""
    load = own_load(500, "day_absent", (), "krasnodar")
    a, b = np.asarray(load).reshape(365, 24), np.asarray(shift_load_to_day(load)).reshape(365, 24)
    assert np.allclose(a.sum(axis=1), b.sum(axis=1))
    moved = (a - b)[:, 19:23].sum(axis=1)
    assert (moved <= 2 + 1e-9).all() and moved.mean() > 1.9
    assert np.allclose((b - a)[:, 11:15].sum(axis=1), moved)
    assert (b >= 0).all()


def test_tips_tariff_and_no_shift_with_netting():
    """Подсказки T4.5 на доме 500 кВт·ч/мес: тариф день/ночь — да (выигрыш ≥ 0,5 года, посчитан конфигуратором).
    Перенос стирки на день при помесячном зачёте срок не меняет (19–22 и 11–14 — одна дневная зона),
    поэтому этой подсказки нет."""
    load = own_load(500, "day_absent", (), "krasnodar")
    res = run_configurator("krasnodar", "city_single", load)
    alt = run_configurator("krasnodar", "city_zones", load)["configs"][0]["simple_payback"]
    out = tips(res, "krasnodar", "city_single", load)
    assert 1 <= len(out) <= 3
    assert out[0].startswith("Переход на тариф день/ночь")
    gain = res["configs"][0]["simple_payback"] - alt
    assert f"{gain:.1f}".replace(".", ",") in out[0]
    assert not any(t.startswith("Перенесите") for t in out)
    shifted = run_configurator("krasnodar", "city_single", shift_load_to_day(load))["configs"][0]
    assert shifted["simple_payback"] == pytest.approx(res["configs"][0]["simple_payback"], abs=0.01)
    zones = run_configurator("krasnodar", "city_zones", load)
    assert tips(zones, "krasnodar", "city_zones", load) == []    # на день/ночь подсказывать о тарифе нечего


def test_tips_no_payback():
    """«Не окупается» — когда простой срок всех вариантов больше 25 лет, не только inf (как в verdict)."""
    res = {"configs": [{"simple_payback": 31.0, "self_share": 80.0}, {"simple_payback": float("inf"),
                                                                      "self_share": 80.0}]}
    assert tips(res, "krasnodar", "city_zones", ()) == [hint_no_payback()]
    res["configs"][0]["simple_payback"] = 20.0
    assert tips(res, "krasnodar", "city_zones", ()) == []
    assert tips({"configs": []}, "krasnodar", "city_single", ()) == []


def test_day_figure_draws_all_hours():
    """График T4.4: два рисунка с общей шкалой, у каждой линии 25 точек — последняя ступенька кончается в 24:00."""
    load = portrait_load("day_absent", "krasnodar")
    best = run_configurator("krasnodar", "city_single", load)["configs"][0]
    figs = day_figures(average_day(best, "krasnodar", load, 7), average_day(best, "krasnodar", load, 1))
    axes = [f.axes[0] for f in figs]
    assert len(figs) == 2 and axes[0].get_ylim() == axes[1].get_ylim()
    for ax in axes:
        lines = [ln for ln in ax.get_lines() if len(ln.get_xdata()) > 2]
        assert len(lines) == 2 and all(ln.get_xdata()[-1] == 24 for ln in lines)
        assert ax.get_xlim() == (0, 24)


@pytest.mark.parametrize("kw, expected", [
    (dict(roof_area_m2=3), ["Площадь крыши"]),
    (dict(allowed_kw=1), ["Мощность по договору с сетью"]),
    (dict(allowed_kw=2.5, phases=3), ["Мощность по договору с сетью"]),
    (dict(budget_rub=50_000), ["Бюджет"]),
    (dict(roof_area_m2=3, budget_rub=50_000, allowed_kw=1), ["Мощность по договору с сетью", "Площадь крыши", "Бюджет"]),
])
def test_why_nothing_fits(kw, expected):
    """Когда ни одна станция не подходит, сервис называет каждую причину отдельно, с числами из каталога."""
    load = portrait_load("day_absent", "krasnodar")
    assert run_configurator("krasnodar", "city_single", load, **kw)["configs"] == []
    reasons = why_nothing_fits("krasnodar", "city_single", load, **kw)
    assert [r.split(".**")[0].strip("*") for r in reasons] == expected


def test_why_nothing_fits_numbers_match_catalog():
    """Числа в причинах — те же, что у самой маленькой и самой дешёвой станции подбора."""
    load = portrait_load("day_absent", "krasnodar")
    cheapest = min(c["capex_rub"] for c in run_configurator("krasnodar", "city_single", load, roof_area_m2=6)["configs"])
    budget = why_nothing_fits("krasnodar", "city_single", load, roof_area_m2=6, budget_rub=cheapest - 1)
    assert len(budget) == 1 and f"{cheapest:,.0f}".replace(",", " ") in budget[0]
    assert run_configurator("krasnodar", "city_single", load, roof_area_m2=6, budget_rub=cheapest)["configs"]
    assert why_nothing_fits("krasnodar", "city_single", load) == []      # всё подходит — причин нет

