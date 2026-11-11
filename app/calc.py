# app/calc.py
"""Расчётная часть веб-сервиса: подбор конфигурации СЭС под дом пользователя. НЕ импортирует streamlit —
можно вызывать из теста или консоли.

Числа — только из модели: конфигуратор src/config (каталог оборудования, энергорасчёт по паспорту панели,
подбор), экономика — src/econ (та же модель тарифов, цены выкупа и окупаемости, что и в отчётах).
Потребление — почасовой профиль команды 1: готовый портрет (data/hourly_profiles) или build_profile
по квитанциям, режиму присутствия и приборам (src/energy/api.py).
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.config.catalog import inverter as catalog_inverter, panel as catalog_panel  # noqa: E402
from src.config.configurator import GOALS, House, binding_constraint, configure, hourly_ac  # noqa: E402
from src.config.weather import local_calendar  # noqa: E402
from src.econ.inputs import TariffPlan  # noqa: E402
from src.energy.api import build_profile  # noqa: E402
from app.texts import TARIFFS  # noqa: E402

MONTHS_GEN = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
              "октябрь", "ноябрь", "декабрь"]
PROFILES_DIR = ROOT / "data" / "hourly_profiles"   # почасовые портреты команды 1 (8760 ч, местное время)

# Приборы, дающие сниженный тариф (категория reduced), и диапазоны потребления для них:
# первый ключ — отопительный период (октябрь–апрель), второй — май–сентябрь (data/tariff_ranges_2026.csv)
HEATING_STOVE_RANGES = ("reduced_heating", "reduced_heating_stove")
HEATING_RANGES = ("reduced_heating", "reduced_heating_nostove")
STOVE_RANGES = ("reduced_stove",)


def get_plan(tariff_key: str, appliances=()) -> TariffPlan:
    """Тариф с учётом приборов (T4.2).

    Дом с электроотоплением и (или) электроплитой и в городе платит по сниженному тарифу — категория reduced,
    как у села (data/tariffs_2026.csv: «Разделы 2–8: сельское население; город с электроплитами/электроотоплением»).
    Вид тарифа (одноставочный или день/ночь) и название остаются теми, что выбрал пользователь; меняются
    категория и диапазоны потребления. Кондиционер и насос тариф не меняют.
    """
    plan = TARIFFS[tariff_key]["plan"]
    heating, stove = "el_heating" in appliances, "el_stove" in appliances
    if heating:
        ranges = HEATING_STOVE_RANGES if stove else HEATING_RANGES
    elif stove:
        ranges = STOVE_RANGES
    else:
        return plan
    return TariffPlan(plan.name, "reduced", plan.tariff_type, ranges, plan.date_from)


def reduced_by_appliances(tariff_key: str, appliances=()) -> bool:
    """True, если из-за приборов расчёт идёт по сниженному тарифу, хотя выбран городской."""
    return TARIFFS[tariff_key]["plan"].price_category == "base" and get_plan(tariff_key, appliances).price_category == "reduced"


@lru_cache(maxsize=16)
def portrait_load(profile_id: str, city: str) -> tuple:
    """Почасовое потребление готового портрета команды 1; () — если файла нет."""
    path = PROFILES_DIR / f"{profile_id}_{city}_8760.csv"
    if not path.exists():
        return ()
    return tuple(pd.read_csv(path, encoding="utf-8-sig").load_kwh.astype(float))


def own_load(monthly_kwh, presence: str, appliances, city: str) -> tuple:
    """Почасовое потребление по квитанциям: build_profile команды 1 (месячные суммы точные, распределение по часам —
    по режиму присутствия и приборам). monthly_kwh — одно среднее значение или 12 месячных."""
    months = list(monthly_kwh) if isinstance(monthly_kwh, (list, tuple)) else [float(monthly_kwh)] * 12
    if len(months) != 12 or min(months) <= 0:
        raise ValueError("Потребление по месяцам: нужны все 12 значений больше нуля")
    return tuple(float(v) for v in build_profile(months, presence, set(appliances), city))


def run_configurator(city: str, tariff_key: str, load: tuple, appliances=(), roof_area_m2: float = 40,
                     tilt: float = 30, azimuth: float = 180, shading: str = "none", phases: int = 1,
                     allowed_kw: float = 15, budget_rub: float | None = None, goal: str = "own",
                     profile_id: str = "custom", netting: bool = True) -> dict:
    """Подбор для веб-сервиса. Возвращает словарь из простых типов (для кеша Streamlit):
    {"configs": [вариант, ...], "constraint": текст} — первый вариант рекомендуемый; configs пуст, если подходящих нет.
    Вариант: panel, panel_id, n_panels, kwp, area_m2, inverter, strings, capex/границы, bom, gen_kwh,
    clipped_kwh и поля api.Result (simple_payback, disc_payback, npv_rub, effect_rub, self_share, export_share, …).
    """
    if goal not in GOALS:
        raise ValueError(f"Цель подбора: одна из {sorted(GOALS)}")
    house = House(city=city, plan=get_plan(tariff_key, appliances), load_8760=tuple(load),
                  roof_area_m2=roof_area_m2, tilt=tilt, azimuth=azimuth, shading=shading, phases=phases,
                  allowed_kw=allowed_kw, budget_rub=budget_rub, goal=goal, profile_id=profile_id,
                  netting=netting)
    best = configure(house)
    out = []
    for c in best:
        out.append({
            "panel": c.panel.name, "panel_id": c.panel.panel_id, "panel_w": c.panel.pmax_w,
            "n_panels": c.n_panels, "kwp": c.kwp, "area_m2": c.area_m2,
            "inverter": c.inverter.name, "inverter_id": c.inverter.inverter_id, "inverter_kw": c.inverter.ac_kw,
            "phases": c.inverter.phases, "strings": list(c.strings),
            "capex_rub": c.capex_rub, "capex_low_rub": c.capex_low_rub, "capex_high_rub": c.capex_high_rub,
            "bom": [list(r) for r in c.bom], "gen_kwh": c.gen_kwh, "clipped_kwh": c.clipped_kwh,
            "load_kwh": float(sum(load)), **c.result,
        })
    return {"configs": out, "constraint": binding_constraint(best[0], house) if best else ""}


def average_day(config: dict, city: str, load: tuple, month: int, tilt: float = 30, azimuth: float = 180,
                shading: str = "none") -> dict:
    """Средние сутки месяца для графика «лето / зима» (T4.4): выработка станции, потребление дома и
    самопотребление по часам 0–23, кВт·ч в час. config — вариант из run_configurator (нужны panel_id,
    n_panels, inverter_id, strings); остальные параметры — те же, что ушли в run_configurator.
    Самопотребление считается по каждому часу года, а потом усредняется: min(выработка, потребление) часа."""
    if not 1 <= month <= 12:
        raise ValueError("Месяц: от 1 до 12")
    house = House(city=city, plan=next(iter(TARIFFS.values()))["plan"], load_8760=tuple(load), tilt=tilt,
                  azimuth=azimuth, shading=shading)
    gen, _ = hourly_ac(catalog_panel(config["panel_id"]), int(config["n_panels"]),
                       catalog_inverter(config["inverter_id"]), tuple(config["strings"]), house)
    cal = local_calendar()
    sel = (cal.month == month).to_numpy()
    hours = cal.hour.to_numpy()[sel]
    frame = pd.DataFrame({"hour": hours, "gen": gen[sel], "load": pd.Series(load).to_numpy()[sel]})
    frame["self"] = frame[["gen", "load"]].min(axis=1)
    day = frame.groupby("hour")[["gen", "load", "self"]].mean()
    return {k: [float(v) for v in day[k]] for k in ("gen", "load", "self")}

@lru_cache(maxsize=1)
@lru_cache(maxsize=1)
def phase_limits() -> dict:
    """Самые мощные инверторы каталога по числу фаз: {фазы: (кВт на выходе, кВт панелей по паспорту)}."""
    inv = pd.read_csv(ROOT / "data" / "equipment" / "inverters.csv", encoding="utf-8-sig")
    return {int(ph): (float(g.ac_kw.max()), float(g.max_pv_kw.max())) for ph, g in inv.groupby("phases")}


def data_versions() -> dict:
    """Какие данные лежат в основе расчёта — для подписи под результатом (берётся из файлов, не вручную)."""
    plan = next(iter(TARIFFS.values()))["plan"]
    y, m, d = plan.date_from.split("-")
    bb = pd.read_csv(ROOT / "data" / "buyback_by_category.csv", encoding="utf-8-sig").month.sort_values()
    first, last = bb.iloc[0], bb.iloc[-1]
    buyback = (f"{MONTHS_GEN[int(first[5:7]) - 1]}–{MONTHS_GEN[int(last[5:7]) - 1]} {last[:4]} г."
               if first[:4] == last[:4] else f"{first}–{last}")
    meteo = json.loads((ROOT / "data" / "raw" / "pvgis" / "krasnodar_tmy.json").read_text(encoding="utf-8"))
    meteo = meteo["inputs"]["meteo_data"]
    prices = pd.read_csv(ROOT / "data" / "equipment" / "inverters.csv", encoding="utf-8-sig").price_accessed.max()
    return {"tariffs_from": f"{d}.{m}.{y}", "buyback": buyback,
            "weather": f"типичный метеогод PVGIS по {meteo['year_min']}–{meteo['year_max']} годам",
            "prices": pd.Timestamp(prices).strftime("%d.%m.%Y")}
