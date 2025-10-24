import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(page_title="EdgeFinder Lite (MVP)", layout="wide")
st.title("🧭 EdgeFinder Lite (MVP)")

# Instruments we score
INSTRUMENTS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "XAUUSD=X",  # Gold vs USD
}

# -------------------------------------------------
# DATA FETCH
# -------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_prices(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    Safely pull price history for a ticker from yfinance.
    Returns a cleaned DataFrame or an empty DataFrame on error.
    """
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        # yfinance sometimes returns non-DataFrame if it fails
        if not isinstance(df, pd.DataFrame):
            return pd.DataFrame()

        df = df.dropna()
        return df
    except Exception:
        return pd.DataFrame()


# -------------------------------------------------
# INDICATORS / SCORING
# -------------------------------------------------
def score_trend(df: pd.DataFrame) -> int:
    """
    Trend score 0-3 using moving averages and slope.
    Returns 1 (neutral) if we can't really judge trend.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return 1

    close = df["Close"]

    # need some history to say anything
    if len(close) < 60:
        return 1

    ma50 = close.rolling(50).mean()

    # fallback: if not enough candles for a real 200MA, reuse 50MA
    if len(close) >= 200:
        ma200 = close.rolling(200).mean()
    else:
        ma200 = ma50

    score = 0

    # 1) price above ma50
    try:
        if close.iloc[-1] > ma50.iloc[-1]:
            score += 1
    except Exception:
        pass

    # 2) ma50 above ma200
    try:
        if ma50.iloc[-1] > ma200.iloc[-1]:
            score += 1
    except Exception:
        pass

    # 3) ma50 rising over last ~5 bars
    try:
        # make sure we have enough points in ma50
        if len(ma50) >= 6 and (ma50.iloc[-1] - ma50.iloc[-6]) > 0:
            score += 1
    except Exception:
        pass

    return int(score)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute RSI for a price series.
    Returns a full Series of RSI values, may contain NaNs at the start.
    """
    delta = series.diff()

    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)

    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()

    rs = roll_up / (roll_down + 1e-9)
    out = 100 - (100 / (1 + rs))
    return out


def score_momentum(df: pd.DataFrame) -> int:
    """
    Momentum score 0-3 from RSI.
    Returns 1 (neutral) if not enough candles / calculation fails.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return 1

    # need some candles for RSI to be meaningful
    if len(df) < 15:
        return 1

    try:
        rsi_series = rsi(df["Close"])
        if rsi_series is None or len(rsi_series) == 0:
            return 1
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


def score_macro_placeholder(symbol: str) -> int:
    """
    Placeholder macro score.
    Later this becomes Retail Sales / PMI / CPI surprise.
    """
    return 1


def score_cot_placeholder(symbol: str) -> int:
    """
    Placeholder COT score.
    Later this becomes non-commercial net positioning z-score.
    """
    return 1


def overall_recommendation(total: int) -> str:
    """
    Map the combined score (0-12) to a friendly label.
    """
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
    Return last Close as float, or 'N/A' if not available.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return "N/A"
    try:
        return float(df["Close"].iloc[-1])
    except Exception:
        return "N/A"


def safe_last_date(df: pd.DataFrame):
    """
    Return last timestamp as YYYY-MM-DD string, or '' if not available.
    """
    if df is None or df.empty:
        return ""
    try:
        return df.index[-1].date().isoformat()
    except Exception:
        return ""


# -------------------------------------------------
# SIDEBAR CONTROLS
# -------------------------------------------------
with st.sidebar:
    st.header("Settings")
    period = st.selectbox("History period", ["3mo", "6mo", "1y"], index=1)
    interval = st.selectbox("Interval", ["1d", "1h"], index=0)
    st.caption("Shorter period = faster load. If data fails to load, you'll see N/A but the app won't crash.")


# -------------------------------------------------
# MAIN TABLE BUILD
# -------------------------------------------------
rows = []

with st.status("Fetching data…", expanded=False) as status:
    for symbol_name, yfticker in INSTRUMENTS.items():
        # pull data
        df = get_prices(yfticker, period=period, interval=interval)

        # compute scores (all are safe / guarded)
        trend_score = score_trend(df)
        momentum_score = score_momentum(df)
        macro_score = score_macro_placeholder(symbol_name)
        cot_score = score_cot_placeholder(symbol_name)

        total_score = trend_score + momentum_score + macro_score + cot_score

        # safely get last price/date
        last_price = safe_last_price(df)
        last_date = safe_last_date(df)

        # build the row
        row = {
            "Symbol": symbol_name,
            "Trend(0-3)": trend_score,
            "Momentum(0-3)": momentum_score,
            "Macro(0-3)": macro_score,
            "COT(0-3)": cot_score,
            "Total(0-12)": total_score,
            "Recommendation": overall_recommendation(total_score),
            "Last Price": last_price,
            "Updated": last_date,
        }
        rows.append(row)

    status.update(label="Done", state="complete", expanded=False)

# show results
df_table = pd.DataFrame(rows).sort_values("Total(0-12)", ascending=False)
st.dataframe(df_table, use_container_width=True)

st.caption("Stable build ✅ No more index errors if data is missing. Next step: real Macro score using Retail Sales / PMI / CPI.")
