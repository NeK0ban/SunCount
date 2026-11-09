"""Примеры подбора конфигуратором: 4 портрета команды 1 × 2 города × 4 тарифа × ввод 1 или 3 фазы.

Дом по умолчанию: крыша 40 м², юг, 30°, без тени, мощность по договору 15 кВт, цель «для своих нужд»
(выработка за год не больше потребления, наименьший срок окупаемости). Дом с электроотоплением считается
по сниженному тарифу и в городе (app/calc.py: get_plan).

Выход: results/config_examples.csv. Запуск: python scripts/configurator_examples.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.calc import portrait_load, run_configurator  # noqa: E402
from app.texts import PORTRAITS, TARIFFS  # noqa: E402

rows = []
for pid in PORTRAITS:
    appliances = ("el_heating",) if pid == "el_heating" else ()
    for city in ("krasnodar", "maykop"):
        load = portrait_load(pid, city)
        for tariff in TARIFFS:
            for phases in (1, 3):
                r = run_configurator(city, tariff, load, appliances, phases=phases, profile_id=pid)
                b = r["configs"][0]
                rows.append({
                    "profile_id": pid, "city": city, "tariff": TARIFFS[tariff]["label"], "phases": phases,
                    "load_kwh": round(b["load_kwh"]), "panel": b["panel"], "n_panels": b["n_panels"],
                    "kwp": b["kwp"], "inverter": b["inverter"], "strings": "+".join(map(str, b["strings"])),
                    "capex_rub": round(b["capex_rub"]), "gen_kwh": round(b["gen_kwh"]),
                    "self_share": round(b["self_share"], 1), "export_share": round(b["export_share"], 1),
                    "simple_payback": round(b["simple_payback"], 3), "disc_payback": round(b["disc_payback"], 3),
                    "npv_rub": round(b["npv_rub"]), "constraint": r["constraint"],
                })
df = pd.DataFrame(rows)
(ROOT / "results").mkdir(exist_ok=True)
df.to_csv(ROOT / "results" / "config_examples.csv", index=False, encoding="utf-8-sig")
print(f"results/config_examples.csv: {len(df)} домов")
print("Мощность панелей, кВт:", sorted(df.kwp.unique()))
print(df.groupby(["profile_id", "phases"]).agg(kwp_min=("kwp", "min"), kwp_max=("kwp", "max"),
                                              payback_min=("simple_payback", "min"),
                                              payback_max=("simple_payback", "max")).round(2).to_string())
print(df.constraint.str.split(":").str[0].value_counts().to_string())
