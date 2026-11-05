"""Тесты страницы веб-сервиса через streamlit.testing (без браузера): режимы ввода T4.2 работают без ошибок.

Запуск из корня репозитория: python -m pytest -q
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.econ.inputs import DATA

APP = str(DATA.parent / "app" / "streamlit_app.py")
REAL = pd.read_csv(DATA.parent / "results" / "real_payback.csv", encoding="utf-8-sig")


def run(at: AppTest) -> AppTest:
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def metric(at: AppTest, label: str) -> str:
    """Значение карточки; неразрывные пробелы (texts.NB) заменены обычными."""
    return next(m.value for m in at.metric if m.label == label).replace(" ", " ")


@pytest.fixture
def app():
    return run(AppTest.from_file(APP, default_timeout=60))


def test_default_portrait(app):
    """По умолчанию — готовый портрет «Семья днём на работе», Краснодар, город, одноставочный: как в real_payback."""
    row = REAL[(REAL.profile_id == "day_absent") & (REAL.city == "krasnodar")
               & (REAL.tariff == "Город, одноставочный") & REAL.recommended].iloc[0]
    assert metric(app, "Мощность станции") == f"{int(row.pv_kw)} кВт"
    assert metric(app, "Срок окупаемости").startswith(f"{row.simple_payback:.1f}".replace(".", ","))
    assert not app.slider   # в режиме портрета ползунка доли самопотребления нет


@pytest.mark.parametrize("pid", ["day_absent", "home_all_day", "ac", "el_heating"])
@pytest.mark.parametrize("tariff", ["city_single", "city_zones", "rural_single", "rural_zones"])
def test_all_portraits(app, pid, tariff):
    sb = {s.label: s for s in app.selectbox}
    sb["Тариф"].set_value(tariff)
    sb["Портрет домохозяйства"].set_value(pid)
    run(app)
    info = " ".join(i.value for i in app.info)
    reduced_note = "сниженному тарифу" in info
    assert reduced_note == (pid == "el_heating" and tariff.startswith("city"))


def test_custom_mode_heating_hint_and_monthly(app):
    app.radio[0].set_value("custom")
    run(app)
    app.multiselect[0].set_value(["el_heating"])
    run(app)
    assert any("по месяцам" in w.value for w in app.warning)          # подсказка для электроотопления
    assert any("сниженному тарифу" in i.value for i in app.info)      # пометка о сниженном тарифе
    radios = {r.label: r for r in app.radio}
    radios["Потребление"].set_value("months")
    run(app)
    months = [n for n in app.number_input if n.key and n.key.startswith("month_")]
    assert len(months) == 12
    assert not any("по месяцам" in w.value for w in app.warning)
    months[0].set_value(2000)
    run(app)
    assert any("625 кВт·ч" in m.value for m in app.markdown)   # среднее (2000 + 11 × 500) / 12 во фразе-выводе


def test_custom_capex(app):
    app.checkbox[0].check()
    run(app)
    caps = {n.key: n for n in app.number_input if n.key and n.key.startswith("capex_")}
    assert [caps[f"capex_{kw}"].value for kw in (3, 5, 10)] == [193_000, 291_000, 584_000]
    caps["capex_5"].set_value(100_000)
    run(app)
    assert metric(app, "Мощность станции") == "5 кВт"
