import math
import requests
import streamlit as st

st.set_page_config(page_title="Калькулятор позиции", page_icon="📊", layout="centered")
st.title("📊 Калькулятор позиции")
st.caption("qty = stop_rub / (ticks × step_price)")


# ---------- Загрузка списков инструментов ----------

@st.cache_data(ttl=600)
def load_stocks():
    url = (
        "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/"
        "securities.json?iss.meta=off&iss.only=securities"
        "&securities.columns=SECID,SHORTNAME,MINSTEP"
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
            minstep = row[idx["MINSTEP"]]
            if minstep:
                result.append((secid, name, float(minstep)))
        return result
    except Exception:
        return []


@st.cache_data(ttl=600)
def load_futures():
    url = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/"
        "securities.json?iss.meta=off&iss.only=securities"
        "&securities.columns=SECID,SHORTNAME,MINSTEP,STEPPRICE"
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
            minstep = row[idx["MINSTEP"]]
            stepprice = row[idx["STEPPRICE"]]
            if minstep and stepprice:
                result.append((secid, name, float(minstep), float(stepprice)))
        return result
    except Exception:
        return []


stocks = load_stocks()
futures = load_futures()

# ---------- Формируем список опций ----------

options = []

for secid, name, minstep in stocks:
    options.append({
        "label": f"{secid} — {name} (акция)",
        "secid": secid,
        "type": "Акция",
        "step_actual": minstep,   # фактический MINSTEP с биржи
        "step_default": 1.0,      # по умолчанию для акций — 1 ₽
    })

for secid, name, minstep, stepprice in futures:
    options.append({
        "label": f"{secid} — {name} (фьючерс)",
        "secid": secid,
        "type": "Фьючерс",
        "step_actual": stepprice,  # STEPPRICE
        "step_default": stepprice,
    })

options.sort(key=lambda x: x["label"])
labels = [o["label"] for o in options]


# ---------- Выбор инструмента (вне формы → реактивный UI) ----------

st.subheader("Инструмент")
selected_label = st.selectbox(
    "Выберите тикер",
    options=labels if labels else ["— список недоступен —"],
    index=0,
    help="Список подгружается с MOEX ISS и кэшируется на 10 минут.",
)

selected = next((o for o in options if o["label"] == selected_label), None)

if selected and selected["type"] == "Акция":
    st.caption(
        f"ℹ️ Фактический MINSTEP = **{selected['step_actual']} ₽**. "
        f"По умолчанию для акций стоимость шага = **1 ₽** (см. настройку ниже)."
    )

use_actual_minstep = st.checkbox(
    "Для акций: использовать фактический MINSTEP вместо 1 ₽",
    value=False,
    help="По умолчанию 1 тик = 1 ₽ движения цены акции. "
         "Включите, чтобы использовать биржевой MINSTEP (например, 0.01 ₽ для SBER).",
)

manual_ticker = st.checkbox("Ввести тикер вручную (если его нет в списке)")
ticker_manual = ""
if manual_ticker:
    ticker_manual = st.text_input("Тикер", value="SBER")


# ---------- Форма расчёта ----------

with st.form("calc"):
    st.subheader("Параметры расчёта")
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
    info_note = ""

    if manual_step:
        step_price = step_manual
        instrument_label = "ручной ввод шага"
    elif manual_ticker:
        secid = ticker_manual.strip().upper()
        if secid:
            info = None
            # пробуем как фьючерс
            try:
                url = (
                    f"https://iss.moex.com/iss/engines/futures/markets/forts/"
                    f"securities/{secid}.json?iss.meta=off&iss.only=securities"
                    f"&securities.columns=SECID,SHORTNAME,MINSTEP,STEPPRICE"
                )
                r = requests.get(url, timeout=10)
                block = r.json().get("securities", {})
                if block.get("data"):
                    row = dict(zip(block["columns"], block["data"][0]))
                    if row.get("MINSTEP") and row.get("STEPPRICE"):
                        info = ("Фьючерс", float(row["STEPPRICE"]),
                                row.get("SHORTNAME", secid), float(row["MINSTEP"]))
            except Exception:
                pass
            # пробуем как акцию
            if not info:
                try:
                    url = (
                        f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/"
                        f"securities/{secid}.json?iss.meta=off&iss.only=securities"
                        f"&securities.columns=SECID,SHORTNAME,MINSTEP"
                    )
                    r = requests.get(url, timeout=10)
                    block = r.json().get("securities", {})
                    if block.get("data"):
                        row = dict(zip(block["columns"], block["data"][0]))
                        if row.get("MINSTEP"):
                            info = ("Акция", float(row["MINSTEP"]),
                                    row.get("SHORTNAME", secid), float(row["MINSTEP"]))
                except Exception:
                    pass

            if info:
                typ, actual, name, minstep = info
                if typ == "Акция":
                    if use_actual_minstep:
                        step_price = actual
                        info_note = f"MINSTEP = {actual} ₽"
                    else:
                        step_price = 1.0
                        info_note = f"шаг = 1 ₽ (MINSTEP = {actual} ₽)"
                else:
                    step_price = actual
                    info_note = f"STEPPRICE = {actual} ₽"
                instrument_label = f"{secid} — {name} ({typ})"
            else:
                st.error(f"Не удалось найти тикер **{secid}** на MOEX.")
    else:
        if options and selected:
            if selected["type"] == "Акция":
                if use_actual_minstep:
                    step_price = selected["step_actual"]
                    info_note = f"MINSTEP = {selected['step_actual']} ₽"
                else:
                    step_price = 1.0
                    info_note = f"шаг = 1 ₽ (MINSTEP = {selected['step_actual']} ₽)"
            else:
                step_price = selected["step_actual"]
                info_note = f"STEPPRICE = {selected['step_actual']} ₽"
            instrument_label = selected["label"]
        else:
            st.error("Список инструментов не загрузился. Используйте ручной ввод.")

    if step_price and step_price > 0:
        st.success(f"Инструмент: **{instrument_label}** · {info_note}")

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
