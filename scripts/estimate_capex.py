"""Оценка капзатрат СЭС «под ключ» для 3, 5, 10 кВт (задачи 2.1, T2.4, T1.7).

С 03.11.2026 база — по коммерческим предложениям установщиков Краснодара (data/kp_responses.csv):
КП (база):   ₽ за ватт панелей сетевой станции «под ключ» у каждой компании, интерполяция по мощности
             внутри её собственных КП, среднее по компаниям × мощность + плата за подключение.
             Монтаж там, где КП дано без него (Экопроект-Энерго), — 20 % комплекта (компания: 15–25 %).
КП (низ):    то же, минимум по компаниям, монтаж 15 %.
Верх:        прежняя база (до 03.11): комплект краснодарского продавца из каталога
             (data/equipment_offers.csv) + монтаж + защита + подключение + доставка.
             По КП трёх компаний она оказалась выше рынка на 20–50 % (docs/kp_plan.md, «Выводы по КП»).
Для справки (колонки capex_components_rub и capex_published_rub, в модель не идут):
В — сумма компонентов по рознице (data/capex_components.csv);
Б — опубликованные цены «под ключ» (data/turnkey_prices.csv, общероссийские) + плата за подключение.

Конфиденциальные КП в data/kp_responses.csv не вносятся и в расчёт не входят.

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
kp = pd.read_csv(DATA / "kp_responses.csv", encoding="utf-8-sig")

# --- КП: монтаж, если компания дала только комплект (Экопроект-Энерго, 20.10.2026: «15–25 % от стоимости
#     комплекта»); база — середина, низ — 15 %
KP_INSTALL_SHARE = {"base": 0.20, "low": 0.15}
KP_NEAREST_TOL = 0.20     # мощность вне диапазона КП компании: берём её ближайшее КП, если оно отличается ≤ 20 %


def kp_points(install_share):
    """{компания: [(кВт панелей, ₽/Вт без платы за подключение), …]} по сетевым КП «под ключ»."""
    d = kp[kp.inverter_type.str.startswith("on-grid")].copy()
    w = d.panel_model.str.extract(r"(\d{3})\s*Вт", expand=False).astype(float)
    d["kwp"] = (w * d.panel_count / 1000).fillna(d.pv_kw)
    d["total"] = d.price_total_rub.fillna(d.price_equipment_rub * (1 + install_share))
    d = d.dropna(subset=["total"])
    return {c: sorted(zip(g.kwp, g.total / (g.kwp * 1000))) for c, g in d.groupby("company")}


def kp_rub_per_w(points, kw):
    """₽/Вт компании для мощности kw: интерполяция внутри её КП или ближайшее КП в пределах допуска; иначе None."""
    x, y = zip(*points)
    if x[0] <= kw <= x[-1]:
        return float(np.interp(kw, x, y))
    near = min(range(len(x)), key=lambda i: abs(x[i] - kw))
    return y[near] if abs(x[near] - kw) / kw <= KP_NEAREST_TOL else None


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
    # --- КП установщиков: среднее (база) и минимум (низ) по компаниям + плата за подключение
    #     (её нет ни в одном КП; доставка в КП входит)
    kp_base = [r for r in (kp_rub_per_w(p, kw) for p in kp_points(KP_INSTALL_SHARE["base"]).values()) if r]
    kp_low = [r for r in (kp_rub_per_w(p, kw) for p in kp_points(KP_INSTALL_SHARE["low"]).values()) if r]
    kp_capex = float(np.mean(kp_base)) * kw * 1000 + grid_connection(kw)
    kp_capex_low = min(kp_low) * kw * 1000 + grid_connection(kw)
    rows.append({
        "pv_kw": kw, "panels": panels,
        "capex_low_rub": round(kp_capex_low, -3), "capex_base_rub": round(kp_capex, -3), "capex_high_rub": round(base, -3),
        "inverter_rub": round(med("inverter", kw), -2),
        "base_rub_per_kw": round(round(kp_capex, -3) / kw, -2),
        "grid_connection_rub": grid_connection(kw), "grid_connection_max_rub": GRID_LGOT_RUB_PER_KW * kw,
        "kp_companies": len(kp_base),
        "capex_components_rub": round(bottom_up, -3), "capex_published_rub": round(published, -3),
        "method_low": "КП установщиков: минимум по компаниям, монтаж 15 %",
        "method_base": f"КП установщиков: среднее по {len(kp_base)} компани{'и' if len(kp_base) == 1 else 'ям'} + подключение",
        "method_high": "прежняя база: комплект Краснодара из каталога + монтаж + BOS",
    })

est = pd.DataFrame(rows)
est.to_csv(DATA / "capex_estimate.csv", index=False, encoding="utf-8-sig")
print(est[["pv_kw", "capex_low_rub", "capex_base_rub", "capex_high_rub", "base_rub_per_kw", "kp_companies",
           "inverter_rub", "capex_components_rub", "capex_published_rub"]].to_string(index=False))
for c, pts in kp_points(KP_INSTALL_SHARE["base"]).items():
    print(f"КП {c}:", ", ".join(f"{k:.2f} кВт — {r:.1f} ₽/Вт" for k, r in pts))

# --- график: КП (низ и база), прежняя база (верх); В и Б — для справки
fig, ax = plt.subplots(figsize=(8, 3.8))
x = np.arange(len(SIZES))
bars = [("capex_low_rub", "КП: минимум (низ)", "#9ecae1"),
        ("capex_base_rub", "КП: среднее (база)", "#1f6fb2"),
        ("capex_high_rub", "Прежняя база (верх)", "#c0392b"),
        ("capex_components_rub", "В: компоненты по рознице (справочно)", "#bdbdbd"),
        ("capex_published_rub", "Б: опубликовано «под ключ» (справочно)", "#636363")]
width = 0.16
for j, (col, label, color) in enumerate(bars):
    pos = x + (j - 2) * width
    ax.bar(pos, est[col] / 1000, width, color=color, label=label)
    for i, v in enumerate(est[col] / 1000):
        ax.text(pos[i], v + 8, f"{v:.0f}", ha="center", fontsize=7, color=color if j < 3 else "#444444")
ax.set_xticks(x, [f"{kw} кВт" for kw in SIZES])
ax.set_ylabel("тыс. ₽")
ax.set_title("Капзатраты сетевой СЭС «под ключ» с платой за подключение: база по КП установщиков")
ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
fig.savefig(ROOT / "results" / "capex_estimate.png", dpi=200, bbox_inches="tight")
print("\nГрафик:", ROOT / "results" / "capex_estimate.png")
