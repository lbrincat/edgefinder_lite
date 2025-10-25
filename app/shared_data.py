import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import streamlit as st

# We'll try using the mobile site versions for lighter HTML.
REGION_URLS = {
    "us": "https://m.investing.com/economic-calendar/united-states",
    "eurozone": "https://m.investing.com/economic-calendar/euro-zone",
    "uk": "https://m.investing.com/economic-calendar/united-kingdom",
    "canada": "https://m.investing.com/economic-calendar/canada",
    "australia": "https://m.investing.com/economic-calendar/australia",
    "new_zealand": "https://m.investing.com/economic-calendar/new-zealand",
    "switzerland": "https://m.investing.com/economic-calendar/switzerland",
    "japan": "https://m.investing.com/economic-calendar/japan",
}

MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; Pixel 4 XL) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_calendar_html(url: str):
    """
    Download the page HTML for a region.
    We spoof a mobile device UA to avoid heavier desktop anti-bot.
    Return None if blocked or error.
    """
    if not url:
        return None
    try:
        resp = requests.get(url, headers=MOBILE_HEADERS, timeout=6)
        if resp.status_code == 200 and resp.text:
            return resp.text
    except Exception:
        return None
    return None


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _extract_numeric_percent(txt: str | None):
    """
    Find the first thing that looks like a percent: 0.5%, -0.2%, etc.
    Return float (0.5, -0.2, etc.) or None.
    """
    if not txt:
        return None
    m = re.search(r"([-+]?\d+\.\d+)\s*%", txt)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _extract_numeric_plain(txt: str | None):
    """
    For PMI where it's usually like "51.2"
    Return float(51.2) or None.
    """
    if not txt:
        return None
    m = re.search(r"([-+]?\d+\.\d+)", txt)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _parse_calendar_table(html: str):
    """
    Parse the HTML with BeautifulSoup.
    We'll look for table rows (<tr>) that contain indicator names.
    We'll try to pull columns like Actual / Forecast / Previous.
    Return a list of dict rows like:
      {
        'name': 'Retail Sales (MoM)',
        'actual': '0.5%',
        'forecast': '0.2%',
        'previous': '0.3%'
      }
    If we can't find structured <tr>, we fall back to regex scraping of the whole HTML.
    """
    data_rows = []

    if not html:
        return data_rows

    soup = BeautifulSoup(html, "html.parser")

    # Heuristic: Find all rows that look like economic calendar lines
    # Often Investing.com uses <tr> with multiple <td>, where first column is event name.
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue

        # Clean all cells
        cells = [_clean_text(td.get_text()) for td in tds]

        # We try to guess columns:
        # [time?, event name, actual, forecast, previous, ...]
        # We'll try flexible matching.
        event_name = cells[1] if len(cells) > 1 else ""
        actual_val = cells[2] if len(cells) > 2 else ""
        forecast_val = cells[3] if len(cells) > 3 else ""
        previous_val = cells[4] if len(cells) > 4 else ""

        if any(keyword in event_name.lower() for keyword in ["retail sales", "pmi", "cpi", "consumer price", "inflation"]):
            data_rows.append({
                "name": event_name,
                "actual_raw": actual_val,
                "forecast_raw": forecast_val,
                "previous_raw": previous_val,
            })

    # If that failed (0 rows found), we fall back to very rough regex scan
    if not data_rows:
        # crude fallback block slicing
        for kw in ["Retail Sales", "retail sales", "PMI", "pmi", "CPI", "cpi", "Consumer Price", "consumer price"]:
            idx = html.lower().find(kw.lower())
            if idx == -1:
                continue
            block = html[idx: idx + 400]
            # Pull up to 3 percentages for actual/forecast/previous
            percents = re.findall(r"[-+]?\d+\.\d+\s*%", block)
            data_rows.append({
                "name": kw,
                "actual_raw": percents[0] if len(percents) > 0 else "",
                "forecast_raw": percents[1] if len(percents) > 1 else "",
                "previous_raw": percents[2] if len(percents) > 2 else "",
            })

    return data_rows


def _extract_indicator_rows(rows, indicator_keywords):
    """
    Filter parsed table rows for the first one whose 'name' matches any keyword.
    Returns that row dict or None.
    """
    for r in rows:
        n = r.get("name", "").lower()
        if any(k in n for k in indicator_keywords):
            return r
    return None


