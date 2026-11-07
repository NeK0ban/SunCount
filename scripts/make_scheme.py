"""Схема решения SunCount (версия 5.0 мастер-ТЗ, 08.11.2026): конфигуратор домашней микрогенерации.

По замечаниям наставника (06.11.2026): без блока экономики (о ней — устно), без PVGIS и Streamlit как
отдельных блоков; в центре — подбор конфигурации под дом пользователя.
Выход: reports/scheme/SunCount_scheme.png. Запуск: python scripts/make_scheme.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "scheme"
DARK, MID, LIGHT, GREY = "#1f4e79", "#2e75b6", "#dbe5f1", "#f2f2f2"
T1_FILL, T1_EDGE = "#fff2cc", "#bf9000"
plt.rcParams["font.family"] = "DejaVu Sans"
NL = chr(10)


def lines(*parts: str) -> str:
    return NL.join(parts)


def box(ax, x, y, w, h, title, body="", fill=LIGHT, edge=MID, tcolor=DARK, bcolor="#222222", tsize=12.5,
        bsize=10.2, dashed=False, lw=1.6, title_dy=0.028, body_dy=0.075):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008,rounding_size=0.012", fc=fill, ec=edge,
                                lw=lw, ls="--" if dashed else "-"))
    ax.text(x + w / 2, y + h - title_dy, title, ha="center", va="top", fontsize=tsize, weight="bold", color=tcolor)
    if body:
        ax.text(x + w / 2, y + h - body_dy, body, ha="center", va="top", fontsize=bsize, color=bcolor,
                linespacing=1.35)


def arrow(ax, a, b, color=MID, lw=1.8):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=16, color=color, lw=lw))


fig = plt.figure(figsize=(17, 7.6), dpi=150)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.text(0.5, 0.975, "SunCount — конфигуратор домашней микрогенерации", ha="center", va="top", fontsize=17,
        weight="bold", color=DARK)

# --- вход: что сообщает пользователь
ax.text(0.105, 0.905, "Пользователь сообщает", ha="center", fontsize=13.5, weight="bold", color=DARK)
inputs = [("Дом и тариф", lines("город, тариф,", "приборы в доме")),
          ("Потребление", lines("типичная семья", "или свои квитанции")),
          ("Крыша", lines("площадь, наклон,", "сторона света, тень")),
          ("Договор с сетью", lines("1 или 3 фазы,", "мощность по договору")),
          ("Цель", lines("свои нужды, быстрая", "окупаемость, бюджет"))]
for k, (t, b) in enumerate(inputs):
    box(ax, 0.02, 0.765 - k * 0.155, 0.17, 0.125, t, b, fill=GREY, edge="#7f7f7f", tsize=11.5, bsize=9.6)

# --- база знаний (одна группа)
ax.add_patch(FancyBboxPatch((0.228, 0.545), 0.539, 0.34, boxstyle="round,pad=0.004,rounding_size=0.012",
                            fc="#f7fafd", ec="#bdd7ee", lw=1.2))
ax.text(0.4975, 0.905, "Что знает сервис", ha="center", fontsize=13.5, weight="bold", color=DARK)
knowledge = [
    (lines("Правила", "микрогенерации"),
     lines("лимит выдачи 15 → 50 кВт,", "мощность по договору,", "продажа излишков,", "плата за подключение")),
    (lines("Тарифы и", "цена выкупа"),
     lines("город / село, зоны суток,", "диапазоны, тариф", "по приборам, цена ТНС", "по тарифу владельца")),
    (lines("Каталог", "оборудования"),
     lines("панели и инверторы:", "паспорт и цена продавца;", "крепёж, кабель,", "защита, монтаж")),
]
for k, (t, b) in enumerate(knowledge):
    box(ax, 0.24 + k * 0.177, 0.665, 0.157, 0.21, t, b, body_dy=0.1, bsize=9.8)
box(ax, 0.24, 0.558, 0.33, 0.085, "Профили потребления — команда 1",
    "почасовое потребление типичных семей и по квитанциям", fill=T1_FILL, edge=T1_EDGE, tcolor="#7f6000",
    tsize=10.5, bsize=9.2, title_dy=0.016, body_dy=0.05)
box(ax, 0.594, 0.558, 0.157, 0.085, "Ветер, микро-ГЭС", "в будущем — тот же подход", fill="white", edge=MID,
    tsize=10.5, bsize=9.2, dashed=True, title_dy=0.016, body_dy=0.05)

# --- ядро: подбор конфигурации
box(ax, 0.228, 0.12, 0.539, 0.385, "", fill="#eaf1fb", edge=DARK, lw=2.2)
ax.text(0.4975, 0.488, "Подбор конфигурации", ha="center", va="top", fontsize=14.5, weight="bold", color=DARK)
steps = [("1. Энергорасчёт", lines("выработка каждой панели", "по часам: погода типичного", "года, наклон и сторона",
                                   "крыши, температура,", "паспорт панели")),
         ("2. Перебор вариантов", lines("модель и число панелей,", "инвертор, соединение", "цепочек; проверка правил,",
                                        "паспорта инвертора,", "крыши и бюджета")),
         ("3. Выбор по цели", lines("почасовой баланс дома,", "счёт по тарифу, доход", "от излишков; лучший",
                                    "вариант и запасные"))]
for k, (t, b) in enumerate(steps):
    box(ax, 0.243 + k * 0.177, 0.17, 0.155, 0.25, t, b, fill="white", edge=MID, tsize=11.5, bsize=9.8)
    if k < 2:
        arrow(ax, (0.401 + k * 0.177, 0.3), (0.417 + k * 0.177, 0.3), lw=2)

# --- результат
ax.text(0.885, 0.905, "Что получает пользователь", ha="center", fontsize=13.5, weight="bold", color=DARK)
box(ax, 0.795, 0.33, 0.18, 0.545, "Готовая станция",
    lines("", "", "конкретные модели", "и число панелей", "", "инвертор и схема", "соединения", "",
          "смета «под ключ»", "с ценами продавцов", "", "срок окупаемости", "и выгода за 25 лет", "",
          "что ограничило", "размер станции"),
    fill=DARK, edge=DARK, tcolor="white", bcolor="white", tsize=13, bsize=10.2)
box(ax, 0.795, 0.2, 0.18, 0.1, "Владелец дома", "решение о покупке", fill=GREY, edge="#7f7f7f", tsize=11,
    bsize=9.5, title_dy=0.022, body_dy=0.06)
box(ax, 0.795, 0.075, 0.18, 0.1, "Установщик", "расчёт для клиента вместе с КП", fill=GREY, edge="#7f7f7f",
    tsize=11, bsize=9.5, title_dy=0.022, body_dy=0.06)

# --- стрелки: входы собираются в шину и идут в подбор
for k in range(5):
    y = 0.8275 - k * 0.155
    ax.plot([0.19, 0.207], [y, y], color="#7f7f7f", lw=1.4)
ax.plot([0.207, 0.207], [0.8275 - 4 * 0.155, 0.8275], color="#7f7f7f", lw=1.4)
arrow(ax, (0.207, 0.3), (0.228, 0.3), color="#7f7f7f", lw=1.8)
arrow(ax, (0.4975, 0.545), (0.4975, 0.507), lw=2.2)
arrow(ax, (0.767, 0.45), (0.795, 0.45), color=DARK, lw=2.4)
arrow(ax, (0.885, 0.33), (0.885, 0.302), color=DARK, lw=1.4)

OUT.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT / "SunCount_scheme.png", dpi=150)
print(OUT / "SunCount_scheme.png")
