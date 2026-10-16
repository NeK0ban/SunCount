"""Генерирует data/tariffs_2026.csv из таблицы ТНС энерго Кубань (приказ ДГРТ КК № 18/2025-э)."""
import csv, pathlib

SRC = "https://kuban.tns-e.ru/calculations/tariffs/tariff-table/"
DOC = "Приказ ДГРТ Краснодарского края от 17.12.2025 № 18/2025-э (Краснодарский край, Республика Адыгея, ФТ «Сириус»)"
ACCESSED = "2026-10-13"

# (зона, часы) -> {категория: {диапазон: (01.01–30.09, 01.10–31.12)}}
ZONES = [
    ("single", "flat", "0-24"),
    ("two_zone", "day", "7-23"),
    ("two_zone", "night", "23-7"),
    ("three_zone", "peak", "7-10,17-21"),
    ("three_zone", "semipeak", "10-17,21-23"),
    ("three_zone", "night", "23-7"),
]
PRICES = {
    # Раздел 1: население (город, газовые плиты и иные случаи) и приравненные
    "base": {
        "I":   [(7.47, 8.31), (8.39, 9.33), (4.49, 5.00), (8.40, 9.34), (7.47, 8.31), (4.49, 5.00)],
        "II":  [(10.17, 11.70), (11.41, 13.13), (6.12, 7.04), (11.43, 13.14), (10.17, 11.70), (6.12, 7.04)],
        "III": [(14.88, 17.84), (16.70, 20.02), (8.93, 10.68), (16.71, 20.03), (14.88, 17.84), (8.93, 10.68)],
    },
    # Разделы 2–8: сельское население; город с электроплитами и/или электроотоплением
    "reduced": {
        "I":   [(5.24, 5.83), (5.88, 6.54), (3.16, 3.52), (5.89, 6.55), (5.24, 5.83), (3.16, 3.52)],
        "II":  [(7.12, 8.20), (7.99, 9.19), (4.30, 4.95), (8.00, 9.20), (7.12, 8.20), (4.30, 4.95)],
        "III": [(14.88, 17.84), (16.70, 20.02), (8.93, 10.68), (16.71, 20.03), (14.88, 17.84), (8.93, 10.68)],
    },
}
CATEGORY_NAME = {
    "base": "Раздел 1: городское население (газ. плиты, иные случаи)",
    "reduced": "Разделы 2–8: сельское население; город с электроплитами/электроотоплением",
}
PERIODS = [("2026-01-01", "2026-09-30"), ("2026-10-01", "2026-12-31")]

out = pathlib.Path(__file__).resolve().parents[1] / "data" / "tariffs_2026.csv"
with out.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["date_from", "date_to", "category", "category_name", "tariff_type", "zone", "hours",
                "range", "price_rub_kwh", "vat_included", "document", "source_url", "accessed"])
    for cat, ranges in PRICES.items():
        for rng, values in ranges.items():
            for (ttype, zone, hours), pair in zip(ZONES, values):
                for (d1, d2), price in zip(PERIODS, pair):
                    w.writerow([d1, d2, cat, CATEGORY_NAME[cat], ttype, zone, hours, rng,
                                f"{price:.2f}", "yes", DOC, SRC, ACCESSED])
print("written", out)