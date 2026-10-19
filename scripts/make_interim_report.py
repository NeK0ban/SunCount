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
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.econ import params as P  # noqa: E402
from src.econ.exchange import annual_from_monthly, make_stub_monthly  # noqa: E402
from src.econ.inputs import TariffPlan, buyback_monthly, pv_monthly_kwh_per_kw, zone_prices  # noqa: E402
from src.econ.model import (Scenario, Tariff, annual_effect, annual_effect_monthly, cash_flows,  # noqa: E402
                            discount_factors)

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
CAPEX = pay.groupby("pv_kw").capex_rub.first().to_dict()


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
ax.bar_label(b, fmt="%.2f", fontsize=8)
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
          color=C["red"], lw=2, label="Тариф город, одноставочный (покупка из сети)")
ax.hlines(tprice("2026-01-01", "reduced", "single", "flat"), pd.Timestamp("2026-01-01"), pd.Timestamp("2026-09-30"),
          color=C["rural"], lw=2, label="Тариф село, одноставочный")
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
ax.bar_label(bp, labels=[f"{e:+.1f} %" for e in v.error_pct], fontsize=8)
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
ax.set_title("Выработка СЭС 1 кВт по месяцам (PVGIS-SARAH3, оптимальный угол, потери 14 %)")
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
ax.text(21, 22, "порог гипотезы 2: 20 %", color=C["red"], fontsize=8)
ax.set_xlabel("Доля самопотребления, %")
ax.set_ylabel("Доля излишков в эффекте, %")
ax.set_ylim(0, 100)
ax.set_title("Проверка гипотезы 2 на условных профилях (СЭС 3 кВт)")
ax.legend(frameon=False, fontsize=8)
f_hyp = save(fig, "07_hypothesis")

# 8. Эффект диапазонов тарифа
heavy_shape = [1.6, 1.5, 1.2, 0.9, 0.8, 1.0, 1.2, 1.2, 0.9, 0.8, 1.2, 1.6]
cases = [("Дом 6 000 кВт·ч/год,\nСЭС 5 кВт", 6000, 5, None), ("Дом 18 000 кВт·ч/год,\nСЭС 10 кВт", 18000, 10, heavy_shape)]
tz, mon = [], []
for _, load, kw, shape in cases:
    ms = make_stub_monthly("x", kw, load, 60, "krasnodar", load_shape=shape)
    p_i = zone_prices(PLANS[0])["I"]["day"]
    tz.append(annual_effect(annual_from_monthly(ms), Tariff.flat("ТЗ", p_i), np.mean(list(buyback_monthly("flat").values()))).effect_rub)
    mon.append(annual_effect_monthly(ms, PLANS[0]).effect_rub)
fig, ax = plt.subplots(figsize=(6, 2.8))
xc = np.arange(2)
ax.bar(xc - 0.2, np.array(tz) / 1000, 0.4, color="#bbbbbb", label="формула ТЗ (I диапазон, средний выкуп)")
bm = ax.bar(xc + 0.2, np.array(mon) / 1000, 0.4, color=C["city"], label="помесячно: диапазоны + сезонный выкуп")
ax.bar_label(bm, labels=[f"{100 * (m / t - 1):+.0f} %" for t, m in zip(tz, mon)], fontsize=8)
ax.set_xticks(xc, [c[0] for c in cases])
ax.set_ylabel("Годовой эффект, тыс. ₽")
ax.set_title("Учёт диапазонов тарифа (город, одноставочный)")
ax.legend(frameon=False, fontsize=7, loc="upper left")
f_ranges = save(fig, "08_ranges")

fig_h, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
for ax, (col, title, vmax) in zip(axes, [("simple_payback", "Простой срок окупаемости, лет", 16),
                                         ("disc_payback", "Дисконтированный срок окупаемости, лет", 25)]):
    hp = pay[pay.pv_kw == 5].pivot_table(index="self_share_target", columns="tariff", values=col)[[pl.name for pl in PLANS]]
    ax.imshow(hp.values, cmap="RdYlGn_r", vmin=4, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(hp.columns)), [c.replace(", ", "\n") for c in hp.columns], fontsize=8)
    ax.set_yticks(range(len(hp.index)), [f"{i} %" for i in hp.index])
    ax.grid(False)
    for i in range(hp.shape[0]):
        for j in range(hp.shape[1]):
            ax.text(j, i, f"{hp.values[i, j]:.1f}".replace(".", ","), ha="center", va="center", fontsize=10)
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
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=18, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1f4e79")),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=4),
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


