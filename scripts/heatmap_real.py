"""T3.3 — тепловая карта «профиль × тариф → срок окупаемости» на реальных данных.

Вход: results/real_payback.csv (Р1, T1.6). Если файла ещё нет, те же цифры считаются здесь же
из data/energy_metrics_monthly.csv через src/econ/api.py (evaluate + recommend — метод T1.6):
группировка по (profile_id, city, pv_kw) → 12 записей → для каждого из 4 тарифов, рекомендуемая
мощность — api.recommend по трём мощностям (3, 5, 10 кВт). Данные проверены в
docs/team1_data_check.md (4 портрета × 2 города × 3 мощности, все 12 месяцев).

Что строится (мастер-ТЗ, T3.3):
  results/heatmap_real_<город>.png        — основная карта: простой срок рекомендуемой мощности,
                                            в ячейке «7,8 / 5 кВт»;
  results/heatmap_real_<город>_disc.png   — то же по дисконтированному сроку;
  results/heatmap_real_<город>_<кВт>kw.png / _<кВт>kw_disc.png — по каждой мощности 3/5/10;
  для каждого города отдельно: krasnodar, maykop;
  единая шкала на всех картах: RdYlGn_r, 4…16 лет (простой) и 4…25 (дисконтированный),
  «не окупается» показывается как «не окуп.» (белым по красному).
Плюс таблица results/heatmap_real.csv (utf-8-sig), с долей излишков export_share — для части Б гипотезы 2 (T3.4).

Дом с электроотоплением и в городе платит по пониженному тарифу с диапазонами отопительного периода
(как в промежуточном отчёте, раздел 7), поэтому для портрета el_heating считаются только столбцы «Село»
с range_keys ("reduced_heating", "reduced_heating_nostove"), а в столбцах «Город» на карте — серая ячейка.

Запуск: python scripts/heatmap_real.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ.exchange import MonthlyMetrics, read_csv    # noqa: E402
from src.econ.inputs import TariffPlan                     # noqa: E402

PLANS = [                # порядок столбцов карты (палитра T3.5)
    TariffPlan("Город, одноставочный", "base", "single", ("base",)),
    TariffPlan("Город, день/ночь", "base", "two_zone", ("base",)),
    TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",)),
    TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",)),
]
# строки карты: порядок и подписи — по документации (МАСТЕР-ТЗ, exchange_format.md)
PORTRAITS = [
    ("day_absent", "Семья днём\nна работе / учёбе"),
    ("home_all_day", "Кто-то дома\nвесь день"),
    ("ac", "Дом с\nкондиционером"),
    ("el_heating", "Электроотопление /\nэлектробойлер"),
]
CITIES = [("krasnodar", "Краснодар"), ("maykop", "Майкоп")]
HEATING, HEATING_RANGES = "el_heating", ("reduced_heating", "reduced_heating_nostove")
POWS = (3, 5, 10)

SPECTRUM, VMIN = "RdYlGn_r", 4      # зелёный — быстро, красный — долго (как в make_interim_report)
VMAX = {"simple": 16, "disc": 25}
METRIC_RU = {"simple": "простой", "disc": "дисконтированный"}

plt.rcParams.update({"font.family": "sans-serif",
                     "font.sans-serif": ["Arial", "DejaVu Sans"],
                     "axes.unicode_minus": False})

INF = float("inf")
out = ROOT / "results"
out.mkdir(exist_ok=True)


# ----------------------------------------------------------------- вход: real_payback или расчёт
real_file = out / "real_payback.csv"
if real_file.exists():
    src_desc = "results/real_payback.csv (Р1, T1.6)"
    raw = pd.read_csv(real_file, encoding="utf-8-sig")
    pay = raw[["profile_id", "city", "pv_kw", "tariff", "capex_rub", "self_share", "export_share",
               "simple_payback", "disc_payback", "recommended"]].copy()
else:
    src_desc = "data/energy_metrics_monthly.csv (расчёт здесь, метод T1.6 — real_payback.csv от Р1 ещё нет)"
    from src.econ.api import recommend                   # noqa: E402

    months_all = read_csv(ROOT / "data" / "energy_metrics_monthly.csv", MonthlyMetrics)
    groups: dict[tuple, list] = {}
    for r in months_all:
        groups.setdefault((r.profile_id, r.city, r.pv_kw), []).append(r)
    rows = []
    for pid in sorted({k[0] for k in groups}):
        for city, _ in CITIES:
            months_by_kw = {kw: sorted(groups[(pid, city, kw)], key=lambda r: r.month)
                            for kw in POWS if (pid, city, kw) in groups}
            if not months_by_kw:
                continue
            for plan in PLANS:
                if pid == HEATING:       # дом с электроотоплением: только пониженный тариф с отопительными диапазонами
                    if plan.price_category != "reduced":
                        continue
                    plan = TariffPlan(plan.name, "reduced", plan.tariff_type, HEATING_RANGES)
                best_kw, res_by_kw = recommend(months_by_kw, plan)
                for kw, res in res_by_kw.items():
                    rows.append({
                        "profile_id": pid, "city": city, "pv_kw": kw, "tariff": plan.name,
                        "capex_rub": res.capex_rub, "self_share": res.self_share,
                        "export_share": res.export_share,
                        "simple_payback": res.simple_payback, "disc_payback": res.disc_payback,
                        "recommended": kw == best_kw,
                    })
    pay = pd.DataFrame(rows)

pay["simple_payback"] = pay.simple_payback.round(1)
pay["disc_payback"] = pay.disc_payback.round(1)
pay["export_share"] = pay.export_share.round(1)
pay.to_csv(out / "heatmap_real.csv", index=False, encoding="utf-8-sig")

# ----------------------------------------------------------------- проверка полноты (ТЗ: ровно одна recommended)
n_groups = pay[["profile_id", "city", "tariff"]].drop_duplicates().shape[0]
n_rec = int((pay.recommended == True).sum())             # noqa: E712
print(f"Вход: {src_desc}")
print(f"Таблица results/heatmap_real.csv: {len(pay)} строк "
      f"({pay.profile_id.nunique()} портрета × {pay.city.nunique()} города × "
      f"{pay.pv_kw.nunique()} мощности × {len(PLANS)} тарифа; у {HEATING} — только 2 «сельских» тарифа).")
print(f"Рекомендуемых строк: {n_rec} из {n_groups} троек (портрет, город, тариф) — "
      + ("OK" if n_rec == n_groups else "ОШИБКА: у каждой тройки должна быть ровно одна"))


# ----------------------------------------------------------------- карта
def heatmap(city_id: str, metric: str, pv_kw: int | None = None) -> Path:
    """Одна карта: строки — портреты, столбцы — 4 тарифа.

    pv_kw=None → рекомендуемая мощность (в ячейке срок и мощность), иначе мощность фиксирована.
    Единая шкала VMAX[metric] на всех картах; inf — «не окуп.».
    """
    col = f"{metric}_payback"
    city_ru = dict(CITIES)[city_id]
    sub = pay[pay.city == city_id]
    sub = sub[sub.recommended] if pv_kw is None else sub[sub.pv_kw == pv_kw]
    hp = sub.pivot(index="profile_id", columns="tariff", values=col) \
        .reindex(index=[p for p, _ in PORTRAITS], columns=[p.name for p in PLANS])
    vals = hp.values.astype(float)
    if pv_kw is None:
        hp_kw = sub.pivot(index="profile_id", columns="tariff", values="pv_kw") \
            .reindex(index=[p for p, _ in PORTRAITS], columns=[p.name for p in PLANS])

    vmax = VMAX[metric]
    thresh = VMIN + 0.85 * (vmax - VMIN)     # выше — ячейка тёмная, текст белым
    fig, ax = plt.subplots(figsize=(9.6, 5.0))
    cmap = plt.get_cmap(SPECTRUM).copy()
    cmap.set_bad("#e6e6e6")                  # тариф к портрету не применяется (el_heating × «Город»)
    shown = np.ma.masked_invalid(np.where(np.isinf(vals), vmax, vals))
    im = ax.imshow(shown, cmap=cmap, vmin=VMIN, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(PLANS)), [p.name.replace(", ", "\n") for p in PLANS], fontsize=8.5)
    ax.set_yticks(range(len(PORTRAITS)), [lbl for _, lbl in PORTRAITS], fontsize=8.5)
    ax.tick_params(length=0)
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            if np.isnan(vals[i, j]):
                ax.text(j, i, "пониженный тариф —\nсм. «Село»", ha="center", va="center", fontsize=7.5,
                        color="#555555")
                continue
            ok = np.isfinite(vals[i, j])
            color = "white" if (not ok or vals[i, j] >= thresh) else "black"
            if not ok:
                ax.text(j, i, "не окуп.", ha="center", va="center", fontsize=8, color=color)
            elif pv_kw is None:
                ax.text(j, i, f"{vals[i, j]:.1f}".replace(".", ",") +
                        f" / {int(hp_kw.values[i, j])} кВт",
                        ha="center", va="center", fontsize=9, color=color)
            else:
                ax.text(j, i, f"{vals[i, j]:.1f}".replace(".", ","),
                        ha="center", va="center", fontsize=10, color=color)
    power_line = ("рекомендуемая мощность, в ячейке — срок / мощность"
                  if pv_kw is None else f"СЭС {pv_kw} кВт")
    ax.set_title(f"{METRIC_RU[metric]} срок окупаемости, лет — {power_line}", fontsize=10)
    cbar = fig.colorbar(im, ax=ax, shrink=0.82)
    cbar.set_label("лет", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    cbar.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
    fig.suptitle(f"{city_ru}: тепловая карта «портрет × тариф» — "
                 f"{METRIC_RU[metric]} срок окупаемости\n"
                 f"Реальные портреты команды 1 (data/energy_metrics_monthly.csv); "
                 f"шкала {VMIN}…{vmax} лет общая для всех карт", fontsize=11)
    fig.text(0.01, 0.045, "Дом с электроотоплением и в городе платит по пониженному тарифу (с диапазонами "
             "отопительного периода), поэтому для него — только столбцы «Село».", fontsize=8, color="#333333")
    fig.text(0.01, 0.015, "Источник: расчёт SunCount, данные — docs/assumptions.md",
             fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(0, 0.08, 1, 1.0))

    suffix = "_disc" if metric == "disc" else ""
    power = f"_{pv_kw}kw" if pv_kw is not None else ""
    fname = out / f"heatmap_real_{city_id}{power}{suffix}.png"
    fig.savefig(fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return fname


made = []
for city_id, _ in CITIES:
    made.append(heatmap(city_id, "simple"))
    made.append(heatmap(city_id, "disc"))
    for kw in POWS:
        made.append(heatmap(city_id, "simple", kw))
        made.append(heatmap(city_id, "disc", kw))

# ----------------------------------------------------------------- вывод в консоль
print("\nСрок окупаемости на рекомендуемой мощности (пробный обзор):")
for city_id, city_ru in CITIES:
    sub = pay[(pay.city == city_id) & (pay.recommended == True)]   # noqa: E712
    fin = sub[np.isfinite(sub.simple_payback)]
    n_inf = len(sub) - len(fin)
    print(f"  {city_ru}: простой {fin.simple_payback.min():.1f}…{fin.simple_payback.max():.1f} лет"
          + (f", не окупается — {n_inf} из {len(sub)}" if n_inf else "")
          + f"; дисконт. {sub.disc_payback[np.isfinite(sub.disc_payback)].min():.1f}…"
            f"{sub.disc_payback[np.isfinite(sub.disc_payback)].max():.1f} лет")
print("\nЛучшие и худшие ячейки (простой срок, рекомендуемая мощность):")
sub = pay[pay.recommended == True].copy()                            # noqa: E712
fin = sub[np.isfinite(sub.simple_payback)].nsmallest(3, "simple_payback")
for _, r in fin.iterrows():
    print(f"  быстро: {r.profile_id} × {r.tariff} × {r.city} = {r.simple_payback:.1f} лет "
          f"({int(r.pv_kw)} кВт)".replace(".", ","))
worst = sub[np.isfinite(sub.simple_payback)].nlargest(3, "simple_payback")
for _, r in worst.iterrows():
    print(f"  долго:  {r.profile_id} × {r.tariff} × {r.city} = {r.simple_payback:.1f} лет "
          f"({int(r.pv_kw)} кВт)".replace(".", ","))

print("\nГотово: results/heatmap_real.csv, " + ", ".join(str(f.name) for f in made))
