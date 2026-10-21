# SunCount — калькулятор окупаемости домашней СЭС

Адыгея и Краснодарский край. Команда 2: экономика и калькулятор.

Мастер-ТЗ команды — всё в одном документе (проект, архитектура, задачи каждого участника, сроки): [docs/MASTER_TZ.md](docs/MASTER_TZ.md)
План и статусы задач: [PLAN.md](PLAN.md)

## Структура
- `docs/` — тексты для отчёта (нормативка, методика)
- `data/` — исходные данные с источниками и датами (тарифы, цены выкупа, КП на оборудование)
- `src/econ/exchange.py` — формат обмена с командой 1 (раздел 4 ТЗ) + условные данные
- `src/econ/model.py` — экономическая модель (эффект, простой и дисконтированный срок окупаемости)
- `src/econ/params.py` — параметры по годам с источниками; `src/econ/inputs.py` — загрузка тарифов, цен выкупа, PVGIS
- `docs/assumptions.md` — реестр параметров, допущений и учтённых факторов (для отчёта)
- `docs/kp_plan.md` — запросы КП установщикам: кому отправлены, текст, формат ответов
- `data/raw/` — скачанные оригиналы (не редактировать); в `tns_microgen/` — один файл на год (последний месяц года содержит все месяцы)
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
```

## Просмотр данных в Excel
CSV-файлы — рабочий формат для кода (разделитель запятая, UTF-8). Русский Excel показывает их одной колонкой,
поэтому для просмотра открывай `SunCount_data.xlsx` — все таблицы на отдельных листах.
Пересоздать его: `python scripts/export_excel.py`. Редактировать данные — в CSV, не в xlsx.