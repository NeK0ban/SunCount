"""Оценка капзатрат СЭС «под ключ» для 3, 5, 10 кВт двумя способами + выбор базового значения (задача 2.1).

В (снизу):  панели + инвертор + крепёж + кабель/MC4 + защита + монтаж + оформление + доставка
            по отдельным ценам компонентов (data/capex_components.csv) — НИЖНЯЯ граница
            (покупка по рознице без наценки установщика).
База:       комплект краснодарского продавца (data/equipment_offers.csv: панели+инвертор+крепёж+кабели)
            + монтаж + защита + оформление + доставка — так работает типичный местный установщик.
Б (сверху): опубликованные цены «под ключ» (data/turnkey_prices.csv) — ВЕРХНЯЯ граница
            (включают наценку установщика, проект, сервис; общероссийские ориентиры).

Результат: data/capex_estimate.csv (+ график results/capex_estimate.png).
Запуск: python scripts/estimate_capex.py
"""
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({"font.family": "Arial", "font.size": 9})
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SIZES = (3, 5, 10)
PANEL_W = 590                 # типичный модуль TOPCon 585–590 Вт (цены Краснодара)

# --- ДОПУЩЕНИЯ (нет опубликованных цен; проверяются в чувствительности через диапазон Б–В)
AC_PROTECTION_RUB = {1: 6000, 3: 10000}   # AC-автомат, AC УЗИП, бокс; 1-фазная / 3-фазная схема
DELIVERY_RUB = 5000
METER_RUB = 0                             # прибор учёта ставит сетевая организация (обязанность с 01.07.2020)

# --- плата за техприсоединение микрогенерации физлица (приказ ДГРТ Краснодарского края от 24.12.2025
#     № 19/2025-э, п. 1; data/capex_components.csv, item grid_connection*): минимум из
#     (а) стоимости по стандартизированным ставкам и (б) льготной ставки 11 470 ₽ за кВт с НДС.
#     Дом уже подключён, строить сеть не нужно → (а) = С1 (ТУ + проверка их выполнения) с НДС 22 %.
#     Ставка С8 (прибор учёта) в открытой части приказа не найдена — если счётчик меняют за счёт
#     заявителя, плата выше, но не больше (б). Верхняя граница для чувствительности — (б).
VAT = 0.22
GRID_C1_RUB = round(17363.37 * (1 + VAT))   # 21 183 ₽
GRID_LGOT_RUB_PER_KW = 11470


def grid_connection(kw):
    return min(GRID_C1_RUB, GRID_LGOT_RUB_PER_KW * kw)
CABLE_M_PER_STRING = 40                   # 2 полюса × ~20 м от крыши до инвертора

comp = pd.read_csv(DATA / "capex_components.csv", encoding="utf-8-sig")
kits = pd.read_csv(DATA / "equipment_offers.csv", encoding="utf-8-sig")
turn = pd.read_csv(DATA / "turnkey_prices.csv", encoding="utf-8-sig")


def med(item, kw=None):
    d = comp[comp["item"] == item]
    if kw is not None:
        d = d[d.applies_to_kw.astype(str) == str(kw)]
    return float(d.price_rub.median())


def balance_of_system(kw):
    """Общие для обоих способов статьи, не входящие в комплект: защита, монтаж, оформление, доставка."""
    strings = 1 if kw <= 5 else 2
    phases = 1 if kw <= 5 else 3
    dc_protection = strings * (med("dc_spd") + 2 * med("dc_fuse"))
    return {
        "Защита DC/AC": dc_protection + AC_PROTECTION_RUB[phases],
        "Монтаж и пусконаладка": med("labour") * kw,
        "Подключение, доставка": grid_connection(kw) + DELIVERY_RUB + METER_RUB,
    }


