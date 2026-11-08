# Функции команды 1 для веб-сервиса (T1.3)

Модуль `src/energy/api.py` — реализация команды 1, версия по годам от 03.11.2026 (пакет `SunCount_TEAM1_YEARWISE_2005_2023_2026-11-03.zip`, оригиналы — `docs/sources/team1/2026-11-03/`; первая версия — `2026-11-02/`). Интерфейс совпадает с предложением мастер-ТЗ (раздел 11.2), кроме наклона по умолчанию: 30° вместо 35° (согласовано 24.10); команда 1 подтвердила его поставкой. Проверено Р1 03–04.11.2026 (проверки № 3 и 4): функции работают с нашим классом `MonthlyMetrics`, а результат `simulate` считается нашей моделью (`src/econ/api.evaluate`).

Почасовая выработка 1 кВт — PVGIS-SARAH3 + ERA5, 2005–2023, наклон 30°, юг, потери 14 %, местное время UTC+3. Балансы `simulate` считает по каждому из 19 лет (`data/solar_reference/solar_<город>_tilt30_az180_1kw_by_year.npy`, 19 × 8760) и усредняет помесячные энергии; «типичный год» (`…_1kw.npy`, каждый час усреднён по годам) возвращается только для графика. Другой наклон или азимут — только после выгрузки новой базы (иначе `FileNotFoundError`).

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

## Как функции используются после перехода к конфигуратору (08.11.2026)

Конфигуратору нужен только почасовой профиль потребления: готовый портрет из `data/hourly_profiles/` или `build_profile` по квитанциям. Выработку он считает сам — по паспорту панели на типичном метеогоде PVGIS (`docs/method/configurator.md`). Поэтому `simulate` и ряды выработки команды 1 (`data/hourly_solar/`, `data/solar_reference/`) в веб-сервисе больше не участвуют. Они нужны только для материалов этапа 2 на 3, 5 и 10 кВт: `scripts/run_real.py`, тепловая карта, гипотеза 2.

```python
from app.calc import average_day, own_load, run_configurator

load = own_load([500] * 12, "home_all_day", ("ac",), "krasnodar")   # внутри — build_profile команды 1
res = run_configurator("krasnodar", "city_zones", load, appliances=("ac",), roof_area_m2=40, phases=1)
best = res["configs"][0]                                             # рекомендуемая станция со сметой
july = average_day(best, "krasnodar", load, 7)                       # средние сутки июля для графика T4.4
```

Если выбран прибор «электроотопление», тариф пониженный с диапазонами отопительного периода: `TariffPlan(..., "reduced", ..., ("reduced_heating", "reduced_heating_nostove"))`.

## Готовые портреты

Помесячные показатели портретов — `data/energy_metrics_monthly.csv` (`read_csv(path, MonthlyMetrics)`), почасовые ряды — `data/hourly_profiles/<портрет>_<город>_8760.csv` (потребление) и `data/hourly_solar/solar_<город>_<кВт>kw.csv` (выработка).

## Открытые вопросы к команде 1

- Расчёт по «типичному году» завышал долю самопотребления на 0,7–6,4 п. п. — исправлено командой 1 03.11 (проверка № 4), сигнатуры функций не менялись.
- Портрет `pump_farm` — не сделан (необязательный).
