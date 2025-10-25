import streamlit as st
import pandas as pd
from shared_data import get_macro_snapshot_all

st.set_page_config(page_title="Macro Dashboard", layout="wide")
st.title("🌍 Macro Dashboard")

macro_snapshot = get_macro_snapshot_all()
last_updated = macro_snapshot.get("last_updated", "N/A")
st.caption(f"🕒 Last updated: {last_updated}")

display_order = [
    ("eurozone",     "🇪🇺 Eurozone"),
    ("uk",           "🇬🇧 United Kingdom"),
    ("us",           "🇺🇸 United States"),
    ("canada",       "🇨🇦 Canada"),
    ("australia",    "🇦🇺 Australia"),
    ("new_zealand",  "🇳🇿 New Zealand"),
    ("switzerland",  "🇨🇭 Switzerland"),
    ("japan",        "🇯🇵 Japan"),
]

def fmt_retail(retail):
    if not retail:
        return "N/A"
    a = retail.get("actual", None)
    f = retail.get("forecast", None)
    p = retail.get("previous", None)
    status = ""
    if a is not None and f is not None and a > f:
        status = "✅"
    elif a is not None and p is not None and a > p:
        status = "✅"
    elif a is not None and p is not None and a < p:
        status = "❌"
    else:
        status = "➖"
    def fmt(x):
        return f"{x:.2f}%" if x is not None else "?"
    return f"{fmt(a)} vs {fmt(f)} / {fmt(p)} {status}"

def fmt_pmi(pmi):
    if not pmi:
        return "N/A"
    cur = pmi.get("current", None)
    prev = pmi.get("previous", None)
    if cur is None:
        return "N/A"
    if prev is not None:
        if cur > prev:
            arrow = "↑"
        elif cur < prev:
            arrow = "↓"
        else:
            arrow = "↔"
    else:
        arrow = "↔"
    exp_flag = "✅" if cur >= 50 else "❌"
    return f"{cur:.1f} {arrow} {exp_flag}"

def fmt_cpi(cpi):
    if not cpi:
        return "N/A"
    a = cpi.get("actual_yoy", None)
    f = cpi.get("forecast_yoy", None)
    if a is None:
        return "N/A"
    if f is not None:
        if a > f:
            fire = "🔥"
        elif a < f:
            fire = "🧊"
        else:
            fire = "↔"
    else:
        fire = ""
    return f"{a:.2f}% {fire}"

table_rows = []
for key, label in display_order:
    info = macro_snapshot.get(key, {})
    score = info.get("score", 1)
    bias  = info.get("bias", "Neutral / mixed")
    retail_txt = fmt_retail(info.get("retail"))
    pmi_txt    = fmt_pmi(info.get("pmi"))
    cpi_txt    = fmt_cpi(info.get("cpi"))

    table_rows.append({
        "Region": label,
        "Retail Sales (m/m)": retail_txt,
        "PMI": pmi_txt,
        "CPI YoY": cpi_txt,
        "Macro Score (0-3)": score,
        "Bias": bias,
    })

df_macro = pd.DataFrame(table_rows)

def color_score(val):
    styles = {
        3: "background-color: #2ecc71; color: white;",
        2: "background-color: #f1c40f; color: black;",
        1: "background-color: #bdc3c7; color: black;",
        0: "background-color: #e74c3c; color: white;",
    }
    return styles.get(val, "")

styled_macro = df_macro.style.applymap(
    color_score, subset=["Macro Score (0-3)"]
).set_table_styles([
    {"selector": "th", "props": [("background-color", "#1e1e1e"), ("color", "white")]}
])

st.dataframe(styled_macro, use_container_width=True)

strongest = df_macro.sort_values("Macro Score (0-3)", ascending=False).iloc[0]
weakest = df_macro.sort_values("Macro Score (0-3)", ascending=True).iloc[0]

st.markdown(
    f"**Summary:** Strongest macro right now is {strongest['Region']} "
    f"({strongest['Macro Score (0-3)']}/3). "
    f"Weakest is {weakest['Region']} "
    f"({weakest['Macro Score (0-3)']}/3)."
)
