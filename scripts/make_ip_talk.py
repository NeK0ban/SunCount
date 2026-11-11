"""Презентация к «Экспертной трубе по интеллектуальной собственности» (18.11.2026) — reports/ip_truba/.

Формат задан организаторами: 3 минуты выступления, три слайда — «Проблема, решение и целевая аудитория»,
«Этапы реализации, ресурсы и финансы», «Объекты интеллектуальной собственности» (рекомендации и памятка для команд).
Оформление — шаблон АГУ, как у промежуточного доклада; общие функции — из scripts/make_interim_talk.py.
На слайдах нет схем, кода и формул: публичный показ считается раскрытием (памятка, раздел «Чего не показывать»).

Версия 11.11.2026 — по правкам наставника на распечатке: простое название, команда справа, дата внизу по центру,
заголовки выше, крупнее шрифт и меньше текста, целевая аудитория — компании, вместо метрики — объём рынка,
этапы — линией времени, суммы бюджета на пилот и оформление ИС.

Выход: reports/ip_truba/SunCount_IS_truba.pptx и tekst_vystupleniya.md (текст на 3 минуты, он же в заметках).
Запуск: python scripts/make_ip_talk.py [путь.pptx]
"""
import sys
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_interim_talk import (BLUE, L_TITLE, L_TITLE_ONLY, MUTED, NB, TEMPLATE, W0, X0, add_slide,  # noqa: E402
                               clear_slides, drop_empty_placeholders, fill, load_numbers, notes, panel, place, textbox)
from make_interim_talk import ru as _ru  # noqa: E402


def ru(x, nd=0) -> str:
    """Как в промежуточном докладе; nd < 0 — округление до десятков (-1) или сотен (-2): 289,6 → «290»."""
    return _ru(round(x, nd)) if nd < 0 else _ru(x, nd)

OUT_DIR = ROOT / "reports" / "ip_truba"
OUT = OUT_DIR / "SunCount_IS_truba.pptx"
SPEECH_MD = OUT_DIR / "tekst_vystupleniya.md"

TITLE = "SunCount — сервис подбора солнечной электростанции для частного дома"
TEAM = "Власов К., Прищепа М., Цирульник Ю., Кривоносов В., Рогочий А."
MENTOR = "ст. преподаватель кафедры АСОИУ Онищенко С. В."   # так записал наставник на распечатке 11.11.2026
DATE = "18 ноября 2026 г., Майкоп"

N_INSTALLERS, N_SHOPS = 14, 18          # docs/grant/customers.md, 09.11.2026
N_HOUSES = 1_160_000                    # индивидуальных домов в крае, Краснодарстат (Коммерсантъ, 16.06.2017), market.md
NESK_TO_TNS = 705 / 1997                # покупка у микрогенерации май–сентябрь 2026: НЭСК 705 МВт·ч, ТНС 1 997 (market.md)
# Гипотезы и оценки команды (не статистика; обоснование — docs/grant/market.md, раздел «Объём рынка для SunCount»):
SUB_PRICE = 5000                        # подписка компании, ₽ в месяц — гипотеза, проверяется на пилоте
SOM_COMPANIES = 10                      # компаний-клиентов за два года из 32 найденных
PILOT_BUDGET = 1_000_000                # пилот: работа команды, сервер, выезды на дома — оценка
IP_BUDGET = 100_000                     # оформление ИС: пошлины Роспатента, второй класс знака, поверенный — оценка

WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def market(d: dict) -> dict:
    """Объём рынка: TAM — станция на каждом частном доме края, SAM — новые станции за год, SOM — наша выручка."""
    vol = pd.read_csv(ROOT / "data" / "buyback_prices.csv", encoding="utf-8-sig").set_index("month").volume_total_kwh
    prev, last = vol["2024-10":"2025-09"].sum(), vol["2025-10":"2026-09"].sum()   # ТНС, 12 месяцев, кВт·ч
    em = pd.read_csv(ROOT / "data" / "energy_metrics.csv", encoding="utf-8-sig")
    exp5 = em[em.pv_kw == 5].export_kwh.mean()      # выдача в сеть станции 5 кВт за год, команда 1
    stations_prev, stations_last = prev / exp5, last / exp5
    new_year = (stations_last - stations_prev) * (1 + NESK_TO_TNS)
    capex = float(d["ex"].capex_rub.mean())          # средняя смета по 64 примерам конфигуратора
    return dict(growth=last / prev, stations_prev=stations_prev, stations_last=stations_last, new_year=new_year,
                capex=capex, tam=N_HOUSES * capex, sam=new_year * capex, som=SOM_COMPANIES * SUB_PRICE * 12)