rub = lambda x: f"{x:,.0f}".replace(",", " ")
ru = lambda x, nd=2: f"{x:.{nd}f}".replace(".", ",")
bmf, bmz = buyback_monthly("flat"), buyback_monthly("zones")
flat_avg, zones_avg = bbc.flat_rub_kwh.mean(), bbc.zones_day_rub_kwh.mean()
b24 = bb[bb.month.str.startswith("2024")]
b25 = bb[bb.month.str.startswith("2025")]
b26 = bb[bb.month.str.startswith("2026")]
w24 = (b24.price_rub_kwh * b24.volume_total_kwh).sum() / b24.volume_total_kwh.sum()
w25 = (b25.price_rub_kwh * b25.volume_total_kwh).sum() / b25.volume_total_kwh.sum()
w26 = (b26.price_rub_kwh * b26.volume_total_kwh).sum() / b26.volume_total_kwh.sum()
p5 = pay[pay.pv_kw == 5]

story = []
# ---------- титул
story += [Spacer(1, 4.5 * cm), para("SunCount", "title"),
          para("Калькулятор окупаемости домашней солнечной электростанции<br/>для Адыгеи и Краснодарского края", "sub"),
          Spacer(1, 1 * cm),
          para("<b>Промежуточный отчёт команды 2</b><br/>Тема 2. Оценка влияния тарифов и условий микрогенерации "
               "на срок окупаемости домашней СЭС", "sub"),
          Spacer(1, 1.2 * cm), para(f"Состояние на {TODAY} · этап 1 «Погружение» (12–25 октября 2026)", "sub"),
          Spacer(1, 2.5 * cm),
          para("<b>Важно.</b> Все расчёты окупаемости в этом отчёте — <b>предварительные</b>: профили потребления пока "
               "условные (данные команды 1 ожидаются до 04.12.2026), капзатраты оценены по ценам компонентов и "
               "комплектов (точность ±15–20 %). Тарифы, цены выкупа, выработка и экономические параметры — "
               "по официальным и фактическим данным со ссылками.", "note"),
          PageBreak()]

# ---------- 1. Введение
story += [para("1. Исследовательский вопрос и задачи команды 2", "h1"),
          para("<b>Вопрос проекта:</b> как профиль потребления и тариф влияют на окупаемость домашней солнечной "
               "электростанции? По закону о микрогенерации владелец СЭС может продавать излишки в сеть, но, как "
               "правило, дешевле, чем покупает электроэнергию. Поэтому выгода зависит от того, <i>когда</i> дом тратит энергию."),
          para("<b>Гипотеза 2:</b> срок окупаемости определяется прежде всего тарифом и долей самопотребления, а доход от "
               "продажи излишков составляет не более пятой части (20 %) годового экономического эффекта."),
          para("<b>Задачи команды 2</b> и статус на сегодня:")]
story.append(table([
    ["Задача", "Статус", "Результат"],
    ["Нормативная база микрогенерации, изменения 2026 г.", "готово", "раздел 2"],
    ["Тарифы для населения Адыгеи и Краснодарского края", "готово", "раздел 3, data/tariffs_2026.csv"],
    ["Цена выкупа излишков и её динамика за 1–2 года", "готово (по тарифам — расчёт, на подтверждении)", "раздел 4"],
    ["Формат обмена данными с командой 1", "согласован 17.10.2026", "docs/exchange_format.md"],
    ["Капзатраты на СЭС 3/5/10 кВт «под ключ»", "готово (оценка по 2 способам, ±15–20 %)", "раздел 6"],
    ["Экономическая модель (простой и дисконтированный срок)", "готово", "раздел 5"],
    ["Расчёт на условных долях самопотребления 20–80 %", "готово (предварительно)", "раздел 7"],
    ["Анализ чувствительности, тепловая карта на реальных профилях, калькулятор", "этапы 3–4", "—"],
], [0.5, 0.25, 0.25]))

