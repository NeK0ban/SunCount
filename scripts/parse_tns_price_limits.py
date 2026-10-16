"""Восстанавливает цену выкупа излишков микрогенерации ОТДЕЛЬНО для владельцев на одноставочном
тарифе и на тарифе по зонам суток — из открытых отчётов ТНС энерго Кубань «Предельные уровни
нерегулируемых цен» (лист «<670кВт»).

Логика (ОП № 442, п. 65(3)): ГП покупает у микрогенерации по цене не выше оптовой цены
электроэнергии + цены мощности с коэффициентом оплаты мощности ценовой категории владельца.
  * 1-я ЦК (одноставочный): W1 = энергия + мощность × k1 — «средневзвешенная нерегулируемая цена
    для 1-й ЦК» из отчёта;
  * 2-я ЦК (день/ночь): солнце отдаёт энергию днём, поэтому берём дневную зону; оптовая часть =
    предельный уровень дневной зоны по договорам купли-продажи − (сбытовая надбавка + инфраструктура),
    а эту разницу оцениваем как (предельный уровень 1-й ЦК по купле-продаже − W1).
Проверка: взвешиваем по объёмам из отчёта о покупке у микрогенерации (data/buyback_prices.csv)
и сравниваем с фактической средневзвешенной ценой.

Запуск: python -I scripts/parse_tns_price_limits.py
"""
import csv
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "tns_price_limits"
OUT = ROOT / "data" / "buyback_by_category.csv"
PAGE = ("https://kuban.tns-e.ru/disclosure/raskrytie-informatsii-subektom-rynka-elektricheskoy-energii-moshchnosti/"
        "market-report-gp/predelnye-urovni-nereguliruemykh-tsen-na-elektroenergiyu-moshchnost-postavlyaemuyu-potrebitelyam-pok/")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse(path):
    sh = xlrd.open_workbook(path).sheet_by_index(0)  # «<670кВт» — население и мелкие потребители
    rec = {"lim_purchase": [], "day2_purchase": []}
    for r in range(min(sh.nrows, 90)):
        cells = [str(v).strip() for v in sh.row_values(r)]
        txt = " ".join(cells)
        nums = [n for n in map(num, cells) if n is not None]
        if "цена на электрическую энергию на оптовом рынке" in txt and nums:
            rec["energy"] = nums[-1]
        elif "цена на мощность на оптовом рынке" in txt and nums:
            rec["capacity"] = nums[-1]
        elif "коэффициент оплаты мощности" in txt and "первой ценовой" in txt and nums:
            rec["k1"] = nums[-1]
        elif "Предельный уровень" in txt and "без НДС" in txt and len(nums) == 4:
            rec["lim_purchase"].append(nums[0])  # [0] — по договорам энергоснабжения, [1] — купли-продажи
        elif cells[0].startswith("Дневная зона") and nums:
            rec["day2_purchase"].append(nums[0])
    w1 = rec["energy"] + rec["capacity"] * rec["k1"]
    markup = rec["lim_purchase"][1] - w1           # сбытовая надбавка + инфраструктурные платежи
    day2 = rec["day2_purchase"][1] - markup
    return {"energy_rub_mwh": rec["energy"], "capacity_rub_mw": rec["capacity"], "k1": rec["k1"],
            "flat_rub_kwh": w1 / 1000, "zones_day_rub_kwh": day2 / 1000, "markup_rub_kwh": markup / 1000}


observed = {}
with (ROOT / "data" / "buyback_prices.csv").open(encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        observed[r["month"]] = r

rows = []
for f in sorted(RAW.glob("*.xls")):
    month = f.stem  # файлы названы по расчётному месяцу: 2026-09.xls = сентябрь 2026
    rec = {"month": month, **parse(f)}
    o = observed.get(month)
    if o:
        v1, v2, v3 = (float(o[k]) for k in ("volume_flat_kwh", "volume_zones_kwh", "volume_other_kwh"))
        pred = (v1 * rec["flat_rub_kwh"] + v2 * rec["zones_day_rub_kwh"] + v3 * rec["flat_rub_kwh"]) / (v1 + v2 + v3)
        rec["predicted_avg_rub_kwh"] = pred
        rec["observed_avg_rub_kwh"] = float(o["price_rub_kwh"])
        rec["error_pct"] = 100 * (pred / rec["observed_avg_rub_kwh"] - 1)
    rows.append(rec)

cols = ["month", "flat_rub_kwh", "zones_day_rub_kwh", "predicted_avg_rub_kwh", "observed_avg_rub_kwh", "error_pct",
        "energy_rub_mwh", "capacity_rub_mw", "k1", "markup_rub_kwh"]
with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(cols + ["status", "source_url", "accessed"])
    for r in rows:
        w.writerow([round(r[c], 4) if isinstance(r.get(c), float) else r.get(c, "") for c in cols]
                   + ["расчёт по открытым данным (оценка)", PAGE, "2026-10-13"])
        print({c: (round(r[c], 3) if isinstance(r.get(c), float) else r.get(c)) for c in cols[:6]})
print("written", OUT)