def numbers() -> dict:
    d = load_numbers()
    d["m"] = market(d)
    return d


def approx(text: str) -> str:
    return text.replace("≈ ", "≈" + NB)


def speech(d: dict) -> list:
    m = d["m"]
    a, b = ru(d["capex"][0] / 1000), ru(d["capex"][1] / 1000)
    return [
        ("Титул", "Прищепа Максим (Р1)",
         "Добрый вечер. Мы — команда 2 Адыгейского государственного университета. Наш проект SunCount — сервис "
         "подбора солнечной электростанции для частного дома."),
        ("Проблема, решение и целевая аудитория", "Прищепа Максим (Р1)",
         "Человек хочет поставить дома солнечную станцию или другую установку на возобновляемых источниках, но не "
         f"знает, что выбрать и окупится ли она. Станция стоит от {a} до {b} тысяч рублей, ошибка обходится дорого. "
         "Наш веб-сервис подбирает станцию под конкретный дом: пользователь получает состав оборудования, смету под "
         "ключ и срок окупаемости по своему счёту за электричество. Целевая аудитория — компании, которые продают "
         f"станции: {N_INSTALLERS} установщиков и {N_SHOPS} магазинов оборудования в крае и Адыгее. Сервис на их сайте "
         "считает станцию клиенту, а для владельца дома он бесплатный. Объём рынка: потенциал — около "
         f"{ru(m['tam'] / 1e9, -1)} миллиардов рублей, если станция появится на каждом частном доме края. Сегодня "
         f"ставят около {ru(m['new_year'], -2)} новых станций в год, это около {ru(m['sam'] / 1e6, -1)} миллионов "
         "рублей, и за год рынок вырос втрое. Наша цель — десять компаний-клиентов, около "
         f"{ru(m['som'] / 1000, -2)} тысяч рублей в год."),
        ("Этапы реализации, ресурсы и финансы", "Рогочий Александр (Р5)",
         "Исследование и прототип сделаны в ходе учебного проекта, без бюджета. Рабочая версия сервиса будет готова "
         "к 21 декабря, тоже в рамках курса. В январе оформляем права: соглашение авторов и заявки в Роспатент на "
         f"программу, базу данных и товарный знак — по нашей оценке, около {ru(IP_BUDGET / 1000)} тысяч рублей. Затем "
         "пилот с двумя установщиками на 3–10 реальных домах: сверяем смету и выработку. Пилот оцениваем примерно в "
         "миллион рублей — это работа команды, сервер и выезды на объекты. Дальше — подписки установщиков и "
         "магазинов, развитие идёт из выручки."),
        ("Объекты интеллектуальной собственности", "Прищепа Максим (Р1)",
         "Объектов у нас три. Главный — программа для ЭВМ: в ней соединены правила рынка, каталог оборудования и "
         "расчёт по часам. Охраняем её авторским правом и регистрируем в Роспатенте. Второй — база данных: каталог "
         "с ценами, тарифы и цены выкупа. Третий — название, товарный знак. Патент не заявляем: методика расчёта — "
         "математический метод, по закону это не изобретение. Авторы — пять участников команды, соглашение о правах "
         "подписываем в ноябре. Чужие данные и библиотеки, например погоду PVGIS, используем по их открытым "
         "лицензиям со ссылкой на источник. Заказчик получает неисключительную лицензию, права остаются у авторов. "
         "Вопрос к вам: кого правильно указать заявителем — авторов или вуз?"),
    ]


def lift_title(s) -> None:
    """Заголовок выше, чем в макете (правка наставника): по центру полосы между верхним краем и линией."""
    place(s.shapes.title, X0, 0.2, W0, 1.25)
    s.shapes.title.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE


def line(s, x1, y1, x2, y2, width=3.0, arrow=False, color=BLUE, name=None):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    if arrow:
        ln = c.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    if name:
        c.name = name
    return c


