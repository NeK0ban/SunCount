"""T2.6, шаг 3: калькуляторы-аналоги и SunCount на одинаковых входных данных → results/competitors_same_inputs.csv.

Входные данные задания (docs/grant/competitors.md, раздел 2): дом в Краснодаре, 500 кВт·ч в месяц, станция около 5 кВт,
городской одноставочный тариф 8,31 ₽ (I диапазон с 01.10.2026), цена выкупа 4,44 ₽ — где калькулятор позволяет их ввести.
Остальное — по умолчанию калькулятора.

Числа аналогов — то, что калькуляторы показали на своих страницах (скриншоты в docs/sources/competitors/), и формулы,
прочитанные в коде этих страниц 12.11.2026. GronEnergy выдаёт результат только после отправки имени и телефона — форму мы
не отправляли, его результат восстановлен по коду страницы (функция calculateRecommendations в /js/calculator.js).

Чтобы сравнивать сравнимое, у каждого инструмента считаются три вещи:
- выработка на 1 кВт панелей — против PVGIS для Краснодара (results/yield_validation.csv);
- как оценена энергия: весь объём по тарифу, весь по цене выкупа или раздельно (своё потребление и излишки);
- цена станции за ватт и что в неё входит.
Запуск: python scripts/t26_competitors.py
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.calc import get_plan, own_load  # noqa: E402
from src.config.configurator import House, _economics, candidates  # noqa: E402

OUT = ROOT / "results" / "competitors_same_inputs.csv"
MONTHLY_KWH, TARIFF, BUYBACK = 500, 8.31, 4.44
LAT_KRASNODAR = 45.035


def pvgis_krasnodar() -> float:
    yv = pd.read_csv(ROOT / "results" / "yield_validation.csv", encoding="utf-8-sig")
    return float(yv[yv.city == "krasnodar"].pvgis_kwh_per_kw_mean.iloc[0])


def suncount_5kw() -> dict:
    """Наш конфигуратор: тот же дом, инвертор 5 кВт и панели ближе всего к 5 кВт (при равенстве — дешевле)."""
    load = own_load(MONTHLY_KWH, "day_absent", (), "krasnodar")
    house = House(city="krasnodar", plan=get_plan("city_single"), load_8760=tuple(load), roof_area_m2=60, tilt=30,
                  azimuth=180, shading="none", phases=1, allowed_kw=15, goal="payback", profile_id="custom")
    # инвертор 5 кВт, как у аналогов: с инвертором 3,6 кВт часть летней выработки срезается, и сравнение «на 1 кВт»
    # было бы нечестным в нашу же пользу по цене и не в пользу по выработке
    c = min((c for c in candidates(house) if c.inverter.ac_kw >= 5), key=lambda c: (abs(c.kwp - 5.0), c.capex_rub))
    _economics(c, house, np.asarray(load, dtype=float), full=True)
    r = c.result
    return dict(tool="SunCount (наш конфигуратор)", date="2026-11-12", kwp=c.kwp, gen_kwh=c.gen_kwh,
                capex_rub=c.capex_rub, capex_includes="оборудование, крепёж, кабели, защита, монтаж, подключение",
                effect_rub=r["effect_rub"], payback_years=r["simple_payback"],
                valuation=(f"своё потребление по тарифу, помесячный зачёт по договору ТНС, остаток — по цене выкупа; "
                           f"самопотребление {r['self_share']:.0f} % выработки"),
                note=f"{c.n_panels} × {c.panel.name}, инвертор {c.inverter.name}; погода — типичный год PVGIS")


def solar_e() -> dict:
    """Solar-E: ответ calc.php для 45,035 / 38,975, 9 × 550 Вт, наклон 30° (широта − 15°) — 7 707,50 кВт·ч в год."""
    gen, cost = 7707.495312, 9 * 19400 + 62000          # модуль 550 Вт по 19 400 ₽ и инвертор SOFAR 5KTLM-G2 за 62 000 ₽
    econom = gen * TARIFF                                 # в коде: amoun_year * price_power — вся выработка по тарифу
    infl, s = 6.0, 0.0                                    # инфляция по умолчанию 6 %, + 0,1 п. п. в год (код страницы)
    for i in range(1, 21):
        s += econom * (1 + (infl + 0.1 * (i - 1)) / 100)
    return dict(tool="Solar-E (solar-e.ru/solarcalc)", date="2026-11-12", kwp=4.95, gen_kwh=gen, capex_rub=cost,
                capex_includes="модули и инвертор; крепёж, расходники и монтаж — флажки, по умолчанию выключены",
                effect_rub=econom, payback_years=math.ceil(cost / (s / 20)),
                valuation="вся выработка по тарифу 8,31 ₽", note="выработка = мощность × инсоляция NASA на наклонную "
                "плоскость, потерь нет; срок на странице «4 года» (округление вверх, с инфляцией 6 %)")


def energob() -> dict:
    """EnergoB: в коде таблица инсоляции по широтам с шагом 5° при «оптимальном угле», КПД системы 0,82."""
    lat45 = [2.70, 3.70, 4.60, 5.15, 5.50, 5.60, 5.70, 5.50, 4.80, 3.80, 2.85, 2.45]
    lat50 = [2.20, 3.25, 4.30, 4.95, 5.30, 5.40, 5.50, 5.20, 4.45, 3.35, 2.40, 2.00]
    t = (LAT_KRASNODAR - 45) / 5
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gen = sum((a + (b - a) * t) * 5.0 * 0.82 * d for a, b, d in zip(lat45, lat50, days))
    cost = 10 * 13500 + 52000 + 15000                     # цены по умолчанию; аккумулятор убран (сетевая станция)
    return dict(tool="EnergoB (solar.energob.ru/calculator)", date="2026-11-12", kwp=5.0, gen_kwh=gen,
                capex_rub=cost, capex_includes="панели, инвертор и «монтаж и комплектующие» 15 000 ₽ — цены по умолчанию",
                effect_rub=gen * TARIFF, payback_years=cost / (gen * TARIFF),
                valuation="вся выработка по тарифу 8,31 ₽",
                note="на странице «данные NASA 2001–2023», в коде — своя таблица по широтам с шагом 5°, без координат; "
                     "на странице 6 529 кВт·ч и 3,7 года")


def learnt_solar() -> dict:
    """Learn TS: Краснодарский край — 4,2 пиковых часа в сутки, выработка × 0,75; экономия всегда по 6 ₽."""
    kw = math.ceil((MONTHLY_KWH / 30 / 4.2 * 1.2) * 1000 / 500) * 500 / 1000
    gen = round(kw * 4.2 * 365 * 0.75)
    return dict(tool="Learn TS (learnt-solar.ru/solar-hch.html)", date="2026-11-12", kwp=kw, gen_kwh=gen,
                capex_rub=np.nan, capex_includes="стоимость не считает", effect_rub=gen * 6, payback_years=np.nan,
                valuation="вся выработка по 6 ₽ — тариф в коде, ввести свой нельзя",
                note="мощность подбирает сам по потреблению; инвертор 1,4 кВт к панелям 5 кВт — по среднему "
                     "потреблению дома, а не по мощности панелей")


def gronenergy(sell: bool) -> dict:
    """GronEnergy: calculateRecommendations() из /js/calculator.js страницы, регион «Краснодар, Сочи» = 1 100 кВт·ч/кВт."""
    ins, loss, budget = 1100, 0.12, 500000                # бюджет по умолчанию «200–500 тыс.»
    power = min(max(math.ceil(MONTHLY_KWH * 12 / (ins * (1 - loss))), 3), 50)
    panels = math.ceil(power * 1000 / 435)
    battery = max(MONTHLY_KWH / 30 * 0.5 * 8 / 24, 5) * 25000 if sell else 0
    cost = panels * 10600 + power * 25000 + power * 15000 + battery
    if cost > budget:
        power = max(math.floor(power * budget / cost), 3)
        cost = budget
    gen = round(power * ins * (1 - loss))
    price = BUYBACK if sell else TARIFF
    effect, acc, years, tariff = gen * price, 0.0, 0, TARIFF
    while acc < cost and years < 30:
        acc += gen * (BUYBACK if sell else tariff)
        years += 1
        tariff *= 1.05
    goal = "цели «экономия» и «продажа излишков»" if sell else "цель «экономия»"
    return dict(tool=f"GronEnergy (gronenergy.ru/vybor-stantsii), {goal}", date="2026-11-12", kwp=power,
                gen_kwh=gen, capex_rub=cost, capex_includes=("панели, инвертор, монтаж" + (" и аккумулятор; сумма "
                "урезана до бюджета 500 000 ₽" if sell else "")),
                effect_rub=effect, payback_years=years,
                valuation=("вся выработка по цене выкупа 4,44 ₽" if sell else "вся выработка по тарифу, +5 % в год"),
                note="результат выдаётся после отправки имени и телефона — восстановлен по коду страницы; "
                     "мощность подбирает сам")


def earlier() -> list:
    """InnoQuest и SOLAR IMPRO посчитаны 31.10.2026 (docs/grant/competitors.md, раздел 2)."""
    return [
        dict(tool="InnoQuest (innoquest.ru)", date="2026-10-31", kwp=5.0, gen_kwh=6093, capex_rub=350000,
             capex_includes="«стоимость СЭС» 70 ₽/Вт по умолчанию", effect_rub=2400 * TARIFF + 3693 * BUYBACK,
             payback_years=8.2, valuation="40 % выработки по тарифу, излишки по цене выкупа, которую вводит "
             "пользователь (здесь 4,44 ₽)", note="рост тарифа 5 % в год входит в срок"),
        dict(tool="SOLAR IMPRO (solar-impro.ru)", date="2026-10-31", kwp=5.0, gen_kwh=np.nan, capex_rub=477445,
             capex_includes="гибридная станция с АКБ 13 кВт·ч и монтажом 18 %", effect_rub=60000, payback_years=8.0,
             valuation="весь счёт за год (5 000 ₽ × 12) при тарифе 10,05 ₽", note="выработку не показывает"),
    ]


def main() -> None:
    rows = [suncount_5kw(), *earlier(), solar_e(), energob(), learnt_solar(), gronenergy(False), gronenergy(True)]
    df = pd.DataFrame(rows)
    pv = pvgis_krasnodar()
    df["kwh_per_kw"] = df.gen_kwh / df.kwp
    df["vs_pvgis_pct"] = (df.kwh_per_kw / pv - 1) * 100
    df["rub_per_w"] = df.capex_rub / (df.kwp * 1000)
    df["effect_per_kw_rub"] = df.effect_rub / df.kwp
    df.attrs["pvgis"] = pv
    cols = ["tool", "date", "kwp", "gen_kwh", "kwh_per_kw", "vs_pvgis_pct", "capex_rub", "rub_per_w", "capex_includes",
            "effect_rub", "effect_per_kw_rub", "payback_years", "valuation", "note"]
    df[cols].round(2).to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"PVGIS, Краснодар: {pv:.0f} кВт·ч/кВт")
    print(df[["tool", "kwp", "gen_kwh", "kwh_per_kw", "vs_pvgis_pct", "capex_rub", "rub_per_w", "effect_rub",
              "payback_years"]].round(1).to_string())
    print(df.valuation.iloc[0])
    print(df.note.iloc[0])


if __name__ == "__main__":
    main()