def parse_retail_sales(rows):
    """
    Look for Retail Sales.
    Return dict {actual, forecast, previous} as floats (percent m/m) or None.
    """
    r = _extract_indicator_rows(
        rows,
        ["retail sales"]
    )
    if not r:
        return None

    actual = _extract_numeric_percent(r.get("actual_raw"))
    forecast = _extract_numeric_percent(r.get("forecast_raw"))
    previous = _extract_numeric_percent(r.get("previous_raw"))

    if actual is None and forecast is None and previous is None:
        return None

    return {
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
    }


def parse_pmi(rows):
    """
    Look for PMI (Composite/Manufacturing/Services).
    We'll just grab the first PMI-style row.
    Return dict {current, previous} as floats or None.
    """
    r = _extract_indicator_rows(
        rows,
        ["pmi"]
    )
    if not r:
        return None

    current = _extract_numeric_plain(r.get("actual_raw"))
    prev    = _extract_numeric_plain(r.get("previous_raw"))

    if current is None and prev is None:
        return None

    return {
        "current": current,
        "previous": prev,
    }


def parse_cpi(rows):
    """
    Look for CPI / Consumer Price Index / Inflation.
    Return dict {actual_yoy, forecast_yoy, previous_yoy} (floats, % YoY if available)
    We attempt to treat the row as YoY.
    """
    r = _extract_indicator_rows(
        rows,
        ["cpi", "consumer price", "inflation"]
    )
    if not r:
        return None

    actual = _extract_numeric_percent(r.get("actual_raw"))
    forecast = _extract_numeric_percent(r.get("forecast_raw"))
    previous = _extract_numeric_percent(r.get("previous_raw"))

    if actual is None and forecast is None and previous is None:
        return None

    return {
        "actual_yoy": actual,
        "forecast_yoy": forecast,
        "previous_yoy": previous,
    }


def score_region_macro(retail, pmi, cpi):
    """
    Same scoring logic:
    +1 if retail sales looks strong
    +1 if PMI looks expansionary/improving
    +1 if CPI looks hot (supports higher-for-longer rates)
    """
    score = 0

    # Retail: actual beats forecast or previous
    if retail:
        a = retail.get("actual")
        f = retail.get("forecast")
        p = retail.get("previous")
        if a is not None:
            if (f is not None and a > f) or (p is not None and a > p):
                score += 1

    # PMI: current >= 50 (expansion) OR > previous
    if pmi:
        cur = pmi.get("current")
        prev = pmi.get("previous")
        if cur is not None:
            if cur >= 50:
                score += 1
            elif prev is not None and cur > prev:
                score += 1

    # CPI: actual > forecast (hot inflation)
    if cpi:
        act = cpi.get("actual_yoy")
        fc  = cpi.get("forecast_yoy")
        if act is not None:
            if fc is not None and act > fc:
                score += 1
            elif fc is None and act is not None and act >= 2.0:
                score += 1

    return max(0, min(score, 3))


def summarize_bias(score: int):
    if score >= 3:
        return "Strong macro, bullish bias"
    if score == 2:
        return "Supportive macro, mild bullish bias"
    if score == 1:
        return "Neutral / mixed"
    return "Weak macro, bearish bias"


def get_region_macro(region_key: str):
    """
    Fetch + parse one region.
    Always returns a dict with keys:
      retail, pmi, cpi, score, bias
    Even if scraping fails, we still return a fallback (score=0).
    """
    url = REGION_URLS.get(region_key)
    html = _fetch_calendar_html(url)

    rows = _parse_calendar_table(html)

    retail = parse_retail_sales(rows)
    pmi    = parse_pmi(rows)
    cpi    = parse_cpi(rows)

    score = score_region_macro(retail, pmi, cpi)
    bias_text = summarize_bias(score)

    return {
        "retail": retail,
        "pmi": pmi,
        "cpi": cpi,
        "score": score,
        "bias": bias_text,
    }


@st.cache_data(ttl=43200, show_spinner=False)  # cache 12h
def get_macro_snapshot_all():
    """
    Build snapshot for all regions + timestamp.
    Streamlit will cache this so we don't hammer the source.
    """
    snapshot = {}
    for region_key in REGION_URLS.keys():
        snapshot[region_key] = get_region_macro(region_key)

    snapshot["last_updated"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return snapshot
