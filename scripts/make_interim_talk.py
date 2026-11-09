"""Промежуточный доклад команды 2 (T5.3) — reports/SunCount_interim_talk.pptx.

Оформление — шаблон АГУ / «Приоритет» из reports/kurs/02_problema_potrebitelya/SunCount_problema_potrebitelya.pptx
(макеты, логотипы, нижняя полоса с номером слайда берутся из него как есть). Цифры — из файлов репозитория:
results/config_examples.csv, results/yield_validation.csv, results/real_payback.csv, data/tariffs_2026.csv,
data/buyback_by_category.csv, data/equipment/*.csv; смета — прямо из конфигуратора (app/calc.py).
Скриншот веб-сервиса — reports/interim_talk/web_service.png (снят с запущенного веб-сервиса).

Запуск: python scripts/make_interim_talk.py [путь.pptx]
"""
import copy
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.calc import portrait_load, run_configurator  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from make_scheme import draw_scheme  # noqa: E402

TEMPLATE = ROOT / "reports" / "kurs" / "02_problema_potrebitelya" / "SunCount_problema_potrebitelya.pptx"
OUT = ROOT / "reports" / "SunCount_interim_talk.pptx"
SHOT = ROOT / "reports" / "interim_talk" / "web_service.png"

BLUE = RGBColor(0x1E, 0x4E, 0x79)      # цвет заголовков и полосы шаблона
GREY = RGBColor(0xA6, 0xA6, 0xA6)      # второй ряд на диаграммах, как в шаблоне
TEXT = RGBColor(0x00, 0x00, 0x00)
MUTED = RGBColor(0x59, 0x59, 0x59)
TINT = RGBColor(0xE9, 0xEF, 0xF6)      # светлая подложка для выносок
FONT = "Calibri"

# макеты шаблона
L_TITLE, L_TWO, L_TWO_RIGHT, L_TITLE_ONLY = 1, 3, 4, 6
X0, Y0, W0, Y1 = 1.92, 2.02, 10.5, 6.68   # рабочее поле под заголовком и над нижней полосой, дюймы

PORTRAIT_NAMES = {"day_absent": "Семья днём на работе", "home_all_day": "Кто-то дома весь день",
                  "ac": "Дом с кондиционером", "el_heating": "Дом с электроотоплением"}


