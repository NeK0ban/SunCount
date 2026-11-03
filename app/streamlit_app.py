# app/streamlit_app.py
"""Точка входа калькулятора SunCount. Запуск из корня репозитория: python -m streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.calc import PV_SIZES, calculate_scenario, data_versions  # noqa: E402
from app.texts import (CITIES, HOW_IT_WORKS, INTRO, LIFETIME_YEARS, METHOD_URL, SELF_SHARE_NOTE,  # noqa: E402
                       TARIFF_NOTE, TARIFFS, footnote, format_percent, format_rub, format_years, format_years_range,
                       verdict)

HIGHLIGHT = "background-color: #e8f1fa"   # строка рекомендуемой мощности в таблице


@st.cache_data(max_entries=500)
def run_calculation(monthly_kwh: float, self_share_pct: float, city: str, tariff_key: str):
    """Кэш Streamlit (правило 4 архитектуры): одинаковые входы не пересчитываются."""
    return calculate_scenario(monthly_kwh, self_share_pct, city, tariff_key)


@st.cache_data
def load_versions() -> dict:
    return data_versions()


st.set_page_config(page_title="SunCount — окупаемость солнечной электростанции", layout="wide")

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
        help="От 50 до 5 000 кВт·ч — среднее за год по квитанциям за электроэнергию.",
    )

    self_share_pct = st.slider(
        "Доля самопотребления, %",
        min_value=20,
        max_value=80,
        value=40,
        step=5,
        help="Какая часть выработки СЭС расходуется в доме сразу, а не уходит в сеть.",
    )
    st.caption(SELF_SHARE_NOTE)


# ---------- Основной экран ----------
st.caption("SunCount · Краснодарский край и Республика Адыгея")
st.title("Окупаемость домашней солнечной электростанции")
st.write(INTRO)

best_kw, results = run_calculation(monthly_kwh, self_share_pct, city_key, tariff_key)
rec = results[best_kw]

st.markdown(verdict(city_key, monthly_kwh, tariff_key, best_kw, results))

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Мощность станции",
    f"{int(best_kw)} кВт",
    help="Рекомендуемый вариант из 3, 5 и 10 кВт — с наименьшим простым сроком окупаемости; "
         "при почти равных сроках (разница меньше 0,05 года) — меньшая, более дешёвая мощность",
    border=True,
)
c2.metric(
    "Срок окупаемости",
    format_years(rec["simple_payback"]),
    help="Стоимость станции / годовой эффект первого года",
    border=True,
)
c3.metric(
    "Эффект в год",
    format_rub(rec["effect_rub"]),
    help="Экономия на счёте за электричество + доход от продажи излишков",
    border=True,
)
c4.metric(
    "Самопотребление",
    format_percent(rec["self_share"]),
    help="Какая часть выработки СЭС расходуется в доме, а не уходит в сеть "
         "(фактическая, для рекомендуемой мощности)",
    border=True,
)
if rec["simple_payback"] > LIFETIME_YEARS:
    st.warning(f"При таком потреблении станция не окупается за срок службы ({LIFETIME_YEARS} лет).")

st.subheader("Сравнение мощностей")
rows = []
for kw in PV_SIZES:
    r = results[kw]
    rows.append({
        "Мощность": f"{kw} кВт",
        "Цена станции": format_rub(r["capex_rub"]),
        "Годовой эффект": format_rub(r["effect_rub"]),
        "Доход от излишков": f"{format_rub(r['export_rub'])} · {format_percent(r['export_share'])}",
        "Простой срок": format_years(r["simple_payback"]),
        "При мин./макс. цене": format_years_range(r["payback_low"], r["payback_high"]),
        "Дисконт. срок": format_years(r["disc_payback"]),
    })
table = pd.DataFrame(rows)
best_row = PV_SIZES.index(best_kw)
styled = table.style.apply(lambda row: [HIGHLIGHT if row.name == best_row else "" for _ in row], axis=1)
st.dataframe(styled, width="stretch", hide_index=True)
st.caption(
    "Выделена рекомендуемая мощность. «При мин./макс. цене» — простой срок при нижней и верхней оценке "
    "цены станции. Дисконтированный срок учитывает рост тарифов, износ панелей, замену инвертора "
    "и НДФЛ с дохода от излишков с 2029 г."
)

with st.expander("Как считается"):
    st.write(HOW_IT_WORKS)
    st.markdown(f"Методика, параметры и источники данных: [docs/assumptions.md]({METHOD_URL})")

st.caption(footnote(load_versions()))
