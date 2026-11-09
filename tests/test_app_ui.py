"""Тесты страницы веб-сервиса через streamlit.testing (без браузера): ввод и вывод конфигуратора.

Запуск из корня репозитория: python -m pytest -q
"""
import pytest
from streamlit.testing.v1 import AppTest

from src.econ.inputs import DATA

APP = str(DATA.parent / "app" / "streamlit_app.py")


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


def radio(at, label):
    return next(r for r in at.radio if r.label == label)


def test_default(app):
    assert {m.label for m in app.metric} == {"Мощность панелей", "Цена «под ключ»", "Срок окупаемости", "Эффект в год"}
    assert any("Рекомендуем" in m.value for m in app.markdown)
    assert not app.slider or all(s.label != "Доля самопотребления, %" for s in app.slider)   # ползунка больше нет
    assert len(app.dataframe) == 2   # смета и другие варианты


@pytest.mark.parametrize("pid", ["day_absent", "home_all_day", "ac", "el_heating"])
@pytest.mark.parametrize("tariff", ["city_single", "city_zones", "rural_single", "rural_zones"])
def test_all_portraits(app, pid, tariff):
    sb = {s.label: s for s in app.selectbox}
    sb["Тариф"].set_value(tariff)
    sb["Портрет домохозяйства"].set_value(pid)
    run(app)
    info = " ".join(i.value for i in app.info)
    assert ("сниженному тарифу" in info) == (pid == "el_heating" and tariff.startswith("city"))


def test_custom_mode(app):
    radio(app, "Данные о потреблении").set_value("custom")
    run(app)
    app.multiselect[0].set_value(["el_heating"])
    run(app)
    assert any("по месяцам" in w.value for w in app.warning)
    assert any("сниженному тарифу" in i.value for i in app.info)
    radio(app, "Как ввести потребление").set_value("months")
    run(app)
    months = [n for n in app.number_input if n.key and n.key.startswith("month_")]
    assert len(months) == 12
    months[0].set_value(2000)
    run(app)
    assert not any("по месяцам" in w.value for w in app.warning)


def test_three_phase_big_roof(app):
    # тариф день/ночь: здесь при цели «быстрее окупить» выгодна крупная станция. На городском одноставочном с
    # помесячным зачётом быстрее окупается малая — излишки сверх месячной покупки продаются почти вдвое дешевле тарифа
    next(s for s in app.selectbox if s.label == "Тариф").set_value("city_zones")
    radio(app, "Ввод в дом").set_value(3)
    radio(app, "Что важнее").set_value("payback")
    next(n for n in app.number_input if n.label.startswith("Полезная площадь")).set_value(80)
    run(app)
    kw = float(metric(app, "Мощность панелей").split()[0].replace(",", "."))
    assert kw > 6.5   # трёхфазный ввод открывает инверторы мощнее 5 кВт


def test_budget_too_small(app):
    app.checkbox[0].check()
    run(app)
    next(n for n in app.number_input if n.label.startswith("Бюджет")).set_value(60_000)
    run(app)
    assert any("Ни одна станция" in w.value for w in app.warning)
