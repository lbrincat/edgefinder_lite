import requests
from datetime import datetime
import streamlit as st

# Map dashboard regions to currency codes coming from your PHP API
REGION_CCY = {
    "us": "USD",
    "eurozone": "EUR",
    "uk": "GBP",
    "canada": "CAD",
    "australia": "AUD",
    "new_zealand": "NZD",
    "switzerland": "CHF",
    "japan": "JPY",
}

# Your InfinityFree endpoint
API_URL = "https://economic-calendar.ct.ws/calendar.php"


def fetch_calendar_events():
    """
    Fetch all econ events as JSON from your InfinityFree PHP script.
    Expected per item:
      {
        "currency": "USD",
        "event": "Retail Sales (MoM)",
        "actual": "0.7%",
        "forecast": "0.2%",
        "previous": "0.3%",
        "timestamp": "2025-10-22T12:30:00Z"
      }
    """
    try:
        resp = requests.get(
            API_URL,
            timeout=8,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                "Referer": "https://economic-calendar.ct.ws/",
            },
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            # fallback if something weird happens
            return []
    except Exception:
        return []


def _pct_to_float(pct_str):
    """
    '0.7%' -> 0.7
    '-0.5%' -> -0.5
    '2.1%' -> 2.1
    None or '' -> None
    """
    if not isinstance(pct_str, str):
        return None
    cleaned = pct_str.replace("%", "").strip()
    if cleaned == "" or cleaned.lower() == "n/a":
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def _num_to_float(x):
    """
    '51.2' -> 51.2
    48.7   -> 48.7
    etc.
    """
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).strip())
    except Exception:
        return None


def _pick_latest(events_for_ccy, keywords):
    """
    From all events for one currency (USD, EUR, ...),
    pick the most recent row whose 'event' field matches any keyword.
    We'll sort by timestamp desc.
    """
    filtered = []
    for ev in events_for_ccy:
        name = str(ev.get("event", "")).lower()
        if any(k.lower() in name for k in keywords):
            filtered.append(ev)

    if not filtered:
        return None

    def parse_ts(ts):
        # timestamps are like "2025-10-22T12:30:00Z"
        t = str(ts or "")
        try:
            return datetime.fromisoformat(t.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    filtered.sort(key=lambda ev: parse_ts(ev.get("timestamp")), reverse=True)
    return filtered[0]


def build_region_components(events_for_ccy):
    """
    Extract 3 macro pillars for that currency:
    Retail Sales, PMI, CPI.
    Return (retail, pmi, cpi) where each is a dict
    or None if not found.
    """

    # Retail Sales
    retail_ev = _pick_latest(
        events_for_ccy,
        ["retail sales", "retail sales (mom)", "core retail sales"]
    )
    retail = None
    if retail_ev:
        retail = {
            "actual": _pct_to_float(retail_ev.get("actual")),
            "forecast": _pct_to_float(retail_ev.get("forecast")),
            "previous": _pct_to_float(retail_ev.get("previous")),
        }

    # PMI
    pmi_ev = _pick_latest(
        events_for_ccy,
        ["pmi", "manufacturing pmi", "services pmi", "composite pmi"]
    )
    pmi = None
    if pmi_ev:
        pmi = {
            "current": _num_to_float(pmi_ev.get("actual")),
            "previous": _num_to_float(pmi_ev.get("previous")),
        }

    # CPI / Inflation
    cpi_ev = _pick_latest(
        events_for_ccy,
        ["cpi", "inflation", "inflation rate", "cpi (yoy)"]
    )
    cpi = None
    if cpi_ev:
        cpi = {
            "actual_yoy": _pct_to_float(cpi_ev.get("actual")),
            "forecast_yoy": _pct_to_float(cpi_ev.get("forecast")),
            "previous_yoy": _pct_to_float(cpi_ev.get("previous")),
        }

    return retail, pmi, cpi


def score_region_macro(retail, pmi, cpi):
    """
    +1 Retail Sales beat forecast or previous
    +1 PMI >=50 or improving
    +1 CPI hotter than forecast (implies rate pressure)
    Clamp 0..3
    """
    score = 0

    # Retail
    if retail:
        a = retail.get("actual")
        f = retail.get("forecast")
        p = retail.get("previous")
        if a is not None:
            if (f is not None and a > f) or (p is not None and a > p):
                score += 1

    # PMI
    if pmi:
        cur = pmi.get("current")
        prev = pmi.get("previous")
        if cur is not None:
            if cur >= 50:
                score += 1
            elif prev is not None and cur > prev:
                score += 1

    # CPI
    if cpi:
        act = cpi.get("actual_yoy")
        fc  = cpi.get("forecast_yoy")
        if act is not None:
            if fc is not None and act > fc:
                score += 1
            elif fc is None and act is not None and act >= 2.0:
                score += 1

    if score < 0:
        score = 0
    if score > 3:
        score = 3
    return score


def summarize_bias(score: int):
    if score >= 3:
        return "Strong macro, bullish bias"
    if score == 2:
        return "Supportive macro, mild bullish bias"
    if score == 1:
        return "Neutral / mixed"
    return "Weak macro, bearish bias"


def build_region_snapshot(events, region_key):
    """
    One region = one currency code.
    Example: region_key 'us' -> USD.
    We'll gather that currency's events and build:
    { retail, pmi, cpi, score, bias }
    """
    ccy = REGION_CCY.get(region_key)
    if not ccy:
        return {
            "retail": None,
            "pmi": None,
            "cpi": None,
            "score": 1,
            "bias": "Neutral / mixed",
        }

    events_for_ccy = [ev for ev in events if ev.get("currency") == ccy]

    retail, pmi, cpi = build_region_components(events_for_ccy)
    score = score_region_macro(retail, pmi, cpi)
    bias_text = summarize_bias(score)

    return {
        "retail": retail,
        "pmi": pmi,
        "cpi": cpi,
        "score": score,
        "bias": bias_text,
    }


@st.cache_data(ttl=43200, show_spinner=False)
def get_macro_snapshot_all():
    """
    Pull data (cached ~12h) and build the macro snapshot for all regions.
    Shape:
    {
      "us": {...},
      "eurozone": {...},
      "uk": {...},
      ...
      "last_updated": "2025-10-25 14:07 UTC"
    }
    """
    events = fetch_calendar_events()

    snapshot = {}
    for region_key in REGION_CCY.keys():
        snapshot[region_key] = build_region_snapshot(events, region_key)

    snapshot["last_updated"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return snapshot
