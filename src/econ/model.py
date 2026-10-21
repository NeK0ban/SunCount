"""Экономический модуль команды 2: годовой эффект и срок окупаемости домашней СЭС.

Вход: показатели из раздела 4 ТЗ (годовые EnergyMetrics или помесячные MonthlyMetrics),
тариф, цена выкупа, капзатраты. Выход: годовой эффект в рублях, простой и дисконтированный
срок окупаемости. Параметры по годам — src/econ/params.py (у каждого есть источник).

Два способа посчитать годовой эффект:
  * annual_effect()         — формула ТЗ: самопотребление × тариф + излишки × цена выкупа (годовые данные);
  * annual_effect_monthly() — точнее: счёт за электроэнергию без СЭС минус счёт с СЭС по месяцам
                              (учитывает диапазоны тарифа) + излишки × цена выкупа месяца (сезонность);
  * annual_effect_monthly_net() — как annual_effect_monthly(), но с помесячным зачётом выдачи в сеть
                              против покупки из сети для граждан (ОП № 442, п. 63(1)) — вариант для сравнения.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import params as P
from .exchange import EnergyMetrics, MonthlyMetrics
from .inputs import TariffPlan, buyback_monthly, monthly_bill


@dataclass
class Tariff:
    """Упрощённый тариф без диапазонов, ₽/кВт·ч. Для одноставочного day = night = flat."""
    name: str
    day: float
    night: float

    @classmethod
    def flat(cls, name: str, price: float) -> "Tariff":
        return cls(name, price, price)


@dataclass
class Economics:
    self_rub: float      # экономия на счёте за электроэнергию за счёт самопотребления
    export_rub: float    # доход от продажи излишков
    effect_rub: float    # годовой эффект = self_rub + export_rub
    export_share: float  # доля дохода от излишков в эффекте, % (гипотеза 2: ≤ 20 %)


def _econ(self_rub: float, export_rub: float) -> Economics:
    effect = self_rub + export_rub
    return Economics(self_rub, export_rub, effect, 100 * export_rub / effect if effect else 0.0)


def annual_effect(m: EnergyMetrics, tariff: Tariff, buyback: float) -> Economics:
    """Формула ТЗ. Солнце работает только в дневной зоне (7–23), поэтому самопотребление
    замещает электроэнергию по дневной ставке."""
    return _econ(m.self_kwh * tariff.day, m.export_kwh * buyback)


def annual_effect_monthly(months: list[MonthlyMetrics], plan: TariffPlan) -> Economics:
    """Эффект по месяцам: (счёт без СЭС − счёт с СЭС) + Σ излишки_м × цена выкупа_м.

    Без СЭС дом покупал бы днём import_day + self, ночью — import_night.
    Цена выкупа зависит от тарифа владельца (1-я или 2-я ценовая категория) и месяца.
    """
    bb = buyback_monthly(plan.owner_category)
    saving = export = 0.0
    for r in months:
        without = monthly_bill(plan, r.month, r.import_day_kwh + r.self_kwh, r.import_night_kwh)
        with_pv = monthly_bill(plan, r.month, r.import_day_kwh, r.import_night_kwh)
        saving += without - with_pv
        export += r.export_kwh * bb[r.month]
    return _econ(saving, export)


def annual_effect_monthly_net(months: list[MonthlyMetrics], plan: TariffPlan) -> Economics:
    """Эффект с помесячным зачётом по ОП № 442, п. 63(1) (ПП РФ № 442, ред. ПП № 299 от 02.03.2021).

    Гражданин на одноставочном тарифе оплачивает за месяц max(покупка − выдача, 0), а ГП покупает
    у него max(выдача − покупка, 0). На тарифе день/ночь зачёт идёт отдельно по зонам суток; СЭС отдаёт
    энергию только днём, поэтому выдача зачитывается против дневной покупки.
    self_rub — экономия на счёте (самопотребление + зачёт), export_rub — доход от проданного остатка.
    """
    bb = buyback_monthly(plan.owner_category)
    saving = export = 0.0
    for r in months:
        without = monthly_bill(plan, r.month, r.import_day_kwh + r.self_kwh, r.import_night_kwh)
        day = max(r.import_day_kwh - r.export_kwh, 0.0)
        if plan.owner_category == "flat":
            # одноставочный: зачёт против всей покупки за месяц (сначала дневной — на цену не влияет)
            night = max(r.import_kwh - r.export_kwh, 0.0) - day
            sold = max(r.export_kwh - r.import_kwh, 0.0)
        else:
            night = r.import_night_kwh
            sold = max(r.export_kwh - r.import_day_kwh, 0.0)
        saving += without - monthly_bill(plan, r.month, day, night)
        export += sold * bb[r.month]
    return _econ(saving, export)


def simple_payback(capex: float, effect_rub: float, opex_rub: float = 0.0) -> float:
    """Простой срок окупаемости, лет = капзатраты / (годовой эффект − годовые расходы) — по ТЗ."""
    net = effect_rub - opex_rub
    return capex / net if net > 0 else float("inf")


# ----------------------------------------------------------------- многолетний расчёт
@dataclass
class Scenario:
    """Параметры дисконтированного расчёта. По умолчанию — официальные значения из params.py."""
    start_year: int = P.START_YEAR
    lifetime: int = P.LIFETIME_YEARS
    tariff_growth: dict = field(default_factory=lambda: dict(P.TARIFF_GROWTH))
    buyback_growth: dict = field(default_factory=lambda: dict(P.BUYBACK_GROWTH))
    long_run_growth: float = P.LONG_RUN_GROWTH
    discount_rate: dict = field(default_factory=lambda: dict(P.DISCOUNT_RATE))
    long_run_discount: float = P.LONG_RUN_DISCOUNT
    degradation_first: float = P.DEGRADATION_FIRST_YEAR
    degradation: float = P.DEGRADATION_PER_YEAR
    opex_rub: float = P.OPEX_RUB_PER_YEAR
    inverter_year: int = P.INVERTER_REPLACEMENT_YEAR
    inverter_share: float = P.INVERTER_SHARE_OF_CAPEX
    inverter_cost_rub: float | None = None   # цена инвертора (если известна) — приоритетнее доли
    ndfl_free_until: int = P.NDFL_FREE_UNTIL_YEAR
    ndfl_rate: float = P.NDFL_RATE

    def years(self) -> list[int]:
        return list(range(self.start_year, self.start_year + self.lifetime))


def _price_factors(growth: dict, long_run: float, years: list[int]) -> list[float]:
    """Средний за год коэффициент цены относительно базы (цен на начало первого года).
    Индексация с 1 июля: полгода по старой цене, полгода по новой."""
    level, out = 1.0, []
    for y in years:
        g = growth.get(y, long_run)
        out.append(level * (1 + g / 2))
        level *= 1 + g
    return out


def _degradation_factors(sc: Scenario) -> list[float]:
    """Доля исходной выработки по годам: 1-й год −1 %, далее −0,4 %/год (гарантия производителя)."""
    return [1 - sc.degradation_first * min(t, 1) - sc.degradation * max(t - 1, 0)
            for t in range(sc.lifetime)]


def discount_factors(sc: Scenario) -> list[float]:
    """Коэффициенты дисконтирования (конец года) по ставкам, меняющимся по годам."""
    acc, out = 1.0, []
    for y in sc.years():
        acc /= 1 + sc.discount_rate.get(y, sc.long_run_discount)
        out.append(acc)
    return out


def cash_flows(base: Economics, capex: float, sc: Scenario | None = None) -> list[float]:
    """Годовые денежные потоки (без капзатрат) на весь срок службы, номинальные рубли.

    self_rub растёт с тарифом, export_rub — с ценой выкупа; оба падают с деградацией панелей;
    с года после окончания льготы доход от излишков облагается НДФЛ; в год замены инвертора —
    расход (доля капзатрат, индексированная на инфляцию)."""
    sc = sc or Scenario()
    years = sc.years()
    tf = _price_factors(sc.tariff_growth, sc.long_run_growth, years)
    bf = _price_factors(sc.buyback_growth, sc.long_run_growth, years)
    infl = _price_factors(P.INFLATION, P.LONG_RUN_GROWTH, years)
    deg = _degradation_factors(sc)
    flows = []
    for i, y in enumerate(years):
        export = base.export_rub * bf[i] * deg[i]
        if y > sc.ndfl_free_until:
            export *= 1 - sc.ndfl_rate
        cf = base.self_rub * tf[i] * deg[i] + export - sc.opex_rub * infl[i]
        if i + 1 == sc.inverter_year:
            inverter = sc.inverter_cost_rub if sc.inverter_cost_rub is not None else capex * sc.inverter_share
            cf -= inverter * infl[i]
        flows.append(cf)
    return flows


def discounted_payback(capex: float, flows: list[float], sc: Scenario | None = None) -> float:
    """Дисконтированный срок окупаемости, лет (с интерполяцией внутри года); inf — не окупается."""
    sc = sc or Scenario()
    acc = -capex
    for t, (cf, df) in enumerate(zip(flows, discount_factors(sc)), start=1):
        dcf = cf * df
        if acc + dcf >= 0 and dcf > 0:
            return t - 1 + (-acc) / dcf
        acc += dcf
    return float("inf")


def npv(capex: float, flows: list[float], sc: Scenario | None = None) -> float:
    sc = sc or Scenario()
    return -capex + sum(cf * df for cf, df in zip(flows, discount_factors(sc)))
