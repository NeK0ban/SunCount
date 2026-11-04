"""T1.6 — расчёт окупаемости на реальных профилях команды 1 (мастер-ТЗ, раздел 12.1).

Вход: data/energy_metrics_monthly.csv — помесячные показатели команды 1 (read_csv(..., MonthlyMetrics)).
Метод: группировка по (profile_id, city, pv_kw) → 12 записей → src/econ/api.py: evaluate для каждого тарифа,
для каждой тройки (портрет, город, тариф) — recommend по трём мощностям 3 / 5 / 10 кВт.
Дом с электроотоплением (el_heating) и в городе платит по пониженному тарифу с диапазонами отопительного
периода, поэтому для него считаются только «сельские» тарифы с range_keys ("reduced_heating",
"reduced_heating_nostove") — как в промежуточном отчёте (раздел 7) и на тепловой карте (T3.3).
Запасной вариант (шаг 3 T1.6): если помесячного файла нет, расчёт по годовому data/energy_metrics.csv
через evaluate_tz (формула ТЗ: один тариф без диапазонов и зон суток, средняя цена выкупа) — колонка method.

Выход: results/real_payback.csv (utf-8-sig), колонки по ТЗ:
  profile_id, city, pv_kw, tariff, capex_rub, self_share, coverage, effect_rub, self_rub, export_rub,
  export_share, simple_payback, payback_low, payback_high, disc_payback, npv_rub, recommended;
  плюс вариант с помесячным зачётом (ОП № 442, п. 63(1)): effect_net_rub, export_share_net,
  simple_payback_net, disc_payback_net, и method.

Запуск: python scripts/run_real.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ.api import evaluate, evaluate_tz, recommend  # noqa: E402
from src.econ.exchange import EnergyMetrics, MonthlyMetrics, read_csv  # noqa: E402
from src.econ.inputs import TariffPlan, buyback_monthly, zone_prices  # noqa: E402

PV_SIZES = (3, 5, 10)
PLANS = [
    TariffPlan("Город, одноставочный", "base", "single", ("base",)),
    TariffPlan("Город, день/ночь", "base", "two_zone", ("base",)),
    TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",)),
    TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",)),
]
HEATING, HEATING_RANGES = "el_heating", ("reduced_heating", "reduced_heating_nostove")
COLS = ["profile_id", "city", "pv_kw", "tariff", "capex_rub", "self_share", "coverage", "effect_rub", "self_rub",
        "export_rub", "export_share", "simple_payback", "payback_low", "payback_high", "disc_payback", "npv_rub",
        "recommended", "effect_net_rub", "export_share_net", "simple_payback_net", "disc_payback_net", "method"]


def plans_for(profile_id: str) -> list[TariffPlan]:
    if profile_id != HEATING:
        return PLANS
    return [TariffPlan(p.name, "reduced", p.tariff_type, HEATING_RANGES) for p in PLANS if p.price_category == "reduced"]


def row(pid, city, kw, plan, r, rn, best, method):
    d = {"profile_id": pid, "city": city, "pv_kw": kw, "tariff": plan.name, "capex_rub": round(r.capex_rub),
         "self_share": round(r.self_share, 2), "coverage": round(r.coverage, 2), "effect_rub": round(r.effect_rub),
         "self_rub": round(r.self_rub), "export_rub": round(r.export_rub), "export_share": round(r.export_share, 1),
         # сроки — с 4 знаками: потребители (тепловая карта, отчёт) сами округляют до 0,1, без двойного округления
         "simple_payback": round(r.simple_payback, 4), "payback_low": round(r.payback_low, 4),
         "payback_high": round(r.payback_high, 4), "disc_payback": round(r.disc_payback, 4),
         "npv_rub": round(r.npv_rub), "recommended": kw == best, "method": method}
    if rn is not None:
        d.update(effect_net_rub=round(rn.effect_rub), export_share_net=round(rn.export_share, 1),
                 simple_payback_net=round(rn.simple_payback, 4), disc_payback_net=round(rn.disc_payback, 4))
    return d


rows = []
monthly_file = ROOT / "data" / "energy_metrics_monthly.csv"
if monthly_file.exists():
    groups: dict[tuple, list] = {}
    for rec in read_csv(monthly_file, MonthlyMetrics):
        groups.setdefault((rec.profile_id, rec.city, int(rec.pv_kw)), []).append(rec)
    for pid, city in sorted({(p, c) for p, c, _ in groups}):
        months_by_kw = {kw: sorted(groups[(pid, city, kw)], key=lambda r: r.month) for kw in PV_SIZES}
        for plan in plans_for(pid):
            best, res = recommend(months_by_kw, plan)
            for kw in PV_SIZES:
                rn = evaluate(months_by_kw[kw], plan, kw, netting=True)
                rows.append(row(pid, city, kw, plan, res[kw], rn, best, "помесячная модель"))
else:
    print("ВНИМАНИЕ: нет data/energy_metrics_monthly.csv — запасной расчёт по годовому файлу и формуле ТЗ: "
          "диапазоны тарифа, зоны суток и сезонность цены выкупа НЕ учитываются (отметить в отчёте).")
    annual = {(r.profile_id, r.city, int(r.pv_kw)): r for r in read_csv(ROOT / "data" / "energy_metrics.csv", EnergyMetrics)}
    from src.econ.api import capex_estimate  # noqa: E402
    for pid, city in sorted({(p, c) for p, c, _ in annual}):
        for plan in plans_for(pid):
            tariff = zone_prices(plan)["I"]["day"]
            bb = sum(buyback_monthly(plan.owner_category).values()) / 12
            res = {kw: evaluate_tz(annual[(pid, city, kw)], tariff, bb, capex_estimate(kw)) for kw in PV_SIZES}
            for kw, r in res.items():   # evaluate_tz не знает, что цена из таблицы, — границы считаем сами
                r.payback_low = capex_estimate(kw, "low") / r.effect_rub
                r.payback_high = capex_estimate(kw, "high") / r.effect_rub
            best = min(res, key=lambda kw: (round(res[kw].simple_payback, 2), kw))
            for kw in PV_SIZES:
                rows.append(row(pid, city, kw, plan, res[kw], None, best, "формула ТЗ (годовой файл)"))

df = pd.DataFrame(rows).reindex(columns=COLS)
out = ROOT / "results"
out.mkdir(exist_ok=True)
df.to_csv(out / "real_payback.csv", index=False, encoding="utf-8-sig")

# ----------------------------------------------------------------- проверка готовности (ТЗ)
n_triples = df[["profile_id", "city", "tariff"]].drop_duplicates().shape[0]
rec_per = df.groupby(["profile_id", "city", "tariff"]).recommended.sum()
main_cols = [c for c in COLS if not c.endswith("_net") and c != "effect_net_rub"]
print(f"results/real_payback.csv: {len(df)} строк — {df.profile_id.nunique()} портрета × {df.city.nunique()} города × "
      f"{df.pv_kw.nunique()} мощности × тарифы (у {HEATING} — 2 «сельских»), троек {n_triples}")
print(f"  пустых значений в основных колонках: {int(df[main_cols].isna().sum().sum())}; "
      f"ровно одна рекомендуемая мощность в каждой тройке: {'да' if (rec_per == 1).all() else 'НЕТ'}")
rec = df[df.recommended]
print(f"  рекомендуемая мощность: {rec.pv_kw.value_counts().sort_index().to_dict()}")
print(f"  простой срок на рекомендуемой мощности: {rec.simple_payback.min():.1f}–{rec.simple_payback.max():.1f} лет; "
      f"доля излишков ≤ 20 % — в {int((rec.export_share <= 20).sum())} из {len(rec)}")
print("\nПростой срок по тарифам (все мощности), лет:")
for t, g in df.groupby("tariff", sort=False):
    print(f"  {t}: {g.simple_payback.min():.1f}–{g.simple_payback.max():.1f}; "
          f"с зачётом {g.simple_payback_net.min():.1f}–{g.simple_payback_net.max():.1f}")