def dot(s, cx, cy, r, done, name):
    o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - r), Inches(cy - r), Inches(2 * r), Inches(2 * r))
    o.fill.solid()
    o.fill.fore_color.rgb = BLUE if done else WHITE
    o.line.color.rgb = BLUE
    o.line.width = Pt(2.5)
    o.shadow.inherit = False
    o.name = name
    return o


def build() -> None:
    d = numbers()
    m = d["m"]
    sp = speech(d)
    prs = Presentation(str(TEMPLATE))
    clear_slides(prs)

    # Титул: простое название, команда и наставник справа, дата и город внизу по центру
    s = add_slide(prs, L_TITLE)
    place(s.shapes.title, X0, 1.0, W0, 2.0)
    s.shapes.title.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    fill(s.shapes.title.text_frame, [{"runs": [(TITLE, False)], "size": 40, "color": BLUE, "after": 0}])
    sub = s.placeholders[1]
    place(sub, 6.12, 3.3, 6.3, 1.85)
    sub.text_frame.vertical_anchor = MSO_ANCHOR.TOP
    fill(sub.text_frame, [
        {"runs": [("Команда 2: ", True), (TEAM, False)], "after": 10},
        {"runs": [("Наставник: ", True), (MENTOR, False)], "after": 0},
    ], size=18, align=PP_ALIGN.RIGHT)
    textbox(s, 0, 5.3, 13.333, 0.45, [{"runs": [(DATE, False)], "align": PP_ALIGN.CENTER, "after": 0}], size=18,
            name="Дата и город", anchor=MSO_ANCHOR.MIDDLE)
    notes(s, sp[0][1], sp[0][2])

    # Слайд 1. Проблема, решение и целевая аудитория; справа — объём рынка
    s = add_slide(prs, L_TITLE_ONLY, sp[1][0])
    lift_title(s)
    lw = 6.25
    textbox(s, X0, 2.02, lw, 1.1, [
        {"runs": [("Проблема. ", True), ("Потенциальный покупатель не знает, какую установку ВИЭ ему выбрать и "
                                         "окупится ли она. Ошибка стоит сотни тысяч рублей.", False)], "after": 0},
    ], size=20, name="Проблема")
    textbox(s, X0, 3.1, lw, 1.45, [
        {"runs": [("Решение. ", True), ("Веб-сервис подбирает станцию под конкретный случай. Пользователь получает "
                                        "состав оборудования, смету «под ключ» и срок окупаемости по своему счёту "
                                        "за электричество.", False)], "after": 0},
    ], size=20, name="Решение")
    panel(s, X0, 4.6, lw, 2.05, "Аудитория фон")
    textbox(s, X0 + 0.2, 4.66, lw - 0.4, 1.95, [
        {"runs": [("Целевая аудитория — компании", True)], "size": 20, "color": BLUE, "after": 4},
        {"runs": [(f"Установщики солнечных станций — {N_INSTALLERS} компаний", False)], "bullet": True, "after": 2},
        {"runs": [(f"Магазины оборудования — {N_SHOPS} компаний", False)], "bullet": True, "after": 2},
        {"runs": [("Сервис на их сайте считает станцию клиенту; для владельца дома бесплатно", False)],
         "bullet": True, "after": 0},
    ], size=18, name="Аудитория")

    rx = X0 + lw + 0.3
    rw = X0 + W0 - rx
    textbox(s, rx, 2.02, rw, 0.45, [{"runs": [("Объём рынка (оценка)", True)], "color": BLUE, "after": 0}],
            size=20, name="Рынок заголовок")
    funnel = [
        ("TAM · потенциал", f"≈ {ru(m['tam'] / 1e9, -1)} млрд ₽",
         ["станция на каждом из", f"{ru(N_HOUSES / 1e6, 2)} млн частных домов края"]),
        ("SAM · рынок сегодня", f"≈ {ru(m['sam'] / 1e6, -1)} млн ₽ в год",
         [f"≈ {ru(m['new_year'], -2)} новых станций в год,", "за год рынок вырос втрое"]),
        ("SOM · наша выручка", f"≈ {ru(m['som'] / 1e6, 1)} млн ₽ в год",
         [f"{SOM_COMPANIES} компаний × {ru(SUB_PRICE / 1000)} тыс. ₽ в месяц"]),
    ]
    for k, (lab, big, cap) in enumerate(funnel):
        w = rw - 0.3 * k
        x = rx + (rw - w) / 2
        y = 2.52 + k * 1.39
        panel(s, x, y, w, 1.31, f"Рынок {k + 1} фон")
        textbox(s, x + 0.1, y + 0.06, w - 0.2, 1.2, [
            {"runs": [(lab, True)], "size": 13, "color": MUTED, "after": 0, "align": PP_ALIGN.CENTER},
            {"runs": [(approx(big), True)], "size": 24, "color": BLUE, "after": 0, "align": PP_ALIGN.CENTER},
        ] + [{"runs": [(approx(c), False)], "size": 14, "after": 0, "align": PP_ALIGN.CENTER} for c in cap],
            size=14, name=f"Рынок {k + 1}")
    notes(s, sp[1][1], sp[1][2])

    # Слайд 2. Этапы — линия времени с точками, подробности под ней
    s = add_slide(prs, L_TITLE_ONLY, sp[2][0])
    lift_title(s)
    stages = [
        ("окт.–нояб. 2026", "Исследование и прототип", True,
         f"Правила рынка, 9{NB}аналогов, прототип", "Команда из 5 человек, наставник",
         "0 ₽", "выполнено в ходе учебного проекта"),
        ("до 21.12.2026", "MVP — рабочая версия", False,
         "Веб-сервис: подбор станции, смета, окупаемость", "Команда, профили потребления",
         "0 ₽", "выполняется в ходе учебного проекта"),
        ("январь 2027", "Оформление ИС", False,
         "Соглашение авторов, заявки в Роспатент", "Юрист по ИС, согласование с вузом",
         f"≈ {ru(IP_BUDGET / 1000)} тыс. ₽", "оценка"),
        ("февр.–март 2027", "Пилот", False,
         "2 установщика, до 10 домов: сверка сметы и выработки", "Установщики, сервер, выезды на дома",
         f"≈ {ru(PILOT_BUDGET / 1e6)} млн ₽", "оценка"),
        ("2027–2028", "Продажи", False,
         "Подписки установщиков и магазинов", "Продажи, обновление цен и тарифов",
         "из выручки", f"≈ {ru(m['som'] / 1e6, 1)} млн ₽ в год"),
    ]
    cw = W0 / len(stages)
    ty = 2.6
    line(s, X0 + 0.15, ty, X0 + W0, ty, width=3, arrow=True, name="Линия времени")
    rows_y = {"Результат": (3.62, 0.95), "Ресурсы": (4.66, 0.85), "Бюджет": (5.62, 0.98)}
    for lab, (y, h) in rows_y.items():
        textbox(s, 0.15, y, X0 - 0.3, h, [{"runs": [(lab, True)], "color": MUTED, "after": 0,
                                           "align": PP_ALIGN.RIGHT}], size=15, name=f"Подпись {lab}")
        line(s, X0, y - 0.06, X0 + W0, y - 0.06, width=0.75, color=RGBColor(0xBF, 0xBF, 0xBF), name=f"Черта {lab}")
    for k, (date, name, done, res, rsc, money, note) in enumerate(stages):
        cx = X0 + cw * (k + 0.5)
        x = cx - cw / 2 + 0.05
        w = cw - 0.1
        textbox(s, x, 2.04, w, 0.36, [{"runs": [(date, True)], "color": BLUE, "after": 0, "align": PP_ALIGN.CENTER}],
                size=16, name=f"Этап {k + 1} дата")
        dot(s, cx, ty, 0.15, done, f"Этап {k + 1} точка")
        textbox(s, x, 2.82, w, 0.7, [{"runs": [(name, True)], "after": 0, "align": PP_ALIGN.CENTER}],
                size=18, name=f"Этап {k + 1} название")
        textbox(s, x, rows_y["Результат"][0], w, rows_y["Результат"][1],
                [{"runs": [(res, False)], "after": 0, "align": PP_ALIGN.CENTER}], size=16, name=f"Этап {k + 1} результат")
        textbox(s, x, rows_y["Ресурсы"][0], w, rows_y["Ресурсы"][1],
                [{"runs": [(rsc, False)], "after": 0, "align": PP_ALIGN.CENTER}], size=16, name=f"Этап {k + 1} ресурсы")
        textbox(s, x, rows_y["Бюджет"][0], w, rows_y["Бюджет"][1], [
            {"runs": [(approx(money), True)], "size": 20, "color": BLUE, "after": 0, "align": PP_ALIGN.CENTER},
            {"runs": [(approx(note), False)], "size": 13, "color": MUTED, "after": 0, "align": PP_ALIGN.CENTER},
        ], size=16, name=f"Этап {k + 1} бюджет")
    notes(s, sp[2][1], sp[2][2])

    # Слайд 3. Объекты интеллектуальной собственности — три карточки и четыре тезиса
    s = add_slide(prs, L_TITLE_ONLY, sp[3][0])
    lift_title(s)
    objs = [
        ("Программа для ЭВМ", "подбор станции, смета, окупаемость, веб‑интерфейс",
         "авторское право, свидетельство Роспатента"),
        ("База данных", "каталог оборудования, тарифы, цены выкупа",
         "авторское право, свидетельство Роспатента"),
        ("Название SunCount", "обозначение сервиса, классы МКТУ 9 и 42",
         "товарный знак, регистрация в Роспатенте"),
    ]
    gap = 0.25
    kw = (W0 - 2 * gap) / 3
    for k, (head, what, how) in enumerate(objs):
        x = X0 + k * (kw + gap)
        panel(s, x, 2.06, kw, 2.42, f"Объект {k + 1} фон")
        textbox(s, x + 0.16, 2.12, kw - 0.32, 2.32, [
            {"runs": [(head, True)], "size": 22, "color": BLUE, "after": 6},
            {"runs": [(what, False)], "after": 8},
            {"runs": [("Охрана: ", True), (how, False)], "after": 0},
        ], size=18, name=f"Объект {k + 1}")
    textbox(s, X0, 4.62, W0, 2.05, [
        {"runs": [("Патент не заявляем: ", True),
                  ("математический метод — не изобретение (ст. 1350 ГК РФ)", False)], "after": 8},
        {"runs": [("Авторы — 5 участников команды: ", True), ("соглашение о правах подписываем в ноябре 2026 г.",
                                                              False)], "after": 8},
        {"runs": [("Чужое — по открытым лицензиям: ", True),
                  ("погода PVGIS (CC BY 4.0), библиотека pvlib (BSD)", False)], "after": 8},
        {"runs": [("Заказчику — неисключительная лицензия: ", True), ("права остаются у авторов", False)],
         "after": 0},
    ], size=20, name="Права и лицензия")
    notes(s, sp[3][1], sp[3][2])

    for sl in prs.slides:
        drop_empty_placeholders(sl)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))

    words = [len(x[2].split()) for x in sp]
    lines = ["# Текст выступления — Экспертная труба по интеллектуальной собственности", "",
             "18 ноября 2026 г., онлайн, с 18:00 МСК. На выступление — 3 минуты, затем 5 минут вопросов и 5 минут "
             "обратной связи. Презентация — `reports/ip_truba/SunCount_IS_truba.pptx`, тот же текст стоит в заметках "
             "к слайдам. Собирается скриптом `scripts/make_ip_talk.py`: править текст нужно в функции `speech()`.", "",
             "Версия 11.11.2026 — после правок наставника. Как посчитан объём рынка и откуда суммы бюджета — "
             "`pamyatka_komande.md`, раздел «Объём рынка и бюджет».", "",
             f"Всего {sum(words)} слов — около {ru(sum(words) / 130, 1)} минуты при темпе 130 слов в минуту. Больше "
             "390 слов в три минуты не помещается.", ""]
    for n, (title, who, text) in enumerate(sp):
        head = "Титул" if n == 0 else f"Слайд {n}. {title}"
        lines += [f"## {head}", "", f"**Говорит:** {who}, около {round(len(text.split()) / 130 * 60 / 5) * 5} секунд.",
                  "", text, ""]
    SPEECH_MD.write_text("\n".join(lines), encoding="utf-8")
    print(OUT, len(prs.slides), "слайда;", sum(words), "слов")
    print("рынок:", {k: round(v, 3) for k, v in m.items()})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        OUT = Path(sys.argv[1])
    build()
