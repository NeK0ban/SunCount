"""Цены каталога оборудования из предложений проверенных магазинов (docs/equipment/equipment_sources.md).

Правило: цены берутся только с проверенных сайтов, обычная цена без скидок (если на сайте цена зачёркнута —
берётся зачёркнутая, т. е. цена до скидки). У модели несколько продавцов — в каталог идёт медиана их обычных цен,
по одной цене на продавца. Предложения с used = no (нет паспорта, неясная цена) в расчёт не идут.

Вход: data/equipment/offers.csv. Выход: колонки price_rub, price_note, price_url, price_accessed (у панелей ещё seller и city) в
data/equipment/panels.csv и inverters.csv; price_rub в data/equipment/bos.csv для статей из offers.csv.
Запуск: python scripts/build_equipment_prices.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "data" / "equipment"
OFFERS = "data/equipment/offers.csv"


def fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


offers = pd.read_csv(EQ / "offers.csv", encoding="utf-8-sig")
used = offers[offers.used == "yes"].copy()
if used.price_regular_rub.isna().any():
    raise ValueError("В offers.csv есть используемое предложение без обычной цены")
# одна цена на продавца (если у продавца несколько строк одной модели — берём меньшую обычную цену)
per_seller = used.groupby(["kind", "catalog_id", "seller"], as_index=False).agg(
    price=("price_regular_rub", "min"), accessed=("accessed", "max"), city=("city", "first"))
summary = per_seller.groupby(["kind", "catalog_id"]).agg(
    price=("price", "median"), n=("seller", "count"), low=("price", "min"), high=("price", "max"),
    sellers=("seller", lambda s: "; ".join(x.split(" (")[0] for x in s)), accessed=("accessed", "max"),
    cities=("city", lambda s: "; ".join(dict.fromkeys(str(x) for x in s))))

for file, kind in (("panels.csv", "panel"), ("inverters.csv", "inverter")):
    t = pd.read_csv(EQ / file, encoding="utf-8-sig", dtype={"price_note": str, "price_url": str, "price_accessed": str})
    id_col = "panel_id" if kind == "panel" else "inverter_id"
    for i, row in t.iterrows():
        key = (kind, row[id_col])
        if key not in summary.index:
            raise ValueError(f"{file}: для {row[id_col]} нет ни одного используемого предложения в {OFFERS}")
        s = summary.loc[key]
        t.at[i, "price_rub"] = round(float(s.price))
        t.at[i, "price_note"] = (f"медиана обычных цен {s.n} продавцов ({s.sellers}): {fmt(s.low)}–{fmt(s.high)} ₽"
                                 if s.n > 1 else f"обычная цена продавца {s.sellers}")
        t.at[i, "price_url"] = OFFERS
        t.at[i, "price_accessed"] = s.accessed
        if "seller" in t.columns:   # у панелей продавец и город записаны в каталоге — берём из предложений
            t.at[i, "seller"] = s.sellers
            t.at[i, "city"] = s.cities
    t.to_csv(EQ / file, index=False, encoding="utf-8-sig")
    print(f"{file}: " + ", ".join(f"{r[id_col]} {fmt(r.price_rub)} ₽" for _, r in t.iterrows()))

bos = pd.read_csv(EQ / "bos.csv", encoding="utf-8-sig")
for i, row in bos.iterrows():
    for kind in (row["item"],):
        if (kind, kind) in summary.index:
            bos.at[i, "price_rub"] = round(float(summary.loc[(kind, kind)].price), 2)
missing = [r["item"] for _, r in bos.iterrows() if str(r["source"]).startswith("data/equipment/offers.csv")
           and not (r["item"], r["item"]) in summary.index]
if missing:
    raise ValueError(f"bos.csv: нет цен в {OFFERS} для {missing}")
bos.to_csv(EQ / "bos.csv", index=False, encoding="utf-8-sig")
print("bos.csv: " + ", ".join(f"{r['item']} {r['price_rub']:g}" for _, r in bos.iterrows()
                              if str(r["source"]).startswith("data/equipment/offers.csv")))
