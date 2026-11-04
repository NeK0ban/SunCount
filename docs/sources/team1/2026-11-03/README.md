# SunCount — передача энергетических результатов команды №1

**Актуальная версия: 03.11.2026 — YEARWISE-2005–2023**

## Статус

- Исправлено замечание команды №2: сначала 19 отдельных расчётов `min(load, gen)` с почасовым импортом/экспортом; затем помесячное усреднение энергий. Расчёт по типичному году остаётся **только для графиков**.
- `results/energy_metrics.csv` — **24** строки, `results/energy_metrics_monthly.csv` — **288** строк.
- `results/energy_metrics_per_year.csv` — **456** строк, `results/energy_metrics_monthly_per_year.csv` — **5472** строки.
- `results/team1_typical_year_check.csv` — разница между старым/исправленным методами для 24 комбинаций. Смещение **0,72–6,36 п.п.**
- `results/hypothesis_equal_consumption.csv` — 6 сравнений; диапазон отношений **1.5106–1.5747×**, во всех случаях ≥1,5.
- `src/energy/api.py` сохраняет интерфейсы `build_profile` и `simulate`; `simulate` возвращает 12 помесячных объектов, нагрузку 8760 и генерацию 8760 для графика. Основные показатели берутся из 19 разных лет.
- `data/solar_reference/` включает `*_by_year.npy` по 19 × 8760 часов, типичный ряд для графиков и метаданные. Исходные PVGIS JSON находятся в `data/pvgis_raw/`.
- `data/hourly_profiles/` — 8 сценарных профилей по 8760 часов, `data/hourly_solar/` — 6 графических рядов по 8760 часов.
- Все **13 тестов** прошли. Метаданные/результаты сверки: `results/validation_report.json`.

## Запуск без интернета

```bash
python -m pip install -r requirements.txt
python -m scripts.import_uploaded_pvgis
python -m scripts.generate_outputs --mode verified
python -m scripts.check_team1_data
python -m unittest discover -s tests -v
```

**Особенности:** один условный шаблон потребления 2023 сопоставляется с фактическими моделируемыми почасовыми PVGIS-годами; это контролируемое сценарное допущение. Данные о нагрузках не являются измерениями семей. Оригинальные `docs/exchange_format.md`/`src/econ/exchange.py` команды №2 не предоставлены, поэтому интерфейс v1.0 восстановлен по согласованным колонкам. Для окончательной проверки интеграции необходим их класс. Исходные PVGIS являются модельными солнечными данными, не показаниями реальных станций.

Развёрнутые выводы: `reports/RESULTS_REPORT.md`, готовое сообщение команде №2: `reports/team2_response.md`. PDF: `reports/SunCount_TEAM1_YEARWISE_2005_2023_REPORT.pdf`.
