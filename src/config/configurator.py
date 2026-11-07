"""Подбор конфигурации домашней сетевой СЭС под конкретный дом.

Вход — дом пользователя (House): город, тариф, почасовое потребление (портрет команды 1 или build_profile
по квитанциям и приборам), крыша (полезная площадь, наклон, сторона света, затенение), договор с сетью
(число фаз, максимальная мощность), бюджет и цель подбора.

Перебор: каждая модель панели из каталога × число панелей от 1 до предела крыши × каждый подходящий инвертор.
Для каждого варианта проверяется:
- нормативные ограничения: мощность инвертора (выдача в сеть) не больше максимальной мощности по договору
  с сетью и не больше 50 кВт — предела микрогенерации для граждан (распоряжение Правительства РФ
  от 26.09.2026 № 2675-р); трёхфазный инвертор — только при трёхфазном вводе;
- техника: мощность панелей не больше допустимой для инвертора по паспорту; цепочки панелей проходят
  по напряжению (Voc в самый холодный час 2005–2023 гг. не выше максимального входного, Vmp в жару — не ниже
  нижней границы MPPT, при 25 °C — не выше верхней) и по току короткого замыкания;
- крыша и бюджет: панели помещаются на полезную площадь, полная смета не больше бюджета.
Затем — почасовой баланс выработки и потребления, помесячные записи формата обмена и окупаемость той же
экономической моделью, что и раньше (src/econ: тарифы с диапазонами и зонами суток, цена выкупа по тарифу
владельца, рост тарифов, деградация, замена инвертора, НДФЛ).

Цель подбора:
- "own" (по умолчанию) — станция для своих нужд: за год вырабатывает не больше, чем потребляет дом
  (объект микрогенерации используется для собственных нужд, в сеть отдаются излишки — docs/01_normativka.md);
  среди таких — с наименьшим простым сроком окупаемости;
- "payback" — наименьший простой срок без ограничения по потреблению (часто — самая крупная допустимая станция:
  излишки продаются, а крупная станция дешевле за киловатт);
- "npv" — наибольшая чистая приведённая выгода за 25 лет.
При разнице сроков меньше 0,05 года выбирается более дешёвый вариант.
"""
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import product

import numpy as np

from src.econ.api import INF, evaluate
from src.econ.exchange import MonthlyMetrics, _record
from src.econ.inputs import DAY_HOURS, TariffPlan
from src.econ.model import Scenario, annual_effect_monthly, simple_payback
from src.econ import params as P

from .catalog import Inverter, Panel, bos, inverters, panels
from .pv_yield import panel_dc_w, system_loss
from .weather import design_min_temp, local_calendar

MICROGEN_LIMIT_KW = 50.0      # граждане: выдача в сеть до 50 кВт включительно (распоряжение № 2675-р)
T_CELL_HOT_C = 70.0           # расчётная температура модуля в жару — для нижней границы напряжения цепочки
TIE_YEARS = 0.05
GOALS = {"own": "для своих нужд: выработка за год не больше потребления, наименьший срок окупаемости",
         "payback": "наименьший срок окупаемости", "npv": "наибольшая выгода за 25 лет"}


@dataclass(frozen=True)
class House:
    city: str
    plan: TariffPlan
    load_8760: tuple                  # кВт·ч за каждый час года, местное время (как профили команды 1)
    roof_area_m2: float = 40.0        # полезная площадь крыши под панели
    tilt: float = 30.0
    azimuth: float = 180.0            # 180 — юг, 90 — восток, 270 — запад
    shading: str = "none"             # "none" | "light"
    phases: int = 1                   # ввод в дом: 1 или 3 фазы
    allowed_kw: float = 15.0          # максимальная мощность по договору с сетью (ТУ)
    budget_rub: float | None = None
    goal: str = "own"
    profile_id: str = "custom"

    def __post_init__(self):
        if len(self.load_8760) != 8760:
            raise ValueError("Потребление: нужно 8760 часовых значений")
        if self.roof_area_m2 <= 0 or self.allowed_kw <= 0:
            raise ValueError("Площадь крыши и мощность по договору должны быть больше нуля")
        if self.phases not in (1, 3):
            raise ValueError("Ввод в дом: 1 или 3 фазы")
        if self.goal not in GOALS:
            raise ValueError(f"Цель подбора: одна из {sorted(GOALS)}")
        if self.budget_rub is not None and self.budget_rub <= 0:
            raise ValueError("Бюджет должен быть больше нуля")