# ---------- 2. Нормативка
story += [para("2. Нормативная база микрогенерации", "h1")]
story.append(table([
    ["Документ", "Что важно для проекта"],
    ["35-ФЗ «Об электроэнергетике» (ст. 3), 471-ФЗ от 27.12.2019", "Понятие объекта микрогенерации: присоединение к сетям до 1 кВ, производство для собственных нужд, в сеть — только излишки."],
    ["ПП РФ от 04.05.2012 № 442 (Основные положения розничных рынков)", "Гарантирующий поставщик обязан покупать излишки; цена — не выше оптовой цены электроэнергии и мощности для ценовой категории владельца (п. 65(3))."],
    ["208-ФЗ от 26.06.2026", "Жёсткий лимит 15 кВт отменён; предельные значения выдачи в сеть устанавливает Правительство; микрогенерация разрешена в общем имуществе МКД."],
    ["Распоряжение Правительства от 26.09.2026 № 2675-р", "Лимиты выдачи в сеть: физлица — до 50 кВт, юрлица, ИП и МКД — до 150 кВт включительно."],
    ["ПП РФ от 26.09.2026 № 1242", "Правила техприсоединения (ПП № 861) ссылаются на лимиты Правительства; присоединение к сетям до 1000 В."],
    ["459-ФЗ от 27.12.2019 (ст. 217 НК РФ)", "Доход физлица от продажи излишков освобождён от НДФЛ до 01.01.2029; далее в модели — 13 %."],
], [0.38, 0.62]))
story += [para("<b>Вывод:</b> домашние СЭС 3, 5 и 10 кВт укладываются в любые лимиты, изменения 2026 г. расширяют рынок, "
               "но экономику домашней станции напрямую не меняют. Краснодарский край и Адыгею обслуживает один "
               "гарантирующий поставщик — ПАО «ТНС энерго Кубань», тарифы в регионах одинаковые.")]

# ---------- 3. Тарифы
story += [para("3. Тарифы для населения на 2026 год", "h1"),
          para("Приказ ДГРТ Краснодарского края от 17.12.2025 № 18/2025-э (Краснодарский край, Республика Адыгея, ФТ «Сириус»). "
               "Два периода: с 1 января и с 1 октября 2026 г. (+11 %). Пониженные ставки — для сельского населения и "
               "городских домов с электроплитами / электроотоплением."),
          fig(f_tariffs, "Рис. 1. Тарифы I диапазона. Источник: ТНС энерго Кубань, data/tariffs_2026.csv."),
          para("<b>Диапазоны по объёму:</b> для жилого дома I — до 1100 кВт·ч/мес, II — 1100–1700, III — свыше 1700; "
               f"во II диапазоне городской тариф {ru(tprice('2026-10-01', 'base', 'single', 'flat', 'II'))} ₽, в III — "
               f"{ru(tprice('2026-10-01', 'base', 'single', 'flat', 'III'))} ₽ (с 01.10.2026). Для домов с электроотоплением "
               "в отопительный период границы 3900 и 6000 кВт·ч/мес.")]

# ---------- 4. Цена выкупа
story += [para("4. Цена выкупа излишков", "h1"),
          para("<b>Факт.</b> ТНС энерго Кубань ежемесячно публикует объём и средневзвешенную цену покупки электроэнергии "
               "у владельцев микрогенерации (п. 52в Стандартов раскрытия, ПП РФ № 24). Собраны отчёты за январь 2024 — "
               f"август 2026: средняя цена <b>{ru(w24)} ₽/кВт·ч в 2024 г.</b>, <b>{ru(w25)} ₽ в 2025 г.</b> и "
               f"<b>{ru(w26)} ₽ в 2026 г.</b> (рост около 14–15 % в год) "
               f"(январь–август). Объём покупки растёт: за 8 месяцев 2026 г. — {rub(b26.volume_total_kwh.sum() / 1000)} МВт·ч, "
               f"в {ru(b26.volume_total_kwh.sum() / b25.volume_total_kwh.sum(), 1)} раза больше, чем за весь 2025 г."),
          fig(f_buyback, "Рис. 2. Цена выкупа: факт ТНС и расчёт по тарифу владельца. Источник: отчёты ТНС энерго Кубань."),
          fig(f_volumes, "Рис. 3. Объём покупки у владельцев СЭС по месяцам и тарифам владельцев."),
          para("<b>Цена по тарифу владельца (расчёт).</b> ТНС публикует одну среднюю цену, но по ОП № 442 она зависит от "
               "ценовой категории владельца: оптовая цена энергии + цена мощности × коэффициент категории. Компоненты взяты "
               "из ежемесячных отчётов ТНС «Предельные уровни нерегулируемых цен»:"),
          *bullets([f"одноставочный тариф (1-я ценовая категория) — в среднем <b>{ru(flat_avg)} ₽/кВт·ч</b> (май–сентябрь 2026);",
                    f"тариф день/ночь (2-я категория, дневная зона — солнце отдаёт энергию днём) — <b>{ru(zones_avg)} ₽/кВт·ч</b>;",
                    f"сезонность: зимой выше (ноябрь {ru(bmf[11])} / {ru(bmz[11])} ₽), летом ниже (июнь {ru(bmf[6])} / {ru(bmz[6])} ₽)."]),
          fig(f_check, "Рис. 4. Проверка: если взвесить расчётные цены по объёмам из отчёта ТНС, получается опубликованная "
                       "средняя цена с ошибкой +1…+2 %.", width=W * 0.75),
          para("<b>Что это значит.</b> Тезис «излишки продаются намного дешевле» верен для одноставочного городского тарифа "
               f"({ru(flat_avg)} против 8,31 ₽ — {100 * flat_avg / 8.31:.0f} %). Для тарифа день/ночь выкуп близок к тарифу, "
               f"а у сельского дома ({ru(zones_avg)} против 6,54 ₽ днём) — даже выше. Этот вывод требует подтверждения у ТНС.", "note")]

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
          para("Параметры (полный реестр — docs/assumptions.md):", "h2")]
