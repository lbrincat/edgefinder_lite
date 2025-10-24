import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="EdgeFinder Lite", layout="wide")
st.title("🧭 EdgeFinder Lite (MVP)")

INSTRUMENTS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "XAUUSD=X",
}

@st.cache_data(ttl=3600)
def get_prices(ticker, period="1y", interval="1d"):
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
    df = df.dropna()
    return df

def score_trend(df):
    close = df["Close"]
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    score = 0
    if len(close) < 200:
        return 1
    if close.iloc[-1] > ma50.iloc[-1]: score += 1
    if ma50.iloc[-1] > ma200.iloc[-1]: score += 1
    if (ma50.iloc[-1] - ma50.iloc[-5]) > 0: score += 1
    return score

def rsi(series, period=14):
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()
    rs = roll_up / (roll_down + 1e-9)
    return 100 - (100 / (1 + rs))

def score_momentum(df):
    r = rsi(df["Close"]).iloc[-1]
    if r >= 60: return 3
    if r >= 50: return 2
    if r >= 40: return 1
    return 0

def score_macro_placeholder(symbol):
    return 1

def score_cot_placeholder(symbol):
    return 1

def overall_recommendation(total):
    if total >= 7: return "Strong Buy"
    if total >= 5: return "Buy"
    if total >= 3: return "Neutral"
    if total >= 1: return "Sell"
    return "Strong Sell"

rows = []
for name, yfticker in INSTRUMENTS.items():
    df = get_prices(yfticker)
    trend = score_trend(df)
    mom = score_momentum(df)
    macro = score_macro_placeholder(name)
    cot = score_cot_placeholder(name)
    total = trend + mom + macro + cot
    rows.append({
        "Symbol": name,
        "Trend(0-3)": trend,
        "Momentum(0-3)": mom,
        "Macro(0-3)": macro,
        "COT(0-3)": cot,
        "Total(0-12)": total,
        "Recommendation": overall_recommendation(total),
        "Last Price": float(df["Close"].iloc[-1]),
        "Updated": df.index[-1].date().isoformat(),
    })

df_table = pd.DataFrame(rows).sort_values("Total(0-12)", ascending=False)
st.dataframe(df_table, use_container_width=True)
st.caption("Macro & COT are placeholders. Wire real sources next.")