@dataclass
class Config:
    panel: Panel
    n_panels: int
    inverter: Inverter
    strings: tuple                    # длины цепочек, по одной на занятый вход MPPT
    bom: list                         # [(статья, модель/пояснение, количество, цена за единицу, сумма)]
    capex_rub: float
    capex_low_rub: float
    capex_high_rub: float
    months: list = field(repr=False, default_factory=list)
    result: dict = field(default_factory=dict)
    gen_kwh: float = 0.0
    clipped_kwh: float = 0.0

    @property
    def kwp(self) -> float:
        return round(self.n_panels * self.panel.pmax_w / 1000, 3)

    @property
    def area_m2(self) -> float:
        return self.n_panels * self.panel.area_m2


# ----------------------------------------------------------------- цепочки панелей
def string_limits(panel: Panel, inv: Inverter, city: str) -> tuple[int, int]:
    """Допустимая длина цепочки (панелей подряд) для пары панель — инвертор."""
    t_min = design_min_temp(city)
    voc_cold = panel.voc_v * (1 + panel.beta_voc_pct_c / 100 * (t_min - 25))
    vmp_hot = panel.vmp_v * (1 + panel.beta_voc_pct_c / 100 * (T_CELL_HOT_C - 25))   # β(Voc) как оценка β(Vmp)
    l_max = min(int(inv.max_dc_v // voc_cold), int(inv.mppt_max_v // panel.vmp_v))
    l_min = int(np.ceil(inv.mppt_min_v / vmp_hot))
    return l_min, l_max


def layout(panel: Panel, n: int, inv: Inverter, city: str) -> tuple | None:
    """Раскладка n панелей по входам MPPT (по одной цепочке на вход, длины по возможности равные) или None."""
    if panel.isc_a > inv.max_isc_a_per_mppt:
        return None
    l_min, l_max = string_limits(panel, inv, city)
    for k in range(1, inv.n_mppt * inv.strings_per_mppt + 1):   # меньше цепочек — меньше кабеля и защиты
        base, extra = divmod(n, k)
        lengths = tuple([base + 1] * extra + [base] * (k - extra))
        if lengths[-1] >= l_min and lengths[0] <= l_max and min(lengths) > 0:
            return lengths
    return None


# ----------------------------------------------------------------- смета
def bill_of_materials(panel: Panel, n: int, inv: Inverter, strings: tuple) -> tuple[list, float, float, float]:
    """Смета: оборудование, материалы, монтаж (15–25 % от оборудования, база 20 %), подключение к сети."""
    b = bos()
    k = len(strings)
    items = [
        ("Панели", panel.name, n, panel.price_rub),
        ("Инвертор", inv.name, 1, inv.price_rub),
        ("Крепёж на кровлю", "комплект на одну панель", n, b["mounting"]),
        ("Кабель солнечный 4 мм²", f"{k} цеп. × {b['dc_cable_m_per_string']:.0f} м", k * b["dc_cable_m_per_string"], b["dc_cable"]),
        ("Разъёмы MC4", "пары", 2 * k + 2, b["mc4"]),
        ("Защита DC: УЗИП", "на каждый вход MPPT", k, b["dc_spd"]),
        ("Защита DC: предохранители", "на каждую цепочку, + и −", 2 * k, b["dc_fuse"]),
        ("Защита AC: автомат, УЗИП, бокс", f"{inv.phases}-фазная схема", 1,
         b["ac_protection_3ph"] if inv.phases == 3 else b["ac_protection_1ph"]),
        ("Доставка", "", 1, b["delivery"]),
    ]
    rows = [(name, model, qty, price, qty * price) for name, model, qty, price in items]
    equipment = sum(r[4] for r in rows)
    labour = {lvl: equipment * share for lvl, share in (("low", 0.15), ("base", b["labour_share"]), ("high", 0.25))}
    grid = min(b["grid_connection_c1"], b["grid_connection_per_kw"] * inv.ac_kw)
    rows.append(("Монтаж и пусконаладка", f"{b['labour_share']:.0%} от оборудования (по КП: 15–25 %)", 1,
                 labour["base"], labour["base"]))
    rows.append(("Подключение к сети", "плата сетевой организации (приказ ДГРТ № 19/2025-э)", 1, grid, grid))
    if b.get("meter", 0):
        rows.append(("Прибор учёта", "", 1, b["meter"], b["meter"]))
    total = {lvl: equipment + labour[lvl] + grid + b.get("meter", 0) for lvl in labour}
    return rows, total["base"], total["low"], total["high"]


# ----------------------------------------------------------------- энергия
@lru_cache(maxsize=1)
def _night_mask() -> np.ndarray:
    return ~np.isin(local_calendar().hour.to_numpy(), list(DAY_HOURS))


@lru_cache(maxsize=1)
def _months() -> np.ndarray:
    return local_calendar().month.to_numpy()


def hourly_ac(panel: Panel, n: int, inv: Inverter, strings: tuple, house: House) -> tuple[np.ndarray, float]:
    """Выработка на выходе инвертора по часам, кВт·ч, и сколько отрезано ограничениями инвертора за год."""
    dc = panel_dc_w(panel, house.city, house.tilt, house.azimuth) * n * (1 - system_loss(house.shading))
    # ограничение по входному току MPPT: инвертор не берёт ток выше паспортного — мощность цепочки срезается
    dc_cap = sum(min(panel.imp_a, inv.max_dc_a_per_mppt) * length * panel.vmp_v for length in strings)
    dc_lim = np.minimum(dc, dc_cap)
    ac_full = dc * inv.euro_eff_pct / 100
    ac = np.minimum(dc_lim * inv.euro_eff_pct / 100, inv.ac_kw * 1000)
    return ac / 1000, float((ac_full.sum() - ac.sum()) / 1000)


def monthly_records(gen: np.ndarray, load: np.ndarray, house: House, kwp: float) -> list[MonthlyMetrics]:
    """Почасовой баланс → 12 помесячных записей формата обмена (самопотребление по часам, ночная покупка 23–7)."""
    self_h = np.minimum(gen, load)
    night_import = np.where(_night_mask(), load - self_h, 0.0)
    m = _months()
    recs = []
    for month in range(1, 13):
        sel = m == month
        rec = _record(house.profile_id, house.city, kwp, float(gen[sel].sum()), float(load[sel].sum()),
                      float(self_h[sel].sum()), float(night_import[sel].sum()), cls=MonthlyMetrics, month=month)
        rec.validate()
        recs.append(rec)
    return recs


# ----------------------------------------------------------------- подбор
def candidates(house: House, panel_ids=None) -> list[Config]:
    """Все допустимые конфигурации со сметой (без экономики)."""
    out = []
    invs = [i for i in inverters() if i.phases <= house.phases
            and i.ac_kw <= min(house.allowed_kw, MICROGEN_LIMIT_KW)]
    for p in panels():
        if panel_ids and p.panel_id not in panel_ids:
            continue
        n_roof = int(house.roof_area_m2 // p.area_m2)
        for inv, n in product(invs, range(1, n_roof + 1)):
            if n * p.pmax_w / 1000 > inv.max_pv_kw:
                continue
            strings = layout(p, n, inv, house.city)
            if strings is None:
                continue
            bom, capex, low, high = bill_of_materials(p, n, inv, strings)
            if house.budget_rub is not None and capex > house.budget_rub:
                continue
            out.append(Config(p, n, inv, strings, bom, capex, low, high))
    return out


def _economics(c: Config, house: House, load: np.ndarray, full: bool) -> None:
    gen, clipped = hourly_ac(c.panel, c.n_panels, c.inverter, c.strings, house)
    c.gen_kwh, c.clipped_kwh = float(gen.sum()), clipped
    c.months = monthly_records(gen, load, house, c.kwp)
    if full:
        r = evaluate(c.months, house.plan, c.kwp, capex_rub=c.capex_rub,
                     scenario=Scenario(inverter_cost_rub=c.inverter.price_rub))
        c.result = r.as_dict()
        c.result["payback_low"] = simple_payback(c.capex_low_rub, r.effect_rub, P.OPEX_RUB_PER_YEAR)
        c.result["payback_high"] = simple_payback(c.capex_high_rub, r.effect_rub, P.OPEX_RUB_PER_YEAR)
    else:
        e = annual_effect_monthly(c.months, house.plan)
        c.result = {"effect_rub": e.effect_rub,
                    "simple_payback": simple_payback(c.capex_rub, e.effect_rub, P.OPEX_RUB_PER_YEAR)}


def configure(house: House, panel_ids=None, top: int = 5, full_for: int = 25) -> list[Config]:
    """Лучшие конфигурации по цели дома, первая — рекомендуемая. Пусто — ни одна не проходит ограничения.

    Сначала все варианты оцениваются по годовому эффекту первого года (быстро), затем для лучших full_for
    по простому сроку считается полный многолетний расчёт (дисконтированный срок, NPV, границы цены).
    """
    load = np.asarray(house.load_8760, dtype=float)
    cands = candidates(house, panel_ids)
    for c in cands:
        _economics(c, house, load, full=False)
    if house.goal == "own":
        annual = float(load.sum())
        own = [c for c in cands if c.gen_kwh <= annual]
        cands = own or sorted(cands, key=lambda c: c.gen_kwh)[:1]   # дом меньше одной панели — самый малый вариант
    cands.sort(key=lambda c: (c.result["simple_payback"], c.capex_rub))
    if house.goal == "npv":
        shortlist = cands   # NPV не монотонен по сроку — считаем всё
    else:
        shortlist = cands[:full_for]
    for c in shortlist:
        _economics(c, house, load, full=True)
    if house.goal == "npv":
        shortlist.sort(key=lambda c: (-c.result["npv_rub"], c.capex_rub))
    else:
        best = min(c.result["simple_payback"] for c in shortlist) if shortlist else INF
        shortlist.sort(key=lambda c: (c.result["simple_payback"] - best >= TIE_YEARS, c.capex_rub
                                      if c.result["simple_payback"] - best < TIE_YEARS else c.result["simple_payback"]))
    # разнообразие: в списке не больше двух вариантов с одной моделью панели и одинаковым инвертором
    picked, seen = [], {}
    for c in shortlist:
        key = (c.panel.panel_id, c.inverter.inverter_id)
        if seen.get(key, 0) < 2:
            picked.append(c)
            seen[key] = seen.get(key, 0) + 1
        if len(picked) == top:
            break
    return picked


def _num(value: float) -> str:
    """Число по-русски: 3230.4 -> «3 230», 6.5 -> «6,5» (неразрывный пробел между разрядами)."""
    if float(value).is_integer() or value >= 100:
        return f"{value:,.0f}".replace(",", " ")
    return f"{value:g}".replace(".", ",")


def binding_constraint(best: Config, house: House) -> str:
    """Почему рекомендуемая станция не больше — одна фраза для пользователя."""
    n_roof = int(house.roof_area_m2 // best.panel.area_m2)
    if best.n_panels >= n_roof:
        return (f"площадь крыши: на {house.roof_area_m2:g} м² помещается не больше {n_roof} панелей "
                f"{best.panel.brand} ({best.panel.area_m2:.2f} м² каждая)")
    free = House(**{**house.__dict__, "budget_rub": None})
    bigger = [c for c in candidates(free, [best.panel.panel_id]) if c.n_panels > best.n_panels]
    if not bigger:
        invs = [i for i in inverters() if i.phases <= house.phases
                and i.ac_kw <= min(house.allowed_kw, MICROGEN_LIMIT_KW)]
        top = max(invs, key=lambda i: i.max_pv_kw)
        return (f"инвертор: самый мощный из подходящих по договору с сетью ({house.phases} ф., до "
                f"{_num(house.allowed_kw)} кВт) в каталоге — {top.name}, к нему можно подключить панели "
                f"не больше {_num(top.max_pv_kw)} кВт")
    if house.budget_rub is not None and all(c.capex_rub > house.budget_rub for c in bigger):
        return f"бюджет {_num(house.budget_rub)} ₽"
    if house.goal == "own":
        annual = float(np.sum(house.load_8760))
        nxt = min(bigger, key=lambda c: (c.n_panels, c.capex_rub))
        if hourly_ac(nxt.panel, nxt.n_panels, nxt.inverter, nxt.strings, house)[0].sum() > annual:
            return (f"потребление дома: станция для своих нужд вырабатывает за год не больше, чем дом потребляет "
                    f"({_num(annual)} кВт·ч)")
    return ("экономика: станция побольше окупается дольше — излишки продаются дешевле, "
            "чем стоит электроэнергия из сети")