story.append(table([
    ["Параметр", "Значение", "Источник"],
    ["Рост тарифа населения", "+14,4 % (2027), +12,1 % (2028), +10,1 % (2029), далее 4 %", "Прогноз МЭР, одобрен Правительством 24.09.2026; цель ЦБ по инфляции"],
    ["Рост цены выкупа", "+10,4 %, +7,4 %, +7,0 %, далее 4 %", "Прокси: прогноз МЭР роста оптовых цен на газ"],
    ["Ставка дисконтирования", "11,5 % (2027), 8,5 % (2028), 8 % (2029+)", "Прогноз средней ключевой ставки Банка России"],
    ["Выработка 1 кВт", f"Краснодар {sum(kr.values()):.0f}, Майкоп {sum(mk.values()):.0f} кВт·ч/год", "PVGIS-SARAH3 2005–2023"],
    ["Деградация панелей", "1 % в 1-й год, далее 0,4 %/год", "Линейная гарантия производителей (TOPCon)"],
    ["Срок службы / инвертор", "25 лет; замена инвертора на 12-й год по цене инвертора нужной мощности", "Допущение (срок); цены инверторов 2026"],
    ["НДФЛ с излишков", "0 % до 2028 г., 13 % с 2029 г.", "459-ФЗ, ст. 217 и 224 НК РФ"],
    ["Капзатраты (база)", f"3 кВт — {rub(CAPEX[3])}, 5 кВт — {rub(CAPEX[5])}, 10 кВт — {rub(CAPEX[10])} ₽", "Комплекты Краснодара + монтаж и прочие статьи; диапазон — раздел 6"],
], [0.25, 0.38, 0.37]))
story += [fig(f_pv, "Рис. 6. Сезонность выработки СЭС. Источник: PVGIS (Европейская комиссия, JRC).")]

# ---------- 6. Капзатраты
cap = pd.read_csv(DATA / "capex_estimate.csv", encoding="utf-8-sig").set_index("pv_kw")
comp = pd.read_csv(DATA / "capex_components.csv", encoding="utf-8-sig")
story += [para("6. Капитальные затраты на СЭС «под ключ»", "h1"),
          para("Опубликованных цен «под ключ» у установщиков Краснодара нет (только «расчёт по запросу»), поэтому "
               "капзатраты оценены тремя способами, которые дают нижнюю границу, базовое значение и верхнюю границу:"),
          *bullets(["<b>Способ В (снизу, нижняя граница)</b> — сумма цен компонентов по рознице: панели TOPCon 585–590 Вт "
                    f"(медиана {ru(comp[comp['item'] == 'panel'].price_rub.median())} ₽/Вт, Краснодар), инвертор нужной мощности, "
                    "крепёж для скатной крыши, кабель и MC4, защита DC/AC, монтаж 12 тыс. ₽/кВт, оформление и доставка;",
                    "<b>База</b> — комплект краснодарского продавца (панели, инвертор, крепёж, кабели) + монтаж, защита, "
                    "оформление и доставка: так устроено предложение типичного местного установщика;",
                    "<b>Способ Б (сверху, верхняя граница)</b> — опубликованные общероссийские цены «под ключ» 2026 г. "
                    "(включают наценку установщика, проект и сервис)."]),
          fig(ROOT / "results" / "capex_estimate.png", "Рис. 7. Капзатраты: разбивка способа В по статьям, база и опубликованные "
                                                      "цены «под ключ». Источники: data/capex_components.csv, equipment_offers.csv, turnkey_prices.csv.")]
