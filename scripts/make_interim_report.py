"""Промежуточный отчёт команды 2 SunCount в PDF: графики строятся из данных проекта.

Запуск: python scripts/make_interim_report.py
Результат: reports/SunCount_interim_report.pdf (графики — results/report_figs/)
"""
import datetime as dt
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from matplotlib.ticker import FuncFormatter, ScalarFormatter
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ import params as P  # noqa: E402
from src.econ.exchange import annual_from_monthly, make_stub_monthly, read_csv  # noqa: E402
from src.econ.inputs import TariffPlan, buyback_monthly, pv_monthly_kwh_per_kw, zone_prices  # noqa: E402
from src.econ.model import (Scenario, Tariff, annual_effect, annual_effect_monthly, cash_flows,  # noqa: E402
                            discount_factors, discounted_payback, simple_payback)
HYP_LIMIT, HYP_SHARE = 20, 80   # гипотеза: доля излишков ≤ 20 % не менее чем в 80 % сочетаний (PLAN, решение от 22.10.2026)

DATA, FIGS = ROOT / "data", ROOT / "results" / "report_figs"
OUT = ROOT / "reports" / "SunCount_interim_report.pdf"
FIGS.mkdir(parents=True, exist_ok=True)
OUT.parent.mkdir(parents=True, exist_ok=True)
TODAY = dt.date.today().strftime("%d.%m.%Y")

plt.rcParams.update({"font.family": "Arial", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.3})
C = {"city": "#1f6fb2", "rural": "#e08a1e", "flat": "#1f6fb2", "zones": "#2a9d4b", "grey": "#888888", "red": "#c0392b"}
MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
PLANS = [
    TariffPlan("Город, одноставочный", "base", "single", ("base",)),
    TariffPlan("Город, день/ночь", "base", "two_zone", ("base",)),
    TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",)),
    TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",)),
]
PLAN_COLORS = ["#1f6fb2", "#2a9d4b", "#e08a1e", "#8e44ad"]


def save(fig, name):
    # десятичная запятая на числовых осях (даты и подписи категорий не трогаем)
    for a in fig.axes:
        for axis in (a.xaxis, a.yaxis):
            if isinstance(axis.get_major_formatter(), ScalarFormatter):
                axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−")))
    path = FIGS / f"{name}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


