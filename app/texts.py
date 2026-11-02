# app/texts.py
"""Тексты, форматирование чисел и справочники для калькулятора SunCount."""
import math

from src.econ.inputs import TariffPlan

METHOD_URL = "https://github.com/NeK0ban/SunCount/blob/main/docs/assumptions.md"


def _bad(value: float) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def format_rub(value: float) -> str:
    """Рубли с пробелами между разрядами: 51903.12 -> '51 903 ₽'."""
    if _bad(value):
        return "—"
    if value == float("inf"):
        return "∞"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def format_years(value: float) -> str:
    """Годы — один знак после запятой: 7.74 -> '7,7 года'; inf -> 'не окупается за 25 лет'.

    С дробной частью (а она всегда показывается: «8,0») по-русски пишется «года».
    """
    if _bad(value):
        return "—"
    if value == float("inf"):
        return "не окупается за 25 лет"
    return f"{value:.1f}".replace(".", ",") + " года"


def format_percent(value: float) -> str:
    """Проценты целые: 40.5 -> '41 %'."""
    if _bad(value):
        return "—"
    if value == float("inf"):
        return "∞"
    return f"{value:.0f} %"


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

# Справочник городов
CITIES = {
    "krasnodar": "Краснодар",
    "maykop": "Майкоп",
}

HOW_IT_WORKS = (
    "Выработка станции — по данным PVGIS (Европейская комиссия) для Краснодара и Майкопа. Тарифы — по приказу "
    "ДГРТ Краснодарского края № 18/2025-э, цена выкупа излишков — по отчётам ТНС энерго Кубань и тарифу "
    "владельца. Расчёт идёт по месяцам: счёт за электроэнергию без станции минус счёт со станцией (с учётом "
    "зон суток и диапазонов потребления) плюс доход от продажи излишков. Простой срок окупаемости — стоимость "
    "станции, делённая на годовой эффект первого года."
)
