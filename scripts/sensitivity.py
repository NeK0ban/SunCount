"""T3.1 — анализ чувствительности: 11 параметров, торнадо по 4 тарифам.

Базовый случай (раздел 12.3 мастер-ТЗ): СЭС 5 кВт, Краснодар, потребление 6000 кВт·ч/год,
доля самопотребления 40 % (условный профиль make_stub_monthly — до реальных портретов
команды 1, финал задачи), капзатраты — база из data/capex_estimate.csv,
Scenario(inverter_cost_rub=…) для 5 кВт. Считается для каждого из 4 тарифов.

Метод: меняем по одному параметру — сначала на нижнее, потом на верхнее значение,
остальные базовые; записываем простой и дисконтированный срок окупаемости.
Размах = |верх − низ| (округление до 0,1 года). src/econ/ не меняется:
тариф и цена выкупа — масштабированием Economics (сезонность цены выкупа сохраняется),
сценарии — dataclasses.replace(Scenario, …).

Выход:
  results/sensitivity.csv (utf-8-sig),
  results/tornado_<код тарифа>.png — простой и дисконтированный срок на двух подграфиках.
Коды: city_single, city_zones, rural_single, rural_zones.

Запуск: python scripts/sensitivity.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ.exchange import make_stub_monthly          # noqa: E402
from src.econ.inputs import TariffPlan                   # noqa: E402
from src.econ.model import (Economics, Scenario, annual_effect_monthly,  # noqa: E402
                            cash_flows, discounted_payback, simple_payback)

PV_KW = 5
LOAD_KWH = 6000          # годовое потребление дома, кВт·ч (≈ 500 кВт·ч/мес)
SELF_SHARE = 40          # базовая доля самопотребления, %
PV_KWH_PER_KW_LO, PV_KWH_PER_KW_HI = 1240.0, 1311.5   # выработка: потери 14 % / 9 %

PLANS = [                # (код имени файла, тариф)
    ("city_single", TariffPlan("Город, одноставочный", "base", "single", ("base",))),
    ("city_zones", TariffPlan("Город, день/ночь", "base", "two_zone", ("base",))),
    ("rural_single", TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",))),
    ("rural_zones", TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",))),
]
# палитра 4 тарифов (T3.5)
PALETTE = {"city_single": "#1f6fb2", "city_zones": "#2a9d4b",
           "rural_single": "#e08a1e", "rural_zones": "#8e44ad"}

plt.rcParams.update({"font.family": "sans-serif",
                     "font.sans-serif": ["Arial", "DejaVu Sans"],
                     "axes.unicode_minus": False})

INF = float("inf")


# ----------------------------------------------------------------- вспомогательные
def ru(x: float, nd: int = 1) -> str:
    """Число с десятичной запятой (для подписей графиков)."""
    return f"{x:.{nd}f}".replace(".", ",")


def fmt_years(v: float) -> str:
    return "не окуп." if v == INF else ru(v, 1)


def scaled(e: Economics, k_self: float = 1.0, k_export: float = 1.0) -> Economics:
    """Масштабирует части эффекта (тариф — self, цена выкупа — export)."""
    s, x = e.self_rub * k_self, e.export_rub * k_export
    return Economics(s, x, s + x, 100 * x / (s + x) if s + x else 0.0)


def paybacks(e: Economics, capex: float, sc: Scenario) -> tuple[float, float]:
    """(простой, дисконтированный) срок окупаемости, лет."""
    return (simple_payback(capex, e.effect_rub, sc.opex_rub),
            discounted_payback(capex, cash_flows(e, capex, sc), sc))


def swing(a: float, b: float) -> float:
    """Размах |верх − низ|; если оба варианта не окупаются — 0 (варианты не различаются)."""
    return 0.0 if (a == INF and b == INF) else abs(a - b)


def shown_swing(a: float, b: float, horizon: float) -> float:
    """Размах, как он виден на диаграмме: «не окупается» доходит до горизонта. Ключ сортировки:
    без него все параметры с inf стояли бы наверху в случайном порядке."""
    a, b = (horizon if a == INF else a), (horizon if b == INF else b)
    return abs(a - b)


# ----------------------------------------------------------------- входные данные
cap = pd.read_csv(ROOT / "data" / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw")
CAPEX_BASE = float(cap.capex_base_rub[PV_KW])
CAPEX_LOW = float(cap.capex_low_rub[PV_KW])
CAPEX_HIGH = float(cap.capex_high_rub[PV_KW])
INVERTER_COST = float(cap.inverter_rub[PV_KW])

# коэффициенты цены выкупа — считаются кодом из CSV (май–сентябрь 2026), не вручную
cat = pd.read_csv(ROOT / "data" / "buyback_by_category.csv", encoding="utf-8-sig")


def buyback_coef(col: str) -> tuple[float, float, float, float]:
    """(коэф. низ, коэф. верх, мин. ₽, макс. ₽) по помесячной категории."""
    s = cat[col]
    return float(s.min() / s.mean()), float(s.max() / s.mean()), float(s.min()), float(s.max())


BK_FLAT = buyback_coef("flat_rub_kwh")           # 1-я ЦК (одноставочный)
BK_ZONES = buyback_coef("zones_day_rub_kwh")     # 2-я ЦК (день/ночь)

# базовый профиль и профили для параметров 2 и 11
months = make_stub_monthly("sens", PV_KW, LOAD_KWH, SELF_SHARE, "krasnodar")
months_lo_share = make_stub_monthly("sens", PV_KW, LOAD_KWH, 20, "krasnodar")
months_hi_share = make_stub_monthly("sens", PV_KW, LOAD_KWH, 50, "krasnodar")
months_hi_pv = make_stub_monthly("sens", PV_KW * PV_KWH_PER_KW_HI / PV_KWH_PER_KW_LO,
                                 LOAD_KWH, SELF_SHARE, "krasnodar")

# сценарии (параметры 5–10); замена инвертора — по цене из CSV
SC = Scenario(inverter_cost_rub=INVERTER_COST)
HORIZON = SC.lifetime    # базовый срок службы — горизонт «не окупается»
SC_DISC_LO = replace(SC, discount_rate={y: r - 0.03 for y, r in SC.discount_rate.items()},
                     long_run_discount=SC.long_run_discount - 0.03)
SC_DISC_HI = replace(SC, discount_rate={y: r + 0.03 for y, r in SC.discount_rate.items()},
                     long_run_discount=SC.long_run_discount + 0.03)
SC_TARIFF_4 = replace(SC, tariff_growth={})       # весь срок — долгосрочный рост 4 %
SC_LIFE_30 = replace(SC, lifetime=30)
SC_DEG_06 = replace(SC, degradation=0.006)
SC_NDFL_EXT = replace(SC, ndfl_free_until=2100)   # льготу продлили
SC_OPEX_1 = replace(SC, opex_rub=0.01 * CAPEX_BASE)


# ----------------------------------------------------------------- расчёт
rows: list[dict] = []
for code, plan in PLANS:
    e_base = annual_effect_monthly(months, plan)
    base_pair = paybacks(e_base, CAPEX_BASE, SC)
    simple_base, disc_base = round(base_pair[0], 1), round(base_pair[1], 1)

    e_lo_share = annual_effect_monthly(months_lo_share, plan)
    e_hi_share = annual_effect_monthly(months_hi_share, plan)
    e_hi_pv = annual_effect_monthly(months_hi_pv, plan)

    k_lo, k_hi, p_min, p_max = BK_FLAT if plan.owner_category == "flat" else BK_ZONES

    params = [
        # (параметр, подпись низа, подпись верха, (низ), (верх))
        ("Тариф", "−20 %", "+20 %",
         paybacks(scaled(e_base, k_self=0.8), CAPEX_BASE, SC),
         paybacks(scaled(e_base, k_self=1.2), CAPEX_BASE, SC)),
        ("Доля самопотребления", "20 %", "50 %",
         paybacks(e_lo_share, CAPEX_BASE, SC),
         paybacks(e_hi_share, CAPEX_BASE, SC)),
        ("Цена выкупа", f"{ru(p_min, 2)} ₽", f"{ru(p_max, 2)} ₽",
         paybacks(scaled(e_base, k_export=k_lo), CAPEX_BASE, SC),
         paybacks(scaled(e_base, k_export=k_hi), CAPEX_BASE, SC)),
        ("Цена выкупа, сценарий ТНС ×0,5", "×0,5", "×1,0 (база)",
         paybacks(scaled(e_base, k_export=0.5), CAPEX_BASE, SC),
         base_pair),
        ("Капзатраты", f"{ru(CAPEX_LOW / 1000, 0)} тыс. ₽", f"{ru(CAPEX_HIGH / 1000, 0)} тыс. ₽",
         paybacks(e_base, CAPEX_LOW, SC),
         paybacks(e_base, CAPEX_HIGH, SC)),
        ("Ставка дисконтирования", "−3 п. п.", "+3 п. п.",
         paybacks(e_base, CAPEX_BASE, SC_DISC_LO),
         paybacks(e_base, CAPEX_BASE, SC_DISC_HI)),
        ("Рост тарифа", "4 %/год", "прогноз МЭР",
         paybacks(e_base, CAPEX_BASE, SC_TARIFF_4),
         base_pair),
        ("Срок службы", "25 лет", "30 лет",
         base_pair,
         paybacks(e_base, CAPEX_BASE, SC_LIFE_30)),
        ("Деградация панелей", "0,4 %/год", "0,6 %/год",
         base_pair,
         paybacks(e_base, CAPEX_BASE, SC_DEG_06)),
        ("НДФЛ с дохода от излишков", "с 2029 г.", "льготу продлят",
         base_pair,
         paybacks(e_base, CAPEX_BASE, SC_NDFL_EXT)),
        ("Обслуживание", "0 ₽/год", f"{SC_OPEX_1.opex_rub:,.0f} ₽/год".replace(",", " "),
         base_pair,
         paybacks(e_base, CAPEX_BASE, SC_OPEX_1)),
        ("Выработка СЭС", f"{ru(PV_KWH_PER_KW_LO, 0)} кВт·ч/кВт",
         f"{ru(PV_KWH_PER_KW_HI, 1)} кВт·ч/кВт",
         base_pair,
         paybacks(e_hi_pv, CAPEX_BASE, SC)),
    ]

    for name, lo_label, hi_label, (s_lo, d_lo), (s_hi, d_hi) in params:
        s_lo, s_hi, d_lo, d_hi = round(s_lo, 1), round(s_hi, 1), round(d_lo, 1), round(d_hi, 1)
        rows.append({
            "tariff": plan.name, "parameter": name,
            "low_label": lo_label, "high_label": hi_label,
            "simple_low": s_lo, "simple_high": s_hi,
            "disc_low": d_lo, "disc_high": d_hi,
            "swing_simple": round(swing(s_lo, s_hi), 1),
            "swing_disc": round(swing(d_lo, d_hi), 1),
            "simple_base": simple_base, "disc_base": disc_base,
        })

df = pd.DataFrame(rows)
out = ROOT / "results"
out.mkdir(exist_ok=True)
df.to_csv(out / "sensitivity.csv", index=False, encoding="utf-8-sig")

# ----------------------------------------------------------------- проверка (ТЗ): база vs stub_payback
print(f"База: СЭС {PV_KW} кВт, Краснодар, {LOAD_KWH} кВт·ч/год, самопотребление {SELF_SHARE} %, "
      f"капзатраты {ru(CAPEX_BASE / 1000, 0)} тыс. ₽, инвертор {ru(INVERTER_COST / 1000, 1)} тыс. ₽")
print(f"Коэффициенты цены выкупа (data/buyback_by_category.csv): одноставочный "
      f"{BK_FLAT[0]:.3f}/{BK_FLAT[1]:.3f}, день/ночь {BK_ZONES[0]:.3f}/{BK_ZONES[1]:.3f}")

stub = pd.read_csv(out / "stub_payback.csv", encoding="utf-8-sig")
stub = stub[(stub.pv_kw == PV_KW) & (stub.self_share_target == SELF_SHARE)].set_index("tariff")
print("\nСверка базы со scripts/stub_payback.py (та же точка):")
for code, plan in PLANS:
    row = df[df.tariff == plan.name].iloc[0]
    ref_s = float(stub.loc[plan.name, "simple_payback"])
    ref_d = float(stub.loc[plan.name, "disc_payback"])
    ok = "OK" if abs(row.simple_base - ref_s) < 0.05 and abs(row.disc_base - ref_d) < 0.05 \
        else "РАСХОЖДЕНИЕ"
    print(f"  {plan.name}: {ru(row.simple_base)} / {ru(row.disc_base)} лет против "
          f"{ru(ref_s)} / {ru(ref_d)} в stub_payback — {ok}")

# та же база через единую точку входа модели (T1.4, src/econ/api.py): расчёт не должен расходиться
from src.econ.api import evaluate  # noqa: E402
print("\nСверка базы с src/econ/api.py (evaluate):")
for code, plan in PLANS:
    row = df[df.tariff == plan.name].iloc[0]
    r = evaluate(months, plan, pv_kw=PV_KW)
    ok = "OK" if abs(round(r.simple_payback, 1) - row.simple_base) < 0.05 and \
        abs(round(r.disc_payback, 1) - row.disc_base) < 0.05 else "РАСХОЖДЕНИЕ"
    print(f"  {plan.name}: {ru(r.simple_payback)} / {ru(r.disc_payback)} лет — {ok}")


# ----------------------------------------------------------------- торнадо
def tornado(code: str, plan: TariffPlan) -> None:
    """Одна диаграмма на тариф: простой и дисконтированный срок, параметры по размаху.

    Полоса идёт от «низа» до «верха» вокруг пунктирной линии базового срока:
    тёмный сегмент — вариант «низ» параметра, светлый — «верх»; на концах — значения сроков.
    """
    sub = df[df.tariff == plan.name]
    simple_base, disc_base = float(sub.iloc[0].simple_base), float(sub.iloc[0].disc_base)
    color = PALETTE[code]

    # подграфики независимы: каждый сортируется по своему размаху и подписывает параметры сам
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.6))
    specs = [
        (axes[0], "simple_low", "simple_high", "swing_simple", simple_base,
         f"Простой срок окупаемости, лет — база {ru(simple_base)}"),
        (axes[1], "disc_low", "disc_high", "swing_disc", disc_base,
         f"Дисконтированный срок окупаемости, лет — база {ru(disc_base)}"),
    ]
    for ax, col_lo, col_hi, col_swing, base, title in specs:
        # горизонт оси: максимум конечных значений; «не окупается» упирается в срок службы
        recs = sub.to_dict("records")
        finite = [float(r[c]) for r in recs for c in (col_lo, col_hi) if r[c] != INF]
        has_inf = any(float(r[c]) == INF for r in recs for c in (col_lo, col_hi))
        cap_val = max(finite + ([float(HORIZON)] if has_inf else []))
        # сортировка по видимому размаху (inf → горизонт), при равенстве — как в таблице
        data = sorted(recs, key=lambda r: -shown_swing(float(r[col_lo]), float(r[col_hi]), cap_val))
        n = len(data)

        for y, row in enumerate(data):     # data[0] (максимальный размах) — сверху
            lo, hi = float(row[col_lo]), float(row[col_hi])
            a, b = (cap_val if lo == INF else lo), (cap_val if hi == INF else hi)
            left, right, width = min(a, b), max(a, b), abs(a - b)
            if width < 0.05:            # параметр не меняет срок
                txt = "оба: не окуп." if lo == INF else f"не влияет: {fmt_years(lo)}"
                ax.text(base + 0.3, y, txt, va="center", ha="left",
                        fontsize=8, color="#333333")
                continue
            lo_is_left = a <= b
            # полоса от «низа» до «верха», разрезанная линией базы:
            # тёмный сегмент — вариант «низ», светлый — «верх»
            mid = min(max(base, left), right)
            if mid > left:
                ax.barh(y, mid - left, left=left, color=color,
                        alpha=0.9 if lo_is_left else 0.4, height=0.62, zorder=3)
            if right > mid:
                ax.barh(y, right - mid, left=mid, color=color,
                        alpha=0.4 if lo_is_left else 0.9, height=0.62, zorder=3)
            # подписи значений на концах полосы
            ax.text(left - 0.25, y, fmt_years(lo if lo_is_left else hi),
                    va="center", ha="right", fontsize=8)
            ax.text(right + 0.25, y, fmt_years(hi if lo_is_left else lo),
                    va="center", ha="left", fontsize=8)

        ax.axvline(base, color="black", lw=1.3, ls="--", zorder=5)
        ax.set_yticks(range(n), [r["parameter"] for r in data], fontsize=9)
        ax.set_ylim(n - 0.4, -0.6)     # ось инвертирована: сверху — самый влиятельный
        ax.set_xlabel("лет", fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="x", alpha=0.3, zorder=0)
        ax.set_xlim(0, cap_val + 4.5)   # запас под подписи значений
        ax.tick_params(labelsize=9)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))  # T3.5

    handles = [Patch(facecolor=color, alpha=0.9, label="Низ параметра"),
               Patch(facecolor=color, alpha=0.4, label="Верх параметра")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.075),
               ncol=2, fontsize=8, frameon=False, title="Полоса: от «низа» до «верха» параметра",
               title_fontsize=8)
    fig.suptitle(f"{plan.name}: анализ чувствительности срока окупаемости (торнадо)\n"
                 f"База: СЭС {PV_KW} кВт, Краснодар, потребление {LOAD_KWH} кВт·ч/год, самопотребление "
                 f"{SELF_SHARE} %, капзатраты {ru(CAPEX_BASE / 1000, 0)} тыс. ₽", fontsize=12)
    fig.text(0.01, 0.05,
             f"«не окуп.» — не окупается за базовый срок службы {HORIZON} лет; такие параметры отсортированы "
             "по видимой длине полосы (до горизонта).",
             fontsize=8.5, color="#333333")
    fig.text(0.01, 0.02, "Источник: расчёт SunCount, данные — docs/assumptions.md",
             fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(0, 0.13, 1, 0.95))
    fig.savefig(out / f"tornado_{code}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


for code, plan in PLANS:
    tornado(code, plan)

# ----------------------------------------------------------------- вывод в консоль
print("\nРанжирование факторов (топ-3 по размаху):")


def fmt_swing(v: float) -> str:
    return "∞ (параметр решает: окупается/нет)" if v == INF else f"+{ru(v)} г."


for code, plan in PLANS:
    sub = df[df.tariff == plan.name]
    key = lambda lo, hi: sub.apply(lambda r: shown_swing(r[lo], r[hi], float(HORIZON)), axis=1)
    top_s = sub.assign(k=key("simple_low", "simple_high")).nlargest(3, "k")[["parameter", "swing_simple"]]
    top_d = sub.assign(k=key("disc_low", "disc_high")).nlargest(3, "k")[["parameter", "swing_disc"]]
    print(f"\n  {plan.name} (база {ru(float(sub.iloc[0].simple_base))} / "
          f"{ru(float(sub.iloc[0].disc_base))} лет):")
    print("    простой:    " + "; ".join(f"{r.parameter} {fmt_swing(r.swing_simple)}"
                                         for r in top_s.itertuples()))
    print("    дисконт.:  " + "; ".join(f"{r.parameter} {fmt_swing(r.swing_disc)}"
                                        for r in top_d.itertuples()))

print("\nГотово: results/sensitivity.csv, "
      + ", ".join(f"results/tornado_{c}.png" for c, _ in PLANS))
