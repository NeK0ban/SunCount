# SunCount — калькулятор окупаемости домашней СЭС

Адыгея и Краснодарский край. Команда 2: экономика и калькулятор.

Мастер-ТЗ команды — всё в одном документе (проект, архитектура, задачи каждого участника, сроки): [docs/MASTER_TZ.md](docs/MASTER_TZ.md)
План и статусы задач: [PLAN.md](PLAN.md)

## Структура
- `docs/` — тексты для отчёта (нормативка, методика)
- `docs/grant/` — материалы для заявки на грант: обзор калькуляторов, монетизация, научная проблема, литература, патентный поиск
- `data/` — исходные данные с источниками и датами (тарифы, цены выкупа, КП на оборудование)
- `src/econ/exchange.py` — формат обмена с командой 1 (раздел 4 ТЗ) + условные данные
- `src/econ/model.py` — экономическая модель (эффект, простой и дисконтированный срок окупаемости)
- `src/econ/api.py` — единая точка входа модели для калькулятора, аналитики и тестов: `evaluate`, `recommend`, `evaluate_tz`
- `src/energy/api.py` — функции команды 1 `build_profile` / `simulate` (почасовое потребление и выработка → помесячные показатели), описание — `docs/api_team1.md`
- `src/econ/params.py` — параметры по годам с источниками; `src/econ/inputs.py` — загрузка тарифов, цен выкупа, PVGIS
- `docs/assumptions.md` — реестр параметров, допущений и учтённых факторов (для отчёта)
- `docs/kp_plan.md` — запросы КП установщикам: кому отправлены, текст, формат ответов
- `data/energy_metrics*.csv`, `data/hourly_profiles/`, `data/hourly_solar/`, `data/solar_reference/` — данные команды 1 (годовые и помесячные показатели, почасовые ряды); протокол проверки — `docs/team1_data_check.md`, скрипт — `scripts/check_team1_data.py`
- `data/raw/` — скачанные оригиналы (не редактировать); в `tns_microgen/` — один файл на год (последний месяц года содержит все месяцы)
- `reports/` — отчёты и презентации, оглавление — [reports/README.md](reports/README.md): в корне — результаты по ТЗ (промежуточный и итоговый отчёт), `reports/kurs/` — задания курса по лекциям, `reports/pasport/` — паспорт проекта
- `reports/weekly/` — недельные отчёты команды в .docx (что сделано, что в работе, планы); текст правится в `reports/weekly/src/*.md`, docx собирает `python scripts/make_weekly_report.py`
- `app/` и `.streamlit/config.toml` — веб-калькулятор на Streamlit (настройки: светлая тема, без кнопки Deploy): `streamlit_app.py` (интерфейс), `calc.py` (расчёт через `src/econ/api.py`, без Streamlit), `texts.py` (тексты и форматирование)
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
python scripts/export_excel.py
python scripts/make_interim_report.py   # промежуточный отчёт → reports/SunCount_interim_report.pdf
python scripts/sensitivity.py           # анализ чувствительности → results/sensitivity.csv, results/tornado_*.png
python -m streamlit run app/streamlit_app.py   # калькулятор SunCount → http://localhost:8501
```

## Просмотр данных в Excel
CSV-файлы — рабочий формат для кода (разделитель запятая, UTF-8). Русский Excel показывает их одной колонкой,
поэтому для просмотра открывай `SunCount_data.xlsx` — все таблицы на отдельных листах.
Пересоздать его: `python scripts/export_excel.py`. Редактировать данные — в CSV, не в xlsx.