rows, breakdown = [], {}
for kw in SIZES:
    panels = math.ceil(kw * 1000 / PANEL_W)
    strings = 1 if kw <= 5 else 2
    # --- способ В: снизу
    b = {
        "Панели": med("panel") * kw * 1000,
        "Инвертор": med("inverter", kw),
        "Крепёж": med("mounting") * panels,
        "Кабель, MC4": strings * CABLE_M_PER_STRING * med("dc_cable") + (2 * strings + 2) * med("mc4"),
        **balance_of_system(kw),
    }
    breakdown[kw] = b
    bottom_up = sum(b.values())
    # --- база: комплект краснодарского продавца + то, чего нет в комплекте
    k = kits.assign(rub_per_kw=kits.price_equipment_rub / kits.pv_kw)
    kit_per_kw = float(k[k.pv_kw <= 5].rub_per_kw.median() if kw <= 5 else k[k.pv_kw >= 6].rub_per_kw.median())
    base = kit_per_kw * kw + sum(balance_of_system(kw).values())
    # --- способ Б: опубликованные цены «под ключ» (середина диапазона) + плата за подключение
    #     (в опубликованные цены она не входит, data/turnkey_prices.csv, колонка includes).
    #     Для 10 кВт данных нет → цену за кВт от 5 кВт переносим с эффектом масштаба комплектов
    #     (отношение цены комплекта за кВт 6–15 кВт к 3–5 кВт), без постоянных статей.
    t = turn[turn.pv_kw == kw]
    if len(t):
        published = float(((t.price_low_rub + t.price_high_rub) / 2).median()) + grid_connection(kw)
    else:
        t5 = turn[turn.pv_kw == 5]
        per_kw5 = float(((t5.price_low_rub + t5.price_high_rub) / 2).median()) / 5
        scale = float(k[k.pv_kw >= 6].rub_per_kw.median()) / float(k[k.pv_kw <= 5].rub_per_kw.median())
        published = per_kw5 * kw * scale + grid_connection(kw)
    rows.append({
        "pv_kw": kw, "panels": panels,
        "capex_low_rub": round(bottom_up, -3), "capex_base_rub": round(base, -3), "capex_high_rub": round(published, -3),
        "inverter_rub": round(med("inverter", kw), -2),
        "base_rub_per_kw": round(round(base, -3) / kw, -2),
        "grid_connection_rub": grid_connection(kw), "grid_connection_max_rub": GRID_LGOT_RUB_PER_KW * kw,
        "method_low": "В: сумма компонентов по рознице", "method_base": "комплект Краснодара + монтаж + BOS",
        "method_high": "Б: опубликованные цены «под ключ»" + ("" if len(t) else " (экстраполяция от 5 кВт)"),
    })

est = pd.DataFrame(rows)
est.to_csv(DATA / "capex_estimate.csv", index=False, encoding="utf-8-sig")
print(est[["pv_kw", "panels", "capex_low_rub", "capex_base_rub", "capex_high_rub", "base_rub_per_kw", "inverter_rub"]].to_string(index=False))
for kw, b in breakdown.items():
    print(f"\nВ, {kw} кВт:", {k: round(v) for k, v in b.items()})

# --- график: разбивка способа В + база + Б
fig, ax = plt.subplots(figsize=(8, 3.8))
x = np.arange(len(SIZES))
bottom = np.zeros(len(SIZES))
cmap = plt.get_cmap("tab20c")
for i, part in enumerate(breakdown[SIZES[0]]):
    vals = np.array([breakdown[kw][part] for kw in SIZES]) / 1000
    ax.bar(x - 0.25, vals, 0.35, bottom=bottom, color=cmap(i), label=part)
    bottom += vals
ax.bar(x + 0.15, est.capex_base_rub / 1000, 0.2, color="#1f6fb2", label="База (комплект + монтаж)")
ax.bar(x + 0.35, est.capex_high_rub / 1000, 0.2, color="#c0392b", alpha=0.75, label="Б: опубликовано «под ключ»")
for i, r in est.iterrows():
    ax.text(i + 0.15, r.capex_base_rub / 1000 + 8, f"{r.capex_base_rub / 1000:.0f}", ha="center", fontsize=8, color="#1f6fb2")
    ax.text(i - 0.25, r.capex_low_rub / 1000 + 8, f"{r.capex_low_rub / 1000:.0f}", ha="center", fontsize=8)
    ax.text(i + 0.35, r.capex_high_rub / 1000 + 8, f"{r.capex_high_rub / 1000:.0f}", ha="center", fontsize=8, color="#c0392b")
ax.set_xticks(x, [f"{kw} кВт" for kw in SIZES])
ax.set_ylabel("тыс. ₽")
ax.set_title("Капзатраты СЭС «под ключ»: В (по компонентам), база и Б (опубликованные цены)")
ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
fig.savefig(ROOT / "results" / "capex_estimate.png", dpi=200, bbox_inches="tight")
print("\nГрафик:", ROOT / "results" / "capex_estimate.png")
