import math
import requests
import streamlit as st

st.set_page_config(page_title="Калькулятор позиции", page_icon="📊", layout="centered")
st.title("📊 Калькулятор позиции")
st.caption("qty = stop_rub / (ticks × step_price)")


# ---------- Загрузка списков инструментов ----------

@st.cache_data(ttl=600)
def load_stocks():
    """Список акций TQBR: [(secid, shortname, minstep), ...]"""
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
            if minstep:  # пропускаем инструменты без шага цены
                result.append((secid, name, float(minstep)))
        return result
    except Exception:
        return []


@st.cache_data(ttl=600)
def load_futures():
    """Список фьючерсов RFUD: [(secid, shortname, minstep, stepprice), ...]"""
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


# Загружаем один раз при старте (кэшируется)
stocks = load_stocks()
futures = load_futures()

# Собираем общий список для selectbox: (label, secid, type, step_price)
# Для акций step_price = minstep (шаг уже в рублях), для фьючерсов — stepprice.
options = []

for secid, name, minstep in stocks:
    label = f"{secid} — {name} (акция)"
    options.append((label, secid, "Акция", minstep))

for secid, name, minstep, stepprice in futures:
    label = f"{secid} — {name} (фьючерс)"
    options.append((label, secid, "Фьючерс", stepprice))

options.sort(key=lambda x: x[0])


# ---------- Форма калькулятора ----------

with st.form("calc"):
    st.subheader("Инструмент")

    # Основной выбор — из списка
    selected_label = st.selectbox(
        "Выберите тикер",
        options=[o[0] for o in options] if options else ["— список недоступен —"],
        index=0,
        help="Список подгружается с MOEX ISS. Если тикера нет — включите ручной ввод ниже.",
    )

    # Ручной ввод как fallback
    manual_ticker = st.checkbox("Ввести тикер вручную")
    ticker_manual = ""
    if manual_ticker:
        ticker_manual = st.text_input("Тикер (например, SBER или GDZ6)", value="SBER")

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

    if manual_step:
        step_price = step_manual
        instrument_label = "ручной ввод шага"
    elif manual_ticker:
        # Ручной тикер: пробуем определить через API (фьючерс → акция)
        secid = ticker_manual.strip().upper()
        if secid:
            info = None
            # Пробуем фьючерс
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
                        info = ("Фьючерс", float(row["STEPPRICE"]), row.get("SHORTNAME", secid))
            except Exception:
                pass
            # Если не фьючерс — пробуем акцию
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
                            info = ("Акция", float(row["MINSTEP"]), row.get("SHORTNAME", secid))
                except Exception:
                    pass
            if info:
                typ, step_price, name = info
                instrument_label = f"{secid} — {name} ({typ})"
            else:
                st.error(f"Не удалось найти тикер **{secid}** на MOEX. Проверьте написание или включите ручной ввод шага.")
    else:
        # Выбор из selectbox
        if options:
            chosen = next((o for o in options if o[0] == selected_label), None)
            if chosen:
                _, secid, typ, step_price = chosen
                instrument_label = selected_label
            else:
                st.error("Не удалось распознать выбранный инструмент.")
        else:
            st.error("Список инструментов не загрузился. Включите ручной ввод тикера или шага.")

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
