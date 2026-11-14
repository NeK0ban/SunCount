# app/charts.py
"""График «потребление на фоне выработки» для летнего и зимнего дня (задача T4.4).
Внутри НЕТ streamlit — можно вызывать из теста или консоли.
Данные — только app/calc.py: average_day() (выработка, потребление и самопотребление
средних суток месяца по часам, кВт·ч в час). Никаких выдуманных кривых.
"""
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# Правило 6 архитектуры приложения: Arial с запасным — на сервере без Windows его нет
plt.rcParams["font.family"] = ["Arial", "DejaVu Sans"]

COLOR_LOAD = "#1f6fb2"   # потребление — синий (палитра проекта, T3.5)
COLOR_GEN = "#e08a1e"    # выработка — оранжевый
COLOR_SELF = "#2a9d4b"   # самопотребление — зелёный
DAY_START, DAY_END = 7, 23   # границы дневной зоны тарифа день/ночь (7:00 и 23:00)
EDGES = list(range(25))   # 0…24: последняя ступенька — час 23:00–24:00


def _fmt_kwh(value, _pos) -> str:
    """Подпись оси с десятичной запятой (стиль проекта)."""
    if value == 0:
        return "0"
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _steps(values) -> list:
    """24 значения → 25 точек для steps-post: без повтора последнего значения час 23–24 не рисуется."""
    return list(values) + [values[-1]]


def _draw(ax, day: dict, title: str, ymax: float) -> None:
    """Один график: линии потребления и выработки, заливка самопотребления, границы зон."""
    # каждый час занимает интервал [h, h+1) — ступеньки как в реальном почасовом профиле
    ax.plot(EDGES, _steps(day["load"]), drawstyle="steps-post", color=COLOR_LOAD, lw=1.8,
            label="Потребление дома")
    ax.plot(EDGES, _steps(day["gen"]), drawstyle="steps-post", color=COLOR_GEN, lw=1.8,
            label="Выработка станции")
    ax.fill_between(EDGES, _steps(day["self"]), step="post", color=COLOR_SELF, alpha=0.25,
                    label="Самопотребление")
    for hour in (DAY_START, DAY_END):
        ax.axvline(hour, color="0.45", ls="--", lw=1)
    ax.text(DAY_START + 0.2, ymax * 0.95, "7:00", color="0.3", fontsize=8, va="top")
    ax.text(DAY_END - 0.2, ymax * 0.95, "23:00", color="0.3", fontsize=8, va="top", ha="right")
    ax.set_xlim(0, 24)
    ax.set_ylim(0, ymax)
    ax.set_xticks(range(0, 25, 6))
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_kwh))
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25, lw=0.6)


def _one(day: dict, title: str, ymax: float):
    fig, ax = plt.subplots(figsize=(6, 4.4))
    _draw(ax, day, title, ymax)
    ax.set_ylabel("кВт·ч за час")
    ax.set_xlabel("час суток (местное время)")
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=8.5, bbox_to_anchor=(0.5, 1.0),
               frameon=False, handlelength=1.5, columnspacing=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return fig


def day_figures(summer: dict, winter: dict) -> tuple:
    """Два графика с общей шкалой: средние сутки июля и января. Возвращает две matplotlib Figure (для st.pyplot).
    Отдельные рисунки, а не один на двоих: в веб-сервисе они стоят в двух колонках — на компьютере рядом,
    на телефоне друг под другом во всю ширину (в общем рисунке на телефоне подписи не читаются)."""
    ymax = max(max(summer["load"]), max(summer["gen"]),
               max(winter["load"]), max(winter["gen"])) * 1.15 or 1.0
    return (_one(summer, "Летний день (средние сутки июля)", ymax),
            _one(winter, "Зимний день (средние сутки января)", ymax))
