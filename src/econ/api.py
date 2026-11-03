"""Единая точка входа экономической модели для калькулятора (Р4), аналитики (Р3) и тестов (Р5) — задача T1.4.

Калькулятор и скрипты вызывают модель только отсюда, а не внутренние функции model.py. Внутри — те же функции,
что в scripts/stub_payback.py, поэтому результаты совпадают с results/stub_payback.csv.

    from src.econ.api import evaluate, recommend, evaluate_tz
    from src.econ.exchange import make_stub_monthly
    from src.econ.inputs import TariffPlan

    plan = TariffPlan("Город, день/ночь", "base", "two_zone", ("base",))
    res = evaluate(make_stub_monthly("s", 5, 6000, 40), plan, pv_kw=5)     # res.simple_payback, res.effect_rub, …
    best_kw, by_kw = recommend({kw: make_stub_monthly("s", kw, 6000, 40) for kw in (3, 5, 10)}, plan)
    res_tz = evaluate_tz(year_metrics, tariff_rub=8.31, buyback_rub_kwh=4.44, capex_rub=291_000)   # формула ТЗ

ТЗ курса: «на входе — показатели раздела 4, тариф и цена выкупа; на выходе — годовой эффект в рублях и срок
окупаемости в годах». Тариф задаётся TariffPlan (или числом в evaluate_tz), цена выкупа — buyback_rub_kwh.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache

import pandas as pd

from .exchange import EnergyMetrics, MonthlyMetrics, annual_from_monthly
from .inputs import DATA, TariffPlan
from .model import (Economics, Scenario, Tariff, annual_effect, annual_effect_monthly, annual_effect_monthly_net,
                    cash_flows, discounted_payback, npv, simple_payback)

CAPEX_LEVELS = ("low", "base", "high")   # колонки capex_<level>_rub в data/capex_estimate.csv
TIE_YEARS = 0.05                         # сроки, различающиеся меньше, считаем равными (recommend)
INF = float("inf")


@dataclass
class Result:
    pv_kw: float
    capex_rub: float          # использованные капзатраты
    self_share: float         # %, из энергетических данных
    coverage: float           # %
    self_rub: float           # экономия на счёте за год (первый год, цены 01.10.2026)
    export_rub: float         # доход от излишков за год
    effect_rub: float         # годовой эффект
    export_share: float       # % излишков в эффекте (гипотеза 2, часть Б)
    simple_payback: float     # лет; inf — не окупается
    disc_payback: float       # лет; inf — не окупается за срок службы
    npv_rub: float
    payback_low: float        # простой срок при capex_low (data/capex_estimate.csv); nan — мощности нет
    payback_high: float       # простой срок при capex_high                     в таблице или цена своя (capex_rub)

    def as_dict(self) -> dict:
        return asdict(self)


@lru_cache
def _capex_table() -> pd.DataFrame:
    return pd.read_csv(DATA / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw")


def capex_estimate(pv_kw: float, level: str = "base") -> float:
    """Капзатраты «под ключ» из data/capex_estimate.csv: level = 'low' | 'base' | 'high'."""
    if level not in CAPEX_LEVELS:
        raise ValueError(f"capex_level: одно из {CAPEX_LEVELS}, получено {level!r}")
    t = _capex_table()
    if pv_kw not in t.index:
        raise ValueError(f"Капзатрат для {pv_kw} кВт нет в data/capex_estimate.csv "
                         f"(есть {list(t.index)}); передайте свою цену capex_rub")
    return float(t.at[pv_kw, f"capex_{level}_rub"])


def default_scenario(pv_kw: float) -> Scenario:
    """Сценарий по умолчанию: официальные параметры params.py и цена инвертора нужной мощности
    (как в scripts/stub_payback.py); для мощности не из таблицы — доля капзатрат."""
    t = _capex_table()
    return Scenario(inverter_cost_rub=float(t.at[pv_kw, "inverter_rub"]) if pv_kw in t.index else None)


def _scenario(pv_kw: float, scenario: Scenario | None) -> Scenario:
    """Сценарий пользователя без цены инвертора получает цену из таблицы (как default_scenario)."""
    if scenario is None:
        return default_scenario(pv_kw)
    if scenario.inverter_cost_rub is None and pv_kw in _capex_table().index:
        return replace(scenario, inverter_cost_rub=default_scenario(pv_kw).inverter_cost_rub)
    return scenario


def _check_prices(capex_rub: float | None, buyback_rub_kwh: float | None) -> None:
    if capex_rub is not None and not capex_rub > 0:
        raise ValueError(f"capex_rub должна быть больше 0, получено {capex_rub}")
    if buyback_rub_kwh is not None and not buyback_rub_kwh >= 0:
        raise ValueError(f"buyback_rub_kwh не может быть отрицательной, получено {buyback_rub_kwh}")


def _range_paybacks(pv_kw: float, effect_rub: float, opex_rub: float) -> tuple[float, float]:
    if pv_kw not in _capex_table().index:
        return float("nan"), float("nan")
    return tuple(simple_payback(capex_estimate(pv_kw, lvl), effect_rub, opex_rub) for lvl in ("low", "high"))


def _result(pv_kw: float, self_share: float, coverage: float, e: Economics, capex: float, sc: Scenario,
            table_capex: bool = True) -> Result:
    flows = cash_flows(e, capex, sc)
    # границы по таблице капзатрат имеют смысл, только если и сама цена — из таблицы
    low, high = _range_paybacks(pv_kw, e.effect_rub, sc.opex_rub) if table_capex else (float("nan"), float("nan"))
    values = dict(pv_kw=pv_kw, capex_rub=capex, self_share=self_share, coverage=coverage,
                  self_rub=e.self_rub, export_rub=e.export_rub, effect_rub=e.effect_rub, export_share=e.export_share,
                  simple_payback=simple_payback(capex, e.effect_rub, sc.opex_rub),
                  disc_payback=discounted_payback(capex, flows, sc), npv_rub=npv(capex, flows, sc),
                  payback_low=low, payback_high=high)
    return Result(**{k: float(v) for k, v in values.items()})   # обычные float, без numpy-типов


def evaluate(months: list[MonthlyMetrics], plan: TariffPlan, pv_kw: float,
             capex_level: str = "base",
             capex_rub: float | None = None,
             buyback_rub_kwh: float | None = None,
             scenario: Scenario | None = None,
             netting: bool = False) -> Result:
    """Окупаемость одной станции по 12 помесячным записям в формате обмена (команда 1 или make_stub_monthly).

    capex_level     — уровень оценки капзатрат из data/capex_estimate.csv;
    capex_rub       — своя цена станции пользователя, приоритетнее capex_level;
    buyback_rub_kwh — своя цена выкупа, одна на все месяцы; None — по тарифу владельца и месяцу (отчёты ТНС);
    scenario        — параметры многолетнего расчёта; None — default_scenario(pv_kw);
    netting         — помесячный зачёт выдачи против покупки (ОП № 442, п. 63(1)); False — основной вариант
                      без зачёта (формула ТЗ), True — вариант с зачётом. Какой вариант основной — решит
                      команда после ответа ТНС (PLAN.md, решение от 21.10).
    """
    if len(months) != 12 or sorted(r.month for r in months) != list(range(1, 13)):
        raise ValueError("Нужно ровно 12 помесячных записей (месяцы 1–12)")
    if any(r.pv_kw != pv_kw for r in months):
        raise ValueError(f"В записях мощность {sorted({r.pv_kw for r in months})}, а pv_kw = {pv_kw}")
    for r in months:
        r.validate()
    _check_prices(capex_rub, buyback_rub_kwh)
    capex = float(capex_rub) if capex_rub is not None else capex_estimate(pv_kw, capex_level)
    sc = _scenario(pv_kw, scenario)
    effect_fn = annual_effect_monthly_net if netting else annual_effect_monthly
    e = effect_fn(months, plan, buyback=buyback_rub_kwh)
    year = annual_from_monthly(months)
    return _result(pv_kw, year.self_share, year.coverage, e, capex, sc, table_capex=capex_rub is None)


def recommend(months_by_kw: dict[int, list[MonthlyMetrics]], plan: TariffPlan,
              **kwargs) -> tuple[int, dict[int, Result]]:
    """Мощность с наименьшим простым сроком окупаемости (по ТЗ) + результаты по всем мощностям.

    Сроки, различающиеся меньше чем на 0,05 года, считаются равными — тогда берётся меньшая (более дешёвая)
    мощность. Если не окупается ни одна станция, возвращается мощность с наибольшим годовым эффектом;
    что станция не окупается, калькулятор видит по simple_payback == inf. kwargs передаются в evaluate()
    (capex_level, buyback_rub_kwh, scenario, netting; capex_rub здесь не имеет смысла — цена у мощностей разная).
    """
    if "capex_rub" in kwargs:
        raise ValueError("recommend(): своя цена capex_rub одна на все мощности — используйте evaluate()")
    if not months_by_kw:
        raise ValueError("recommend(): нет ни одной мощности для сравнения")
    results = {kw: evaluate(months, plan, kw, **kwargs) for kw, months in sorted(months_by_kw.items())}
    finite = {kw: r for kw, r in results.items() if r.simple_payback != INF}
    if not finite:
        return max(results, key=lambda kw: results[kw].effect_rub), results
    best = min(r.simple_payback for r in finite.values())
    return min(kw for kw, r in finite.items() if r.simple_payback - best < TIE_YEARS), results   # критерий — здесь


def evaluate_tz(metrics: EnergyMetrics, tariff_rub: float, buyback_rub_kwh: float, capex_rub: float,
                scenario: Scenario | None = None) -> Result:
    """Дословная формула ТЗ курса: эффект = самопотребление × тариф + излишки × цена выкупа (годовые данные,
    один тариф без диапазонов и зон суток); простой срок = капзатраты / эффект. Дисконтированный срок и NPV —
    по тому же сценарию, что в evaluate(). Цена станции своя, поэтому payback_low / payback_high — nan."""
    metrics.validate()
    _check_prices(capex_rub, buyback_rub_kwh)
    e = annual_effect(metrics, Tariff.flat("ТЗ", tariff_rub), buyback_rub_kwh)
    sc = _scenario(metrics.pv_kw, scenario)
    return _result(metrics.pv_kw, metrics.self_share, metrics.coverage, e, float(capex_rub), sc, table_capex=False)
