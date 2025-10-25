import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

from shared_data import get_macro_snapshot_all

st.set_page_config(page_title="EdgeFinder Lite", layout="wide")
st.title("📊 EdgeFinder Lite — Signals")

INSTRUMENTS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "CAD=X",
    "USDCHF": "CHF=X",
    "XAUUSD": "XAUUSD=X",
    "XAGUSD": "XAGUSD=X",
}

MACRO_REGION = {
    "EURUSD": "eurozone",
    "GBPUSD": "uk",
    "USDJPY": "us",
    "AUDUSD": "australia",
    "NZDUSD": "new_zealand",
    "USDCAD": "canada",
    "USDCHF": "switzerland",
    "XAUUSD": "us",
    "XAGUSD": "us",
}

@st.cache_data(ttl=3600, show_spinner=False)
def get_prices(ticker: str, period: str = "6mo", interval: str = "1d"):
    # swallow yfinance stdout/stderr spam
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            df = yf.download(
                ticker,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
            )
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df.dropna()
        else:
            return pd.DataFrame()
    except Exception as e:
        print(f"PRICE-ERROR {ticker}:", e)
        return pd.DataFrame()

def score_trend(df: pd.DataFrame) -> int:
    if df.empty or "Close" not in df.columns:
        return 1
    close = df["Close"]
    if len(close) < 60:
        return 1
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean() if len(close) >= 200 else ma50
    score = 0
    try:
        if close.iloc[-1] > ma50.iloc[-1]:
            score += 1
    except Exception:
        pass
    try:
        if ma50.iloc[-1] > ma200.iloc[-1]:
            score += 1
    except Exception:
        pass
    try:
        if len(ma50) >= 6 and (ma50.iloc[-1] - ma50.iloc[-6]) > 0:
            score += 1
    except Exception:
        pass
    return int(score)

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()
    rs = roll_up / (roll_down + 1e-9)
    out = 100 - (100 / (1 + rs))
    return out

def score_momentum(df: pd.DataFrame) -> int:
    if df.empty or "Close" not in df.columns:
        return 1
    if len(df) < 15:
        return 1
    try:
        rsi_series = rsi(df["Close"])
        last_rsi = rsi_series.iloc[-1]
    except Exception:
        return 1
    if pd.isna(last_rsi):
        return 1
    if last_rsi >= 60:
        return 3
    if last_rsi >= 50:
        return 2
    if last_rsi >= 40:
        return 1
    return 0

def overall_recommendation(total: int) -> str:
    if total >= 7:
        return "Strong Buy"
    if total >= 5:
        return "Buy"
    if total >= 3:
        return "Neutral"
    if total >= 1:
        return "Sell"
    return "Strong Sell"

def safe_last_price(df: pd.DataFrame):
    if df.empty or "Close" not in df.columns:
        return "N/A"
    try:
        return float(df["Close"].iloc[-1])
    except Exception:
        return "N/A"

def safe_last_date(df: pd.DataFrame):
    if df.empty:
        return ""
    try:
        return df.index[-1].date().isoformat()
    except Exception:
        return ""

with st.sidebar:
    st.header("Settings")
    period = st.selectbox("History period", ["3mo", "6mo", "1y"], index=1)
    interval = st.selectbox("Interval", ["1d", "1h"], index=0)
    st.caption("Shorter period = faster load.")

with st.status("Loading macro data…", expanded=False) as macro_status:
    macro_snapshot = get_macro_snapshot_all()
    macro_status.update(label="Macro loaded", state="complete", expanded=False)

rows = []

with st.status("Fetching price data…", expanded=False) as price_status:
    for sym_name, yfticker in INSTRUMENTS.items():
        df_px = get_prices(yfticker, period=period, interval=interval)

        trend_score = score_trend(df_px)
        mom_score = score_momentum(df_px)

        region_key = MACRO_REGION.get(sym_name, "us")
        region_info = macro_snapshot.get(region_key, {})
        macro_score = region_info.get("score", 1)

        cot_score = 1  # placeholder

        total_score = trend_score + mom_score + macro_score + cot_score

        rows.append({
            "Symbol": sym_name,
            "Trend(0-3)": trend_score,
            "Momentum(0-3)": mom_score,
            "Macro(0-3)": macro_score,
            "COT(0-3)": cot_score,
            "Total(0-12)": total_score,
            "Recommendation": overall_recommendation(total_score),
            "Last Price": safe_last_price(df_px),
            "Updated": safe_last_date(df_px),
        })
    price_status.update(label="Price loaded", state="complete", expanded=False)

df_table = pd.DataFrame(rows)

def color_macro(val):
    styles = {
        3: "background-color: #2ecc71; color: white;",
        2: "background-color: #f1c40f; color: black;",
        1: "background-color: #bdc3c7; color: black;",
        0: "background-color: #e74c3c; color: white;",
    }
    return styles.get(val, "")

styled = df_table.sort_values("Total(0-12)", ascending=False).style.applymap(
    color_macro, subset=["Macro(0-3)"]
).set_table_styles([
    {"selector": "th", "props": [("background-color", "#1e1e1e"), ("color", "white")]}
])

st.dataframe(styled, use_container_width=True)

st.caption(
    "Macro(0-3) is live Retail Sales / PMI / CPI for that region. "
    "Green = strong, Red = weak. "
    "COT(0-3) is placeholder for now."
)
