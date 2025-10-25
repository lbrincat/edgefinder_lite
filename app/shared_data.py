import requests
import re
from datetime import datetime
import streamlit as st

REGION_URLS = {
    "us": "https://www.investing.com/economic-calendar/united-states",
    "eurozone": "https://www.investing.com/economic-calendar/euro-zone",
    "uk": "https://www.investing.com/economic-calendar/united-kingdom",
    "canada": "https://www.investing.com/economic-calendar/canada",
    "australia": "https://www.investing.com/economic-calendar/australia",
    "new_zealand": "https://www.investing.com/economic-calendar/new-zealand",
    "switzerland": "https://www.investing.com/economic-calendar/switzerland",
    "japan": "https://www.investing.com/economic-calendar/japan",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def _fetch_calendar_html(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        return None
    return None

def _extract_block(html: str, keyword: str, span: int = 400):
    if not html:
        return None
    idx = html.lower().find(keyword.lower())
    if idx == -1:
        return None
    return html[idx: idx + span]

def _extract_percents(block: str):
    if not block:
        return []
    matches = re.findall(r'[-+]?\d+\.\d+\s*%', block)
    vals = []
    for m in matches:
        try:
            vals.append(float(m.replace('%', '').strip()))
        except Exception:
            pass
    return vals

def _extract_numbers(block: str):
    if not block:
        return []
    matches = re.findall(r'[-+]?\d+\.\d+', block)
    vals = []
    for m in matches:
        try:
            vals.append(float(m.strip()))
        except Exception:
            pass
    return vals

def parse_retail_sales(block: str):
    vals = _extract_percents(block)
    if not vals:
        return None
    data = {
        "actual":   vals[0] if len(vals) > 0 else None,
        "forecast": vals[1] if len(vals) > 1 else None,
        "previous": vals[2] if len(vals) > 2 else None,
    }
    return data

def parse_pmi(block: str):
    vals = _extract_numbers(block)
    if not vals:
        return None
    data = {
        "current":  vals[0] if len(vals) > 0 else None,
        "previous": vals[1] if len(vals) > 1 else None,
    }
    return data

def parse_cpi(block: str):
    vals = _extract_percents(block)
    if not vals:
        return None
    data = {
        "actual_yoy":   vals[0] if len(vals) > 0 else None,
        "forecast_yoy": vals[1] if len(vals) > 1 else None,
        "previous_yoy": vals[2] if len(vals) > 2 else None,
    }
    return data

def score_region_macro(retail, pmi, cpi):
    score = 0

    if retail and "actual" in retail:
        actual = retail.get("actual")
        forecast = retail.get("forecast")
        previous = retail.get("previous")
        if actual is not None:
            if (forecast is not None and actual > forecast) or (previous is not None and actual > previous):
                score += 1

    if pmi and "current" in pmi:
        cur = pmi.get("current")
        prev = pmi.get("previous")
        if cur is not None:
            if cur >= 50:
                score += 1
            elif prev is not None and cur > prev:
                score += 1

    if cpi and "actual_yoy" in cpi:
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

def get_region_macro(region_key: str):
    url = REGION_URLS.get(region_key)
    html = _fetch_calendar_html(url) if url else None

    retail_block = _extract_block(html, "Retail Sales")
    pmi_block    = _extract_block(html, "PMI")
    cpi_block    = _extract_block(html, "CPI")

    retail = parse_retail_sales(retail_block) if retail_block else None
    pmi    = parse_pmi(pmi_block) if pmi_block else None
    cpi    = parse_cpi(cpi_block) if cpi_block else None

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
    snapshot = {}
    for r in REGION_URLS.keys():
        snapshot[r] = get_region_macro(r)
    snapshot["last_updated"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return snapshot