def plural(n: int, one: str, few: str, many: str) -> str:
    """Склонение по числу: 1 расчёт, 2 расчёта, 64 расчёта, 65 расчётов."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def ru(x, nd=0):
    """Число по-русски: 175960 -> «175 960», 2.36 -> «2,36»."""
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s


# ----------------------------------------------------------------- данные
def count_tests() -> int:
    """Сколько автотестов в tests/ (pytest --collect-only), чтобы число на слайде не устаревало."""
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    m = re.search(r"(\d+) tests? collected", out)
    if not m:
        raise RuntimeError("не удалось посчитать тесты: " + out[-300:])
    return int(m.group(1))


def load_numbers() -> dict:
    ex = pd.read_csv(ROOT / "results" / "config_examples.csv", encoding="utf-8-sig")
    yv = pd.read_csv(ROOT / "results" / "yield_validation.csv", encoding="utf-8-sig")
    rp = pd.read_csv(ROOT / "results" / "real_payback.csv", encoding="utf-8-sig")
    tar = pd.read_csv(ROOT / "data" / "tariffs_2026.csv", encoding="utf-8-sig")
    bb = pd.read_csv(ROOT / "data" / "buyback_by_category.csv", encoding="utf-8-sig").sort_values("month")
    city = tar[(tar.category == "base") & (tar.range == "I")]
    last = city.date_from.max()
    flat = city[(city.tariff_type == "single")].sort_values("date_from").price_rub_kwh.tolist()
    zones = city[(city.date_from == last) & (city.tariff_type == "two_zone")].set_index("zone").price_rub_kwh
    y = yv.groupby("city").agg(pvgis=("pvgis_kwh_per_kw_mean", "first"), ours=("ours_tmy_kwh_per_kw", "mean"),
                               dmin=("diff_min_pct", "min"), dmean_lo=("diff_mean_pct", "min"),
                               dmean_hi=("diff_mean_pct", "max"))
    portraits = []
    for pid in ("day_absent", "home_all_day", "ac", "el_heating"):
        g = ex[ex.profile_id == pid]
        inv_kw = sorted({float(s.split("SUN-")[1].split("K")[0]) for s in g.inverter})
        portraits.append(dict(
            pid=pid, load=(g.load_kwh.min(), g.load_kwh.max()), n=(g.n_panels.min(), g.n_panels.max()),
            kwp=(g.kwp.min(), g.kwp.max()), inv=inv_kw, capex=(g.capex_rub.min(), g.capex_rub.max()),
            pb=(g.simple_payback.min(), g.simple_payback.max()),
            exp=(g.export_share.min(), g.export_share.max()), self=(g.self_share.min(), g.self_share.max())))
    lim = ex.constraint.str.split(":").str[0].value_counts()
    return dict(
        ex=ex, portraits=portraits, n_cases=len(ex), limits=lim,
        capex=(ex.capex_rub.min(), ex.capex_rub.max()), pb=(ex.simple_payback.min(), ex.simple_payback.max()),
        self=(ex.self_share.min(), ex.self_share.max()), exp_cfg=(ex.export_share.min(), ex.export_share.max()),
        exp_real=(rp.export_share_net.min(), rp.export_share_net.max()),   # с зачётом, как у ТНС
        b_real=(int((rp.export_share_net <= 20).sum()), len(rp)), b_cfg=(int((ex.export_share <= 20).sum()), len(ex)),
        yv=y,
        tariff_now=flat[-1], tariff_before=flat[-2], tariff_from=last,
        zones=(zones["day"], zones["night"]), bb_month=bb.month.iloc[-1],
        bb_flat=bb.flat_rub_kwh.iloc[-1], bb_day=bb.zones_day_rub_kwh.iloc[-1])


# ----------------------------------------------------------------- оформление
def clear_slides(prs):
    lst = prs.slides._sldIdLst
    for sld in list(lst):
        prs.part.drop_rel(sld.rId)
        lst.remove(sld)


def add_slide(prs, layout: int, title: str | None = None):
    lay = prs.slide_layouts[layout]
    s = prs.slides.add_slide(lay)
    # номер слайда: python-pptx не переносит его из макета — копируем плейсхолдер макета
    for sp in lay.placeholders:
        if sp.placeholder_format.type is not None and sp.placeholder_format.idx == 12:
            s.shapes._spTree.append(copy.deepcopy(sp._element))
    if title is not None:
        s.shapes.title.text_frame.text = nbsp(title)
        s.shapes.title.text_frame.paragraphs[0].runs[0].font.bold = False
    return s


def place(shape, x, y, w, h):
    """Положение и размер целиком: у плейсхолдера без своих координат одна ширина сдвигает его в угол."""
    shape.left, shape.top, shape.width, shape.height = Inches(x), Inches(y), Inches(w), Inches(h)


def drop_empty_placeholders(slide):
    for ph in list(slide.placeholders):
        if ph.placeholder_format.idx == 12 or ph.placeholder_format.type == 1:   # номер слайда, заголовок
            continue
        if ph.has_text_frame and not ph.text_frame.text.strip():
            ph._element.getparent().remove(ph._element)


def _bullet(p, on: bool, size: int):
    pPr = p._p.get_or_add_pPr()
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    if on:
        pPr.set("marL", str(int(Emu(Inches(0.3)))))
        pPr.set("indent", str(-int(Emu(Inches(0.3)))))
        bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
        pPr.append(bu)
    else:
        pPr.set("marL", "0")
        pPr.set("indent", "0")
        pPr.append(pPr.makeelement(qn("a:buNone"), {}))


NB = chr(0xA0)   # неразрывный пробел
NBSP_RE = re.compile(r"(\d) (кВт·ч|кВт|МВт·ч|тыс\.|млн|₽|%|года|лет|панел|м²|из|вместо)")
GLUE = {"тыс. ₽": "тыс." + NB + "₽", "«3, 5 или 10": "«3," + NB + "5" + NB + "или" + NB + "10"}


def nbsp(text: str) -> str:
    """Число и единица — неразрывно: «10 кВт» не разъезжается по строкам."""
    text = re.sub(r"(?<=\d) (?=\d{3}(?!\d))", NB, text)   # разряды: «1 100», «21 183»
    text = NBSP_RE.sub(r"\1" + NB + r"\2", text)
    for old, new in GLUE.items():
        text = text.replace(old, new)
    return re.sub(r"(\s)(\d+) (запасн)", r"\1\2" + NB + r"\3", text)


def fill(tf, paras, size=18, space_after=8, color=TEXT, align=PP_ALIGN.LEFT):
    """paras: список абзацев; абзац — строка или dict(runs=[(текст, жирный)], bullet=bool, size=, color=, after=)."""
    tf.clear()
    tf.word_wrap = True
    for i, para in enumerate(paras):
        if isinstance(para, str):
            para = {"runs": [(para, False)]}
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = para.get("align", align)
        p.space_after = Pt(para.get("after", space_after))
        p.space_before = Pt(0)
        _bullet(p, para.get("bullet", False), para.get("size", size))
        for text, bold in para["runs"]:
            r = p.add_run()
            r.text = nbsp(text)
            f = r.font
            f.size = Pt(para.get("size", size))
            f.bold = bold
            f.name = FONT
            f.color.rgb = para.get("color", color)


def textbox(slide, x, y, w, h, paras, size=16, anchor=MSO_ANCHOR.TOP, name=None, **kw):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    tf.vertical_anchor = anchor
    fill(tf, paras, size=size, **kw)
    if name:
        tb.name = name
    return tb


def panel(slide, x, y, w, h, name):
    """Светлая подложка без рамки — выделяет вывод или выноску."""
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = TINT
    shp.line.fill.background()
    shp.shadow.inherit = False
    shp.name = name
    return shp


def stat(slide, x, y, w, big, small, name):
    panel(slide, x, y, w, 1.45, name + " фон")
    textbox(slide, x + 0.2, y + 0.12, w - 0.4, 0.7, [{"runs": [(big, True)], "size": 34, "color": BLUE, "after": 0}],
            name=name + " число")
    textbox(slide, x + 0.2, y + 0.8, w - 0.4, 0.6, [{"runs": [(small, False)], "size": 15, "after": 0}],
            name=name + " подпись")


def table(slide, x, y, w, rows, col_w, size=14, header=True, name="Таблица", row_h=0.42, bold_last=False,
          highlight_col=None):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                                   Inches(row_h * len(rows)))
    shape.name = name
    tbl = shape.table
    # «Сетка таблицы» без заливки — как таблица в шаблоне
    tbl._tbl.tblPr.find(qn("a:tableStyleId")).text = "{5940675A-B579-460E-94D1-54222C63F5DA}"
    tbl.first_row = header
    tbl.horz_banding = False
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            right = isinstance(val, tuple)
            text = val[0] if right else val
            bold = (header and i == 0) or (bold_last and i == len(rows) - 1)
            fill(cell.text_frame, [{"runs": [(text, bold or j == highlight_col)], "after": 0,
                                    "align": PP_ALIGN.RIGHT if right else PP_ALIGN.LEFT}], size=size,
                 color=BLUE if j == highlight_col else TEXT)
            if j == highlight_col:
                cell.fill.solid()
                cell.fill.fore_color.rgb = TINT
    return shape


def style_chart(chart, title, colors, legend=True, fmt='#,##0', label_size=13):
    chart.font.name = FONT
    chart.font.size = Pt(12)
    chart.has_title = True
    tf = chart.chart_title.text_frame
    tf.text = title
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size, r.font.bold, r.font.name = Pt(14), True, FONT
    plot = chart.plots[0]
    plot.gap_width = 70
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.font.size, dl.font.name = Pt(label_size), FONT
    dl.number_format, dl.number_format_is_linked = fmt, False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    for s, c in zip(plot.series, colors):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = c
    va = chart.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = RGBColor(0xD9, 0xD9, 0xD9)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(11)
    va.tick_labels.font.color.rgb = MUTED
    va.tick_labels.number_format, va.tick_labels.number_format_is_linked = fmt, False
    ca = chart.category_axis
    ca.tick_labels.font.size = Pt(12)
    ca.format.line.color.rgb = RGBColor(0xBF, 0xBF, 0xBF)
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(12)


def notes(slide, who, text):
    slide.notes_slide.notes_text_frame.text = f"Говорит: {who}.\n\n{text}"


def speech(d: dict, best: dict, n_tests: int) -> dict:
    """Текст докладчиков по слайдам (заметки к слайдам и reports/interim_talk/tekst_doklada.md). Цифры — из данных."""
    a, b = ru(d["capex"][0] / 1000), ru(d["capex"][1] / 1000)
    pb0, pb1 = ru(d["pb"][0], 1), ru(d["pb"][1], 1)
    return {
        "title": ("Рогочий Александр (Р5)",
                  "Добрый день. Мы — команда 2 проекта SunCount, системы поддержки принятия решений по выбору домашней "
                  "солнечной электростанции для Адыгеи и Краснодарского края. За этот этап продукт изменился: по "
                  "замечаниям научного руководителя сервис больше не выбирает из готовых станций на 3, 5 и 10 "
                  "киловатт, а подбирает станцию под конкретный дом — с моделями оборудования, сметой и сроком "
                  "окупаемости."),
        "problem": ("Рогочий Александр (Р5)",
                    "Владелец частного дома решил поставить солнечную станцию. Ему нужно понять, какая станция нужна "
                    "именно ему, из чего её собрать, сколько это стоит и когда окупится. Ответ зависит сразу от "
                    "тарифа, от того, когда семья тратит электричество, от крыши, договора с сетью и цены выкупа "
                    "излишков. Готовые калькуляторы этого не учитывают и почти всегда предлагают типовые 3, 5 или "
                    f"10 киловатт без сметы. А ошибка дорогая: станции для типичных семей стоят от {a} до {b} тысяч "
                    "рублей."),
        "actual": ("Власов Кирилл (Р2)",
                   "Почему это важно сейчас. С конца сентября 2026 года гражданин может продавать в сеть излишки "
                   "станции до 50 киловатт вместо 15. Рынок быстро растёт: ТНС энерго Кубань купила у владельцев "
                   "станций 899 мегаватт-часов в 2025 году и уже 2 364 за девять месяцев 2026-го, с мая излишки "
                   "покупает и второй поставщик края, НЭСК. А станция есть меньше чем у одного частного дома из тысячи: "
                   "почти все покупатели ещё впереди."),
        "analogs": ("Власов Кирилл (Р2)",
                    "Мы проверили девять существующих калькуляторов. Калькуляторы установщиков, например SOLAR IMPRO, "
                    "считают экономией весь счёт за электричество и ведут к заявке на свою станцию. У InnoQuest число "
                    "панелей и цену выкупа задаёт сам пользователь, а потребление — одной долей «днём». PVGIS считает "
                    "только выработку. Никто не подбирает станцию по часовому профилю дома и не учитывает тариф "
                    "день/ночь и цену выкупа по тарифу владельца. Это делает SunCount, и при этом мы ничего не "
                    "продаём."),
        "solution": ("Прищепа Максим (Р1)",
                     "Наше решение — система, которая подбирает станцию под конкретный дом. Сверху то, что знает "
                     "сервис: правила микрогенерации, тарифы и цена выкупа, каталог оборудования с паспортами и ценами. "
                     "Жёлтым — профили потребления по часам, их делает команда 1. Пользователь вводит дом, крышу, "
                     "договор с сетью и цель. Подбор идёт в три шага: энергорасчёт по паспорту панели, перебор "
                     "вариантов с проверкой правил, выбор по цели. На выходе — готовая станция со сметой и сроком "
                     "окупаемости."),
        "rules": ("Власов Кирилл (Р2)",
                  "У каждого числа в сервисе есть документ. Выдача в сеть — до 50 киловатт. Излишки покупает "
                  "гарантирующий поставщик по цене, которая зависит от тарифа владельца: в сентябре "
                  f"{ru(d['bb_flat'], 2)} рубля на одноставочном тарифе и {ru(d['bb_day'], 2)} днём на тарифе "
                  "день/ночь. Главное мы узнали в ноябре из договора ТНС с владельцем станции: расчёты идут с "
                  "помесячным зачётом — отданное в сеть за месяц сначала гасит покупку, и только остаток продаётся. "
                  "НДС с гражданина не берётся. Так теперь и считает сервис."),
        "yield": ("Цирульник Юрий (Р3)",
                  "Раньше выработка была одним числом из PVGIS. Теперь мы считаем её сами, по часам, для конкретной "
                  "панели и крыши: положение солнца, свет на скат, температура панели и слабый свет по паспорту, "
                  "потери и пределы инвертора. PVGIS остался только источником погоды. На типичном метеогоде "
                  "расхождение с PVGIS — 2–3 процента. На одной и той же погоде наш расчёт выше на 4,5–4,8 процента — "
                  "причину разбираю и сверю с данными реальных станций."),
        "smeta": ("Кривоносов Вячеслав (Р4)",
                  "Сервис не просто называет мощность, а собирает смету. Пример — семья, которая днём на работе: "
                  "четыре панели, инвертор на 3 киловатта, крепёж, кабель, защита, монтаж и подключение к сети — "
                  f"всего {ru(best['capex_rub'])} рублей. Цены — только с восемнадцати проверенных магазинов, обычные, "
                  "без скидок, у каждой модели есть паспорт производителя. Смета сходится с предложениями "
                  "установщиков: около 3 киловатт — 195 тысяч у нас и 194–209 тысяч у установщика."),
        "results": ("Прищепа Максим (Р1)",
                    "Вот что сервис подобрал для типичных семей команды 1 в Краснодаре и Майкопе: крыша 40 квадратных "
                    "метров, юг, договор 15 киловатт, цель — для своих нужд. Семье, которая днём на работе, хватает "
                    "2,36 киловатта, дому с электроотоплением нужно 8–9. Ни одна станция не совпала с типовыми 3, 5 или "
                    f"10 киловаттами: размер определяется потреблением дома. Срок окупаемости — от {pb0} до {pb1} "
                    "года, быстрее всего на тарифе день/ночь."),
        "hypothesis": ("Цирульник Юрий (Р3)",
                       "Гипотеза 2 из ТЗ курса: срок окупаемости определяется прежде всего тарифом и долей "
                       "самопотребления, а доход от излишков — не больше пятой части эффекта. Предварительно обе части "
                       "не подтверждаются. Сильнее всего на срок влияют стоимость станции и цена выкупа. А доход от "
                       f"излишков не больше 20 процентов лишь в {d['b_cfg'][0]} из {d['b_cfg'][1]} подборов: днём, "
                       "когда станция работает, дома мало кто есть. Вывод для продукта: решают точная смета и подбор "
                       "под дом. Финальный вывод — на финальных данных команды 1 до 14 декабря."),
        "web": ("Кривоносов Вячеслав (Р4)",
                "Так выглядит веб-сервис. Слева пользователь описывает дом: город и тариф, потребление — готовый "
                "портрет семьи или свои квитанции, крышу, договор с сетью и цель. Справа — рекомендация одной фразой, "
                "мощность, цена под ключ, срок окупаемости и эффект в год, ниже смета и запасные варианты. Расчёт "
                f"проверяют {n_tests} {plural(n_tests, 'автотест', 'автотеста', 'автотестов')}. До конца ноября "
                "довожу интерфейс, в декабре — график лета и зимы, подсказки и публикация."),
        "team": ("Рогочий Александр (Р5)",
                 "Кто за что отвечает. Максим — руководитель, экономическая модель и конфигуратор. Кирилл — данные и "
                 "правила рынка: нормативка, тарифы, цена выкупа, каталог оборудования. Юрий — аналитика: "
                 "чувствительность, гипотеза 2, проверка выработки. Вячеслав — веб-сервис. Я — автотесты, отчёты и "
                 "презентации. Профили потребления семей нам даёт команда 1."),
        "plan": ("Прищепа Максим (Р1)",
                 "План до защиты. В ноябре — свежая цена выкупа, расширение каталога, доводка интерфейса, проверка "
                 "выработки и автотесты. 4 декабря команда 1 передаёт финальные профили, после этого пересчитываем "
                 "подбор и гипотезу 2. В середине декабря — публикация веб-сервиса, 20–21 декабря — итоговая "
                 "презентация и отчёт. Спасибо, готовы ответить на вопросы."),
    }


TALK_MD = ROOT / "reports" / "interim_talk" / "tekst_doklada.md"


def write_speech_md(order: list, titles: dict, sp: dict) -> None:
    """Текст выступления по слайдам — тот же, что в заметках к слайдам."""
    words = {k: len(sp[k][1].split()) for k in order}
    total = sum(words.values())
    lines = ["# Текст доклада по слайдам", "",
             "Собирается скриптом `scripts/make_interim_talk.py` вместе с презентацией "
             "`reports/SunCount_interim_talk.pptx`, тот же текст — в заметках к слайдам. Править текст — в функции "
             "`speech()` скрипта, иначе при пересборке правка пропадёт.", "",
             f"Всего около {total} слов — примерно {ru(total / 130, 1)} минуты при спокойном темпе 130 слов в минуту.",
             ""]
    for n, k in enumerate(order, 1):
        who, text = sp[k]
        sec = round(words[k] / 130 * 60 / 5) * 5
        lines += [f"## Слайд {n}. {titles[k]}", "", f"**Говорит:** {who}, около {sec} секунд.", "", text, ""]
    TALK_MD.parent.mkdir(parents=True, exist_ok=True)
    TALK_MD.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------- слайды
def build():
    d = load_numbers()
    best0 = run_configurator("krasnodar", "city_single", portrait_load("day_absent", "krasnodar"))["configs"][0]
    n_tests = count_tests()
    SP = speech(d, best0, n_tests)
    prs = Presentation(str(TEMPLATE))
    clear_slides(prs)

    # 1. Титул
    s = add_slide(prs, L_TITLE)
    fill(s.shapes.title.text_frame,
         [{"runs": [("SunCount: система поддержки принятия решений по выбору домашней солнечной электростанции", False)],
           "size": 36, "color": BLUE, "after": 0}])
    fill(s.placeholders[1].text_frame, [
        {"runs": [("Адыгея и Краснодарский край · промежуточный доклад, этап 2", True)], "size": 16},
        {"runs": [("Команда 2: ", True), ("Власов Кирилл, Прищепа Максим, Цирульник Юрий, Кривоносов Вячеслав, "
                                          "Рогочий Александр", False)], "size": 16},
        {"runs": [("Наставник: ", True), ("Онищенко Стефан Владимирович", False)], "size": 16},
        {"runs": [("Майкоп, ноябрь 2026 г.", False)], "size": 16},
    ], size=16)
    notes(s, *SP["title"])

    # 2. Проблема
    s = add_slide(prs, L_TWO, "Проблема")
    fill(s.placeholders[2].text_frame, [
        {"runs": [("Владельцу дома не хватает понятной и независимой рекомендации: ", True),
                  ("какую станцию купить, из чего её собрать, сколько она будет стоить и когда окупится "
                   "при его тарифе и по действующим правилам.", False)], "after": 14},
        {"runs": [("Ответ зависит от тарифа, режима потребления, крыши, договора с сетью, цены выкупа "
                   "излишков и цен оборудования", False)], "bullet": True},
        {"runs": [("Готовые калькуляторы — от продавцов или с завышенной экономией; почти все предлагают "
                   "«3, 5 или 10 кВт» без привязки к дому и без сметы", False)], "bullet": True},
        {"runs": [("Итог — переплата за лишнюю мощность, слишком маленькая станция или отказ от покупки",
                   False)], "bullet": True},
        {"runs": [("Для кого: ", True), ("владельцы частных домов Адыгеи и края и установщики, которые считают "
                                         "станцию клиенту", False)], "bullet": True},
    ], size=17)
    place(s.placeholders[2], 1.95, 2.0, 6.1, 4.6)
    s.placeholders[1]._element.getparent().remove(s.placeholders[1]._element)
    stat(s, 8.45, 2.1, 3.95, f"{ru(d['capex'][0] / 1000)}–{ru(d['capex'][1] / 1000)} тыс. ₽",
         "стоят станции, подобранные для типичных семей", "Выноска цена")
    stat(s, 8.45, 3.8, 3.95, f"{ru(d['pb'][0], 1)}–{ru(d['pb'][1], 1)} года",
         "срок окупаемости — зависит от тарифа и семьи", "Выноска срок")
    textbox(s, 8.45, 5.45, 3.95, 0.9, [{"runs": [("Расчёт SunCount на портретах команды 1, "
                                                  "results/config_examples.csv", False)], "size": 12,
                                        "color": MUTED, "after": 0}], name="Источник")
    notes(s, *SP["problem"])

    # 3. Актуальность
    s = add_slide(prs, L_TWO_RIGHT, "Актуальность")
    cd = CategoryChartData()
    cd.categories = ["2024", "2025", "2026, 9 мес."]
    cd.add_series("МВт·ч", (492, 899, 2364))
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(X0), Inches(Y0), Inches(5.6), Inches(4.65), cd)
    gf.name = "Диаграмма покупка излишков"
    style_chart(gf.chart, "Покупка излишков у владельцев микрогенерации, ТНС энерго Кубань, МВт·ч", [BLUE],
                legend=False)
    fill(s.placeholders[1].text_frame, [
        {"runs": [("Правила стали выгоднее: ", True),
                  ("гражданин продаёт излишки станции до 50 кВт вместо 15 (208-ФЗ, распоряжение № 2675-р)",
                   False)], "bullet": True},
        {"runs": [("Рынок растёт: ", True), ("покупка излишков +83 % за 2025 г.; с мая 2026 г. их покупает "
                                             "и АО «НЭСК»", False)], "bullet": True},
        {"runs": [("Почти весь рынок впереди: ", True),
                  ("1,16 млн частных домов в крае (2016 г.), станция с продажей излишков — меньше чем у 0,1 %", False)],
         "bullet": True},
        {"runs": [("Тариф растёт: ", True),
                  (f"с 01.10.2026 — {ru(d['tariff_now'], 2)} ₽ за кВт·ч в городе, "
                   f"+{ru((d['tariff_now'] / d['tariff_before'] - 1) * 100)} %", False)], "bullet": True},
    ], size=16, space_after=10)
    notes(s, *SP["actual"])

    # 4. Аналоги
    s = add_slide(prs, L_TITLE_ONLY, "Чем мы отличаемся от готовых калькуляторов")
    rows = [
        ["Что умеет", "Установщики (SOLAR IMPRO и др.)", "InnoQuest", "PVGIS", "SunCount"],
        ["Подбирает станцию под дом: модели, число панелей, инвертор", "типовые комплекты",
         "число панелей задаёт пользователь", "нет", "да"],
        ["Потребление дома по часам", "нет", "только доля «днём»", "нет", "да, профили команды 1"],
        ["Тариф день/ночь и диапазоны потребления", "нет", "нет", "нет", "да"],
        ["Цена выкупа по тарифу владельца и помесячный зачёт", "нет: экономия = весь счёт",
         "цену вводит пользователь", "нет", "да"],
        ["Смета с ценами магазинов", "своя цена, ведёт к заявке", "₽/Вт по умолчанию", "нет", "да"],
        ["Не продаёт оборудование", "нет", "да", "да", "да"],
    ]
    table(s, X0, Y0 + 0.05, W0, rows, [3.05, 2.25, 1.95, 0.95, 2.3], size=14, row_h=0.56, name="Таблица аналогов",
          highlight_col=4)
    textbox(s, X0, 6.36, W0, 0.32, [{"runs": [("Проверено девять калькуляторов, 28–31.10.2026 — "
                                               "docs/grant/competitors.md", False)], "size": 12, "color": MUTED,
                                     "after": 0}], name="Источник аналогов")
    notes(s, *SP["analogs"])

    # 4. Решение — схема (фигуры PowerPoint, та же функция, что и reports/scheme/SunCount_scheme.pptx)
    s = add_slide(prs, L_TITLE_ONLY, "Решение: подбор станции под дом")
    draw_scheme(s, X0, Y0)
    notes(s, *SP["solution"])

    # 5. Правила рынка
    s = add_slide(prs, L_TITLE_ONLY, "Что сервис знает о правилах и деньгах")
    m = d["bb_month"]
    rows = [
        ["Правило", "Что это значит для дома", "Документ"],
        ["Выдача в сеть", "до 50 кВт для гражданина (было 15)", "208-ФЗ, распоряжение № 2675-р"],
        ["Продажа излишков", f"по цене, зависящей от тарифа владельца: за {m[5:7]}.{m[:4]} — "
                             f"{ru(d['bb_flat'], 2)} ₽ (одноставочный), {ru(d['bb_day'], 2)} ₽ "
                             "(день/ночь, днём)", "ПП № 442 (Основные положения), п. 65(3); отчёты ТНС"],
        ["Тариф (город, до 1 100 кВт·ч в мес.)",
         f"{ru(d['tariff_now'], 2)} ₽; день/ночь — {ru(d['zones'][0], 2)} / {ru(d['zones'][1], 2)} ₽",
         "приказ ДГРТ № 18/2025-э"],
        ["Помесячный зачёт", "отданное в сеть за месяц сначала гасит покупку из сети (на тарифе день/ночь — "
                             "по зонам), по цене выкупа продаётся остаток", "договор ТНС с владельцем станции, п. 5.2"],
        ["Подключение к сети", "21 183 ₽, но не больше 11 470 ₽ за кВт", "приказ ДГРТ № 19/2025-э"],
        ["Налог", "доход от излишков без НДФЛ до 01.01.2029; НДС с гражданина нет", "ст. 217 НК РФ; договор ТНС, п. 2.2"],
    ]
    table(s, X0, Y0 + 0.05, W0, rows, [2.3, 5.1, 3.1], size=14, row_h=0.5, name="Таблица правил")
    textbox(s, X0, 6.12, W0, 0.5, [{"runs": [("Всё это — в расчёте каждого варианта: инвертор не мощнее договора "
                                              "с сетью и не больше 50 кВт, доход от излишков — по цене выкупа "
                                              "для тарифа владельца", False)], "size": 14, "color": MUTED,
                                    "after": 0}], name="Пояснение")
    notes(s, *SP["rules"])

    # 6. Энергорасчёт
    s = add_slide(prs, L_TWO, "Выработка — по паспорту панели")
    fill(s.placeholders[2].text_frame, [
        {"runs": [("Считаем сами, по часам, для конкретной панели и крыши:", True)], "after": 10},
        {"runs": [("погода — типичный метеогод PVGIS по 2005–2023 гг.", False)], "bullet": True},
        {"runs": [("свет на скат: наклон, сторона света, отражение", False)], "bullet": True},
        {"runs": [("температура панели и слабый свет — по паспорту", False)], "bullet": True},
        {"runs": [("потери системы 11,4 %, КПД и пределы инвертора", False)], "bullet": True},
        {"runs": [("Сторона света видна в расчёте: ", True),
                  ("восток и запад дают на 17–21 % меньше юга", False)], "after": 0},
    ], size=17)
    place(s.placeholders[2], 1.95, 2.0, 5.0, 4.65)
    s.placeholders[1]._element.getparent().remove(s.placeholders[1]._element)
    yv = d["yv"]
    cd = CategoryChartData()
    cd.categories = ["Краснодар", "Майкоп"]
    cd.add_series("Наш расчёт, типичный метеогод", [round(yv.loc[c, "ours"]) for c in ("krasnodar", "maykop")])
    cd.add_series("PVGIS, среднее 2005–2023", [round(yv.loc[c, "pvgis"]) for c in ("krasnodar", "maykop")])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(7.15), Inches(Y0), Inches(5.27), Inches(3.75), cd)
    gf.name = "Диаграмма выработка"
    style_chart(gf.chart, "Выработка за год, кВт·ч на 1 кВт панелей", [BLUE, GREY])
    gf.chart.value_axis.minimum_scale = 0
    textbox(s, 7.15, 5.85, 5.27, 0.8, [{"runs": [
        ("На одной и той же погоде наш расчёт на ", False),
        (f"{ru(yv.dmean_lo.min(), 1)}–{ru(yv.dmean_hi.max(), 1)} %", True),
        (" выше PVGIS — причину разбираем (T3.7)", False)], "after": 0}], size=14, name="Сверка")
    notes(s, *SP["yield"])

    # 7. Смета на примере
    s = add_slide(prs, L_TITLE_ONLY, "Смета «под ключ» по ценам магазинов")
    res = run_configurator("krasnodar", "city_single", portrait_load("day_absent", "krasnodar"))
    best = res["configs"][0]
    bom = {r[0]: r for r in best["bom"]}
    group = lambda names: sum(bom[n][4] for n in names)  # noqa: E731
    rows = [
        ["Статья", "Что входит", ("Сумма, ₽",)],
        ["Панели", f"{best['n_panels']} × {best['panel'].split(' (')[0]}", (ru(bom['Панели'][4]),)],
        ["Инвертор", best["inverter"], (ru(bom["Инвертор"][4]),)],
        ["Крепёж и кабель", "крепёж, кабель 4 мм², разъёмы MC4",
         (ru(group(["Крепёж на кровлю", "Кабель солнечный 4 мм²", "Разъёмы MC4"])),)],
        ["Защита", "УЗИП, автомат, бокс",
         (ru(group(["УЗИП постоянного тока", "Автомат переменного тока", "УЗИП переменного тока",
                    "Бокс для защиты"])),)],
        ["Монтаж", "20 % от оборудования (по КП 15–25 %)", (ru(bom["Монтаж и пусконаладка"][4]),)],
        ["Подключение и доставка", "приказ ДГРТ № 19/2025-э; доставка — допущение",
         (ru(bom["Подключение к сети"][4] + bom["Доставка"][4]),)],
        ["Итого", f"{ru(best['kwp'], 2)} кВт, Краснодар", (ru(best["capex_rub"]),)],
    ]
    table(s, X0, Y0 + 0.05, 6.9, rows, [1.75, 3.55, 1.6], size=14, row_h=0.52, name="Таблица сметы",
          bold_last=True)
    textbox(s, 9.1, Y0 + 0.05, 3.32, 4.5, [
        {"runs": [("Пример: семья, которая днём на работе, город, одноставочный тариф", True)], "after": 10},
        {"runs": [("Цены — только с 18 проверенных магазинов из 30, обычные, без скидок", False)],
         "bullet": True},
        {"runs": [("В каталоге 3 панели и 7 инверторов Deye с паспортами производителей", False)],
         "bullet": True},
        {"runs": [("Смета сходится с КП установщиков: около 3 кВт — 195 тыс. ₽, по КП 194–209 тыс.", False)],
         "bullet": True},
    ], size=15, name="Пояснение сметы")
    notes(s, *SP["smeta"])

    # 8. Результаты на портретах команды 1
    s = add_slide(prs, L_TITLE_ONLY, "Подбор для типичных семей Краснодара и Майкопа")
    rows = [["Портрет команды 1", ("Потребление, кВт·ч/год",), "Станция",
             ("Цена, тыс. ₽",), ("Срок по 4 тарифам, лет",)]]
    for p in d["portraits"]:
        rng = lambda a, nd=0, k=1: (ru(a[0] / k, nd) if round(a[0] / k, nd) == round(a[1] / k, nd)  # noqa: E731
                                    else f"{ru(a[0] / k, nd)}–{ru(a[1] / k, nd)}")
        inv = "/".join(ru(v, 0) for v in p["inv"])
        load10 = tuple(round(v, -1) for v in p["load"])
        rows.append([PORTRAIT_NAMES[p["pid"]], (rng(load10, 0),),
                     f"{rng(p['n'])} пан., {rng(p['kwp'], 2)} кВт; инвертор {inv} кВт",
                     (rng(p["capex"], 0, 1000),), (rng(p["pb"], 1),)])
    table(s, X0, Y0 + 0.05, W0, rows, [2.6, 1.7, 3.35, 1.2, 1.65], size=15, row_h=0.48, name="Таблица подбора")
    lim = d["limits"]
    n = d["n_cases"]
    facts = [
        ("0 из 4", "портретов получили «типовые» 3, 5 или 10 кВт"),
        (f"{lim.get('потребление дома', 0)} из {n}", "случаев размер ограничило потребление дома"),
        (f"{ru(d['self'][0])}–{ru(d['self'][1])} %", "выработки дом расходует сам, остальное продаёт"),
    ]
    for k, (big, small) in enumerate(facts):
        x = X0 + k * (W0 + 0.3) / 3
        w = (W0 - 0.6) / 3
        panel(s, x, 5.22, w, 1.38, f"Факт {k + 1} фон")
        textbox(s, x + 0.15, 5.25, w - 0.3, 0.6, [{"runs": [(big, True)], "size": 28, "color": BLUE, "after": 0}],
                name=f"Факт {k + 1} число")
        textbox(s, x + 0.15, 5.83, w - 0.3, 0.8, [{"runs": [(small, False)], "size": 14, "after": 0}],
                name=f"Факт {k + 1} подпись")
    notes(s, *SP["results"])

    # 9. Гипотеза 2
    s = add_slide(prs, L_TWO, "Гипотеза 2: предварительный вывод")
    fill(s.placeholders[2].text_frame, [
        {"runs": [("Гипотеза: ", True), ("срок окупаемости определяется прежде всего тарифом и долей "
                                         "самопотребления, а доход от излишков — не больше 20 % годового "
                                         "эффекта", False)], "after": 12},
        {"runs": [("Часть А не подтверждается: ", True),
                  ("сильнее всего на срок влияют стоимость станции (+2,7…+4,4 года) и цена выкупа "
                   "(+2,2…+3,4 года); доля самопотребления — лишь на 4–7-м месте (анализ этапа 2)", False)],
         "bullet": True},
        {"runs": [("Часть Б не подтверждается: ", True),
                  (f"с помесячным зачётом доход от излишков — {ru(d['exp_real'][0])}–{ru(d['exp_real'][1])} % "
                   f"эффекта у станций 3/5/10 кВт и {ru(d['exp_cfg'][0])}–{ru(d['exp_cfg'][1])} % у подобранных; "
                   f"не больше 20 % — в {d['b_cfg'][0]} из {d['b_cfg'][1]} подборов, а нужно в 80 %", False)],
         "bullet": True},
        {"runs": [("Вывод для продукта: ", True), ("окупаемость решают цена станции и цена выкупа — "
                                                   "поэтому нужны точная смета и подбор под дом", False)],
         "after": 0},
    ], size=16, space_after=10)
    place(s.placeholders[2], 1.95, 2.0, 5.45, 4.65)
    s.placeholders[1]._element.getparent().remove(s.placeholders[1]._element)
    cd = CategoryChartData()
    short = {"day_absent": "Днём на работе", "home_all_day": "Дома весь день", "ac": "С кондиционером",
             "el_heating": "С электроотоплением"}
    order = d["portraits"][::-1]          # у горизонтальной диаграммы первая категория — внизу
    cd.categories = [short[p["pid"]] for p in order]
    cd.add_series("меньше всего", [round(p["exp"][0]) for p in order])
    cd.add_series("больше всего", [round(p["exp"][1]) for p in order])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(7.6), Inches(Y0), Inches(4.82), Inches(4.2), cd)
    gf.name = "Диаграмма доля излишков"
    style_chart(gf.chart, "Доход от излишков в годовом эффекте подобранных станций, % (с зачётом)", [GREY, BLUE],
                fmt="0")
    gf.chart.value_axis.maximum_scale = 100
    gf.chart.value_axis.minimum_scale = 0
    textbox(s, 7.6, 6.25, 4.82, 0.4, [{"runs": [("Порог гипотезы — 20 %. Разброс — по городам и тарифам",
                                                  False)], "size": 12, "color": MUTED, "after": 0}],
            name="Пояснение диаграммы")
    notes(s, *SP["hypothesis"])

    # 10. Веб-сервис
    s = add_slide(prs, L_TITLE_ONLY, "Веб-сервис")
    pic_h = 4.62
    pic_w = pic_h * 1500 / 900
    pic = s.shapes.add_picture(str(SHOT), Inches(X0), Inches(Y0), Inches(pic_w), Inches(pic_h))
    pic.name = "Скриншот веб-сервиса"
    pic.line.color.rgb = RGBColor(0xBF, 0xBF, 0xBF)
    pic.line.width = Pt(0.75)
    x = X0 + pic_w + 0.3
    textbox(s, x, Y0, X0 + W0 - x, pic_h, [
        {"runs": [("Ввод: ", True), ("дом и тариф, потребление, крыша, договор с сетью, цель", False)],
         "after": 12},
        {"runs": [("Вывод: ", True), ("рекомендация одной фразой, смета, схема цепочек, что ограничило размер, "
                                      "4 запасных варианта", False)], "after": 12},
        {"runs": [("Проверка: ", True), (f"{n_tests} {plural(n_tests, 'автотест', 'автотеста', 'автотестов')}", False)], "after": 12},
        {"runs": [("Дальше: ", True), ("график лето/зима, подсказки, публикация до 16.12", False)], "after": 0},
    ], size=15, name="Описание веб-сервиса")
    notes(s, *SP["web"])

    # 12. Команда
    s = add_slide(prs, L_TITLE_ONLY, "Команда")
    rows = [
        ["Участник", "Роль", "Отвечает за"],
        ["Прищепа Максим (Р1)", "руководитель", "экономическая модель, конфигуратор, интеграция, проверка работ"],
        ["Власов Кирилл (Р2)", "данные и правила рынка", "нормативка, тарифы, цена выкупа ТНС, КП, каталог оборудования"],
        ["Цирульник Юрий (Р3)", "аналитика", "чувствительность, тепловая карта, гипотеза 2, проверка выработки"],
        ["Кривоносов Вячеслав (Р4)", "веб-сервис", "интерфейс, ввод и вывод, графики, публикация"],
        ["Рогочий Александр (Р5)", "качество и отчёты", "автотесты, отчёты, презентации, материалы заявки"],
    ]
    table(s, X0, Y0 + 0.05, W0, rows, [3.0, 2.4, 5.1], size=15, row_h=0.56, name="Таблица команды")
    panel(s, X0, 5.68, W0, 0.85, "Команда 1 фон")
    textbox(s, X0 + 0.25, 5.68, W0 - 0.5, 0.85, [{"runs": [
        ("Команда 1 (энергетика): ", True), ("профили потребления семей по часам и функция построения профиля по "
                                            "квитанциям — вход нашего конфигуратора", False)], "after": 0}],
            size=16, anchor=MSO_ANCHOR.MIDDLE, name="Команда 1")
    notes(s, *SP["team"])

    # 11. План до защиты
    s = add_slide(prs, L_TITLE_ONLY, "План до защиты")
    steps = [("15.11", "цена выкупа за октябрь"), ("22.11", "инверторы 5–12 кВт в каталоге"),
             ("30.11", "интерфейс, проверка выработки, тесты"), ("04.12", "финальные данные команды 1"),
             ("07.12", "график лето/зима, подсказки"), ("14.12", "гипотеза 2, материалы заявки"),
             ("16.12", "публикация веб-сервиса"), ("20–21.12", "итоговая презентация и отчёт")]
    line_y = 3.75
    x_first, x_last = X0 + 0.55, X0 + W0 - 0.55
    ln = s.shapes.add_connector(1, Inches(x_first), Inches(line_y), Inches(x_last), Inches(line_y))
    ln.line.color.rgb = BLUE
    ln.line.width = Pt(2)
    ln.name = "Линия времени"
    step = (x_last - x_first) / (len(steps) - 1)
    for k, (date, what) in enumerate(steps):
        cx = x_first + k * step
        dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - 0.13), Inches(line_y - 0.13), Inches(0.26),
                                 Inches(0.26))
        dot.fill.solid()
        dot.fill.fore_color.rgb = BLUE
        dot.line.fill.background()
        dot.shadow.inherit = False
        dot.name = f"Точка {date}"
        up = k % 2 == 0
        w = 2.5
        textbox(s, cx - w / 2, line_y - 1.3 if up else line_y + 0.28, w, 1.0,
                [{"runs": [(date, True)], "size": 18, "color": BLUE, "after": 2, "align": PP_ALIGN.CENTER},
                 {"runs": [(what, False)], "size": 14, "after": 0, "align": PP_ALIGN.CENTER}],
                anchor=MSO_ANCHOR.BOTTOM if up else MSO_ANCHOR.TOP, name=f"Этап {date}")
    panel(s, X0, 5.55, W0, 1.0, "Ждём фон")
    textbox(s, X0 + 0.25, 5.55, W0 - 0.5, 1.0, [{"runs": [
        ("Ждём извне: ", True), ("финальные профили команды 1 и их сверку с реальными семьями; отчёт ТНС "
                                 "с ценой выкупа за октябрь", False)], "after": 0}], size=16, anchor=MSO_ANCHOR.MIDDLE,
            name="Ждём извне")
    notes(s, *SP["plan"])

    for sl in prs.slides:
        drop_empty_placeholders(sl)
    order = ["title", "problem", "actual", "analogs", "solution", "rules", "yield", "smeta", "results",
             "hypothesis", "web", "team", "plan"]
    titles = {k: (sl.shapes.title.text_frame.text if sl.shapes.title is not None else "").replace(chr(0xA0), " ")
              for k, sl in zip(order, prs.slides)}
    assert len(prs.slides) == len(order), "порядок слайдов и текстов разошёлся"
    write_speech_md(order, titles, SP)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(OUT, len(prs.slides), "слайдов")


if __name__ == "__main__":
    if len(sys.argv) > 1:   # другой путь — например, если файл открыт в PowerPoint
        OUT = Path(sys.argv[1])
    build()
