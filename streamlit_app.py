import math
import requests
import streamlit as st

st.set_page_config(page_title="Калькулятор позиции", page_icon="", layout="centered")
st.title("Калькулятор позиции", anchor=False)

# ---------- Загрузка списков инструментов ----------

@st.cache_data(ttl=600)
def load_stocks():
    """Список акций TQBR: [(secid, shortname), ...]"""
    url = (
        "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/"
        "securities.json?iss.meta=off&iss.only=securities"
        "&securities.columns=SECID,SHORTNAME"
    )
    try:
        r = requests.get(url, timeout=15)
        block = r.json().get("securities", {})
        cols = block.get("columns", [])
        data = block.get("data", [])
        idx = {name: i for i, name in enumerate(cols)}
        return [
            (row[idx["SECID"]], row[idx["SHORTNAME"]] or row[idx["SECID"]])
            for row in data
        ]
    except Exception:
        return []


@st.cache_data(ttl=600)
def load_futures():
    """Список фьючерсов RFUD: [(secid, shortname, stepprice), ...]"""
    url = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/"
        "securities.json?iss.meta=off&iss.only=securities"
        "&securities.columns=SECID,SHORTNAME,STEPPRICE"
    )
    try:
        r = requests.get(url, timeout=15)
        block = r.json().get("securities", {})
        cols = block.get("columns", [])
        data = block.get("data", [])
        idx = {name: i for i, name in enumerate(cols)}
        result = []
        for row in data:
            secid = row[idx["SECID"]]
            name = row[idx["SHORTNAME"]] or secid
            stepprice = row[idx["STEPPRICE"]]
            if stepprice:
                result.append((secid, name, float(stepprice)))
        return result
    except Exception:
        return []


stocks = load_stocks()
futures = load_futures()

# ---------- Формируем список опций ----------
# step_price: для акций — всегда 1, для фьючерсов — STEPPRICE

options = []

for secid, name in stocks:
    options.append({
        "label": f"{secid} — {name} (акция)",
        "secid": secid,
        "type": "Акция",
        "step_price": 1.0,
    })

for secid, name, stepprice in futures:
    options.append({
        "label": f"{secid} — {name} (фьючерс)",
        "secid": secid,
        "type": "Фьючерс",
        "step_price": stepprice,
    })

options.sort(key=lambda x: x["label"])
labels = [o["label"] for o in options]


# ---------- Выбор инструмента (вне формы → реактивный UI) ----------

selected_label = st.selectbox(
    "Выберите тикер",
    options=labels if labels else ["— список недоступен —"],
    index=0,
    help="Список подгружается с MOEX ISS и кэшируется на 10 минут.",
)
selected = next((o for o in options if o["label"] == selected_label), None)


# ---------- Форма расчёта ----------

with st.form("calc"):
    st.markdown("## Параметры расчёта", anchors=False)
    col1, col2 = st.columns(2)
    with col1:
        stop_rub = st.number_input("Размер стопа, ₽", min_value=0.01, value=1000.0, step=100.0)
    with col2:
        ticks = st.number_input("Стоп в тиках", min_value=1, value=10, step=1)

    manual_step = st.checkbox("Ввести стоимость шага цены вручную")
    step_manual = 0.0
    if manual_step:
        step_manual = st.number_input(
            "Стоимость шага цены, ₽", min_value=0.0, value=0.01, step=0.01, format="%.6f"
        )

    submitted = st.form_submit_button("Рассчитать", use_container_width=True)


# ---------- Расчёт ----------

if submitted:
    step_price = None
    instrument_label = ""

    if manual_step:
        step_price = step_manual
        instrument_label = "ручной ввод шага"

    elif options and selected:
        step_price = selected["step_price"]
        instrument_label = selected["label"]
    else:
        st.error("Список инструментов не загрузился. Используйте ручной ввод.")

    if step_price and step_price > 0:
        st.success(f"Инструмент: **{instrument_label}** · шаг цены = **{step_price} ₽**")

        qty_raw = stop_rub / (ticks * step_price)
        qty = math.floor(qty_raw)

        st.metric("Количество бумаг", f"{qty}")
        st.caption(f"Точное значение до округления: {qty_raw:.4f}")

        if qty < 1:
            st.warning("Размер стопа слишком мал — округлённое количество меньше 1.")

        with st.expander("Показать расчёт"):
            st.write("**Формула:** `qty = stop_rub / (ticks × step_price)`")
            st.write(f"`qty = {stop_rub} / ({ticks} × {step_price}) = {qty_raw:.4f} → {qty}`")
    elif not step_price:
        st.error("Шаг цены не определён. Проверьте тикер или включите ручной ввод шага.")