# =============================================================== данные
tar = pd.read_csv(DATA / "tariffs_2026.csv", encoding="utf-8-sig")
bb = pd.read_csv(DATA / "buyback_prices.csv", encoding="utf-8-sig")
bbc = pd.read_csv(DATA / "buyback_by_category.csv", encoding="utf-8-sig")
eq = pd.read_csv(DATA / "equipment_offers.csv", encoding="utf-8-sig")
pay = pd.read_csv(ROOT / "results" / "stub_payback.csv", encoding="utf-8-sig")
CAPEX = pd.read_csv(DATA / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw").capex_base_rub.to_dict()


def tprice(period, cat, ttype, zone, rng="I"):
    r = tar[(tar.date_from == period) & (tar.category == cat) & (tar.tariff_type == ttype) & (tar.zone == zone) & (tar.range == rng)]
    return float(r.price_rub_kwh.iloc[0])


# =============================================================== графики
# 1. Тарифы 2026
labels = ["Город\nодноставочный", "Город\nдень", "Город\nночь", "Село\nодноставочный", "Село\nдень", "Село\nночь"]
keys = [("base", "single", "flat"), ("base", "two_zone", "day"), ("base", "two_zone", "night"),
        ("reduced", "single", "flat"), ("reduced", "two_zone", "day"), ("reduced", "two_zone", "night")]
p1 = [tprice("2026-01-01", *k) for k in keys]
p2 = [tprice("2026-10-01", *k) for k in keys]
fig, ax = plt.subplots(figsize=(8, 3.4))
x = np.arange(len(labels))
ax.bar(x - 0.2, p1, 0.4, label="01.01–30.09.2026", color="#9ec5e8")
b = ax.bar(x + 0.2, p2, 0.4, label="с 01.10.2026", color=C["city"])
ax.bar_label(b, labels=[f"{v:.2f}".replace(".", ",") for v in p2], fontsize=8)
ax.set_xticks(x, labels)
ax.set_ylabel("₽/кВт·ч (с НДС)")
ax.set_title("Тарифы для населения Краснодарского края и Адыгеи, I диапазон (до 1100 кВт·ч/мес)")
ax.legend(frameon=False)
f_tariffs = save(fig, "01_tariffs")

# 2. Цена выкупа по месяцам + восстановленные цены по категориям + тариф
bb["date"] = pd.to_datetime(bb.month + "-01")
bbc["date"] = pd.to_datetime(bbc.month + "-01")
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(bb.date, bb.price_rub_kwh, "o-", color="black", ms=4, label="Средневзвешенная цена покупки ТНС (факт)")
ax.plot(bbc.date, bbc.flat_rub_kwh, "s--", color=C["flat"], label="Владелец на одноставочном тарифе (расчёт)")
ax.plot(bbc.date, bbc.zones_day_rub_kwh, "^--", color=C["zones"], label="Владелец на тарифе день/ночь (расчёт)")
ax.hlines(tprice("2026-01-01", "base", "single", "flat"), pd.Timestamp("2026-01-01"), pd.Timestamp("2026-09-30"),
          color=C["red"], lw=2, label="Тариф город, одноставочный, до 30.09.2026 (покупка из сети)")
ax.hlines(tprice("2026-01-01", "reduced", "single", "flat"), pd.Timestamp("2026-01-01"), pd.Timestamp("2026-09-30"),
          color=C["rural"], lw=2, label="Тариф село, одноставочный, до 30.09.2026")
ax.set_ylabel("₽/кВт·ч")
ax.set_ylim(0, 10)
ax.set_title("Цена выкупа излишков микрогенерации ПАО «ТНС энерго Кубань»")
ax.legend(frameon=False, fontsize=7, loc="lower left", ncol=2)
f_buyback = save(fig, "02_buyback")

# 3. Объёмы покупки у микрогенерации
fig, ax = plt.subplots(figsize=(8, 2.8))
ax.bar(bb.date, bb.volume_flat_kwh / 1000, width=20, color=C["flat"], label="владельцы на одноставочном тарифе")
ax.bar(bb.date, bb.volume_zones_kwh / 1000, width=20, bottom=bb.volume_flat_kwh / 1000, color=C["zones"],
       label="владельцы на тарифе по зонам суток")
ax.bar(bb.date, bb.volume_other_kwh / 1000, width=20, bottom=(bb.volume_flat_kwh + bb.volume_zones_kwh) / 1000,
       color=C["grey"], label="3–6 ценовые категории")
ax.set_ylabel("МВт·ч в месяц")
ax.set_title("Сколько электроэнергии ТНС энерго Кубань купило у владельцев СЭС")
ax.legend(frameon=False, fontsize=7)
f_volumes = save(fig, "03_volumes")

# 4. Проверка восстановления цены
v = bbc.dropna(subset=["observed_avg_rub_kwh"])
fig, ax = plt.subplots(figsize=(6, 2.8))
xm = np.arange(len(v))
ax.bar(xm - 0.2, v.observed_avg_rub_kwh, 0.4, color="black", label="факт (опубликовано ТНС)")
bp = ax.bar(xm + 0.2, v.predicted_avg_rub_kwh, 0.4, color="#9ec5e8", label="модель (по категориям)")
ax.bar_label(bp, labels=[f"{e:+.1f} %".replace(".", ",") for e in v.error_pct], fontsize=8)
ax.set_xticks(xm, [MONTHS[int(m[5:7]) - 1] + " 2026" for m in v.month])
ax.set_ylim(0, 7.5)
ax.set_ylabel("₽/кВт·ч")
ax.set_title("Проверка: модель цены выкупа против факта")
ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
f_check = save(fig, "04_check")

# 5. PVGIS
kr, mk = pv_monthly_kwh_per_kw("krasnodar"), pv_monthly_kwh_per_kw("maykop")
fig, ax = plt.subplots(figsize=(8, 2.8))
ax.bar(np.arange(12) - 0.2, [kr[m] for m in range(1, 13)], 0.4, color=C["city"], label=f"Краснодар ({sum(kr.values()):.0f} кВт·ч/год)")
ax.bar(np.arange(12) + 0.2, [mk[m] for m in range(1, 13)], 0.4, color=C["rural"], label=f"Майкоп ({sum(mk.values()):.0f} кВт·ч/год)")
ax.set_xticks(range(12), MONTHS)
ax.set_ylabel("кВт·ч на 1 кВт мощности")
ax.set_title("Выработка СЭС 1 кВт по месяцам (PVGIS-SARAH3, наклон 30°, юг, потери 14 %)")
ax.legend(frameon=False)
f_pv = save(fig, "05_pvgis")

# 6. Накопленный дисконтированный денежный поток, 5 кВт, самопотребление 40 %
sc = Scenario(inverter_cost_rub=float(pd.read_csv(DATA / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw").inverter_rub[5]))
months40 = make_stub_monthly("stub_40", 5, 6000, 40, "krasnodar")
fig, ax = plt.subplots(figsize=(8, 3.4))
years = np.arange(0, sc.lifetime + 1)
for plan, col in zip(PLANS, PLAN_COLORS):
    e = annual_effect_monthly(months40, plan)
    flows = cash_flows(e, CAPEX[5], sc)
    cum = np.concatenate([[-CAPEX[5]], -CAPEX[5] + np.cumsum(np.array(flows) * np.array(discount_factors(sc)))])
    ax.plot(years, cum / 1000, color=col, lw=2, label=plan.name)
ax.axhline(0, color="black", lw=0.8)
ax.axvline(sc.inverter_year, color=C["grey"], ls=":", lw=1)
ax.text(sc.inverter_year + 0.2, ax.get_ylim()[0] * 0.9, "замена\nинвертора", fontsize=7, color=C["grey"])
ax.set_xlabel("Год работы СЭС")
ax.set_ylabel("тыс. ₽ (дисконтировано)")
ax.set_title("Накопленный дисконтированный денежный поток: СЭС 5 кВт, самопотребление 40 %")
ax.legend(frameon=False, fontsize=8)
f_cash = save(fig, "06_cashflow")

# 7. Гипотеза 2: доля дохода от излишков
fig, ax = plt.subplots(figsize=(8, 3.2))
for plan, col in zip(PLANS, PLAN_COLORS):
    d = pay[(pay.pv_kw == 3) & (pay.tariff == plan.name)]
    ax.plot(d.self_share, d.export_share_pct, "o-", color=col, label=plan.name)
ax.axhline(20, color=C["red"], ls="--")
ax.text(21, 22, "граница для одного сочетания: 20 %", color=C["red"], fontsize=8)
ax.set_xlabel("Доля самопотребления, %")
ax.set_ylabel("Доля излишков в эффекте, %")
ax.set_ylim(0, 100)
ax.set_title("Часть Б гипотезы 2: доля дохода от излишков, СЭС 3 кВт (условные профили)")
ax.legend(frameon=False, fontsize=8)
f_hyp = save(fig, "07_hypothesis")

# 8. Эффект диапазонов тарифа
heavy_shape = [1.6, 1.5, 1.2, 0.9, 0.8, 1.0, 1.2, 1.2, 0.9, 0.8, 1.2, 1.6]
cases = [("Дом 6 000 кВт·ч/год,\nСЭС 5 кВт", 6000, 5, None, 50), ("Дом 18 000 кВт·ч/год,\nСЭС 10 кВт", 18000, 10, heavy_shape, 60)]
tz, mon = [], []
for _, load, kw, shape, share in cases:
    ms = make_stub_monthly("x", kw, load, share, "krasnodar", load_shape=shape)
    p_i = zone_prices(PLANS[0])["I"]["day"]
    tz.append(annual_effect(annual_from_monthly(ms), Tariff.flat("ТЗ", p_i), np.mean(list(buyback_monthly("flat").values()))).effect_rub)
    mon.append(annual_effect_monthly(ms, PLANS[0]).effect_rub)
fig, ax = plt.subplots(figsize=(6, 2.8))
xc = np.arange(2)
ax.bar(xc - 0.2, np.array(tz) / 1000, 0.4, color="#bbbbbb", label="формула ТЗ (I диапазон, средний выкуп)")
bm = ax.bar(xc + 0.2, np.array(mon) / 1000, 0.4, color=C["city"], label="помесячно: диапазоны + сезонный выкуп")
ax.bar_label(bm, labels=[(f"{round(100 * (m / t - 1)):+d} %" if round(100 * (m / t - 1)) else "0 %").replace("-", "−")
                         for t, m in zip(tz, mon)], fontsize=8)
ax.set_xticks(xc, [c[0] for c in cases])
ax.set_ylabel("Годовой эффект, тыс. ₽")
ax.set_title("Учёт диапазонов тарифа (город, одноставочный)")
ax.legend(frameon=False, fontsize=7, loc="upper left")
f_ranges = save(fig, "08_ranges")

# 9. Помесячный зачёт (ОП № 442, п. 63(1)) против модели ТЗ, самопотребление 20 %
fig, axes = plt.subplots(1, 3, figsize=(9, 3.0), sharey=True)
for ax, kw in zip(axes, (3, 5, 10)):
    d = pay[(pay.pv_kw == kw) & (pay.self_share_target == 20)].set_index("tariff").loc[[pl.name for pl in PLANS]]
    xt = np.arange(len(d))
    bo = ax.bar(xt - 0.2, d.simple_payback, 0.4, color=PLAN_COLORS)
    bn = ax.bar(xt + 0.2, d.simple_payback_net, 0.4, color="white", edgecolor=PLAN_COLORS, hatch="///")
    ax.bar_label(bo, labels=[f"{v:.1f}".replace(".", ",") for v in d.simple_payback], fontsize=6)
    ax.bar_label(bn, labels=[f"{v:.1f}".replace(".", ",") for v in d.simple_payback_net], fontsize=6)
    ax.set_xticks(xt, [n.replace("Город, ", "Г, ").replace("Село, ", "С, ").replace("одноставочный", "1 ст.")
                       .replace("день/ночь", "д/н") for n in d.index], fontsize=7)
    ax.set_title(f"{kw} кВт", fontsize=9)
axes[0].set_ylabel("Простой срок, лет")
from matplotlib.patches import Patch  # noqa: E402
fig.legend([Patch(facecolor="#777777"), Patch(facecolor="white", edgecolor="#777777", hatch="///")],
           ["основной вариант (без зачёта)", "сценарий: помесячный зачёт по п. 63(1)"],
           frameon=False, fontsize=7, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.06))
fig.suptitle("Простой срок окупаемости: основной вариант и сценарий с зачётом (самопотребление 20 %)", fontsize=9)
f_net = save(fig, "10_netting")

fig_h, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
for ax, (col, title, vmax) in zip(axes, [("simple_payback", "Простой срок окупаемости, лет", 16),
                                         ("disc_payback", "Дисконтированный срок окупаемости, лет", 25)]):
    hp = pay[pay.pv_kw == 5].pivot_table(index="self_share_target", columns="tariff", values=col)[[pl.name for pl in PLANS]]
    vals = hp.values.astype(float)
    ax.imshow(np.where(np.isfinite(vals), vals, vmax), cmap="RdYlGn_r", vmin=4, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(hp.columns)), [c.replace(", ", "\n") for c in hp.columns], fontsize=8)
    ax.set_yticks(range(len(hp.index)), [f"{i} %" for i in hp.index])
    ax.grid(False)
    for i in range(hp.shape[0]):
        for j in range(hp.shape[1]):
            ok = np.isfinite(vals[i, j])
            ax.text(j, i, f"{vals[i, j]:.1f}".replace(".", ",") if ok else "не окуп.", ha="center", va="center",
                    fontsize=10 if ok else 8, color="black" if ok else "white")
    ax.set_title(title, fontsize=10)
axes[0].set_ylabel("Доля самопотребления")
fig_h.suptitle("СЭС 5 кВт, Краснодар, потребление 6000 кВт·ч/год", fontsize=10)
f_heat = save(fig_h, "09_heatmap_5kw")

# =============================================================== PDF
pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", "C:/Windows/Fonts/ariali.ttf"))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-Bold")

S = {
    "title": ParagraphStyle("t", fontName="Arial-Bold", fontSize=22, leading=27, alignment=TA_CENTER, spaceAfter=10),
    "sub": ParagraphStyle("s", fontName="Arial", fontSize=12, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#444444")),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=18, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1f4e79"),
                         keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=4, keepWithNext=1),
    "p": ParagraphStyle("p", fontName="Arial", fontSize=9.5, leading=13, spaceAfter=4),
    "li": ParagraphStyle("li", fontName="Arial", fontSize=9.5, leading=13, leftIndent=12, bulletIndent=2, spaceAfter=2),
    "cap": ParagraphStyle("c", fontName="Arial-Italic", fontSize=8, leading=10, textColor=colors.HexColor("#555555"), spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=8, leading=10),
    "cellb": ParagraphStyle("cellb", fontName="Arial-Bold", fontSize=8, leading=10),
    "note": ParagraphStyle("n", fontName="Arial", fontSize=9, leading=12, backColor=colors.HexColor("#fff4e0"),
                           borderPadding=6, spaceBefore=4, spaceAfter=8),
}
W = A4[0] - 3.6 * cm


def para(t, s="p"):
    return Paragraph(t, S[s])


def bullets(items):
    return [Paragraph(i, S["li"], bulletText="•") for i in items]


def fig(path, caption, width=W):
    img = Image(str(path))
    img.drawWidth, img.drawHeight = width, width * img.imageHeight / img.imageWidth
    return KeepTogether([img, para(caption, "cap")])


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), S["cellb" if header and i == 0 else "cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * W for w in widths], repeatRows=1 if header else 0)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0f8") if header else colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 7.5)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(1.8 * cm, 1.1 * cm, f"SunCount · промежуточный отчёт команды 2 · {TODAY} · результаты предварительные")
    canvas.drawRightString(A4[0] - 1.8 * cm, 1.1 * cm, f"стр. {doc.page}")
    canvas.restoreState()


NB = "\u00a0"                                   # неразрывный пробел: числа не рвутся при переносе
rub = lambda x: f"{x:,.0f}".replace(",", NB)
ru = lambda x, nd=2: f"{x:.{nd}f}".replace(".", ",")
_tab = [0]


def tcap(text):
    """Подпись таблицы со сквозной нумерацией."""
    _tab[0] += 1
    return para(f"Таблица {_tab[0]}. {text}", "cap")


def yrs(s):
    """Диапазон сроков, лет; «не окупается» вместо inf."""
    s = pd.Series(s, dtype=float)
    fin = s[np.isfinite(s)]
    if not len(fin):
        return "не окупается"
    txt = ru(fin.min(), 1) if fin.min() == fin.max() else f"{ru(fin.min(), 1)}–{ru(fin.max(), 1)}"
    n_inf = int((~np.isfinite(s)).sum())
    return txt + (f"; не окупается в {n_inf} из {len(s)}" if n_inf else "")
