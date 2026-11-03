"""T3.2 — влияние тарифа по зонам суток: выигрыш «день/ночь» против одноставочного + разложение.

Для каждой точки (условная доля самопотребления, мощность, город) считаем пару тарифов
«одноставочный → день/ночь» отдельно для города (price_category base) и для села (reduced):
  gain_years    = простой срок (одноставочный) − простой срок (день/ночь);
  d_self_rub    = self_rub(день/ночь) − self_rub(одноставочный) — дорогая дневная энергия;
  d_export_rub  = export_rub(день/ночь) − export_rub(одноставочный) — цена выкупа дневной зоны;
плюс то же для дисконтированного срока (gain_disc_years). Сроки — через src/econ/api.py (evaluate).

Прототип — на условных профилях make_stub_monthly (доля самопотребления 20–80 %, потребление
6000 кВт·ч/год); недостижимые доли отбрасываются, как в scripts/stub_payback.py. На реальных
портретах команды 1 — до 12.12 (задача T3.2, мастер-ТЗ, раздел 12.3).

Важно для вывода: выигрыш в модели немного завышен — считается, что всё самопотребление дневное,
а летом панели работают с 5–6 утра, то есть частично в ночной зоне (docs/assumptions.md,
ограничения).

Выход:
  results/zones_effect.csv (utf-8-sig) — формат мастер-ТЗ:
    profile, city, pv_kw, area, payback_single, payback_zones, gain_years,
    disc_single, disc_zones, gain_disc_years, d_self_rub, d_export_rub
  results/zones_effect_gain.png — столбцы gain_years по долям самопотребления, цвета город/село;
  results/zones_effect_decomposition.png — выигрыш в рублях, стопка d_self_rub + d_export_rub.

Запуск: python scripts/zones_effect.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ.api import evaluate                     # noqa: E402
from src.econ.exchange import annual_from_monthly, make_stub_monthly   # noqa: E402
from src.econ.inputs import TariffPlan                # noqa: E402

LOAD_KWH = 6000          # годовое потребление дома, кВт·ч (≈ 500 кВт·ч/мес) — УСЛОВНО
CITIES = [("Краснодар", "krasnodar"), ("Майкоп", "maykop")]
PV_SIZES = (3, 5, 10)
SHARES = range(20, 81, 10)

# пары «одноставочный → день/ночь»: город — price_category base, село — reduced
AREAS = [
    ("город", TariffPlan("Город, одноставочный", "base", "single", ("base",)),
               TariffPlan("Город, день/ночь", "base", "two_zone", ("base",))),
    ("село",  TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",)),
               TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",))),
]
AREA_COLOR = {"город": "#1f6fb2", "село": "#e08a1e"}   # палитра T3.5 (город одноставочный / село одноставочный)

# общая сноска под обоими графиками (один стиль с торнадо T3.1)
CAVEAT = ("Выигрыш немного завышен: модель считает всё самопотребление дневным, а летом панели "
          "работают с 5–6 утра частично в ночной зоне (docs/assumptions.md, ограничения).")
SOURCE = "Источник: расчёт SunCount, данные — docs/assumptions.md"

plt.rcParams.update({"font.family": "sans-serif",
                     "font.sans-serif": ["Arial", "DejaVu Sans"],
                     "axes.unicode_minus": False})

INF = float("inf")


# ----------------------------------------------------------------- вспомогательные
def ru(x: float, nd: int = 1) -> str:
    """Число с десятичной запятой (для подписей графиков и консоли)."""
    return f"{x:.{nd}f}".replace(".", ",")


def gain(a: float, b: float) -> float:
    """Выигрыш a − b; если оба срока «не окупаются» — 0 (варианты не различаются)."""
    if a == INF and b == INF:
        return 0.0
    return a - b


# ----------------------------------------------------------------- расчёт
rows: list[dict] = []
skipped: list[str] = []
for city_ru, city_id in CITIES:
    for kw in PV_SIZES:
        for share in SHARES:
            months = make_stub_monthly(f"stub_{share}", kw, LOAD_KWH, share, city_id)
            year = annual_from_monthly(months)
            if year.self_share < share - 2:
                skipped.append(f"{city_ru} {kw} кВт, доля {share} % (факт {year.self_share:g} %)")
                continue  # такая доля недостижима: дому не съесть столько днём
            for area, plan_single, plan_zones in AREAS:
                r_s = evaluate(months, plan_single, pv_kw=kw)
                r_z = evaluate(months, plan_zones, pv_kw=kw)
                p_s, p_z = r_s.simple_payback, r_z.simple_payback
                d_s, d_z = r_s.disc_payback, r_z.disc_payback
                rows.append({   # выигрыш — по неокруглённым срокам, округление только при записи
                    "profile": f"условная доля {share} %", "city": city_ru, "pv_kw": kw, "area": area,
                    "payback_single": round(p_s, 1), "payback_zones": round(p_z, 1),
                    "gain_years": round(gain(p_s, p_z), 1),
                    "disc_single": round(d_s, 1), "disc_zones": round(d_z, 1),
                    "gain_disc_years": round(gain(d_s, d_z), 1),
                    "d_self_rub": round(r_z.self_rub - r_s.self_rub),
                    "d_export_rub": round(r_z.export_rub - r_s.export_rub),
                })

df = pd.DataFrame(rows)
out = ROOT / "results"
out.mkdir(exist_ok=True)
df.to_csv(out / "zones_effect.csv", index=False, encoding="utf-8-sig")

print(f"Точек: {len(df)} строк ({len(CITIES)} города × {len(PV_SIZES)} мощности × доли 20–80 % "
      f"× {len(AREAS)} района); потребление {LOAD_KWH} кВт·ч/год, условные профили make_stub_monthly.")
if skipped:
    print("Недостижимые доли отброшены (дом не съедает столько днём):")
    for s in skipped:
        print("  ", s)

# ----------------------------------------------------------------- проверка: сверка с stub_payback (Краснодар)
stub = pd.read_csv(out / "stub_payback.csv", encoding="utf-8-sig")
name_by_area = {a: (ps.name, pz.name) for a, ps, pz in AREAS}
def same(x: float, y: float) -> bool:
    """Совпадение сроков; inf == inf считается совпадением (в stub тоже «не окупается»)."""
    if x == y:
        return True
    return abs(x - y) < 0.05


print("\nСверка со scripts/stub_payback.py (Краснодар, та же точка):")
bad = 0
for _, r in df[df.city == "Краснодар"].iterrows():
    s = stub[(stub.pv_kw == r.pv_kw) & (stub.self_share_target == int(r.profile.split()[-2]))]
    n_single, n_zones = name_by_area[r.area]
    ref_s = float(s[s.tariff == n_single].simple_payback.iloc[0])
    ref_z = float(s[s.tariff == n_zones].simple_payback.iloc[0])
    ref_ds = float(s[s.tariff == n_single].disc_payback.iloc[0])
    ref_dz = float(s[s.tariff == n_zones].disc_payback.iloc[0])
    ok = (same(r.payback_single, ref_s) and same(r.payback_zones, ref_z) and
          same(r.disc_single, ref_ds) and same(r.disc_zones, ref_dz))
    if not ok:
        bad += 1
        print(f"  РАСХОЖДЕНИЕ: {r.pv_kw} кВт, {r.profile}, {r.area}: "
              f"{r.payback_single}/{r.payback_zones} против {ref_s}/{ref_z} в stub_payback")
print(f"  совпало {len(df[df.city == 'Краснодар']) - bad} из {len(df[df.city == 'Краснодар'])} строк — "
      + ("OK" if bad == 0 else f"РАСХОЖДЕНИЙ: {bad}"))

# ----------------------------------------------------------------- вывод в консоль
print("\nВыигрыш «день/ночь» (простой срок, лет) — диапазон по долям самопотребления:")
for city_ru, _ in CITIES:
    for kw in PV_SIZES:
        for area, _, _ in AREAS:
            sub = df[(df.city == city_ru) & (df.pv_kw == kw) & (df.area == area)]
            if len(sub):
                lo, hi = sub.gain_years.min(), sub.gain_years.max()
                print(f"  {city_ru}, {kw} кВт, {area}: {ru(lo)} … {ru(hi)} "
                      f"(дисконт. {ru(sub.gain_disc_years.min())} … {ru(sub.gain_disc_years.max())})")

def th(x: float) -> str:
    """Рубли с разделителем тысяч (для консоли)."""
    return f"{x:,.0f}".replace(",", " ")


d_self, d_exp = df.d_self_rub.mean(), df.d_export_rub.mean()
print(f"\nРазложение выигрыша в рублях (среднее по всем точкам): "
      f"d_self_rub {th(d_self)} ₽/год, d_export_rub {th(d_exp)} ₽/год")
for area, _, _ in AREAS:
    sub = df[df.area == area]
    print(f"  {area}: d_self_rub {th(sub.d_self_rub.mean())} ₽/год, "
          f"d_export_rub {th(sub.d_export_rub.mean())} ₽/год "
          f"(минимумы: {th(sub.d_self_rub.min())} / {th(sub.d_export_rub.min())})")
print("Замечание: выигрыш немного завышен — модель считает всё самопотребление дневным, "
      "а летом панели работают с 5–6 утра частично в ночной зоне (docs/assumptions.md).")


# ----------------------------------------------------------------- графики
def facet_grid(values_fn, title_fmt, ylabel, fname, note=None):
    """Сетка 2×3: строки — города, столбцы — мощности; столбцы по долям, цвет — город/село."""
    fig, axes = plt.subplots(len(CITIES), len(PV_SIZES), figsize=(18, 8.6), squeeze=False)
    for i, (city_ru, _) in enumerate(CITIES):
        for j, kw in enumerate(PV_SIZES):
            ax = axes[i][j]
            base = df[(df.city == city_ru) & (df.pv_kw == kw)]
            shares_all = sorted(base.profile.str.extract(r"(\d+)")[0].astype(int).unique())
            for area, _, _ in AREAS:
                sub = base[base.area == area].copy()
                sub["share"] = sub.profile.str.extract(r"(\d+)").astype(int)
                sub = sub.sort_values("share")
                if sub.empty:
                    continue
                vals = values_fn(sub)
                x = sub.share.to_numpy() + (-2.1 if area == "город" else 2.1)
                ax.bar(x, vals, width=4.2, color=AREA_COLOR[area], label=area, zorder=3)
            ax.axhline(0, color="black", lw=0.8, zorder=4)
            ax.set_xticks(shares_all)
            ax.set_xlim(min(shares_all) - 5, max(shares_all) + 5)
            ax.set_title(f"{city_ru}, {kw} кВт", fontsize=10)
            ax.set_xlabel("Доля самопотребления (цель), %", fontsize=9)
            ax.grid(axis="y", alpha=0.3, zorder=0)
            ax.tick_params(labelsize=9)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
            if j == 0:
                ax.set_ylabel(ylabel, fontsize=9)
    handles = [plt.Rectangle((0, 0), 1, 1, color=AREA_COLOR[a]) for a, _, _ in AREAS]
    fig.legend(handles=handles, labels=[a for a, _, _ in AREAS], loc="lower center",
               bbox_to_anchor=(0.5, 0.075), ncol=2, fontsize=9, frameon=False, title="Район",
               title_fontsize=9)
    fig.suptitle(title_fmt, fontsize=12)
    if note:
        fig.text(0.01, 0.05, note, fontsize=8.5, color="#333333")
    fig.text(0.01, 0.02, SOURCE, fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(0, 0.13, 1, 0.95))
    fig.savefig(out / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)


facet_grid(
    lambda sub: sub.gain_years,
    "T3.2. Выигрыш тарифа день/ночь: простой срок окупаемости (одноставочный − день/ночь), лет\n"
    "Условные профили: доля самопотребления 20–80 %, потребление 6000 кВт·ч/год",
    "Выигрыш, лет", "zones_effect_gain.png", note=CAVEAT)

# второй график — стопка d_self_rub + d_export_rub
fig, axes = plt.subplots(len(CITIES), len(PV_SIZES), figsize=(18, 8.6), squeeze=False)
for i, (city_ru, _) in enumerate(CITIES):
    for j, kw in enumerate(PV_SIZES):
        ax = axes[i][j]
        base = df[(df.city == city_ru) & (df.pv_kw == kw)]
        shares_all = sorted(base.profile.str.extract(r"(\d+)")[0].astype(int).unique())
        for area, _, _ in AREAS:
            sub = base[base.area == area].copy()
            sub["share"] = sub.profile.str.extract(r"(\d+)").astype(int)
            sub = sub.sort_values("share")
            if sub.empty:
                continue
            x = sub.share.to_numpy() + (-2.1 if area == "город" else 2.1)
            pos_b = sub.d_self_rub.clip(lower=0).to_numpy() * 0  # накопители для +/−
            neg_b = pos_b.copy()
            for col in ("d_self_rub", "d_export_rub"):
                v = sub[col].to_numpy()
                pos, neg = v.clip(min=0), v.clip(max=0)
                ax.bar(x, pos, bottom=pos_b, width=4.2, color=AREA_COLOR[area],
                       alpha=0.9 if col == "d_self_rub" else 0.4, zorder=3)
                ax.bar(x, neg, bottom=neg_b, width=4.2, color=AREA_COLOR[area],
                       alpha=0.9 if col == "d_self_rub" else 0.4, zorder=3)
                pos_b, neg_b = pos_b + pos, neg_b + neg
        ax.axhline(0, color="black", lw=0.8, zorder=4)
        ax.set_xticks(shares_all)
        ax.set_xlim(min(shares_all) - 5, max(shares_all) + 5)
        ax.set_title(f"{city_ru}, {kw} кВт", fontsize=10)
        ax.set_xlabel("Доля самопотребления (цель), %", fontsize=9)
        ax.grid(axis="y", alpha=0.3, zorder=0)
        ax.tick_params(labelsize=9)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " ")))
        if j == 0:
            ax.set_ylabel("Выигрыш, ₽/год", fontsize=9)
handles = [plt.Rectangle((0, 0), 1, 1, color="#888888", alpha=0.9, label="Экономия на самопотреблении (дневная цена)"),
           plt.Rectangle((0, 0), 1, 1, color="#888888", alpha=0.4, label="Доход от излишков (цена выкупа дня)"),
           plt.Rectangle((0, 0), 1, 1, color=AREA_COLOR["город"], label="город"),
           plt.Rectangle((0, 0), 1, 1, color=AREA_COLOR["село"], label="село")]
fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.075), ncol=4,
           fontsize=9, frameon=False)
fig.suptitle("T3.2. Разложение годового выигрыша день/ночь в рублях, ₽/год (стопка)\n"
             "Условные профили: доля самопотребления 20–80 %, потребление 6000 кВт·ч/год", fontsize=12)
fig.text(0.01, 0.05, CAVEAT, fontsize=8.5, color="#333333")
fig.text(0.01, 0.02, SOURCE, fontsize=8.5, color="#555555")
fig.tight_layout(rect=(0, 0.13, 1, 0.95))
fig.savefig(out / "zones_effect_decomposition.png", dpi=200, bbox_inches="tight")
plt.close(fig)

print("\nГотово: results/zones_effect.csv, results/zones_effect_gain.png, "
      "results/zones_effect_decomposition.png")
