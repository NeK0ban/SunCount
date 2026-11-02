# app/streamlit_app.py
"""Точка входа калькулятора SunCount. Запуск из корня репозитория: streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.calc import PV_SIZES, calculate_scenario  # noqa: E402
from app.texts import (CITIES, HOW_IT_WORKS, METHOD_URL, TARIFF_NOTE, TARIFFS, format_percent,  # noqa: E402
                       format_rub, format_years)


@st.cache_data
def run_calculation(monthly_kwh: float, self_share_pct: float, city: str, tariff_key: str):
    """Кэш Streamlit (правило 4 архитектуры): одинаковые входы не пересчитываются."""
    return calculate_scenario(monthly_kwh, self_share_pct, city, tariff_key)


st.set_page_config(page_title="SunCount — калькулятор окупаемости СЭС", layout="wide")

st.title("☀️ SunCount — калькулятор окупаемости домашней СЭС")
st.markdown(
    "Расчёт срока окупаемости солнечной электростанции для частных домов "
    "Краснодарского края и Республики Адыгея."
)

# ---------- Боковая панель: ввод ----------
with st.sidebar:
    st.header("Параметры дома")

    city_key = st.selectbox(
        "Населённый пункт",
        options=list(CITIES.keys()),
        format_func=lambda k: CITIES[k],
    )

    tariff_key = st.selectbox(
        "Тариф",
        options=list(TARIFFS.keys()),
        format_func=lambda k: TARIFFS[k]["label"],
    )
    st.caption(TARIFF_NOTE)

    monthly_kwh = st.number_input(
        "Среднее потребление в месяц, кВт·ч",
        min_value=50,
        max_value=5000,
        value=500,
        step=10,
    )

    self_share_pct = st.slider(
        "Доля самопотребления, %",
        min_value=20,
        max_value=80,
        value=40,
        step=5,
        help="Какая часть выработки СЭС расходуется в доме сразу, а не уходит в сеть.",
    )
    st.caption(
        "⚠️ Условный расчёт до подключения модуля команды 1: доля самопотребления задаётся вручную. "
        "Если дом днём столько не потребляет, фактическая доля будет ниже."
    )

    calc_clicked = st.button("Рассчитать окупаемость", type="primary", width="stretch")


# ---------- Основной экран: вывод ----------
if calc_clicked:
    best_kw, results = run_calculation(monthly_kwh, self_share_pct, city_key, tariff_key)
    rec = results[best_kw]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Рекомендуемая мощность",
        f"{int(best_kw)} кВт",
        help="Вариант из 3, 5 и 10 кВт с наименьшим простым сроком окупаемости",
    )
    c2.metric(
        "Срок окупаемости",
        format_years(rec["simple_payback"]),
        help="Стоимость станции / годовой эффект первого года",
    )
    c3.metric(
        "Годовой эффект",
        format_rub(rec["effect_rub"]),
        help="Экономия на счёте за электричество + доход от продажи излишков",
    )
    c4.metric(
        "Доля самопотребления",
        format_percent(rec["self_share"]),
        help="Какая часть выработки СЭС расходуется в доме, а не уходит в сеть "
             "(для рекомендуемой мощности; может быть ниже заданной, если дом днём столько не потребляет)",
    )
    if rec["simple_payback"] == float("inf"):
        st.warning("При таком потреблении станция не окупается за 25 лет.")

    st.divider()
    st.subheader("Сравнение мощностей")

    rows = []
    for kw in PV_SIZES:
        r = results[kw]
        rows.append({
            "Мощность, кВт": kw,
            "Стоимость станции": format_rub(r["capex_rub"]),
            "Годовой эффект": format_rub(r["effect_rub"]),
            "Доход от излишков": f"{format_rub(r['export_rub'])} ({format_percent(r['export_share'])})",
            "Простой срок": format_years(r["simple_payback"]),
            "Срок (мин. цена станции)": format_years(r["payback_low"]),
            "Срок (макс. цена станции)": format_years(r["payback_high"]),
            "Дисконт. срок": format_years(r["disc_payback"]),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(
        "Дисконтированный срок учитывает рост тарифов, износ панелей, "
        "замену инвертора и налог после 2029 г."
    )

    with st.expander("Как считается"):
        st.write(HOW_IT_WORKS)
        st.markdown(f"Методика, параметры и источники данных: [docs/assumptions.md]({METHOD_URL})")
else:
    st.info("Заполните параметры слева и нажмите «Рассчитать окупаемость».")