cap_rows = [["Мощность", "В: по компонентам", "База (в модели)", "Б: опубликовано", "База, ₽ за кВт", "Инвертор (замена)"]]
for kw, r in cap.iterrows():
    cap_rows.append([f"{kw} кВт ({r.panels} панелей)", rub(r.capex_low_rub), f"<b>{rub(r.capex_base_rub)}</b>", rub(r.capex_high_rub),
                     rub(r.base_rub_per_kw), rub(r.inverter_rub)])
story += [table(cap_rows, [0.2, 0.16, 0.16, 0.16, 0.16, 0.16]),
          para("Таблица: капзатраты, ₽. Для 10 кВт опубликованной цены «под ключ» нет — верхняя граница экстраполирована от 5 кВт.", "cap"),
          para("<b>Точность:</b> базовое значение — около ±15–20 %. Разница между способами В и Б — это наценка установщика, "
               "проектирование и гарантийный сервис. Нижняя и верхняя границы используются в анализе чувствительности. "
               "Допущения: монтаж 12 тыс. ₽/кВт (ориентиры рынка 10–30 % стоимости оборудования), оформление микрогенерации "
               "и доставка 10 тыс. ₽, прибор учёта ставит сетевая организация.", "note")]

# ---------- 7. Результаты
story += [para("7. Предварительные результаты", "h1"),
          para("Условный дом: потребление 6000 кВт·ч/год (500 кВт·ч/мес, равномерно), ночная зона 30 %, Краснодар. "
               "Доля самопотребления задана условно (20–80 %) до получения профилей команды 1."),
          fig(f_heat, "Рис. 8. СЭС 5 кВт: простой и дисконтированный срок окупаемости в зависимости от доли "
                      "самопотребления и тарифа (зелёный — быстрее, красный — дольше).")]
res_rows = [["Тариф", "Простой срок, лет", "Простой срок при капзатратах В…Б", "Дисконт. срок, лет", "Доля излишков, %"]]
for plan in PLANS:
    d = p5[p5.tariff == plan.name]
    res_rows.append([plan.name, f"{ru(d.simple_payback.min(), 1)}–{ru(d.simple_payback.max(), 1)}",
                     f"{ru(d.simple_payback_low.min(), 1)}–{ru(d.simple_payback_high.max(), 1)}",
                     f"{ru(d.disc_payback.min(), 1)}–{ru(d.disc_payback.max(), 1)}",
                     f"{d.export_share_pct.min():.0f}–{d.export_share_pct.max():.0f}"])
story += [table(res_rows, [0.28, 0.16, 0.2, 0.18, 0.18]), para("Таблица: СЭС 5 кВт, диапазон по долям самопотребления 20–50 %.", "cap"),
          fig(f_cash, "Рис. 9. Накопленный дисконтированный денежный поток СЭС 5 кВт; точка пересечения с нулём — "
                      "дисконтированный срок окупаемости."),
          fig(f_hyp, "Рис. 10. Доля дохода от излишков в годовом эффекте. Гипотеза 2 выполняется только правее и ниже "
                     "красной линии.")]

