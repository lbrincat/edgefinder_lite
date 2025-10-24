import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="EdgeFinder Lite (MVP)", layout="wide")
st.title("🧭 EdgeFinder Lite (MVP)")

INSTRUMENTS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "XAUUSD=X",  # Gold
}

# ---------- DATA FETCH ----------

@st.cache_data(ttl=3600, show_spinner=False)
def get_prices(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    Returns OHLC dataframe or an empty dataframe if download fails.
    """
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        # yfinance sometimes returns a dict-like object on errors; guard for that
        if not isinstance(df, pd.DataFrame):
            return pd.DataFrame()

        df = df.dropna()
        return df
    except Exception:
        # if yfinance throws (rate limit, etc.), return empty
        return pd.DataFrame()


# ---------- SCORING HELPERS ----------

def score_trend(df: pd.DataFrame) -> int:
    """
    Trend score 0-3 based on MA relationships and slope.
    Returns 1 (neutral) if we don't have enough data.
    """
    # safety checks
    if df is None or df.empty or "Close" not in df.columns:
        return 1

    close = df["Close"]

    # Need at least ~60 candles so MA50 slope makes sense
    if len(close) < 60:
        return 1

    ma50 = close.rolling(50).mean()

    # If we don't have 200 bars yet, fall back to ma50 as "ma200"
    if len(close) >= 200:
        ma200 = close.rolling(200).mean()
    else:
        ma200 = ma50

    score = 0

    # price above ma50
    try:
        if close.iloc[-1] > ma50.iloc[-1]:
            score += 1
    except Exception:
        pass

    # ma50 above ma200
    try:
        if ma50.iloc[-1] > ma200.iloc[-1]:
            score += 1
    except Exception:
        pass

    # ma50 rising over last ~5 bars
    try:
        if len(ma50) >= 6 and (ma50.iloc[-1] - ma50.iloc[-6]) > 0:
            score += 1
    except Exception:
        pass

    return int(score)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Standard RSI calc, returns a full Series.
    If series is too short, you'll just get mostly NaN.
    """
    delta = series.diff()

    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)

    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()

    rs = roll_up / (roll_down + 1e-9)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def score_momentum(df: pd.DataFrame) -> int:
    """
    Momentum score from RSI.
    Returns 1 (neutral) if we can't compute cleanly.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return 1

    # We need enough points to compute RSI
    if len(df) < 15:
        return 1

    try:
        rsi_series = rsi(df["Close"])
        # guard: rsi_series could be all NaN
        if rsi_series is None or len(rsi_series) == 0:
            return 1
        r = rsi_series.iloc[-1]
    except Exception:
        return 1

    if pd.isna(r):
        return 1
    if r >= 60:
        return 3
    if r >= 50:
        return 2
    if r >= 40:
        return 1
    return 0


def score_macro_placeholder(symbol: str) -> int:
    """
    Placeholder until we wire Retail Sales / PMI / CPI, etc.
    """
    return 1


def score_cot_placeholder(symbol: str) -> int:
    """
    Placeholder until we wire COT positioning.
    """
    return 1


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
    """
    Get last close if available, else 'N/A'.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return "N/A"
    try:
        return float(df["Close"].iloc[-1])
    except Exception:
        return "N/A"


def safe_last_date(df: pd.DataFrame):
    """
    Get last timestamp if available, else ''.
    """
    if df is None or df.empty:
        return ""
    try:
        return str(df.index[-1].date())
    except Exception:
        return ""


# ---------- SIDEBAR CONTROLS ----------

with st.sidebar:
    st.header("Settings")
    period = st.selectbox("History period", ["3mo", "6mo", "1y"], index=1)
    interval = st.selectbox("Interval", ["1d", "1h"], index=0)
    st.caption("Shorter period = faster load.")


# ---------- MAIN TABLE BUILD ----------

rows = []

with st.status("Fetching data…", expanded=False) as status:
    for name, yfticker in INSTRUMENTS.items():
        df = get_prices(yfticker, period=period, interval=interval)

        # compute each component safely
        trend = score_trend(df)
        mom = score_momentum(df)
        macro = score_macro_placeholder(name)
        cot = score_cot_placeholder(name)

        total = trend + mom + macro + cot

        row = {
            "Symbol": name,
            "Trend(0-3)": trend,
            "Momentum(0-3)": mom,
            "Macro(0-3)": macro,
            "COT(0-3)": cot,
            "Total(0-12)": total,
            "Recommendation": overall_recommendation(total),
            "Last Price": safe_last_price(df),
            "Updated": safe_last_date(df),
        }

        rows.append(row)

    status.update(label="Done", state="complete", expanded=False)


df_table = pd.DataFrame(rows).sort_values("Total(0-12)", ascending=False)
st.dataframe(df_table, use_container_width=True)

st.caption("Stable build ✅ — No crashes on empty data. Macro & COT are still placeholders; next step is wiring real Retail Sales / PMI / COT.")
