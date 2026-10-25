import math
import requests
import streamlit as st

st.set_page_config(page_title="Калькулятор позиции", page_icon="📊", layout="centered")
st.title("📊 Калькулятор позиции")
st.caption("qty = stop_rub / (ticks × step_price)")


@st.cache_data(ttl=300)
def get_moex_data(secid: str):
    """Возвращает dict с типом инструмента и стоимостью шага (₽), либо None."""
    secid = secid.strip().upper()
    if not secid:
        return None

    # 1) Пробуем как фьючерс (FORTS)
    try:
        url = (
            f"https://iss.moex.com/iss/engines/futures/markets/forts/"
            f"securities/{secid}.json?iss.meta=off&iss.only=securities"
            f"&securities.columns=SECID,MINSTEP,STEPPRICE,SHORTNAME"
        )
        r = requests.get(url, timeout=10)
        block = r.json().get("securities", {})
        if block.get("data"):
            row = dict(zip(block["columns"], block["data"][0]))
            if row.get("MINSTEP") and row.get("STEPPRICE"):
                return {
                    "type": "Фьючерс",
                    "minstep": float(row["MINSTEP"]),
                    "stepprice": float(row["STEPPRICE"]),
                    "name": row.get("SHORTNAME", secid),
                }
    except Exception:
        pass

    # 2) Пробуем как акцию (TQBR)
    try:
        url = (
            f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/"
            f"securities/{secid}.json?iss.meta=off&iss.only=securities"
            f"&securities.columns=SECID,MINSTEP,SHORTNAME"
        )
        r = requests.get(url, timeout=10)
        block = r.json().get("securities", {})
        if block.get("data"):
            row = dict(zip(block["columns"], block["data"][0]))
            if row.get("MINSTEP"):
                return {
                    "type": "Акция",
                    "minstep": float(row["MINSTEP"]),
                    "stepprice": float(row["MINSTEP"]),  # для акций шаг уже в ₽
                    "name": row.get("SHORTNAME", secid),
                }
    except Exception:
        pass

    return None


with st.form("calc"):
    ticker = st.text_input("Тикер (например, SBER или GDZ6)", value="SBER")
    col1, col2 = st.columns(2)
    with col1:
        stop_rub = st.number_input("Размер стопа, ₽", min_value=0.01, value=1000.0, step=100.0)
    with col2:
        ticks = st.number_input("Стоп в тиках", min_value=1, value=10, step=1)

    manual = st.checkbox("Ввести стоимость шага цены вручную")
    manual_step = 0.0
    if manual:
        manual_step = st.number_input("Стоимость шага цены, ₽", min_value=0.0, value=0.01, step=0.01, format="%.6f")

    submitted = st.form_submit_button("Рассчитать", use_container_width=True)


if submitted:
    info = None
    step_price = None

    if manual:
        step_price = manual_step
    else:
        info = get_moex_data(ticker)
        if info:
            step_price = info["stepprice"]
            st.info(
                f"**{info['name']}** — {info['type']} · "
                f"MINSTEP = {info['minstep']} · STEPPRICE = {info['stepprice']} ₽"
            )

    if not step_price or step_price <= 0:
        st.error("Не удалось определить шаг цены. Проверьте тикер или включите ручной ввод.")
    else:
        qty_raw = stop_rub / (ticks * step_price)
        qty = math.floor(qty_raw)

        st.metric("Количество бумаг", f"{qty}")
        st.caption(f"Точное значение до округления: {qty_raw:.4f}")

        if qty < 1:
            st.warning("Размер стопа слишком мал — округлённое количество меньше 1.")

        with st.expander("Показать расчёт"):
            st.write("**Формула:** `qty = stop_rub / (ticks × step_price)`")
            st.write(f"`qty = {stop_rub} / ({ticks} × {step_price}) = {qty_raw:.4f} → {qty}`")
