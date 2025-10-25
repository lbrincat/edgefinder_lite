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

    We expect each item in the JSON list to look like:
    {
        "currency": "USD",
        "event": "Retail Sales (MoM)",
        "actual": "0.7%",
        "forecast": "0.2%",
        "previous": "0.3%",
        "timestamp": "2025-10-22T12:30:00Z"
    }

    We'll:
    - send browser-like headers
    - log what we got to help debug
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

        print("DEBUG-status:", resp.status_code)
        print("DEBUG-first-300:", resp.text[:300])

        if resp.status_code == 200:
            try:
                data = resp.json()
                print("DEBUG-json-sample:", data[:3] if isinstance(data, list) else data)
                return data
            except Exception as e:
                print("DEBUG-json-parse-error:", e)
                return []
        else:
            print("DEBUG-non-200:", resp.status_code, resp.text[:200])
            return []
    except Exception as e:
        print("DEBUG-request-exception:", e)
        return []


def _pct_to_float(pct_str):
    """
    '0.7%' -> 0.7
    '-0.5%' -> -0.5
    '2.1%' -> 2.1
    'N/A' or '' -> None
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


def _parse_timestamp(ts_value):
    """
    We expect timestamps like '2025-10-22T12:30:00Z'.
    If it's missing or bad, return datetime.min so sorting doesn't explode.
    """
    if not ts_value:
        return datetime.min
    try:
        # fromisoformat can't handle 'Z' directly, so swap for '+00:00'
        return datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _pick_latest(events_for_ccy, keywords):
    """
    For a given currency's events (USD, EUR, ...),
    find the most recent row whose 'event' matches any keyword in `keywords`.

    We'll sort by timestamp desc and return the newest.
    """
    filtered = []
    for ev in events_for_ccy:
        name = str(ev.get("event", "")).lower()
        if any(k.lower() in name for k in keywords):
            filtered.append(ev)

    if not filtered:
        return None

    filtered.sort(key=lambda ev: _parse_timestamp(ev.get("timestamp")), reverse=True)
    return filtered[0]


def build_region_components(events_for_ccy):
    """
    From all events for this currency, extract:
      Retail Sales (MoM / QoQ)
      PMI (Manufacturing/Services/Composite)
      CPI/Inflation (YoY)
    and convert them into structured dicts.

    Returns (retail, pmi, cpi) where each is either dict or None.
    """

    # --- Retail Sales ---
    retail_ev = _pick_latest(
        events_for_ccy,
        ["retail sales", "retail sales (mom)", "core retail sales", "retail sales (qoq)"]
    )
    retail = None
    if retail_ev:
        retail = {
            "actual": _pct_to_float(retail_ev.get("actual")),
            "forecast": _pct_to_float(retail_ev.get("forecast")),
            "previous": _pct_to_float(retail_ev.get("previous")),
        }

    # --- PMI ---
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

    # --- CPI / Inflation ---
    cpi_ev = _pick_latest(
        events_for_ccy,
        ["cpi", "cpi (yoy)", "inflation", "inflation rate"]
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
    Scoring rules (0 to 3 total):

    +1 Retail Sales:
        if actual > forecast OR actual > previous

    +1 PMI:
        if PMI >= 50 (expansion)
        OR PMI is higher than previous

    +1 CPI:
        if inflation (actual) > forecast (hotter than expected)
        OR (no forecast given but inflation >= 2.0)

    Then clamp to [0, 3].
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
            elif fc is None and act >= 2.0:
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
    Build one region's view:
    {
      "retail": {actual, forecast, previous},
      "pmi":    {current, previous},
      "cpi":    {actual_yoy, forecast_yoy, previous_yoy},
      "score":  0-3,
      "bias":   "Strong macro, bullish bias"
    }

    We do this by:
    - finding all events where ev["currency"] == mapped currency (USD, EUR, ...)
    - extracting latest Retail Sales, PMI, CPI
    - scoring them
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

    # Debug: see what we're actually seeing per region
    # (will show in Render logs)
    print(f"DEBUG-{region_key}-events-sample:", events_for_ccy[:3])

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
    Called by Home.py and Macro Dashboard.
    Returns:
    {
      "us": {...},
      "eurozone": {...},
      ...,
      "last_updated": "2025-10-25 14:07 UTC"
    }
    """
    events = fetch_calendar_events()

    # Debug: top-level log
    print("DEBUG-total-events:", len(events))

    snapshot = {}
    for region_key in REGION_CCY.keys():
        snapshot[region_key] = build_region_snapshot(events, region_key)

    snapshot["last_updated"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print("DEBUG-snapshot-keys:", list(snapshot.keys()))
    return snapshot
