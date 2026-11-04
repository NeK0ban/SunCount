"""Воспроизводимые расчётные бытовые профили: кВт·ч за каждый час, НЕ измерения."""
import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

YEAR = 2023  # год PVGIS-SARAH3, не високосный
PROFILES = ('day_absent', 'home_all_day', 'ac', 'el_heating')
CITIES = ('krasnodar', 'maykop')
SEED = 20261019
START = datetime(YEAR, 1, 1)
HOURS = [START + timedelta(hours=i) for i in range(8760)]
assert HOURS[-1] == datetime(YEAR, 12, 31, 23)


def temp_index(city, day_of_year):
    """Только сезонный коэффициент нагрузки, НЕ данные о погоде или температуре PVGIS."""
    # ~пик холода в начале года, пик жары в конце июля
    seasonal = math.cos(2 * math.pi * (day_of_year - 15) / 365)
    colder = 1.04 if city == 'maykop' else 1.0
    heat_need = max(0.0, seasonal + 0.28) * colder
    cool_need = max(0.0, -seasonal - 0.30) * (1.05 if city == 'krasnodar' else 0.93)
    return heat_need, cool_need


def make_profile(city, profile, seed=SEED):
    if city not in CITIES or profile not in PROFILES:
        raise ValueError('Неизвестный город или профиль')
    rng = random.Random(seed + CITIES.index(city) * 1000 + PROFILES.index(profile) * 67)
    out = []
    for d in range(365):
        date = START + timedelta(days=d)
        weekend = date.weekday() >= 5
        someone_home = profile == 'home_all_day'
        heating_profile = profile == 'el_heating'
        ac_profile = profile == 'ac'
        heating, cooling = temp_index(city, d+1)
        # Постоянные нагрузки: холодильник, роутер, ожидание, фоновые приборы
        loads = [0.100 + (0.009 if someone_home else 0.0) + rng.uniform(-0.012, 0.012)
                 for _ in range(24)]

        def add(hour, energy):
            loads[hour % 24] += max(0.0, energy)

        # Бойлер 2 кВт (доля работы внутри часового интервала): семья 4 человека.
        add(6 + rng.choice([0, 0, 1]), rng.uniform(0.45, 0.85))
        add(19 + rng.choice([0, 1, 2]), rng.uniform(1.00, 1.65))
        if weekend or someone_home:
            add(13, rng.uniform(0.10, 0.45))

        # Электроплита, завтрак/обед/ужин; обед дома в выходной или при удалёнке.
        add(7 + rng.choice([0, 1]), rng.uniform(0.35, 0.70))
        if weekend or someone_home:
            add(12 + rng.choice([0, 1, 2]), rng.uniform(0.45, 0.90))
        add(18 + rng.choice([0, 1, 2]), rng.uniform(0.75, 1.30))

        # Освещение и бытовые устройства: больше зимой и в вечерние часы.
        light_season = 0.65 + 0.35 * max(0.0, heating)
        for h in (18, 19, 20, 21, 22):
            add(h, light_season * rng.uniform(0.12, 0.24))
        if weekend or someone_home:
            for h in (10, 11, 14, 15):
                add(h, rng.uniform(0.03, 0.12))

        # ПК, ТВ, гаджеты: преимущественно вечером у отсутствующих днём.
        for h in (19, 20, 21, 22):
            add(h, rng.uniform(0.10, 0.25))
        if someone_home or weekend:
            for h in (10, 11, 12, 14, 15, 16):
                add(h, rng.uniform(0.04, 0.13))

        # Стирка 3-4 раза в неделю, посудомойка 4-5 раз в неделю, в основном вечером.
        if rng.random() < (0.54 if weekend else 0.42):
            add(16 if weekend and rng.random() < 0.50 else 20,
                rng.uniform(0.55, 1.15))
        if rng.random() < 0.64:
            add(21 if rng.random() < 0.85 else 14, rng.uniform(0.70, 1.10))
        # Пылесос и прочая техника, обычно в выходные.
        if weekend and rng.random() < 0.50:
            add(11, rng.uniform(0.30, 0.65))

        # Кондиционер: нагрузка на тёплые месяцы, главным образом после работы,
        # по выходным также в дневное время.
        if ac_profile and cooling > 0:
            for h in ((13, 14, 15, 16, 17, 18, 19, 20, 21) if weekend else (17, 18, 19, 20, 21, 22)):
                add(h, cooling * rng.uniform(1.10, 1.75))

        # Электрическое отопление (эквивалент среднечасовой мощности),
        # отопление бойлером воды УЖЕ учтено отдельно выше.
        if heating_profile and heating > 0:
            for h in range(24):
                modifier = 1.15 if h in (5, 6, 7, 18, 19, 20, 21, 22) else 0.79
                add(h, heating * modifier * rng.uniform(1.78, 2.65))

        # Небольшие суточные колебания нагрузки всех электроприборов.
        for h in range(24):
            loads[h] = round(max(0.0, loads[h] * rng.uniform(0.94, 1.06)), 6)
        out.extend(loads)
    assert len(out) == 8760 and all(v >= 0 for v in out)
    return out


def write_profiles(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    result = {}
    for city in CITIES:
        for profile in PROFILES:
            values = make_profile(city, profile)
            with (root / f'{city}_{profile}_2023.csv').open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp_local', 'load_kwh'])
                writer.writerows((t.strftime('%Y-%m-%d %H:%M:%S'), f'{v:.6f}') for t, v in zip(HOURS, values))
            result[(city, profile)] = values
    return result
