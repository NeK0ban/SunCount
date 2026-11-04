# Функции команды 1 для веб-сервиса (T1.3)

Модуль `src/energy/api.py` — реализация команды 1, версия от 02.11.2026, получена 03.11.2026 (пакет `SunCount_TEAM1_PVGIS_2005_2023_FINAL.zip`, оригиналы — `docs/sources/team1/2026-11-02/`). Интерфейс совпадает с предложением мастер-ТЗ (раздел 11.2), кроме наклона по умолчанию: 30° вместо 35° (согласовано 24.10); команда 1 подтвердила его поставкой. Проверено Р1 03.11.2026: функции работают с нашим классом `MonthlyMetrics`, а результат `simulate` считается нашей моделью (`src/econ/api.evaluate`).

Почасовая выработка 1 кВт берётся из `data/solar_reference/solar_<город>_tilt30_az180_1kw.npy`: PVGIS-SARAH3 + ERA5, 2005–2023, наклон 30°, юг, потери 14 %, «типичный год» (каждый час усреднён по годам), местное время UTC+3. Другой наклон или азимут — только после выгрузки новой базы (иначе `FileNotFoundError`).

## Функции

```python
from src.energy.api import PORTRAITS, build_profile, simulate

PORTRAITS: dict[str, str]   # код портрета -> русское название: day_absent, home_all_day, ac, el_heating

def build_profile(monthly_kwh: list[float],   # ровно 12 неотрицательных значений, кВт·ч за месяц
                  presence: str,              # "day_absent" | "home_all_day"
                  appliances: set[str],       # подмножество {"ac", "el_heating", "pump", "el_stove"}
                  city: str = "krasnodar",    # "krasnodar" | "maykop"
                  ) -> np.ndarray:            # 8760 значений, кВт·ч за час, местное время UTC+3

def simulate(load_8760: np.ndarray,           # 8760 неотрицательных значений, кВт·ч за час
             pv_kw: float,                    # мощность СЭС, кВт (> 0)
             city: str,
             tilt: float = 30,
             azimuth: float = 180,            # pvlib: 180 = юг
             ) -> tuple[list[MonthlyMetrics], np.ndarray, np.ndarray]:
    # 12 помесячных записей в формате обмена (profile_id="custom") + почасовые потребление и выработка
```

- `build_profile` сохраняет месячные суммы ровно такими, какие ввёл пользователь; приборы меняют только распределение по часам. Профиль сценарный, а не измеренный.
- `simulate` считает почасово: самопотребление = min(выработка, потребление); день 7:00–22:59, ночь 23:00–6:59. Балансы проверяются внутри функции.
- Ошибки ввода — `ValueError` с понятным текстом (неизвестный город, не 12 месяцев, отрицательные значения, неизвестный прибор).

## Пример (режим «Свои данные» в веб-сервисе, T4.6)

```python
from src.econ.api import recommend
from src.energy.api import build_profile, simulate

load = build_profile([500] * 12, "home_all_day", {"ac"}, "krasnodar")
months_by_kw = {kw: simulate(load, kw, "krasnodar")[0] for kw in (3, 5, 10)}
best_kw, results = recommend(months_by_kw, plan)                  # plan — TariffPlan выбранного тарифа
months, load_8760, gen_8760 = simulate(load, best_kw, "krasnodar")  # почасовые ряды — для графика T4.4
```

Если выбран прибор «электроотопление», тариф пониженный с диапазонами отопительного периода: `TariffPlan(..., "reduced", ..., ("reduced_heating", "reduced_heating_nostove"))`.

## Готовые портреты

Помесячные показатели портретов — `data/energy_metrics_monthly.csv` (`read_csv(path, MonthlyMetrics)`), почасовые ряды — `data/hourly_profiles/<портрет>_<город>_8760.csv` (потребление) и `data/hourly_solar/solar_<город>_<кВт>kw.csv` (выработка).

## Открытые вопросы к команде 1

- «Типичный год» (усреднение каждого часа по годам) завышает долю самопотребления на 0,7–6,3 п. п. (`scripts/check_team1_data.py`). Предложено считать показатели по каждому году и усреднять; если команда 1 изменит метод, сигнатуры функций остаются прежними.
- Портрет `pump_farm` — не сделан (необязательный).
