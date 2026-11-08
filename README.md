# SunCount — система поддержки принятия решений по выбору домашней СЭС

Адыгея и Краснодарский край. Команда 2: конфигурация станции, правила микрогенерации и экономика. С 08.11.2026 (мастер-ТЗ 5.0) сервис — конфигуратор: подбирает под дом модели и число панелей, инвертор, смету «под ключ» и срок окупаемости. Проблема, актуальность и решение — [docs/project/concept.md](docs/project/concept.md), методика — [docs/method/configurator.md](docs/method/configurator.md), схема — `reports/scheme/SunCount_scheme.png`.

Мастер-ТЗ команды — всё в одном документе (проект, архитектура, задачи каждого участника, сроки): [docs/MASTER_TZ.md](docs/MASTER_TZ.md)
План и статусы задач: [PLAN.md](PLAN.md)

## Структура
- `docs/` — тексты проекта, карта папки — [docs/README.md](docs/README.md): мастер-ТЗ в корне, `project/` (проблема и решение, решения команды, тест-план), `rules/` (нормативка, ТНС), `method/` (методика конфигуратора, реестр допущений), `equipment/` (источники цен, КП), `team1/` (формат обмена и проверки данных команды 1), `sources/` (оригиналы)
- `docs/grant/` — материалы для заявки на грант: обзор калькуляторов, монетизация, научная проблема, литература, патентный поиск
- `data/` — исходные данные с источниками и датами (тарифы, цены выкупа, КП на оборудование)
- `src/config/` — конфигуратор (мастер-ТЗ 5.0): `catalog.py` (каталог `data/equipment/`), `weather.py` (типичный метеогод PVGIS `data/raw/pvgis/*_tmy.json`), `pv_yield.py` (энергорасчёт по паспорту панели, pvlib), `configurator.py` (перебор, ограничения, смета, выбор)
- `data/equipment/` — каталог: панели и инверторы с паспортами, прочие статьи сметы; цены — только с проверенных сайтов из [docs/equipment/equipment_sources.md](docs/equipment/equipment_sources.md), без скидок, все предложения — `offers.csv`
- `src/econ/exchange.py` — формат обмена с командой 1 (раздел 4 ТЗ) + условные данные
- `src/econ/model.py` — экономическая модель (эффект, простой и дисконтированный срок окупаемости)
- `src/econ/api.py` — единая точка входа модели для веб-сервиса, аналитики и тестов: `evaluate`, `recommend`, `evaluate_tz`
- `src/energy/api.py` — функции команды 1 `build_profile` / `simulate` (почасовое потребление и выработка → помесячные показатели), описание — `docs/team1/api_team1.md`
- `src/econ/params.py` — параметры по годам с источниками; `src/econ/inputs.py` — загрузка тарифов, цен выкупа, PVGIS
- `data/energy_metrics*.csv`, `data/hourly_profiles/`, `data/hourly_solar/`, `data/solar_reference/`, `data/reference/` — данные команды 1 (годовые и помесячные показатели, в том числе по каждому году PVGIS, почасовые ряды, помесячное потребление портретов); протокол проверки — `docs/team1/team1_data_check.md`, скрипты — `scripts/check_team1_data.py`, `scripts/check_team1_households.py`; `data/household_validation/` — сценарная сверка пяти смоделированных семей (04.11)
- `data/raw/` — скачанные оригиналы (не редактировать); в `tns_microgen/` — по одному файлу на год (последний месяц года содержит все месяцы), за текущий год — последний опубликованный и предыдущий
- `reports/` — отчёты и презентации, оглавление — [reports/README.md](reports/README.md): в корне — результаты по ТЗ (промежуточный и итоговый отчёт), `reports/kurs/` — задания курса по лекциям, `reports/pasport/` — паспорт проекта
- `reports/weekly/` — недельные отчёты команды в .docx (что сделано, что в работе, планы); текст правится в `reports/weekly/src/*.md`, docx собирает `python scripts/make_weekly_report.py`
- `app/` и `.streamlit/config.toml` — аналитический веб-сервис на Streamlit (настройки: светлая тема, без кнопки Deploy): `streamlit_app.py` (интерфейс), `calc.py` (расчёт через `src/econ/api.py`, без Streamlit), `texts.py` (тексты и форматирование)
- `scripts/` — скрипты расчётов
- `results/` — результаты расчётов

## Запуск
```
pip install -r requirements.txt
python scripts/make_tariffs_csv.py
python -I scripts/parse_tns_buyback.py
python -I scripts/parse_tns_price_limits.py
python scripts/estimate_capex.py
python scripts/stub_payback.py
python scripts/sensitivity.py           # анализ чувствительности → results/sensitivity.csv, results/tornado_*.png
python scripts/check_team1_data.py      # проверка данных команды 1 → results/team1_*.csv
python scripts/check_team1_households.py  # сценарная сверка семей команды 1 → results/team1_household_check.csv
python scripts/zones_effect.py          # тариф день/ночь против одноставочного → results/zones_effect.csv, *.png
python scripts/run_real.py              # окупаемость на портретах команды 1 → results/real_payback.csv (T1.6)
python scripts/heatmap_real.py          # тепловая карта на данных команды 1 → results/heatmap_real*.csv/png
python scripts/export_excel.py          # после всех расчётов: SunCount_data.xlsx
python scripts/make_interim_report.py   # промежуточный отчёт → reports/SunCount_interim_report.pdf
python scripts/build_equipment_prices.py  # цены каталога из data/equipment/offers.csv (только проверенные сайты, без скидок)
python scripts/validate_yield.py       # энергорасчёт против PVGIS → results/yield_validation.csv
python scripts/configurator_examples.py  # подбор на портретах команды 1 → results/config_examples.csv
python scripts/make_scheme.py          # схема решения → reports/scheme/SunCount_scheme.pptx и .png (PNG — через PowerPoint)
python scripts/make_interim_talk.py    # промежуточный доклад → reports/SunCount_interim_talk.pptx
python -m pytest -q                     # автотесты (tests/)
python -m streamlit run app/streamlit_app.py   # веб-сервис SunCount → http://localhost:8501
```

## Просмотр данных в Excel
CSV-файлы — рабочий формат для кода (разделитель запятая, UTF-8). Русский Excel показывает их одной колонкой,
поэтому для просмотра открывай `SunCount_data.xlsx` — все таблицы на отдельных листах.
Пересоздать его: `python scripts/export_excel.py`. Редактировать данные — в CSV, не в xlsx.