bmf, bmz = buyback_monthly("flat"), buyback_monthly("zones")
flat_avg, zones_avg = bbc.flat_rub_kwh.mean(), bbc.zones_day_rub_kwh.mean()
b24 = bb[bb.month.str.startswith("2024")]
b25 = bb[bb.month.str.startswith("2025")]
b26 = bb[bb.month.str.startswith("2026")]
w24 = (b24.price_rub_kwh * b24.volume_total_kwh).sum() / b24.volume_total_kwh.sum()
w25 = (b25.price_rub_kwh * b25.volume_total_kwh).sum() / b25.volume_total_kwh.sum()
w26 = (b26.price_rub_kwh * b26.volume_total_kwh).sum() / b26.volume_total_kwh.sum()
b25s = b25[b25.month.str[5:7] <= bb.month.max()[5:7]]
w25_same = (b25s.price_rub_kwh * b25s.volume_total_kwh).sum() / b25s.volume_total_kwh.sum()
p5 = pay[pay.pv_kw == 5]
last = bb.month.max()
last_name = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"][int(last[5:7]) - 1]
n26 = len(b26)
chk = bbc.dropna(subset=["observed_avg_rub_kwh"])
sep = chk[chk.month == "2026-09"]
capd = pd.read_csv(DATA / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw")
cap_lo = 100 * (1 - capd.capex_low_rub / capd.capex_base_rub)
cap_hi = 100 * (capd.capex_high_rub / capd.capex_base_rub - 1)
CAP_SPREAD = f"от −{cap_lo.max():.0f} до +{cap_hi.max():.0f} % от базы"
GRID = capd.grid_connection_rub.to_dict()
GRID_MAX = capd.grid_connection_max_rub.to_dict()

story = []
# ---------- титул
story += [Spacer(1, 4.5 * cm), para("SunCount", "title"),
          para("Система поддержки принятия решений по выбору домашней солнечной электростанции<br/>для Адыгеи и Краснодарского края", "sub"),
          Spacer(1, 1 * cm),
          para("<b>Промежуточный отчёт команды 2</b><br/>Тема 2. Оценка влияния тарифов и условий микрогенерации "
               "на срок окупаемости домашней СЭС", "sub"),
          Spacer(1, 1.2 * cm), para(f"Состояние на {TODAY} · этап 2 «Сбор данных и первые модели» (26.10–15.11.2026)", "sub"),
          Spacer(1, 0.8 * cm),
          para("Команда 2: Прищепа Максим (руководитель), Власов Кирилл, Цирульник Юрий, Кривоносов Вячеслав, Рогочий Александр<br/>"
               "Наставник: Онищенко Стефан Владимирович<br/>Адыгейский государственный университет · Майкоп, 2026", "sub"),
          Spacer(1, 1.2 * cm),
          para("<b>Важно.</b> Все расчёты окупаемости в этом отчёте — <b>предварительные</b>: профили потребления пока "
               "условные или предварительные данные команды 1 (финальные — до 04.12.2026), капзатраты — по открытым КП "
               f"установщиков, для 3 и 5 кВт — по одной компании (разброс оценок {CAP_SPREAD}). Тарифы, цены выкупа, выработка и экономические параметры — "
               "по официальным и фактическим данным или расчёту по ним, со ссылками; допущения — в разделе 5.", "note"),
          PageBreak()]

# ---------- 1. Введение
story += [para("1. Исследовательский вопрос и задачи команды 2", "h1"),
          para("<b>Вопрос проекта:</b> как профиль потребления и тариф влияют на окупаемость домашней солнечной "
               "электростанции? По закону о микрогенерации владелец СЭС может продавать излишки в сеть, но, как "
               "правило, дешевле, чем покупает электроэнергию. Поэтому выгода зависит от того, <i>когда</i> дом тратит энергию "
               "(если не применяется расчёт объёмов по итогам месяца — см. раздел 5)."),
          para("<b>Сокращения:</b> СЭС — солнечная электростанция; ТЗ — техническое задание курса; КП — коммерческое предложение; "
               "ОП № 442 — Основные положения функционирования розничных рынков электрической энергии (утв. постановлением "
               "Правительства РФ (ПП РФ) от 04.05.2012 № 442); ТНС — ПАО «ТНС энерго Кубань»; ДГРТ — департамент государственного "
               "регулирования тарифов Краснодарского края; МЭР — Минэкономразвития России; МКД — многоквартирный дом. Ценовая "
               "категория — способ расчёта с поставщиком: 1-я — по одноставочной цене, 2-я — по зонам суток.", "cap"),
          para("<b>Гипотеза 2 (команда 2, формулировка ТЗ курса):</b> срок окупаемости определяется прежде всего тарифом и "
               "долей самопотребления, а доход от продажи излишков составляет не более пятой части (20 %) годового "
               "экономического эффекта."),
          para("Гипотеза состоит из двух утверждений, каждое проверяется отдельно:"),
          *bullets(["<b>Часть А</b> — от чего зависит срок. Критерий (мастер-ТЗ, задача T3.4): в анализе чувствительности по "
                    "простому сроку два самых влиятельных фактора — тариф и доля самопотребления, хотя бы для трёх тарифов из "
                    "четырёх. Финальная проверка — торнадо-диаграммы на данных команды 1 (до 12.12.2026). В этом отчёте — "
                    "прототип торнадо на условном профиле и разброс простого срока на данных команды 1 (раздел 7).",
                    "<b>Часть Б</b> — из чего состоит эффект. Показатель — доля дохода от продажи излишков в годовом эффекте. "
                    f"Критерий (из презентации «Тема, задел и гипотеза»): доля не больше {HYP_LIMIT} % не менее чем в {HYP_SHARE} % "
                    "сочетаний «портрет потребления × тариф × мощность» (3, 5 и 10 кВт с равным весом, оба города).",
                    "Гипотеза подтверждается, если подтверждены обе части, и частично — если одна. Гипотезу о профилях "
                    "потребления (у дома, где днём кто-то есть, самопотребление минимум в 1,5 раза выше) проверяет команда 1."]),
          para(f"<b>Задачи команды 2</b> и статус на {TODAY}:")]
story.append(table([
    ["Задача", "Статус", "Результат"],
    ["Нормативная база микрогенерации, изменения 2026 г.", "готово", "раздел 2"],
    ["Тарифы для населения Адыгеи и Краснодарского края", "готово", "раздел 3, data/tariffs_2026.csv"],
    ["Цена выкупа излишков и её динамика за 1–2 года", "готово; правило — по тексту ОП № 442 (п. 65(3)), расчёт проверен на новых данных", "раздел 4"],
    ["Плата за подключение СЭС к сети", "готово по приказу ДГРТ № 19/2025-э (уточнить ставку на счётчик)", "раздел 6"],
    ["Формат обмена данными с командой 1", "согласован 17.10.2026", "docs/exchange_format.md"],
    ["Капзатраты на СЭС 3/5/10 кВт «под ключ»", "готово: база по КП установщиков, низ и верх для чувствительности", "раздел 6"],
    ["Экономическая модель (простой и дисконтированный срок)", "готово", "раздел 5"],
    ["Расчёт на условных долях самопотребления 20–80 %", "готово (предварительно)", "раздел 7"],
    ["Проверка данных команды 1 и расчёт на них", "проверки № 1–4; данные по годам PVGIS от 03.11.2026 приняты", "раздел 7"],
    ["Анализ чувствительности (торнадо: 11 параметров и сценарий выкупа, 4 тарифа)", "прототип готов 02.11.2026 на условном профиле; финал — на данных команды 1", "раздел 7, docs/hypothesis2.md"],
    ["Аналитический веб-сервис (Streamlit)", "каркас готов 03.11.2026: 3 мощности, 4 тарифа, расчёт через единую точку входа модели", "app/"],
    ["Тепловая карта на реальных профилях, итоговая проверка гипотезы 2", "этапы 3–4", "—"],
], [0.5, 0.25, 0.25]))

# ---------- 2. Нормативка
story += [para("2. Нормативная база микрогенерации", "h1")]
story.append(table([
    ["Документ", "Что важно для проекта"],
    ["35-ФЗ «Об электроэнергетике» (ст. 3), в ред. 471-ФЗ от 27.12.2019", "Понятие объекта микрогенерации: присоединение к сетям напряжением до 1000 В, производство для собственных нужд, в сеть — только излишки."],
    ["ОП № 442 (ПП РФ от 04.05.2012 № 442), п. 65(3)", "Гарантирующий поставщик обязан покупать излишки. Цена зависит от тарифа гражданина: на одноставочном — оптовая цена энергии (рынок на сутки вперёд) + цена мощности × коэффициент 1-й ценовой категории; на тарифе по зонам суток — та же цена по зонам суток (2-я категория). Передача и сбытовая надбавка в цену не входят."],
    ["ОП № 442, п. 63(1) (введён ПП РФ от 02.03.2021 № 299) и п. 79", "Объёмы гражданина определяются по итогам расчётного периода — месяца (п. 79): он оплачивает только превышение покупки из сети над выдачей в сеть, а продаёт только превышение выдачи над покупкой; на тарифе день/ночь — отдельно по каждой зоне суток. Нужен прибор учёта с почасовыми измерениями в двух направлениях."],
    ["ПП РФ от 27.12.2004 № 861 (п. 17); приказ ДГРТ от 24.12.2025 № 19/2025-э", "Плата за подключение микрогенерации физлица (мощность до 15 кВт с учётом ранее присоединённой, сеть 0,4 кВ, до сети не более 300 м в городе и 500 м на селе) — меньшая из двух сумм: по стандартизированным ставкам или 11 470 ₽ за 1 кВт с НДС (п. 1 приказа); для льготных категорий (абз. 11–19 п. 17 ПП № 861, по документам) — 1 304,42 ₽ за кВт с НДС (п. 3)."],
    ["208-ФЗ от 26.06.2026", "Жёсткий лимит 15 кВт отменён; предельные значения выдачи в сеть устанавливает Правительство; Правительство определяет случаи и порядок размещения микрогенерации в общем имуществе МКД."],
    ["Распоряжение Правительства РФ от 26.09.2026 № 2675-р", "Лимиты выдачи в сеть: физлица — не более 50 кВт, ИП, юрлица и общее имущество МКД — не более 150 кВт включительно, но не выше максимальной мощности энергопринимающих устройств потребителя."],
    ["ПП РФ от 26.09.2026 № 1242", "В Правила техприсоединения (ПП № 861) добавлено присоединение микрогенерации, в том числе в МКД; «не более 15 кВт» заменено отсылкой к предельным значениям, установленным Правительством; объекты микрогенерации МКД включены в общее имущество (ПП № 491)."],
    ["459-ФЗ от 27.12.2019 (п. 28.1 ст. 217 НК РФ)", "Доход физлица от продажи излишков освобождён от НДФЛ до 01.01.2029; далее в модели — 13 %."],
], [0.38, 0.62]))
story += [para("<b>Вывод:</b> домашние СЭС 3, 5 и 10 кВт укладываются в любые лимиты, изменения 2026 г. расширяют рынок, "
               "но экономику домашней станции напрямую не меняют. Для экономики важны правила ОП № 442, действующие с 2021 г.: "
               "цена выкупа по тарифу владельца (п. 65(3)) и расчёт объёмов по итогам месяца (п. 63(1); в отчёте — сценарий, раздел 5). "
               "Тарифы для населения Краснодарского края и Адыгеи установлены одним приказом и одинаковы. Основной гарантирующий "
               "поставщик — ПАО «ТНС энерго Кубань»; на части территории края гарантирующий поставщик — АО «НЭСК», и цену выкупа "
               "там определяет он. В отчёте цена выкупа рассчитана по данным ТНС.")]

# ---------- 3. Тарифы
story += [para("3. Тарифы для населения на 2026 год", "h1"),
          para("Приказ ДГРТ Краснодарского края от 17.12.2025 № 18/2025-э (Краснодарский край, Республика Адыгея, ФТ «Сириус»). "
               "Два периода: с 1 января и с 1 октября 2026 г. (+11 % в I диапазоне). Пониженные ставки — для сельского населения и "
               "городских домов с электроплитами / электроотоплением."),
          fig(f_tariffs, "Рис. 1. Тарифы I диапазона. Источник: приказ ДГРТ № 18/2025-э (таблица тарифов на сайте ТНС), data/tariffs_2026.csv."),
          para("<b>Диапазоны по объёму:</b> для жилого дома I — до 1100 кВт·ч/мес, II — 1100–1700, III — свыше 1700; "
               f"во II диапазоне городской тариф {ru(tprice('2026-10-01', 'base', 'single', 'flat', 'II'))} ₽, в III — "
               f"{ru(tprice('2026-10-01', 'base', 'single', 'flat', 'III'))} ₽ (с 01.10.2026). Для домов с электроотоплением "
               "в отопительный период границы 3900 и 6000 кВт·ч/мес.")]

# ---------- 4. Цена выкупа
story += [para("4. Цена выкупа излишков", "h1"),
          para("<b>Факт.</b> ТНС энерго Кубань ежемесячно публикует объём и средневзвешенную цену покупки электроэнергии "
               "у владельцев микрогенерации (п. 52в Стандартов раскрытия, ПП РФ № 24). Собраны отчёты за январь 2024 — "
               f"{last_name} {last[:4]}: средняя цена <b>{ru(w24)} ₽/кВт·ч в 2024 г.</b>, <b>{ru(w25)} ₽ в 2025 г.</b> и "
               f"<b>{ru(w26)} ₽ в 2026 г.</b> (январь–{last_name}). Цена растёт: +{100 * (w25 / w24 - 1):.0f} % в 2025 г. к 2024 г. и "
               f"+{100 * (w26 / w25_same - 1):.0f} % за январь–{last_name} 2026 г. к тому же периоду 2025 г. "
               f"Объём покупки растёт: за {n26} месяцев 2026 г. — {rub(b26.volume_total_kwh.sum() / 1000)} МВт·ч, "
               f"в {ru(b26.volume_total_kwh.sum() / b25.volume_total_kwh.sum(), 1)} раза больше, чем за весь 2025 г."),
          fig(f_buyback, "Рис. 2. Цена выкупа: факт ТНС и расчёт по тарифу владельца. Источник: отчёты ТНС энерго Кубань."),
          fig(f_volumes, "Рис. 3. Объём покупки у владельцев СЭС по месяцам и тарифам владельцев. Источник: отчёты ТНС (п. 52в Стандартов раскрытия)."),
          para("<b>Цена по тарифу владельца.</b> ТНС публикует одну среднюю цену, но правило покупки прямо записано в ОП № 442, "
               "п. 65(3): у гражданина на одноставочном тарифе — по средневзвешенной нерегулируемой цене 1-й ценовой категории, "
               "у гражданина на тарифе по зонам суток — по той же цене по зонам суток (2-я категория). Это оптовая цена: цена "
               "энергии на рынке на сутки вперёд + цена мощности × коэффициент категории, без передачи и сбытовой надбавки. "
               "Компоненты взяты из ежемесячных отчётов ТНС «Предельные уровни нерегулируемых цен»; цена дневной зоны — оценка "
               "(дневной предельный уровень 2-й категории минус сбытовая надбавка):"),
          *bullets([f"одноставочный тариф (1-я ценовая категория) — в среднем <b>{ru(flat_avg)} ₽/кВт·ч</b> (май–сентябрь 2026);",
                    f"тариф день/ночь (2-я категория, дневная зона — солнце отдаёт энергию днём) — <b>{ru(zones_avg)} ₽/кВт·ч</b> "
                    "(май–сентябрь 2026);",
                    "сезонность (оценка по сезонному индексу средней цены ТНС за 2024–2026 гг.): дороже всего в ноябре "
                    f"({ru(bmf[11])} / {ru(bmz[11])} ₽), дешевле всего в мае–июне (май {ru(bmf[5])} / {ru(bmz[5])} ₽)."]),
          fig(f_check, "Рис. 4. Проверка: если взвесить расчётные цены по объёмам из отчёта ТНС, получается опубликованная "
                       f"средняя цена с ошибкой +{ru(chk.error_pct.min(), 1)}…+{ru(chk.error_pct.max(), 1)} %.", width=W * 0.75),
          para(f"<b>Проверка на новых данных.</b> Цены по категориям за сентябрь 2026 г. ({ru(float(sep.flat_rub_kwh.iloc[0]))} и "
               f"{ru(float(sep.zones_day_rub_kwh.iloc[0]))} ₽) мы рассчитали по отчёту «Предельные уровни» до того, как ТНС "
               f"опубликовала отчёт о покупке за сентябрь. Когда он вышел ({ru(float(sep.observed_avg_rub_kwh.iloc[0]))} ₽), мы "
               f"взвесили наши цены по его объёмам и получили {ru(float(sep.predicted_avg_rub_kwh.iloc[0]))} ₽ (ошибка "
               f"+{ru(float(sep.error_pct.iloc[0]), 1)} %). Сентябрь не использовался при разработке методики, так что это "
               "проверка на новых данных.") if len(sep) else Spacer(1, 1),
          para("<b>Что это значит.</b> Тезис «излишки продаются намного дешевле» верен для одноставочного городского тарифа "
               f"({ru(flat_avg)} против 8,31 ₽: выкуп — {100 * flat_avg / 8.31:.0f} % тарифа). Для тарифа день/ночь выкуп близок к тарифу, "
               f"а у сельского дома ({ru(zones_avg)} против 6,54 ₽ днём) — даже выше. Правило цены подтверждено текстом ОП № 442; "
               "составляющие цены в отчётах ТНС подписаны «без НДС», и наш расчёт сходится с публикуемой средней ценой — значит, "
               "цена выкупа указана без НДС (гражданин не плательщик НДС, начислений сверху не ожидается; подтвердить у ТНС).", "note")]

# ---------- 5. Методика
story += [para("5. Методика экономической модели", "h1"),
          para("<b>Формула ТЗ:</b> годовой эффект = самопотребление × тариф + излишки × цена выкупа; простой срок окупаемости = "
               "капзатраты / годовой эффект."),
          para("<b>Уточнения модели</b> (src/econ/model.py), расчёт по месяцам:"),
          *bullets(["экономия = счёт за электроэнергию без СЭС − счёт с СЭС (с учётом диапазонов тарифа и зон суток);",
                    "излишки каждого месяца × цена выкупа этого месяца и тарифа владельца;",
                    "дисконтированный срок: рост тарифа и цены выкупа по годам (индексация с 1 июля), деградация панелей, "
                    "замена инвертора, НДФЛ с дохода от излишков после окончания льготы, ставка дисконтирования по годам."]),
          fig(f_ranges, "Рис. 5. Учёт диапазонов: у дома с большим потреблением СЭС «срезает» самые дорогие кВт·ч "
                        "II–III диапазонов, и эффект заметно выше формулы ТЗ.", width=W * 0.75),
          para("Сценарий: расчёт объёмов по итогам месяца (ОП № 442, п. 63(1))", "h2"),
          para("Формула ТЗ и наша модель считают, что всё отданное в сеть продаётся по цене выкупа. В п. 63(1) ОП № 442 для "
               "граждан записан другой порядок: объёмы определяются <b>по итогам расчётного периода (месяца)</b>. Владелец оплачивает только то, на что "
               "покупка из сети превысила выдачу в сеть, и продаёт только остаток выдачи сверх покупки. На тарифе день/ночь зачёт "
               "идёт отдельно по зонам; СЭС отдаёт энергию днём, поэтому она зачитывается против дневной покупки. Получается, что "
               "отданная днём энергия возвращается вечером «по тарифу», а по цене выкупа продаётся только месячный излишек."),
          para("<b>Основной вариант расчёта в отчёте — помесячная модель без зачёта</b> (уточнение формулы ТЗ): по нему "
               "построены все таблицы и рисунки, кроме подраздела «Сценарий» в разделе 7. Зачёт посчитан как сценарий — функция "
               "annual_effect_monthly_net() (src/econ/model.py), прежние функции не менялись. Применяет ли ТНС энерго Кубань "
               "этот порядок на практике, нужно подтвердить; какой вариант станет основным в итоговых расчётах, решим с "
               "наставником.", "note"),
          para("Параметры (полный реестр — docs/assumptions.md):", "h2")]
story.append(table([
    ["Параметр", "Значение", "Источник"],
    ["Рост тарифа населения", "+14,4 % (2027), +12,1 % (2028), +10,1 % (2029), далее 4 %", "Прогноз МЭР, одобрен Правительством 24.09.2026; цель ЦБ по инфляции"],
    ["Рост цены выкупа", "+10,4 %, +7,4 %, +7,0 %, далее 4 %", "Косвенная оценка: прогноз МЭР роста оптовых цен на газ"],
    ["Ставка дисконтирования", "11,5 % (2027), 8,5 % (2028), 8 % (2029+)", "Прогноз средней ключевой ставки Банка России"],
    ["Выработка 1 кВт", f"Краснодар {sum(kr.values()):.0f}, Майкоп {sum(mk.values()):.0f} кВт·ч/год", "PVGIS-SARAH3 2005–2023, наклон 30°, юг (как у команды 1)"],
    ["Деградация панелей", "1 % в 1-й год, далее 0,4 %/год", "Линейная гарантия производителей (TOPCon)"],
    ["Срок службы / инвертор", "25 лет; замена инвертора на 12-й год по цене инвертора нужной мощности", "Допущение (срок); цены инверторов 2026"],
    ["НДФЛ с излишков", "0 % по 2028 г. включительно, 13 % с 2029 г.", "459-ФЗ (п. 28.1 ст. 217 НК РФ), ст. 224 НК РФ"],
    ["Капзатраты (база)", f"3 кВт — {rub(CAPEX[3])}, 5 кВт — {rub(CAPEX[5])}, 10 кВт — {rub(CAPEX[10])} ₽", "КП установщиков Краснодара + плата за подключение; диапазон — раздел 6"],
    ["Плата за подключение", f"{rub(GRID[5])} ₽ (до {rub(GRID_MAX[3])} / {rub(GRID_MAX[5])} / {rub(GRID_MAX[10])} ₽ для 3/5/10 кВт)", "Приказ ДГРТ № 19/2025-э: меньшая из сумм — ставка С1 (выдача техусловий и проверка их выполнения) с НДС или 11 470 ₽/кВт"],
], [0.25, 0.38, 0.37]))
story += [fig(f_pv, "Рис. 6. Сезонность выработки СЭС. Источник: PVGIS (Европейская комиссия, JRC).")]

# ---------- 6. Капзатраты
cap = pd.read_csv(DATA / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw")
kp = pd.read_csv(DATA / "kp_responses.csv", encoding="utf-8-sig")
kp_grid = kp[kp.inverter_type.str.startswith("on-grid")]          # сетевые станции — предмет проекта
kp_hybrid = kp[~kp.inverter_type.str.startswith("on-grid")]       # гибридные с аккумуляторами — вне рамок MVP
story += [para("6. Капитальные затраты на СЭС «под ключ»", "h1"),
          para("Опубликованных цен «под ключ» у установщиков Краснодара нет, поэтому мы запросили коммерческие предложения "
               f"(КП). Открытые КП прислали {kp_grid.company.nunique()} компании: {', '.join(sorted(kp_grid.company.unique()))}. "
               "С 03.11.2026 базовая стоимость станции в модели считается по этим КП:"),
          *bullets(["<b>База</b> — цена ватта сетевой станции «под ключ» у каждой компании (между её собственными КП — "
                    "интерполяция по мощности), среднее по компаниям × мощность + плата за подключение (её нет ни в одном КП). "
                    "Если компания дала только комплект без монтажа, монтаж добавлен как 20 % комплекта (сама компания назвала 15–25 %);",
                    "<b>Нижняя граница</b> — то же, но минимум по компаниям и монтаж 15 %;",
                    "<b>Верхняя граница</b> — прежняя оценка до 03.11: комплект краснодарского продавца из каталога + монтаж, защита, "
                    "подключение и доставка. По КП она оказалась выше рынка на 20–50 %;",
                    "<b>Для справки</b> (в модель не идут): сумма цен компонентов по рознице и опубликованные общероссийские цены "
                    "«под ключ» с платой за подключение."]),
          fig(ROOT / "results" / "capex_estimate.png", "Рис. 7. Капзатраты сетевой СЭС с платой за подключение: КП установщиков "
                                                      "(низ и база), прежняя оценка (верх), компоненты и опубликованные цены — для справки. "
                                                      "Источники: data/kp_responses.csv, capex_components.csv, equipment_offers.csv, turnkey_prices.csv.")]
cap_rows = [["Мощность", "Низ: минимум по КП", "База (в модели)", "Верх: прежняя оценка", "База, ₽ за кВт", "КП в базе",
             "Инвертор (замена)"]]
for kw, r in cap.iterrows():
    cap_rows.append([f"{kw} кВт", rub(r.capex_low_rub), f"<b>{rub(r.capex_base_rub)}</b>", rub(r.capex_high_rub),
                     rub(r.base_rub_per_kw), f"{int(r.kp_companies)}", rub(r.inverter_rub)])
story += [table(cap_rows, [0.12, 0.15, 0.15, 0.16, 0.14, 0.1, 0.18]),
          tcap("Капзатраты, ₽, с платой за подключение. «КП в базе» — сколько компаний дали КП на близкую мощность."),
          para(f"<b>Разброс оценок:</b> нижняя граница ниже базы на {cap_lo.min():.0f}–{cap_lo.max():.0f} %, верхняя выше на "
               f"{cap_hi.min():.0f}–{cap_hi.max():.0f} %. Обе границы используются в анализе чувствительности. Для 3 и 5 кВт база "
               "опирается на одну компанию, поэтому её стоит уточнить, когда придут другие КП. Прибор учёта ставит сетевая "
               "организация.", "note"),
          para("Плата за подключение к сети", "h2"),
          para("По приказу ДГРТ Краснодарского края от 24.12.2025 № 19/2025-э (п. 1; действует с 01.01.2026, в ред. приказа от "
               "06.05.2026 № 10/2026-э) плата за подключение микрогенерации физлица — при мощности до 15 кВт с учётом ранее "
               "присоединённой, сети 0,4 кВ и расстоянии до сети не более 300 м в городе и 500 м на селе — <b>меньшая из двух "
               "сумм</b>: стоимость по стандартизированным ставкам или "
               "<b>11 470 ₽ за 1 кВт</b> запрашиваемой мощности с НДС. Дом уже подключён, строить сеть не нужно, поэтому по ставкам "
               f"остаётся С1 (выдача техусловий и проверка их выполнения): 17 363,37 ₽ без НДС, <b>{rub(GRID[5])} ₽</b> с НДС 22 % "
               "(ст. 164 НК РФ в ред. Федерального закона от 28.11.2025 № 425-ФЗ). "
               "Это значение заложено в базу для всех мощностей. Ставка С8 на прибор учёта в открытой части приказа не найдена; если "
               "счётчик меняют за счёт владельца, плата вырастет, но не выше "
               f"{rub(GRID_MAX[3])} ₽ для 3 кВт, {rub(GRID_MAX[5])} ₽ для 5 кВт и {rub(GRID_MAX[10])} ₽ для 10 кВт (11 470 ₽ × кВт). "
               "Экопроект-Энерго назвал платёж за подключение порядка 70–77 тыс. ₽ — больше предельной суммы по приказу для станций "
               f"до 6 кВт ({rub(11470 * 6)} ₽), из чего он складывается, компания не пояснила.", "note")]

# --- коммерческие предложения (data/kp_responses.csv): только открытые КП, только сетевые станции
kp_rows = [["Компания", "Станция", "Что в цене", "Цена, ₽", "₽ за кВт"]]
for _, r in kp_grid.sort_values(["company", "pv_kw"]).iterrows():
    if pd.notna(r.price_total_rub):
        what, price = "«под ключ»", r.price_total_rub
    else:
        what, price = "комплект без монтажа", r.price_equipment_rub
    kp_rows.append([r.company, f"{r.pv_kw:g} кВт", what, rub(price), rub(price / r.pv_kw)])
story += [para("Коммерческие предложения", "h2"),
          table(kp_rows, [0.26, 0.14, 0.24, 0.18, 0.18]),
          tcap("Открытые КП сетевых станций, без платы за подключение. Даты ответов — "
               f"{', '.join(d.strftime('%d.%m.%Y') for d in sorted(pd.to_datetime(kp_grid.date_collected).unique()))}."
               + (f" Предложения гибридных станций с аккумуляторами ({len(kp_hybrid)}) в расчёт не входят: это вне рамок проекта."
                  if len(kp_hybrid) else ""))]

# сверка КП с диапазоном капзатрат (T1.7): КП на мощности из модели + плата за подключение (её нет ни в одном КП);
# комплект без монтажа — с монтажом 15–25 % (диапазон, названный компанией)
kp_check = []
for _, r in kp_grid[kp_grid.pv_kw.isin(cap.index)].sort_values(["pv_kw", "company"]).iterrows():
    kw = int(r.pv_kw)
    if pd.notna(r.price_total_rub):
        lo = hi = r.price_total_rub + GRID[kw]
        what = "«под ключ»"
    else:
        lo, hi = r.price_equipment_rub * 1.15 + GRID[kw], r.price_equipment_rub * 1.25 + GRID[kw]
        what = "комплект + монтаж 15–25 %"
    inside = cap.capex_low_rub[kw] <= lo and hi <= cap.capex_high_rub[kw]
    price = rub(lo) if lo == hi else f"{rub(lo)}–{rub(hi)}"
    kp_check.append(f"{r.company}, {kw} кВт ({what}): {price} ₽ с подключением — "
                    + ("в диапазоне" if inside else "<b>вне диапазона</b>")
                    + f" {rub(cap.capex_low_rub[kw])}–{rub(cap.capex_high_rub[kw])} ₽")
story += [para("<b>Сверка КП с диапазоном капзатрат.</b> " + "; ".join(kp_check) + ". База сама построена по этим КП, "
               "поэтому сверка показывает прежде всего, что верхняя граница (прежняя оценка) не ниже рыночных цен. КП на другие "
               "мощности (6 и 15 кВт) напрямую не сравниваются — их учитывает интерполяция цены ватта.", "note")]

# ---------- 7. Результаты
pc = lambda x: f"{int(x + 0.5)}"
prc = lambda s: (pc(min(s)) if pc(min(s)) == pc(max(s)) else f"{pc(min(s))}–{pc(max(s))}")
story += [para("7. Предварительные результаты", "h1"),
          para("Условный дом: потребление 6000 кВт·ч/год (500 кВт·ч/мес, равномерно), ночная зона 30 %, Краснодар. "
               "Доля самопотребления задана условно (20–80 %) до получения профилей команды 1; для 5 кВт доли выше 50 %, "
               "а для 10 кВт выше 20 % недостижимы — дом столько днём не потребляет. Все результаты раздела, кроме "
               "подраздела «Сценарий», — основной вариант: помесячная модель без зачёта."),
          fig(f_heat, "Рис. 8. СЭС 5 кВт: простой и дисконтированный срок окупаемости в зависимости от доли "
                      "самопотребления и тарифа (зелёный — быстрее, красный — дольше; «не окуп.» — не окупается за 25 лет).")]
res_rows = [["Тариф", "Простой срок, лет", "Простой срок при капзатратах низ…верх, лет", "Дисконт. срок, лет", "Доля излишков, %"]]
for plan in PLANS:
    d = p5[p5.tariff == plan.name]
    res_rows.append([plan.name, yrs(d.simple_payback),
                     f"{ru(d.simple_payback_low.min(), 1)}–{ru(d.simple_payback_high.max(), 1)}",
                     yrs(d.disc_payback), prc(d.export_share_pct)])
story += [table(res_rows, [0.24, 0.16, 0.2, 0.22, 0.18]),
          tcap("СЭС 5 кВт, основной вариант; диапазон по долям самопотребления 20–50 %."),
          fig(f_cash, "Рис. 9. Накопленный дисконтированный денежный поток СЭС 5 кВт при самопотреблении 40 %; точка "
                      "пересечения с нулём — дисконтированный срок окупаемости."),
          fig(f_hyp, "Рис. 10. Доля дохода от излишков в годовом эффекте, СЭС 3 кВт — самый благоприятный для части Б случай "
                     "(у 5 и 10 кВт доли выше). Точки ниже красной линии — сочетания с долей не больше 20 %; для подтверждения "
                     "части Б таких должно быть не менее 80 %.")]

# --- данные команды 1 (03.11.2026, по годам PVGIS): помесячная модель через единую точку входа src/econ/api.py
from src.econ.api import evaluate as api_evaluate  # noqa: E402
from src.econ.exchange import MonthlyMetrics  # noqa: E402

HEATING_RANGES = ("reduced_heating", "reduced_heating_nostove")   # диапазоны дома с электроотоплением
t1_records = read_csv(DATA / "energy_metrics_monthly.csv", MonthlyMetrics)
t1_combos = {}
for r in t1_records:
    t1_combos.setdefault((r.profile_id, r.city, int(r.pv_kw)), []).append(r)
t1rows = []
for (prof, city, kw), ms in sorted(t1_combos.items()):
    ms = sorted(ms, key=lambda x: x.month)
    # дом с электроотоплением и в городе платит по пониженному тарифу, с диапазонами отопительного периода
    plans = ([TariffPlan(pl.name, pl.price_category, pl.tariff_type, HEATING_RANGES)
              for pl in PLANS if pl.price_category == "reduced"] if prof == "el_heating" else PLANS)
    for plan in plans:
        res = {lvl: api_evaluate(ms, plan, kw, capex_level=lvl) for lvl in ("low", "base", "high")}
        net = api_evaluate(ms, plan, kw, netting=True)
        b = res["base"]
        t1rows.append({"profile": prof, "city": city, "pv_kw": kw, "tariff": plan.name, "self_share": b.self_share,
                       "coverage": b.coverage, "load": sum(m.load_kwh for m in ms), "share": b.export_share,
                       "disc": b.disc_payback, "simple_low": res["low"].simple_payback, "simple_base": b.simple_payback,
                       "simple_high": res["high"].simple_payback, "share_net": net.export_share,
                       "simple_net": net.simple_payback})
t1 = pd.DataFrame(t1rows)
t1["simple"] = t1.simple_base
t1_check = pd.read_csv(ROOT / "results" / "team1_yearwise_check.csv", encoding="utf-8-sig")
t1_hyp = pd.read_csv(ROOT / "results" / "team1_hypothesis_by_years.csv", encoding="utf-8-sig")

# часть А: насколько меняется простой срок, если менять один фактор при прочих равных
FACT_KEYS = ["profile", "city", "pv_kw", "tariff"]


def spread(df, factor):
    others = [k for k in FACT_KEYS if k != factor]
    r = df.groupby(others).simple.agg(lambda s: s.max() - s.min() if len(s) > 1 else np.nan).dropna()
    return r.median(), r.max()


fac = [(k, name, *spread(t1, k)) for k, name in [
    ("tariff", "тариф"), ("profile", "портрет потребления (доля самопотребления)"),
    ("pv_kw", "мощность СЭС"), ("city", "город")]]
cxr = t1.simple_high - t1.simple_low
fac.append(("capex", "стоимость станции", cxr.median(), cxr.max()))
fac.sort(key=lambda f: -f[2])
# критерий части А (T3.4, решение от 22.10): в торнадо T3.1 по простому сроку два первых места — тариф и доля
# самопотребления хотя бы у 3 тарифов из 4; параметры с равным (до 0,1 года) размахом делят место
sens = pd.read_csv(ROOT / "results" / "sensitivity.csv", encoding="utf-8-sig")
SENS_NAMES = {"Капзатраты": "стоимость станции", "Цена выкупа, сценарий ТНС ×0,5": "сценарий «выкуп вдвое дешевле»",
              "Тариф": "тариф", "Доля самопотребления": "доля самопотребления"}


def sens_places(param):
    """Места параметра по размаху простого срока по 4 тарифам с учётом деления мест: (от, до)."""
    lo, hi = [], []
    for _, g in sens.groupby("tariff"):
        v = float(g.loc[g.parameter == param, "swing_simple"].iloc[0])
        lo.append(1 + int((g.swing_simple > v).sum()))
        hi.append(int((g.swing_simple >= v).sum()))
    return min(lo), max(hi)


sens_top2 = {t: set(g.nlargest(2, "swing_simple", keep="all").parameter) for t, g in sens.groupby("tariff")}
n_sens_ok = sum(s == {"Тариф", "Доля самопотребления"} for s in sens_top2.values())
part_a_ok = n_sens_ok >= 3
part_a = "подтверждается" if part_a_ok else "не подтверждается"
sens_leaders = sorted(set().union(*sens_top2.values()) - {"Тариф", "Доля самопотребления"})
tariff_pl, share_pl = sens_places("Тариф"), sens_places("Доля самопотребления")


def pl(a):
    return f"{a[0]}-м" if a[0] == a[1] else f"{a[0]}–{a[1]}-м"
prof_med = next(f[2] for f in fac if f[0] == "profile")
rz_corr = np.nanmedian([g.self_share.corr(g.simple) for _, g in t1[t1.tariff == "Село, день/ночь"].groupby(["pv_kw", "city"])])

# часть Б
n_ok, n_all = int((t1.share <= HYP_LIMIT).sum()), len(t1)
part_b_ok = 100 * n_ok / n_all >= HYP_SHARE


t1_rows = [["Тариф", "Простой срок, лет", "Дисконт. срок, лет", "Доля излишков, %", f"Доля ≤ {HYP_LIMIT} %"]]
for plan in PLANS:
    d = t1[t1.tariff == plan.name]
    t1_rows.append([plan.name, yrs(d.simple), yrs(d.disc), prc(d.share), f"{int((d.share <= HYP_LIMIT).sum())} из {len(d)}"])
fa_rows = [["Фактор (меняется один, остальные те же)", "Размах простого срока: медиана, лет", "Максимум, лет"]]
fa_rows += [[name[0].upper() + name[1:] + (" (от нижней границы до верхней)" if k == "capex" else ""), ru(med, 1), ru(mx, 1)]
            for k, name, med, mx in fac]
story += [para("Расчёт на данных команды 1", "h2"),
          para(f"Команда 1 передала файлы 03.11.2026 (data/energy_metrics.csv, data/energy_metrics_monthly.csv): "
               f"{t1.profile.nunique()} портрета потребления × 2 города × 3 мощности, выработка — PVGIS-SARAH3 за "
               "2005–2023 годы, наклон 30°, юг, потери 14 %. Самопотребление посчитано по каждому из 19 лет отдельно, "
               "потом помесячные объёмы усреднены. Файлы соответствуют формату обмена (протокол проверки № 4 — "
               "docs/team1_data_check.md). Расчёт — основной вариант помесячной модели: диапазоны тарифа, сезонность цены "
               "выкупа, без зачёта; капзатраты — база раздела 6. Дом с электроотоплением и в городе платит по пониженному "
               "тарифу с диапазонами отопительного периода, поэтому этот портрет посчитан только на «сельских» тарифах."),
          para("<b>Оговорка.</b> Почасовая нагрузка у команды 1 сценарная, а не измеренная; сверка с реальными семьями — "
               "к финальным данным. Первая версия файлов (02.11) была посчитана по «типичному году» — каждый час усреднён "
               "по 19 годам, без пасмурных и ясных дней, — и завышала долю самопотребления на "
               f"{ru(t1_check.typical_bias_pp.min(), 1)}–{ru(t1_check.typical_bias_pp.max(), 1)} п. п.; по нашей просьбе "
               "команда 1 пересчитала по годам. Наш независимый пересчёт по исходным рядам PVGIS совпал с файлами "
               "(расхождение помесячных объёмов — меньше одной миллионной кВт·ч; "
               "scripts/check_team1_data.py).", "note"),
          table(t1_rows, [0.24, 0.17, 0.25, 0.16, 0.18]),
          tcap(f"Данные команды 1 от 03.11.2026, основной вариант; всего сочетаний «портрет × город × мощность × тариф»: {n_all}."),
          para("Чтобы предварительно проверить часть А, мы меняли по одному фактору при прочих равных и смотрели, насколько "
               "меняется простой срок. Стоимость станции менялась от нижней границы (минимум по КП) до верхней (прежняя база)."),
          table(fa_rows, [0.5, 0.28, 0.22]),
          tcap("Предварительная проверка части А на данных команды 1. Размах — разница между самым коротким и самым "
               "длинным сроком при смене одного фактора; медиана — по всем сочетаниям остальных факторов."),
          para(f"<b>Гипотеза команды 1.</b> При одинаковом потреблении {rub(t1_hyp.equal_annual_load_kwh.iloc[0])} кВт·ч в год "
               "доля самопотребления у портрета «кто-то дома весь день» выше, чем у «днём никого нет», в "
               f"{ru(t1_hyp.ratio_team1.min(), 2)}–{ru(t1_hyp.ratio_team1.max(), 2)} раза в среднем по 19 годам — то есть "
               "не меньше 1,5 во всех шести сочетаниях города и мощности; наш пересчёт дал те же числа. Запас небольшой: "
               f"в отдельные годы отношение опускается до {ru(t1_hyp.ratio_min_year.min(), 3)} (Краснодар, 10 кВт). "
               "Окончательный вывод — за командой 1.")]

# --- сценарий с помесячным зачётом
story += [para("Сценарий: помесячный зачёт (п. 63(1) ОП № 442)", "h2"),
          para("Если ТНС применяет порядок п. 63(1), отданная в сеть энергия сначала зачитывается против покупки того же "
               "месяца по тарифу, а по цене выкупа продаётся только остаток. Ниже — тот же условный дом."),
          fig(f_net, "Рис. 11. Простой срок окупаемости при самопотреблении 20 %: основной вариант (сплошная заливка) и "
                     "сценарий с помесячным зачётом (штриховка). Г — город, С — село, 1 ст. — одноставочный тариф, д/н — день/ночь.")]
net_rows = [["Мощность", "Тариф", "Срок: основной вариант, лет", "Срок: сценарий, лет", "Доля проданного остатка, %",
             "Доля всей выданной в сеть энергии, %"]]
for kw in (3, 5, 10):
    for plan in PLANS:
        d = pay[(pay.pv_kw == kw) & (pay.tariff == plan.name)]
        full = 100 * (d.effect_net_rub - d.self_rub) / d.effect_net_rub
        net_rows.append([f"{kw} кВт", plan.name, yrs(d.simple_payback), ru(d.simple_payback_net.iloc[0], 1),
                         pc(d.export_share_net_pct.iloc[0]), prc(full)])
story += [table(net_rows, [0.12, 0.21, 0.16, 0.13, 0.18, 0.2]),
          tcap("Сценарий с зачётом, условный дом 6000 кВт·ч/год. Доля проданного остатка — доход от продажи по цене выкупа; "
               "доля всей выданной энергии — вклад всей отданной в сеть энергии, и проданной, и зачтённой по тарифу. С зачётом "
               "срок не зависит от доли самопотребления: месячная покупка равна разнице потребления и выработки, как бы "
               "выработка ни делилась на самопотребление и выдачу.")]

# --- выводы считаются из результатов, чтобы цифры не расходились с таблицами при пересчёте
pv5 = p5.pivot_table(index="self_share_target", columns="tariff", values="simple_payback")
gain_city = pv5["Город, одноставочный"] - pv5["Город, день/ночь"]
gain_rural = pv5["Село, одноставочный"] - pv5["Село, день/ночь"]
rs = p5[p5.tariff == "Село, одноставочный"]
c1 = pay[(pay.tariff == "Город, одноставочный") & (pay.pv_kw.isin([3, 5]))]
cz = pay[(pay.tariff == "Город, день/ночь") & (pay.pv_kw.isin([3, 5]))]
net_gap = c1.groupby("pv_kw").simple_payback_net.first() - cz.groupby("pv_kw").simple_payback_net.first()
rz = pay[pay.tariff == "Село, день/ночь"]
ranges_gain = 100 * (mon[1] / tz[1] - 1)
stub_cnt = pay.assign(ok=pay.export_share_pct <= HYP_LIMIT).groupby("pv_kw").ok.agg(["sum", "size"])
net_cnt = (pay.drop_duplicates(["pv_kw", "tariff"]).assign(ok=lambda d: d.export_share_net_pct <= HYP_LIMIT)
           .groupby("pv_kw").ok.agg(["sum", "size"]))
n_full = int((100 * (pay.effect_net_rub - pay.self_rub) / pay.effect_net_rub <= HYP_LIMIT).sum())
cnt_txt = lambda c: ", ".join(f"{kw} кВт — {int(r['sum'])} из {int(r['size'])}" for kw, r in c.iterrows())
# порог доли самопотребления, при котором доля излишков ≤ 20 % (формула ТЗ): s ≥ b / (b + t · 20/80)
thr = []
for plan in PLANS:
    b = flat_avg if plan.owner_category == "flat" else zones_avg
    thr.append(100 * b / (b + zone_prices(plan)["I"]["day"] * HYP_LIMIT / (100 - HYP_LIMIT)))
if part_b_ok and part_a_ok:
    verdict = "подтверждается"
elif part_b_ok or part_a_ok:
    verdict = "подтверждается частично"
else:
    verdict = "не подтверждается"
net_ok = 100 * net_cnt["sum"].sum() / net_cnt["size"].sum() >= HYP_SHARE

story += [para("Предварительные выводы", "h2"),
          *bullets([f"<b>Тариф день/ночь сокращает срок окупаемости</b> СЭС 5 кВт на {ru(gain_city.min(), 1)}–{ru(gain_city.max(), 1)} "
                    f"года в городе и на {ru(gain_rural.min(), 1)}–{ru(gain_rural.max(), 1)} года на селе по сравнению с "
                    "одноставочным: солнце замещает дорогую дневную энергию, а излишки выкупаются по более высокой цене "
                    "дневной зоны.",
                    "<b>Сельский одноставочный тариф — самый невыгодный</b> (ниже тариф — меньше экономия): простой срок СЭС 5 кВт — "
                    f"{yrs(rs.simple_payback)} года, дисконтированный — {yrs(rs.disc_payback)} года.",
                    f"<b>Учёт диапазонов тарифа важен</b> для домов с большим потреблением: у дома 18{NB}000 кВт·ч/год с СЭС 10 кВт "
                    f"эффект на {ranges_gain:.0f} % выше формулы ТЗ."]),
          para("Проверка гипотезы 2 (предварительно)", "h2"),
          *bullets([f"<b>Часть А {part_a}.</b> В торнадо T3.1 (прототип от 02.11.2026: СЭС 5 кВт, Краснодар, условный "
                    "профиль 6000 кВт·ч в год) тариф и доля самопотребления "
                    + (f"занимают два первых места по простому сроку у {n_sens_ok} {'тарифа' if n_sens_ok == 1 else 'тарифов'} из 4"
                       if n_sens_ok else "не занимают двух первых мест по простому сроку ни у одного из 4 тарифов")
                    + " (нужно не меньше 3)"
                    + (f": первые места занимают {' и '.join(SENS_NAMES.get(s, s.lower()) for s in sens_leaders)}"
                       if sens_leaders else "")
                    + f", тариф — на {pl(tariff_pl)} месте, доля самопотребления — на {pl(share_pl)} "
                    "(docs/hypothesis2.md). На данных команды 1 "
                    + ("доля самопотребления тоже не входит в два главных фактора: "
                       if not part_a_ok and "profile" not in {f[0] for f in fac[:2]} else "")
                    + f"сильнее всего срок меняют {fac[0][1]} (в медиане "
                    f"{ru(fac[0][2], 1)} года) и {fac[1][1]} ({ru(fac[1][2], 1)} года), "
                    "а смена портрета потребления (доли самопотребления) меняет срок в медиане на "
                    f"{ru(prof_med, 1)} года"
                    + (". На сельском тарифе день/ночь связь даже обратная: чем больше дом потребляет сам, тем дольше "
                       "окупается станция, потому что цена выкупа там выше дневного тарифа" if rz_corr > 0 else "")
                    + ". Финальная проверка — торнадо T3.1 на данных команды 1.",
                    f"<b>Часть Б {'подтверждается' if part_b_ok else 'не подтверждается'}.</b> Доля излишков не больше "
                    f"{HYP_LIMIT} % — в {n_ok} из {n_all} сочетаний на данных команды 1 (нужно не менее {HYP_SHARE} %). "
                    f"На условных профилях таких сочетаний «доля самопотребления × тариф»: {cnt_txt(stub_cnt)}. Чтобы доля "
                    f"излишков была не больше {HYP_LIMIT} %, дом должен сам потреблять не меньше {min(thr):.0f}–{max(thr):.0f} % "
                    f"выработки (зависит от тарифа), а у портретов команды 1 самопотребление не выше {t1.self_share.max():.0f} %.",
                    f"<b>Итог: по предварительным данным гипотеза 2 {verdict}.</b> Обе части упираются в одну причину: цена "
                    f"выкупа близка к тарифу — {100 * flat_avg / zone_prices(PLANS[0])['I']['day']:.0f} % городского "
                    f"одноставочного тарифа и {100 * zones_avg / zone_prices(PLANS[1])['I']['day']:.0f} % дневного на тарифе "
                    "день/ночь. Поэтому почти неважно, потребит дом энергию сам или продаст её, а излишки дают большую часть "
                    "эффекта. Окончательный вывод — на финальных помесячных данных команды 1 и после ответа ТНС о зачёте.",
                    "<b>Сценарий с помесячным зачётом</b> (если ТНС его применяет) меняет картину. Доля самопотребления перестаёт "
                    f"влиять совсем; городской одноставочный тариф (3–5 кВт) окупается за {ru(c1.simple_payback_net.min(), 1)}–"
                    f"{ru(c1.simple_payback_net.max(), 1)} года вместо {ru(c1.simple_payback.min(), 1)}–{ru(c1.simple_payback.max(), 1)}, "
                    f"разрыв с городским тарифом день/ночь — {ru(net_gap.min(), 1)}–{ru(net_gap.max(), 1)} года. На селе с тарифом "
                    f"день/ночь зачёт невыгоден ({ru(rz.simple_payback.min(), 1)}–{ru(rz.simple_payback.max(), 1)} → "
                    f"{ru(rz.simple_payback_net.min(), 1)}–{ru(rz.simple_payback_net.max(), 1)} года): цена выкупа там выше "
                    f"дневного тарифа. Для части Б доля проданного остатка не больше {HYP_LIMIT} % в {int(net_cnt['sum'].sum())} из "
                    f"{int(net_cnt['size'].sum())} сочетаний «тариф × мощность» ({cnt_txt(net_cnt)}); если считать всю отданную "
                    f"в сеть энергию — в {n_full} из {len(pay)} строк условного расчёта. "
                    + ("Критерий части Б в этом сценарии выполняется." if net_ok else
                       "Критерий части Б не выполняется и в этом сценарии.")]),
          PageBreak()]

# ---------- 8. Ограничения и планы
story += [para("8. Ограничения, открытые вопросы и дальнейшие шаги", "h1"),
          para("Ограничения текущих расчётов", "h2"),
          *bullets(["Расчёт на условных профилях и на данных команды 1 от 03.11.2026 (по годам PVGIS). Нагрузка команды 1 "
                    "сценарная, со сверкой по реальным семьям — к финальным данным до 04.12.2026.",
                    f"Капзатраты — по открытым КП {kp_grid.company.nunique()} установщиков, для 3 и 5 кВт — по одной компании (разброс {CAP_SPREAD}); диапазон — в чувствительности.",
                    "Часть А гипотезы проверена предварительно — по прототипу торнадо на условном профиле и разбросу срока "
                    "на данных команды 1; финально — по торнадо T3.1 на данных команды 1.",
                    "Цена выкупа по тарифу владельца — правило из ОП № 442 (п. 65(3)), значения рассчитаны по открытым отчётам ТНС "
                    "(сверка +1…2 %, в том числе на сентябре, которого не было при разработке методики); цена — без НДС, как в отчётах ТНС.",
                    "Цена выкупа рассчитана по данным ТНС энерго Кубань; в зоне АО «НЭСК» её определяет НЭСК.",
                    "Помесячный зачёт (п. 63(1)) записан в ОП, но его применение ТНС энерго Кубань на практике не подтверждено; "
                    "от этого зависят выбор основного варианта модели и вывод по обеим частям гипотезы 2.",
                    "Плата за подключение — по приказу ДГРТ; ставка С8 на прибор учёта не найдена (верхняя граница — 11 470 ₽ × кВт).",
                    "Рост цены выкупа — косвенная оценка (прогноз цен на газ), официального прогноза оптовой цены нет.",
                    "Не учтены: трёхзонный тариф, аккумуляторы."]),
          para("Дальнейшие шаги", "h2")]
story.append(table([
    ["Срок", "Шаг"],
    ["до 15.11.2026", "Обращение в ТНС энерго Кубань: применяется ли помесячный зачёт, подтверждение цены выкупа без НДС; у сетевой организации — плата за счётчик; решить с наставником, какой вариант модели основной. КП на сетевую станцию 5 кВт. Промежуточный доклад (5–7 мин)"],
    ["16.11–06.12.2026", "Анализ чувствительности на 3 кВт и по зонам суток, автотесты модели, ввод портретов потребления в веб-сервисе"],
    ["07–18.12.2026", "Пересчёт на реальных профилях команды 1, тепловая карта «профиль × тариф», проверка гипотезы 2 (часть А — торнадо T3.1 до 12.12, часть Б — T3.4 до 14.12), аналитический веб-сервис"],
    ["21–25.12.2026", "Итоговый отчёт, презентация, защита"],
], [0.2, 0.8]))

SRC_LAW = [
    "Федеральный закон от 26.03.2003 № 35-ФЗ «Об электроэнергетике», ст. 3 (в ред. 471-ФЗ от 27.12.2019 и 208-ФЗ от 26.06.2026); "
    "208-ФЗ: publication.pravo.gov.ru/document/0001202606260068 (копия — docs/sources/2026-06-26_zakon_208-FZ_0001202606260068.pdf), "
    "consultant.ru/law/hotdocs/94648.html",
    "Налоговый кодекс РФ: п. 28.1 ст. 217 (в ред. 459-ФЗ от 27.12.2019, consultant.ru/document/cons_doc_LAW_341743/), ст. 224; "
    "ст. 164 (ставка НДС 22 % с 01.01.2026, Федеральный закон от 28.11.2025 № 425-ФЗ; nalog.gov.ru/rn26/news/smi/16596761/)",
    "Основные положения функционирования розничных рынков электрической энергии (ПП РФ от 04.05.2012 № 442, ред. от 06.10.2026), "
    "п. 63(1), 65(3), 79: consultant.ru/document/cons_doc_LAW_130498/ (выписка пп. 63(1) и 65(3) — docs/sources/2026-10-21_op442_p63-1_p65-3.txt); "
    "ПП РФ от 02.03.2021 № 299: base.garant.ru/400418448/",
    "Правила технологического присоединения (ПП РФ от 27.12.2004 № 861), п. 17: consultant.ru/document/cons_doc_LAW_51030/",
    "Стандарты раскрытия информации субъектами оптового и розничных рынков электрической энергии (ПП РФ от 21.01.2004 № 24), п. 52в",
    "Распоряжение Правительства РФ от 26.09.2026 № 2675-р: publication.pravo.gov.ru/document/0001202609260010 (копия — "
    "docs/sources/2026-09-26_rasporyazhenie_2675-r_0001202609260010.pdf)",
    "ПП РФ от 26.09.2026 № 1242: publication.pravo.gov.ru/document/0001202609260011 (копия — "
    "docs/sources/2026-09-26_postanovlenie_1242_0001202609260011.pdf)",
    "Приказ ДГРТ Краснодарского края от 17.12.2025 № 18/2025-э (тарифы для населения на 2026 г.) — по таблице тарифов ТНС: "
    "kuban.tns-e.ru/calculations/tariffs/tariff-table/",
    "Приказ ДГРТ Краснодарского края от 24.12.2025 № 19/2025-э (в ред. от 06.05.2026 № 10/2026-э), плата за техприсоединение: "
    "base.garant.ru/413351706/ (выписка — docs/sources/2026-10-21_prikaz_dgrt_19-2025-e_tp.txt)",
]
SRC_DATA = [
    "ПАО «ТНС энерго Кубань», раскрытие информации: объёмы и средневзвешенная цена покупки у микрогенерации — "
    "kuban.tns-e.ru/disclosure/raskrytie-informatsii-subektom-rynka-elektricheskoy-energii-moshchnosti/market-report-gp/"
    "informatsiya-ob-obemakh-i-srednevzveshennoy-tsene-pokupki-na-roznichnom-rynke-elektricheskoy-energii/; предельные уровни "
    "нерегулируемых цен — тот же раздел, страница predelnye-urovni-nereguliruemykh-tsen-…",
    "Прогноз социально-экономического развития РФ на 2027–2029 гг. (МЭР): bigpowernews.ru/news/document126870.phtml",
    "Банк России — ключевая ставка: cbr.ru/hd_base/keyrate/; прогноз средней ключевой ставки: interfax.ru/business/1105322",
    "PVGIS-SARAH3 (European Commission, JRC): re.jrc.ec.europa.eu/pvg_tools/",
    "Гарантия мощности панелей: TCL MG680 datasheet (tcl.com)",
    "Цены оборудования (data/capex_components.csv, data/equipment_offers.csv): ekoproekt-energo.ru, sv-synergy.ru, altecology.ru, "
    "krasnodar.termodar.ru, solarbreeze.ru, baikaltesla.com, shop.solarhome.ru, bobrovsolar.ru, realsolar.ru, e-solarpower.ru, "
    "nsk-electro.ru, reenergo.ru, clever-energy.ru, newpolus.ru, wind-solar.ru, one-sun.ru; стоимость монтажа: kinozadrot13.ru",
    "Опубликованные цены «под ключ» (data/turnkey_prices.csv): windsolar.pro, kinozadrot13.ru",
    "Ответы на запрос КП: Экопроект-Энерго (письмо от 20.10.2026), Умная Энергия (типовые КП от 02.11.2026) — "
    "data/kp_responses.csv, docs/kp_plan.md",
    "АО «НЭСК» (nesk.ru): отчёты «Предельные уровни нерегулируемых цен» за 01.2025–09.2026 и типовой договор с владельцем "
    "микрогенерации — data/raw/nesk_price_limits/, data/raw/nesk_microgen/",
    "Данные команды 1 от 03.11.2026 (по годам PVGIS): data/energy_metrics*.csv, почасовые ряды data/hourly_*; "
    "отчёт и исходники — docs/sources/team1/2026-11-03/ (первая версия — 2026-11-02/); протокол проверки — "
    "docs/team1_data_check.md",
    "PVGIS 5.3, почасовые ряды 2005–2023 (seriescalc, 30°, юг, 14 %) — data/raw/team1_pvgis/",
]
story += [para("Источники", "h1"), para("Нормативные акты", "h2"),
          *[para(f"{i}. {s}", "li") for i, s in enumerate(SRC_LAW, 1)],
          para("Данные", "h2"),
          *[para(f"{i}. {s}", "li") for i, s in enumerate(SRC_DATA, len(SRC_LAW) + 1)],
          para("Даты обращения к интернет-источникам — 13.10–03.11.2026.", "cap")]


doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm,
                        bottomMargin=1.7 * cm, title="SunCount — промежуточный отчёт команды 2", author="Команда 2 SunCount")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("PDF:", OUT)
