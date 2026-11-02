# app/texts.py
"""Тексты, форматирование чисел и справочники для калькулятора SunCount."""
import math

from src.econ.inputs import TariffPlan

METHOD_URL = "https://github.com/NeK0ban/SunCount/blob/main/docs/assumptions.md"
INF = float("inf")


def _bad(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def format_rub(value: float) -> str:
    """Рубли с пробелами между разрядами: 51903.12 -> '51 903 ₽'."""
    if _bad(value):
        return "—"
    if value == INF:
        return "∞"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def format_years(value: float) -> str:
    """Годы — один знак после запятой: 7.74 -> '7,7 года'; inf -> 'не окупается за 25 лет'.

    С дробной частью (а она всегда показывается: «8,0») по-русски пишется «года».
    """
    if _bad(value):
        return "—"
    if value == INF:
        return "не окупается за 25 лет"
    return f"{value:.1f}".replace(".", ",") + " года"


def format_years_range(low: float, high: float) -> str:
    """Диапазон сроков: (7.8, 14.6) -> '7,8–14,6 года'."""
    if _bad(low) or _bad(high):
        return "—"
    if high == INF:
        return f"от {format_years(low)} до «не окупается»"
    return f"{low:.1f}–{high:.1f}".replace(".", ",") + " года"


def format_percent(value: float) -> str:
    """Проценты целые: 40.5 -> '41 %'."""
    if _bad(value):
        return "—"
    if value == INF:
        return "∞"
    return f"{value:.0f} %"


def format_kwh(value: float) -> str:
    """Киловатт-часы с пробелами между разрядами: 1500 -> '1 500 кВт·ч'."""
    return f"{value:,.0f}".replace(",", " ") + " кВт·ч"


# Справочник тарифов — строго как в scripts/stub_payback.py (мастер-ТЗ, T4.1)
TARIFFS = {
    "city_single": {
        "label": "Город, одноставочный",
        "plan": TariffPlan("Город, одноставочный", "base", "single", ("base",)),
    },
    "city_zones": {
        "label": "Город, день/ночь",
        "plan": TariffPlan("Город, день/ночь", "base", "two_zone", ("base",)),
    },
    "rural_single": {
        "label": "Село, одноставочный",
        "plan": TariffPlan("Село, одноставочный", "reduced", "single", ("reduced_gas_rural",)),
    },
    "rural_zones": {
        "label": "Село, день/ночь",
        "plan": TariffPlan("Село, день/ночь", "reduced", "two_zone", ("reduced_gas_rural",)),
    },
}
TARIFF_NOTE = ("Село — сельское население; в городе эта же ставка действует для домов "
               "с электроплитой или электроотоплением.")

# Справочник городов: именительный и предложный падеж («в Краснодаре»)
CITIES = {
    "krasnodar": "Краснодар",
    "maykop": "Майкоп",
}
CITIES_IN = {
    "krasnodar": "Краснодаре",
    "maykop": "Майкопе",
}

INTRO = ("Калькулятор подбирает мощность станции из вариантов 3, 5 и 10 кВт и считает срок окупаемости "
         "по действующим тарифам и цене выкупа излишков. Параметры дома задаются на панели слева.")

SELF_SHARE_NOTE = ("Пока профиль потребления условный: долю самопотребления вы задаёте сами. "
                   "Если дом днём столько не потребляет, фактическая доля будет ниже — "
                   "в результатах показана фактическая.")


def verdict(city_key: str, monthly_kwh: float, tariff_key: str, best_kw: int, best: dict) -> str:
    """Одна фраза с выводом для пользователя."""
    who = (f"Для дома в {CITIES_IN[city_key]} с потреблением {format_kwh(monthly_kwh)} в месяц "
           f"на тарифе «{TARIFFS[tariff_key]['label']}»")
    if best["simple_payback"] == INF:
        return f"{who} станция не окупается за 25 лет ни при одной из мощностей 3, 5 и 10 кВт."
    return (f"{who} быстрее всего окупится станция **{best_kw} кВт** — примерно за "
            f"**{format_years(best['simple_payback'])}**. Остальные варианты — в таблице ниже.")


HOW_IT_WORKS = (
    "Выработка станции — по данным PVGIS (Европейская комиссия) для Краснодара и Майкопа. Тарифы — по приказу "
    "ДГРТ Краснодарского края № 18/2025-э, цена выкупа излишков — по отчётам ТНС энерго Кубань и тарифу "
    "владельца. Расчёт идёт по месяцам: счёт за электроэнергию без станции минус счёт со станцией (с учётом "
    "зон суток и диапазонов потребления) плюс доход от продажи излишков. Простой срок окупаемости — стоимость "
    "станции, делённая на годовой эффект первого года. Дисконтированный срок учитывает рост тарифов, износ "
    "панелей, замену инвертора и налог на доход от излишков после 2029 г."
)


def footnote(versions: dict) -> str:
    """Подпись о версиях данных под результатом."""
    return (f"Тарифы с {versions['tariffs_from']}; цена выкупа — по отчётам ТНС за {versions['buyback']}; "
            f"выработка — PVGIS, {versions['pvgis']}. Расчёт предварительный: профили потребления "
            "команды 1 ещё не подключены.")
