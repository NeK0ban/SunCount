"""Формат обмена данными между модулем команды 1 и модулем команды 2 (раздел 4 ТЗ).

Годовой файл:   одна запись = «портрет домохозяйства × мощность СЭС» (EnergyMetrics).
Помесячный файл: те же поля + month (MonthlyMetrics) — нужен для диапазонов тарифа и
сезонной цены выкупа; см. docs/exchange_format.md.
Пока реальных профилей нет, make_stub() / make_stub_monthly() дают условные значения в том же формате.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

TOL_KWH = 1.0  # допуск на округление при проверке балансов


@dataclass
class EnergyMetrics:
    profile_id: str          # портрет домохозяйства
    city: str                # maykop / krasnodar
    pv_kw: float             # мощность СЭС, кВт
    gen_kwh: float           # выработка, кВт·ч за период
    load_kwh: float          # потребление
    self_kwh: float          # самопотребление
    export_kwh: float        # излишки, отданные в сеть
    import_kwh: float        # покупка из сети
    import_day_kwh: float    # покупка из сети в дневной зоне (7–23)
    import_night_kwh: float  # покупка из сети в ночной зоне (23–7)
    self_share: float        # самопотребление / выработка, %
    coverage: float          # самопотребление / потребление, %

    def validate(self) -> None:
        """Проверяет энергетические балансы; бросает ValueError при расхождении."""
        checks = {
            "gen = self + export": self.gen_kwh - self.self_kwh - self.export_kwh,
            "load = self + import": self.load_kwh - self.self_kwh - self.import_kwh,
            "import = day + night": self.import_kwh - self.import_day_kwh - self.import_night_kwh,
        }
        bad = {k: round(v, 2) for k, v in checks.items() if abs(v) > TOL_KWH}
        if bad:
            raise ValueError(f"{self.profile_id}/{self.pv_kw} кВт: нарушены балансы {bad}")
        if not 0 <= self.self_share <= 100 or not 0 <= self.coverage <= 100:
            raise ValueError(f"{self.profile_id}/{self.pv_kw} кВт: доли должны быть в 0–100 %")


@dataclass
class MonthlyMetrics(EnergyMetrics):
    month: int = 1           # 1–12


TEXT_FIELDS = {"profile_id", "city"}
INT_FIELDS = {"month"}
FIELDS = [f.name for f in fields(EnergyMetrics)]


def _record(profile_id, city, pv_kw, gen, load, self_kwh, load_night, cls=EnergyMetrics, **extra):
    export, imp = gen - self_kwh, load - self_kwh
    return cls(
        profile_id=profile_id, city=city, pv_kw=pv_kw, gen_kwh=round(gen, 1), load_kwh=round(load, 1),
        self_kwh=round(self_kwh, 1), export_kwh=round(export, 1), import_kwh=round(imp, 1),
        import_day_kwh=round(imp - load_night, 1), import_night_kwh=round(load_night, 1),
        self_share=round(100 * self_kwh / gen, 2) if gen else 0.0,
        coverage=round(100 * self_kwh / load, 2) if load else 0.0, **extra,
    )


def make_stub_monthly(profile_id: str, pv_kw: float, load_kwh: float, self_share_pct: float,
                      city: str = "krasnodar", night_share_of_load: float = 0.30,
                      load_shape: list[float] | None = None) -> list[MonthlyMetrics]:
    """Условные помесячные записи до получения данных команды 1.

    Выработка — реальная сезонность PVGIS для города (src/econ/inputs.py).
    Потребление — load_shape (12 весов) или равномерно; доля ночной зоны — night_share_of_load.
    Самопотребление каждого месяца = min(выработка × доля, дневное потребление месяца).
    """
    from .inputs import pv_monthly_kwh_per_kw
    pv = pv_monthly_kwh_per_kw(city)
    shape = load_shape or [1.0] * 12
    out = []
    for m in range(1, 13):
        gen = pv[m] * pv_kw
        load = load_kwh * shape[m - 1] / sum(shape)
        night = load * night_share_of_load
        self_kwh = min(gen * self_share_pct / 100, load - night)
        rec = _record(profile_id, city, pv_kw, gen, load, self_kwh, night, cls=MonthlyMetrics, month=m)
        rec.validate()
        out.append(rec)
    return out


def annual_from_monthly(records: list[MonthlyMetrics]) -> EnergyMetrics:
    """Сворачивает 12 помесячных записей в годовую."""
    r0 = records[0]
    s = {k: sum(getattr(r, k) for r in records) for k in
         ("gen_kwh", "load_kwh", "self_kwh", "import_night_kwh")}
    m = _record(r0.profile_id, r0.city, r0.pv_kw, s["gen_kwh"], s["load_kwh"], s["self_kwh"], s["import_night_kwh"])
    m.validate()
    return m


def make_stub(profile_id: str, pv_kw: float, load_kwh: float, self_share_pct: float,
              city: str = "krasnodar", night_share_of_load: float = 0.30) -> EnergyMetrics:
    """Годовая условная запись (сумма make_stub_monthly)."""
    return annual_from_monthly(make_stub_monthly(profile_id, pv_kw, load_kwh, self_share_pct, city, night_share_of_load))


def write_csv(records: list[EnergyMetrics], path: str | Path) -> None:
    names = [f.name for f in fields(records[0])]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=names)
        w.writeheader()
        w.writerows(asdict(r) for r in records)


def read_csv(path: str | Path, cls=EnergyMetrics) -> list:
    """Читает и проверяет файл обмена. Для помесячного файла: read_csv(path, MonthlyMetrics)."""
    names = [f.name for f in fields(cls)]
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        conv = lambda k: r[k] if k in TEXT_FIELDS else int(r[k]) if k in INT_FIELDS else float(r[k])
        m = cls(**{k: conv(k) for k in names})
        m.validate()
        out.append(m)
    return out
