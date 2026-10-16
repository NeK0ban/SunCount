"""Предварительная прикидка окупаемости SunCount на условных долях самопотребления (задачи 2.4–2.5).

Реальное: тарифы ТНС с 01.10.2026 (с диапазонами), цена выкупа по тарифу владельца и по месяцам,
сезонность выработки PVGIS, официальные параметры по годам (src/econ/params.py).
Условное: капзатраты (каталог × наценка на монтаж), профиль потребления (доля самопотребления 20–80 %,
равномерное потребление по месяцам) — заменить КП и данными команды 1.

Запуск: python scripts/stub_payback.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ.exchange import annual_from_monthly, make_stub_monthly, write_csv  # noqa: E402
from src.econ.inputs import TariffPlan, buyback_monthly, zone_prices  # noqa: E402
from src.econ.model import (Scenario, Tariff, annual_effect, annual_effect_monthly,  # noqa: E402
                            cash_flows, discounted_payback, npv, simple_payback)

CITY = "krasnodar"
LOAD_KWH = 6000          # годовое потребление дома, кВт·ч (≈ 500 кВт·ч/мес) — УСЛОВНО
PV_SIZES = (3, 5, 10)

PLANS = [
    TariffPlan("Город, одноставочный", "base", "single", ("base",)),
    TariffPlan("Город, день/ночь", "base", "two_zone", ("base",)),
    TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",)),
    TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",)),
]

# --- капзатраты: база и диапазон из scripts/estimate_capex.py (data/capex_estimate.csv)
cap = pd.read_csv(ROOT / "data" / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw")
CAPEX = cap.capex_base_rub.astype(float).to_dict()
CAPEX_LOW, CAPEX_HIGH = cap.capex_low_rub.to_dict(), cap.capex_high_rub.to_dict()

rows, monthly_out = [], []
for kw in PV_SIZES:
    for share in range(20, 81, 10):
        months = make_stub_monthly(f"stub_{share}", kw, LOAD_KWH, share, CITY)
        year = annual_from_monthly(months)
        if year.self_share < share - 2:
            continue  # такая доля недостижима: дому не съесть столько днём
        monthly_out += months
        sc = Scenario(inverter_cost_rub=float(cap.inverter_rub[kw]))
        for plan in PLANS:
            e = annual_effect_monthly(months, plan)
            flows = cash_flows(e, CAPEX[kw], sc)
            rows.append({
                "pv_kw": kw, "capex_rub": CAPEX[kw], "self_share_target": share,
                "self_share": round(year.self_share, 1), "tariff": plan.name,
                "effect_rub": round(e.effect_rub), "self_rub": round(e.self_rub), "export_rub": round(e.export_rub),
                "export_share_pct": round(e.export_share, 1),
                "simple_payback": round(simple_payback(CAPEX[kw], e.effect_rub), 1),
                "simple_payback_low": round(simple_payback(CAPEX_LOW[kw], e.effect_rub), 1),
                "simple_payback_high": round(simple_payback(CAPEX_HIGH[kw], e.effect_rub), 1),
                "disc_payback": round(discounted_payback(CAPEX[kw], flows, sc), 1),
                "npv_rub": round(npv(CAPEX[kw], flows, sc)),
            })

out = ROOT / "results"
out.mkdir(exist_ok=True)
write_csv(monthly_out, ROOT / "data" / "stub_energy_metrics_monthly.csv")
write_csv([annual_from_monthly(monthly_out[i:i + 12]) for i in range(0, len(monthly_out), 12)],
          ROOT / "data" / "stub_energy_metrics.csv")
df = pd.DataFrame(rows)
df.to_csv(out / "stub_payback.csv", index=False, encoding="utf-8-sig")

print("Капзатраты под ключ (оценка):", CAPEX)
for c in ("flat", "zones"):
    bb = buyback_monthly(c)
    print(f"Цена выкупа ({c}): янв {bb[1]:.2f} … июн {bb[6]:.2f} … ноя {bb[11]:.2f} ₽/кВт·ч")
pt = lambda col: df.pivot_table(index=["pv_kw", "self_share_target"], columns="tariff", values=col)[[p.name for p in PLANS]]
print("\n== Простой срок окупаемости, лет\n" + pt("simple_payback").to_string())
print("\n== Дисконтированный срок окупаемости, лет (inf — не окупается за 25 лет)\n" + pt("disc_payback").to_string())
print("\n== Доля дохода от излишков, % (гипотеза 2: ≤ 20 %)\n" + pt("export_share_pct").to_string())

# --- проверка эффекта диапазонов: дом с большим потреблением (зима тяжелее), 10 кВт, город
heavy_shape = [1.6, 1.5, 1.2, 0.9, 0.8, 1.0, 1.2, 1.2, 0.9, 0.8, 1.2, 1.6]
heavy = make_stub_monthly("heavy", 10, 18000, 60, CITY, load_shape=heavy_shape)
plan = PLANS[0]
e_m = annual_effect_monthly(heavy, plan)
p1 = zone_prices(plan)["I"]["day"]
e_tz = annual_effect(annual_from_monthly(heavy), Tariff.flat("ТЗ", p1), sum(buyback_monthly("flat").values()) / 12)
rub = lambda x: f"{x:,.0f}".replace(",", " ")
print(f"\n== Диапазоны тарифа: дом 18 000 кВт·ч/год, 10 кВт, город одноставочный\n"
      f"   формула ТЗ (I диапазон, средний выкуп): {rub(e_tz.effect_rub)} ₽/год\n"
      f"   помесячно с диапазонами и сезонным выкупом: {rub(e_m.effect_rub)} ₽/год "
      f"({100 * (e_m.effect_rub / e_tz.effect_rub - 1):+.0f} %)")

# --- тепловые карты для 5 кВт
fig, axes = plt.subplots(1, 3, figsize=(20, 5.2), sharey=True)
panels = [("simple_payback", "Простой срок окупаемости, лет", "RdYlGn_r", 4, 16, "{:.1f}"),
          ("disc_payback", "Дисконтированный срок окупаемости, лет", "RdYlGn_r", 4, 25, "{:.1f}"),
          ("export_share_pct", "Доля дохода от излишков, %", "Blues", 0, 100, "{:.0f}")]
for ax, (col, title, cmap, vmin, vmax, fmt) in zip(axes, panels):
    p = df[df.pv_kw == 5].pivot_table(index="self_share_target", columns="tariff", values=col)[[pl.name for pl in PLANS]]
    im = ax.imshow(p.values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(p.columns)), [c.replace(", ", "\n") for c in p.columns], fontsize=8)
    ax.set_yticks(range(len(p.index)), [f"{i} %" for i in p.index])
    for i in range(p.shape[0]):
        for j in range(p.shape[1]):
            ax.text(j, i, fmt.format(p.values[i, j]), ha="center", va="center", fontsize=9)
    ax.set_title(title, fontsize=10)
    fig.colorbar(im, ax=ax, shrink=0.85)
axes[0].set_ylabel("Доля самопотребления (цель)")
capex5 = f"{CAPEX[5]:,.0f}".replace(",", " ")
fig.suptitle(f"SunCount, предварительно: СЭС 5 кВт, Краснодар, капзатраты {capex5} ₽, потребление {LOAD_KWH} кВт·ч/год",
             fontsize=10)
fig.savefig(out / "stub_payback_heatmap_5kw.png", dpi=150, bbox_inches="tight")
print("\nГрафик:", out / "stub_payback_heatmap_5kw.png")