# выводы считаются из результатов, чтобы цифры не расходились с таблицами при пересчёте
pv5 = p5.pivot_table(index="self_share_target", columns="tariff", values="simple_payback")
gain_city = pv5["Город, одноставочный"] - pv5["Город, день/ночь"]
gain_rural = pv5["Село, одноставочный"] - pv5["Село, день/ночь"]
rs = p5[p5.tariff == "Село, одноставочный"]
ranges_gain = 100 * (mon[1] / tz[1] - 1)
story += [para("Предварительные выводы", "h2"),
          *bullets([f"<b>Тариф день/ночь сокращает срок окупаемости</b> СЭС 5 кВт на {ru(gain_city.min(), 1)}–{ru(gain_city.max(), 1)} "
                    f"года в городе и на {ru(gain_rural.min(), 1)}–{ru(gain_rural.max(), 1)} года на селе по сравнению с "
                    "одноставочным: солнце замещает дорогую дневную энергию, а излишки выкупаются по более высокой цене "
                    "дневной зоны.",
                    "<b>Сельский одноставочный тариф — самый невыгодный</b> (ниже тариф — меньше экономия): простой срок "
                    f"{ru(rs.simple_payback.min(), 1)}–{ru(rs.simple_payback.max(), 1)} лет, дисконтированный — "
                    f"{ru(rs.disc_payback.min(), 1)}–{ru(rs.disc_payback.max(), 1)} года.",
                    "<b>Гипотеза 2, по предварительным данным, не подтверждается:</b> доход от излишков составляет "
                    f"{int(pay.export_share_pct.min() + 0.5)}–{int(pay.export_share_pct.max() + 0.5)} % эффекта и опускается ниже 20 % только "
                    "при доле самопотребления от 70–80 %. Окончательно — на реальных профилях команды 1.",
                    f"<b>Учёт диапазонов тарифа важен</b> для домов с большим потреблением: эффект на {ranges_gain:.0f} % выше "
                    "формулы ТЗ."]),
          PageBreak()]

# ---------- 8. Ограничения и планы
story += [para("8. Ограничения, открытые вопросы и дальнейшие шаги", "h1"),
          para("Ограничения текущих расчётов", "h2"),
          *bullets(["Профили потребления условные — ждём данные команды 1 (срок 04.12.2026).",
                    "Капзатраты — оценка по ценам компонентов и комплектов (±15–20 %), не персональные КП; диапазон — в чувствительности.",
                    "Цена выкупа по тарифу владельца — расчёт по открытым отчётам ТНС (сверка +1…2 %), не прямая публикация; "
                    "требует подтверждения у ТНС энерго Кубань.",
                    "Рост цены выкупа — прокси (прогноз цен на газ), официального прогноза оптовой цены нет.",
                    "Не учтены: трёхзонный тариф, аккумуляторы, стоимость присоединения и реверсивного счётчика."]),
          para("Дальнейшие шаги", "h2")]
story.append(table([
    ["Срок", "Шаг"],
    ["до 01.11.2026", "Подтвердить цену выкупа по тарифам у ТНС энерго Кубань; при возможности — 1–2 КП для сверки капзатрат"],
    ["до 15.11.2026", "Пересчёт на КП, промежуточный доклад (5–7 мин)"],
    ["16.11–06.12.2026", "Анализ чувствительности (тариф, самопотребление, выкуп, стоимость оборудования), модуль Python, тесты"],
    ["07–18.12.2026", "Пересчёт на реальных профилях команды 1, тепловая карта «профиль × тариф», проверка гипотезы 2, калькулятор Streamlit"],
    ["21–25.12.2026", "Итоговый отчёт, презентация, защита"],
], [0.2, 0.8]))

story += [para("Источники", "h1"), *bullets([
    "ТНС энерго Кубань — тарифы 2026: kuban.tns-e.ru/calculations/tariffs/tariff-table/",
    "ТНС энерго Кубань — объёмы и средневзвешенная цена покупки у микрогенерации; предельные уровни нерегулируемых цен "
    "(раздел «Раскрытие информации субъектом рынка»): kuban.tns-e.ru/disclosure/",
    "208-ФЗ от 26.06.2026: consultant.ru/law/hotdocs/94648.html; rg.ru/documents/2026/07/01/energetika-dok.html",
    "Распоряжение № 2675-р и ПП № 1242 от 26.09.2026: ppt.ru; bigpowernews.ru/news/document126862.phtml",
    "ПП РФ № 442, № 299: government.ru; base.garant.ru/400418448/",
    "Прогноз социально-экономического развития на 2027–2029 гг. (МЭР): bigpowernews.ru/news/document126870.phtml; vedomosti.ru",
    "Банк России — ключевая ставка и прогноз: cbr.ru/hd_base/keyrate/; interfax.ru/business/1105322",
    "PVGIS (European Commission, JRC): re.jrc.ec.europa.eu",
    "Гарантия мощности панелей: TCL MG680 datasheet (tcl.com)",
    "Цены оборудования: ekoproekt-energo.ru, sv-synergy.ru, altecology.ru, krasnodar.termodar.ru",
])]

doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm,
                        bottomMargin=1.7 * cm, title="SunCount — промежуточный отчёт команды 2", author="Команда 2 SunCount")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("PDF:", OUT)
