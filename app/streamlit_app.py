# app/streamlit_app.py
"""Точка входа веб-сервиса — конфигуратор домашней СЭС. Запуск из корня репозитория:
python -m streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.charts import day_figures  # noqa: E402  # T4.4; первым — в нём matplotlib.use("Agg") до pyplot
import matplotlib.pyplot as plt  # noqa: E402  # T4.4: закрыть figure после st.pyplot
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.calc import (average_day, data_versions, own_load, phase_limits, portrait_load,  # noqa: E402
                      reduced_by_appliances, run_configurator, tips)
from app.texts import (ALLOWED_HELP, APPLIANCES, APPLIANCES_NOTE, CHART_NOTE, CITIES, GOAL_HELP,  # noqa: E402
                       GOAL_LABELS, HEATING_HELP, HEATING_MONTHLY_HINT, HOW_IT_WORKS, INTRO, METHOD_URL, MODES,
                       MONTHS_SHORT, NB, PHASES, PORTRAIT_NOTE, PORTRAITS, PRESENCE, ROOF_HELP, ROOF_SIDES,
                       ROOF_SIDES_HELP, SHADING, SHADING_HELP, TARIFF_NOTE, TARIFFS, footnote, format_percent,
                       format_rub, format_years, format_years_range, hint_no_payback, phases_help,
                       reduced_tariff_note, strings_text, verdict)

HIGHLIGHT = "background-color: #e8f1fa"   # строка рекомендуемого варианта в таблице


@st.cache_data(max_entries=200)
def configure_cached(city, tariff_key, load: tuple, appliances: tuple, roof, tilt, azimuth, shading, phases,
                     allowed_kw, budget, goal, profile_id):
    """Кэш Streamlit (правило 4 архитектуры): одинаковые входы не пересчитываются."""
    return run_configurator(city, tariff_key, load, appliances, roof, tilt, azimuth, shading, phases, allowed_kw,
                            budget, goal, profile_id)


@st.cache_data(max_entries=50)
def own_load_cached(monthly, presence, appliances: tuple, city):
    return own_load(monthly, presence, appliances, city)


# T4.4: кэш средних суток (average_day гоняет почасовой ряд за год — дорого пересчитывать на каждый rerun)
@st.cache_data(max_entries=200)
def average_day_cached(panel_id, n_panels, inverter_id, strings: tuple, city, load: tuple, month, tilt, azimuth,
                       shading):
    """Средние сутки месяца для рекомендуемой станции; аргументы — простые типы для кэша."""
    return average_day({"panel_id": panel_id, "n_panels": n_panels, "inverter_id": inverter_id,
                        "strings": list(strings)}, city, load, month, tilt, azimuth, shading)


# T4.5: кэш подсказок (внутри — повторные прогоны конфигуратора)
@st.cache_data(max_entries=200)
def tips_cached(res, city, tariff_key, load: tuple, appliances: tuple, roof, tilt, azimuth, shading, phases,
                allowed_kw, budget, goal, profile_id):
    return tips(res, city, tariff_key, load, appliances, roof, tilt, azimuth, shading, phases, allowed_kw,
                budget, goal, profile_id)


@st.cache_data
def load_versions() -> dict:
    return data_versions()


def kw(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",") + NB + "кВт"


st.set_page_config(page_title="SunCount — подбор солнечной электростанции", layout="wide")

# ---------- Боковая панель: ввод ----------
with st.sidebar:
    st.header("Ваш дом")
    # Город и тариф — самые важные параметры, сразу вверху
    city_key = st.selectbox("Населённый пункт", options=list(CITIES), format_func=lambda k: CITIES[k])
    tariff_key = st.selectbox("Тариф", options=list(TARIFFS), format_func=lambda k: TARIFFS[k]["label"])
    st.caption(TARIFF_NOTE)
    st.divider()

    # Потребление
    st.subheader("Потребление")
    mode = st.radio("Данные о потреблении", options=list(MODES), format_func=lambda k: MODES[k], horizontal=True,
                    help="«Готовый портрет» — типичная семья по расчётам команды 1; «Свои данные» — потребление "
                         "из ваших квитанций.")
    appliances: set[str] = set()
    if mode == "portrait":
        profile_id = st.selectbox("Портрет домохозяйства", options=list(PORTRAITS),
                                  format_func=lambda k: PORTRAITS[k])
        if profile_id == "el_heating":
            appliances = {"el_heating"}
        st.caption(PORTRAIT_NOTE)
    else:
        profile_id = "custom"
        by_month = st.radio("Как ввести потребление", options=["avg", "months"], horizontal=True,
                            format_func=lambda k: {"avg": "одно среднее значение", "months": "по месяцам"}[k])
        if by_month == "avg":
            monthly = st.number_input("Среднее потребление в месяц, кВт·ч", min_value=50, max_value=5000, value=500,
                                      step=10, help="От 50 до 5 000 кВт·ч — среднее за год по квитанциям.")
        else:
            with st.expander("Потребление по месяцам, кВт·ч", expanded=True):
                st.caption("Все 12 месяцев обязательны — по квитанциям за последний год.")
                # Улучшение для телефона: компактные колонки
                cols = st.columns(3, gap="small")
                values = []
                for i, name in enumerate(MONTHS_SHORT):
                    with cols[i % 3]:
                        values.append(st.number_input(name, min_value=1, max_value=20000, value=500, step=10,
                                                      key=f"month_{i + 1}"))
            monthly = tuple(values)
        presence = st.radio("Когда в доме кто-то есть", options=list(PRESENCE),
                            format_func=lambda k: PRESENCE[k])
        appliances = set(st.multiselect("Основные приборы", options=list(APPLIANCES),
                                        format_func=lambda k: APPLIANCES[k], help=HEATING_HELP))
        if appliances:
            st.caption(APPLIANCES_NOTE)
        if "el_heating" in appliances and by_month == "avg":
            st.warning(HEATING_MONTHLY_HINT)

    st.divider()

    # Крыша
    st.subheader("Крыша")
    roof = st.number_input("Полезная площадь под панели, м²", min_value=3, max_value=500, value=40, step=1,
                           help=ROOF_HELP)
    side = st.selectbox("Куда смотрит скат", options=list(ROOF_SIDES),
                        format_func=lambda k: ROOF_SIDES[k],
                        help=ROOF_SIDES_HELP)
    tilt = st.slider("Наклон крыши, градусы", min_value=0, max_value=60, value=30, step=5,
                     help="0 — плоская крыша, обычная скатная — 25–35°.")
    shading = st.radio("Тень на крыше днём", options=list(SHADING),
                       format_func=lambda k: SHADING[k],
                       help=SHADING_HELP)

    st.divider()

    # Подключение к сети
    st.subheader("Подключение к сети")
    phases = st.radio("Ввод в дом", options=list(PHASES),
                      format_func=lambda k: PHASES[k], horizontal=True,
                      help=phases_help(phase_limits()))
    allowed_kw = st.number_input("Мощность по договору с сетью, кВт", min_value=1.0, max_value=150.0, value=15.0,
                                 step=0.5, help=ALLOWED_HELP)

    st.divider()

    # Цель
    st.subheader("Цель")
    goal = st.radio("Что важнее", options=list(GOAL_LABELS),
                    format_func=lambda k: GOAL_LABELS[k], help=GOAL_HELP)
    budget = None
    if st.checkbox("Ограничить бюджет"):
        budget = float(st.number_input("Бюджет на станцию «под ключ», ₽", min_value=50_000, max_value=10_000_000,
                                       value=400_000, step=10_000))

# ---------- Основной экран ----------
st.caption("SunCount · Краснодарский край и Республика Адыгея")
st.title("Подбор домашней солнечной электростанции")
st.write(INTRO)

if mode == "portrait":
    load = portrait_load(profile_id, city_key)
    if not load:
        st.info("Портреты появятся после передачи данных командой 1 (до 04.12). Пока используйте режим «Свои данные».")
        st.stop()
else:
    load = own_load_cached(monthly, presence, tuple(sorted(appliances)), city_key)

res = configure_cached(city_key, tariff_key, load, tuple(sorted(appliances)), float(roof), float(tilt), float(side),
                       shading, int(phases), float(allowed_kw), budget, goal, profile_id)
configs = res["configs"]
if not configs:
    st.warning("Ни одна станция из каталога не подходит под эти условия: увеличьте бюджет или площадь крыши, "
               "проверьте мощность по договору с сетью.")
    st.stop()

best = configs[0]
st.markdown(verdict(best, goal))

if reduced_by_appliances(tariff_key, appliances):
    st.info(reduced_tariff_note(appliances))

# 4 карточки — на телефоне будут в 2 колонки
c1, c2 = st.columns(2)
c3, c4 = st.columns(2)
c1.metric("Мощность панелей", kw(best["kwp"]),
          help=f"{best['n_panels']} × {best['panel_w']:.0f} Вт; инвертор {best['inverter_kw']:g} кВт", border=True)
c2.metric("Цена «под ключ»", format_rub(best["capex_rub"]),
          help="Оборудование, материалы, монтаж и плата за подключение к сети — смета ниже", border=True)
c3.metric("Срок окупаемости", format_years(best["simple_payback"]),
          help="Цена станции / годовой эффект первого года", border=True)
c4.metric("Эффект в год", format_rub(best["effect_rub"]),
          help="Экономия на счёте за электричество + доход от продажи излишков", border=True)

st.caption(f"Размер станции ограничивает: {res['constraint']}.")

# ---------- T4.5: подсказки, посчитанные моделью ----------
tips_list = tips_cached(res, city_key, tariff_key, load, tuple(sorted(appliances)), float(roof), float(tilt),
                        float(side), shading, int(phases), float(allowed_kw), budget, goal, profile_id)
if hint_no_payback() in tips_list:
    st.warning(hint_no_payback())
advice = [tip for tip in tips_list if tip != hint_no_payback()]
if advice:
    st.subheader("Как сократить срок окупаемости")
    for tip in advice:
        st.markdown(f"- {tip}")

# Смета и устройство станции — на телефоне будут друг под другом
left, right = st.columns([3, 2])
with left:
    st.subheader("Смета")
    bom = pd.DataFrame([{"Статья": r[0], "Модель / пояснение": r[1],
                         "Кол-во": f"{r[2]:g}", "Цена": format_rub(r[3]), "Сумма": format_rub(r[4])}
                        for r in best["bom"]])
    st.dataframe(bom, width="stretch", hide_index=True)
    # Улучшение: итог жирным шрифтом (отдельно от caption)
    st.markdown(f"**Итого: {format_rub(best['capex_rub'])}**")
    st.caption(f"При монтаже 15–25 % от оборудования — "
               f"{format_rub(best['capex_low_rub'])} – {format_rub(best['capex_high_rub'])}. "
               "Цены — в каталоге data/equipment/ со ссылками на продавцов.")

with right:
    st.subheader("Как устроена станция")
    st.markdown(
        f"- **Панели:** {best['n_panels']} × {best['panel']}, займут {str(round(best['area_m2'], 1)).replace('.', ',')} м²\n"
        f"- **Соединение:** {strings_text(best)}\n"
        f"- **Инвертор:** {best['inverter']}, {best['phases']}-фазный\n"
        f"- **Выработка:** {format_rub(best['gen_kwh']).replace('₽', 'кВт·ч')} в год "
        f"(потребление дома {format_rub(best['load_kwh']).replace('₽', 'кВт·ч')})\n"
        f"- **Самопотребление:** {format_percent(best['self_share'])} выработки расходуется в доме, "
        f"остальное уходит в сеть: за месяц зачитывается в счёт покупки из сети, остаток продаётся\n"
        f"- **Дисконтированный срок:** {format_years(best['disc_payback'])}; "
        f"выгода за 25 лет {format_rub(best['npv_rub'])}"
    )

# ---------- T4.4: потребление на фоне выработки, лето и зима ----------
st.subheader("Потребление на фоне выработки: лето и зима")
summer = average_day_cached(best["panel_id"], int(best["n_panels"]), best["inverter_id"], tuple(best["strings"]),
                            city_key, load, 7, float(tilt), float(side), shading)
winter = average_day_cached(best["panel_id"], int(best["n_panels"]), best["inverter_id"], tuple(best["strings"]),
                            city_key, load, 1, float(tilt), float(side), shading)
# две колонки: на компьютере графики рядом, на телефоне друг под другом во всю ширину
for col, fig in zip(st.columns(2), day_figures(summer, winter)):
    col.pyplot(fig)
    plt.close(fig)
st.caption(CHART_NOTE)

# Другие варианты
st.subheader("Другие варианты")
rows = [{
    "Панели": f"{c['n_panels']} × {c['panel']}", "Мощность": kw(c["kwp"]), "Инвертор": c["inverter"],
    "Цена": format_rub(c["capex_rub"]), "Простой срок": format_years(c["simple_payback"]),
    "При монтаже 15–25 %": format_years_range(c["payback_low"], c["payback_high"]),
    "Дисконт. срок": format_years(c["disc_payback"]), "Выгода за 25 лет": format_rub(c["npv_rub"]),
} for c in configs]
table = pd.DataFrame(rows)
st.dataframe(table.style.apply(lambda row: [HIGHLIGHT if row.name == 0 else "" for _ in row], axis=1),
             width="stretch", hide_index=True)
st.caption("Выделен рекомендуемый вариант. Дисконтированный срок учитывает рост тарифов, износ панелей, замену "
           "инвертора и НДФЛ с дохода от излишков с 2029 г.")

with st.expander("Как считается"):
    st.write(HOW_IT_WORKS)
    st.markdown(f"Методика, параметры и источники данных: [docs/method/configurator.md]({METHOD_URL})")

# Подпись о версиях данных и оговорка «расчёт ориентировочный» — под результатом, не внутри свёрнутого блока
st.caption(footnote(load_versions()))
