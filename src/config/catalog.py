"""Каталог оборудования: панели, инверторы, прочие статьи сметы (data/equipment/*.csv).

Каждая цена и каждый паспортный параметр — со ссылкой на источник в самом CSV. Добавить модель = дописать строку.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

EQUIPMENT = Path(__file__).resolve().parents[2] / "data" / "equipment"


@dataclass(frozen=True)
class Panel:
    panel_id: str
    brand: str
    model: str
    pmax_w: float
    vmp_v: float
    imp_a: float
    voc_v: float
    isc_a: float
    eff_pct: float
    gamma_pmax_pct_c: float   # температурный коэффициент мощности, %/°C (отрицательный)
    beta_voc_pct_c: float     # температурный коэффициент Voc, %/°C
    alpha_isc_pct_c: float
    noct_c: float
    length_mm: float
    width_mm: float
    price_rub: float
    seller: str
    price_url: str
    datasheet_url: str

    @property
    def area_m2(self) -> float:
        return self.length_mm * self.width_mm / 1e6

    @property
    def name(self) -> str:
        return f"{self.brand} {self.model}"


@dataclass(frozen=True)
class Inverter:
    inverter_id: str
    brand: str
    model: str
    phases: int
    ac_kw: float
    max_pv_kw: float          # максимальная мощность массива панелей по паспорту
    max_dc_v: float
    mppt_min_v: float
    mppt_max_v: float
    n_mppt: int
    strings_per_mppt: int
    max_dc_a_per_mppt: float   # рабочий ток на MPPT: выше него инвертор ограничивает мощность
    max_isc_a_per_mppt: float  # допустимый ток короткого замыкания на MPPT
    euro_eff_pct: float
    price_rub: float
    price_url: str
    datasheet_url: str

    @property
    def name(self) -> str:
        return f"{self.brand} {self.model}"


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(EQUIPMENT / name, encoding="utf-8-sig")


def _build(cls, df: pd.DataFrame) -> tuple:
    names = [f for f in cls.__dataclass_fields__]
    return tuple(cls(**{k: row[k] for k in names}) for _, row in df.iterrows())


@lru_cache(maxsize=1)
def panels() -> tuple[Panel, ...]:
    return _build(Panel, _read("panels.csv"))


@lru_cache(maxsize=1)
def inverters() -> tuple[Inverter, ...]:
    return _build(Inverter, _read("inverters.csv"))


@lru_cache(maxsize=1)
def bos() -> dict[str, float]:
    """Прочие статьи сметы: {item: цена}."""
    t = _read("bos.csv")
    return dict(zip(t["item"], t["price_rub"].astype(float)))


def panel(panel_id: str) -> Panel:
    for p in panels():
        if p.panel_id == panel_id:
            return p
    raise ValueError(f"Нет панели {panel_id!r} в data/equipment/panels.csv")


def inverter(inverter_id: str) -> Inverter:
    for i in inverters():
        if i.inverter_id == inverter_id:
            return i
    raise ValueError(f"Нет инвертора {inverter_id!r} в data/equipment/inverters.csv")
