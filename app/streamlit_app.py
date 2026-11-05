# app/streamlit_app.py
"""Точка входа веб-сервиса SunCount. Запуск из корня репозитория: python -m streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.calc import (PV_SIZES, base_capex, calculate_scenario, data_versions,  # noqa: E402
                      get_portrait_months, portrait_monthly_load, reduced_by_appliances)
from app.texts import (APPLIANCES, APPLIANCES_NOTE, CITIES, HEATING_HELP, HEATING_MONTHLY_HINT,  # noqa: E402
                       HOW_IT_WORKS, INTRO, LIFETIME_YEARS, METHOD_URL, MODES, MONTHS_SHORT, PORTRAIT_NOTE,
                       PORTRAITS, PRESENCE, SELF_SHARE_NOTE, TARIFF_NOTE, TARIFFS, footnote, format_percent,
                       format_rub, format_years, format_years_range, reduced_tariff_note, verdict)

HIGHLIGHT = "background-color: #e8f1fa"   # строка рекомендуемой мощности в таблице


@st.cache_data(max_entries=500)
def run_calculation(monthly_kwh, self_share_pct: float, city: str, tariff_key: str, profile_id, appliances: tuple,
                    custom_capex: tuple | None):
    """Кэш Streamlit (правило 4 архитектуры): одинаковые входы не пересчитываются.
    Приборы и своя цена передаются кортежами — они хешируются однозначно."""
    return calculate_scenario(monthly_kwh, self_share_pct, city, tariff_key, profile_id=profile_id,
                              appliances=set(appliances), custom_capex=dict(custom_capex) if custom_capex else None)


@st.cache_data
def load_versions() -> dict:
    return data_versions()


st.set_page_config(page_title="SunCount — окупаемость солнечной электростанции", layout="wide")

# ---------- Боковая панель: ввод (мастер-ТЗ, T4.2) ----------
with st.sidebar:
    st.header("Параметры дома")

    mode = st.radio("Данные о потреблении", options=list(MODES), format_func=lambda k: MODES[k], horizontal=True,
                    help="«Готовый портрет» — типичная семья по расчётам команды 1; «Свои данные» — потребление "
                         "из ваших квитанций.")

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

    profile_id = None
    appliances: set[str] = set()
    monthly_kwh = 500
    self_share_pct = 40   # в режиме портрета не используется: доля посчитана командой 1

    if mode == "portrait":
        profile_id = st.selectbox("Портрет домохозяйства", options=list(PORTRAITS.keys()),
                                  format_func=lambda k: PORTRAITS[k])
        if profile_id == "el_heating":
            appliances = {"el_heating"}
        st.caption(PORTRAIT_NOTE)
    else:
        by_month = st.radio("Потребление", options=["avg", "months"], horizontal=True,
                            format_func=lambda k: {"avg": "одно среднее значение", "months": "по месяцам"}[k])
        if by_month == "avg":
            monthly_kwh = st.number_input(
                "Среднее потребление в месяц, кВт·ч",
                min_value=50,
                max_value=5000,
                value=500,
                step=10,
                help="От 50 до 5 000 кВт·ч — среднее за год по квитанциям за электроэнергию.",
            )
        else:
            with st.expander("Потребление по месяцам, кВт·ч", expanded=True):
                st.caption("Все 12 месяцев обязательны — по квитанциям за последний год.")
                cols = st.columns(3)
                values = []
                for i, name in enumerate(MONTHS_SHORT):
                    with cols[i % 3]:
                        values.append(st.number_input(name, min_value=1, max_value=20000, value=500, step=10,
                                                      key=f"month_{i + 1}"))
            monthly_kwh = tuple(values)

        presence = st.radio("Когда в доме кто-то есть", options=list(PRESENCE), format_func=lambda k: PRESENCE[k],
                            help="Учтёт модуль команды 1; пока на расчёт не влияет.")
        appliances = set(st.multiselect("Основные приборы", options=list(APPLIANCES),
                                        format_func=lambda k: APPLIANCES[k], help=HEATING_HELP))
        if appliances & {"ac", "pump"}:
            st.caption(APPLIANCES_NOTE)
        if "el_heating" in appliances and by_month == "avg":
            st.warning(HEATING_MONTHLY_HINT)

        self_share_pct = st.slider(
            "Доля самопотребления, %",
            min_value=20,
            max_value=80,
            value=40,
            step=5,
            help="Какая часть выработки СЭС расходуется в доме сразу, а не уходит в сеть.",
        )
        st.caption(SELF_SHARE_NOTE)

    custom_capex = None
    if st.checkbox("У меня есть своя цена станции", help="Цена «под ключ» из коммерческого предложения "
                                                          "установщика — вместо нашей оценки."):
        defaults = base_capex()
        custom_capex = tuple(
            (kw, st.number_input(f"Станция {kw} кВт, ₽", min_value=10_000, max_value=10_000_000,
                                 value=int(round(defaults[kw], -3)), step=10_000, key=f"capex_{kw}"))
            for kw in PV_SIZES
        )


# ---------- Основной экран ----------
st.caption("SunCount · Краснодарский край и Республика Адыгея")
st.title("Окупаемость домашней солнечной электростанции")
st.write(INTRO)

if mode == "portrait" and not get_portrait_months(profile_id, city_key):
    st.info("Портреты появятся после передачи данных командой 1 (до 04.12). Пока используйте режим «Свои данные».")
    st.stop()

best_kw, results = run_calculation(monthly_kwh, self_share_pct, city_key, tariff_key, profile_id,
                                   tuple(sorted(appliances)), custom_capex)
rec = results[best_kw]

avg_month = (portrait_monthly_load(profile_id, city_key) if mode == "portrait"
             else sum(monthly_kwh) / 12 if isinstance(monthly_kwh, tuple) else monthly_kwh)
st.markdown(verdict(city_key, avg_month, tariff_key, best_kw, results))
if reduced_by_appliances(tariff_key, appliances):
    st.info(reduced_tariff_note(appliances))

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
    "цены станции (при своей цене — прочерк). Дисконтированный срок учитывает рост тарифов, износ панелей, "
    "замену инвертора и НДФЛ с дохода от излишков с 2029 г."
)

with st.expander("Как считается"):
    st.write(HOW_IT_WORKS)
    st.markdown(f"Методика, параметры и источники данных: [docs/assumptions.md]({METHOD_URL})")

st.caption(footnote(load_versions(), portrait=mode == "portrait"))
