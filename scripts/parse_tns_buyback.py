"""Разбирает отчёты ТНС энерго Кубань (п. 52в Стандартов раскрытия, ПП РФ № 24)
об объёмах и средневзвешенной цене покупки электроэнергии с объектов микрогенерации.

Вход: xlsx-файлы из data/raw/tns_microgen/ (каждый файл содержит листы за все месяцы года
нарастающим итогом, поэтому берём последний файл каждого года).
Выход: data/buyback_prices.csv — одна строка на месяц.

Запуск: python -I scripts/parse_tns_buyback.py
"""
import csv
import datetime as dt
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "tns_microgen"
OUT = ROOT / "data" / "buyback_prices.csv"
PAGE = ("https://kuban.tns-e.ru/disclosure/raskrytie-informatsii-subektom-rynka-elektricheskoy-energii-moshchnosti/"
        "market-report-gp/informatsiya-ob-obemakh-i-srednevzveshennoy-tsene-pokupki-na-roznichnom-rynke-elektricheskoy-energii/")
ACCESSED = "2026-10-13"


def parse_sheet(ws):
    rec = {}
    for row in ws.iter_rows(values_only=True):
        cells = [v for v in row if v is not None]
        if not cells:
            continue
        label = str(cells[0])
        if isinstance(cells[0], dt.datetime):
            rec["month"] = cells[0].strftime("%Y-%m")
        elif len(cells) < 2:
            continue
        elif label.startswith("Объем покупки"):
            rec["volume_total_kwh"] = float(cells[1])
        elif "1-й ЦК" in label:
            rec["volume_flat_kwh"] = float(cells[1])
        elif "2-й ЦК" in label:
            rec["volume_zones_kwh"] = float(cells[1])
        elif "3-6" in label:
            rec["volume_other_kwh"] = float(cells[1])
        elif label.startswith("Средневзвешенная цена"):
            rec["price_rub_kwh"] = float(cells[1])
    return rec


# последний (самый полный) файл каждого года
latest = {}
for f in sorted(RAW.glob("*.xlsx")):
    latest[f.stem[:4]] = f

rows = []
for year, f in sorted(latest.items()):
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    for ws in wb.worksheets:
        rec = parse_sheet(ws)
        if "price_rub_kwh" in rec:
            rec["source_file"] = f"data/raw/tns_microgen/{f.name}"
            rows.append(rec)

cols = ["month", "price_rub_kwh", "volume_total_kwh", "volume_flat_kwh", "volume_zones_kwh",
        "volume_other_kwh", "source_file"]
with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(cols + ["buyer", "document", "source_url", "accessed"])
    for r in sorted(rows, key=lambda r: r["month"]):
        w.writerow([round(r[c], 4) if isinstance(r.get(c), float) else r.get(c, "") for c in cols]
                   + ["ПАО «ТНС энерго Кубань»", "п. 52в Стандартов раскрытия информации (ПП РФ от 21.01.2004 № 24)",
                      PAGE, ACCESSED])
        print(r["month"], round(r["price_rub_kwh"], 3), round(r["volume_total_kwh"]))
print("written", OUT, len(rows), "months")
