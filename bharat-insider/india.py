"""India rules shared by every bharat-* skill: the NSE clock and calendar,
symbols, Zerodha trading costs, tick rounding, price bands and a polite
NSE fetcher.

This file is copied into every skill folder so each skill installs on its
own. Edit india/india.py at the repo root, then run tools/sync_india.py;
tests/test_repo.py fails if a copy differs.

Standard library only, Python 3.8+.
"""

import gzip
import http.cookiejar
import time as _time
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

# ------------------------------------------------------------------ clock

IST = timezone(timedelta(hours=5, minutes=30))  # no DST in India
OPEN = time(9, 15)
CLOSE = time(15, 30)
PRE_OPEN = time(9, 0)
SQUARE_OFF = time(15, 20)  # Zerodha's MIS auto square-off
FLAT_BY = time(15, 15)  # our default: out before the broker does it for you


def to_ist(utc):
    """An aware datetime (any zone) to IST."""
    return utc.astimezone(IST)


def ist_to_utc(local):
    """An IST datetime to UTC. A naive datetime is read as IST."""
    if local.tzinfo is None:
        local = local.replace(tzinfo=IST)
    return local.astimezone(timezone.utc)


# --------------------------------------------------------------- calendar

# NSE cash-market trading holidays, from nseindia.com/api/holiday-master
# (checked 2026-11-04). Add each year when NSE publishes it (usually December).
HOLIDAYS = {
    date(2026, 1, 15): "Municipal Corporation Election - Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 2, 15): "Mahashivratri",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 21): "Id-Ul-Fitr (Ramadan Eid)",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Id",
    date(2026, 6, 26): "Muharram",
    date(2026, 8, 15): "Independence Day",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 8): "Diwali Laxmi Pujan",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}
HOLIDAY_YEARS = {2026}

# Muhurat trading: a short evening session on Diwali, announced by NSE
# circular each October (2026: CMTR76941). Normal-market times only.
MUHURAT = {
    date(2026, 11, 8): (time(14, 20), time(15, 30)),
}


def trading_day(d):
    """(is_trading_day, reason). reason is "" on a normal day."""
    if d in MUHURAT:
        return True, "Muhurat session"
    if d.weekday() >= 5:
        return False, "weekend"
    if d.year not in HOLIDAY_YEARS:
        # ponytail: unknown years read as closed, so nothing trades on a guess
        return False, "holiday list unknown for %d" % d.year
    if d in HOLIDAYS:
        return False, "NSE holiday: " + HOLIDAYS[d]
    return True, ""


def session(d):
    """(open, close) as IST datetimes, or None when NSE is closed."""
    ok, _ = trading_day(d)
    if not ok:
        return None
    o, c = MUHURAT.get(d, (OPEN, CLOSE))
    return datetime.combine(d, o, IST), datetime.combine(d, c, IST)


def next_open(d):
    """The first session open strictly after day d (IST datetime), or None
    when no known day follows within 30 days."""
    for k in range(1, 31):
        s = session(d + timedelta(days=k))
        if s:
            return s[0]
    return None


# ---------------------------------------------------------------- symbols

INDEX_YAHOO = {"NIFTY": "^NSEI", "NIFTY50": "^NSEI", "BANKNIFTY": "^NSEBANK", "NIFTYBANK": "^NSEBANK"}


def yahoo_symbol(sym):
    """NSE symbol to Yahoo: RELIANCE -> RELIANCE.NS, NIFTY -> ^NSEI.
    Callers URL-encode the result (M&M.NS -> M%26M.NS)."""
    s = sym.strip().upper()
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return INDEX_YAHOO.get(s.replace(" ", ""), s + ".NS")


# ------------------------------------------------------------------ costs

# Zerodha, NSE, from zerodha.com/charges and the brokerage calculator's own
# formulas. Fractions, not percent. "ipft" is NSE's investor protection fund
# charge, which Zerodha adds to the exchange charge.
RATES = {
    "checked": "2026-11-04",
    "eq_intraday": {"brokerage_pct": 0.0003, "brokerage_cap": 20.0, "stt_sell_pct": 0.00025,
                    "exchange_pct": 0.0000297, "ipft_pct": 0.000001, "sebi_pct": 0.000001,
                    "stamp_buy_pct": 0.00003, "gst_pct": 0.18},
    "fut": {"brokerage_pct": 0.0003, "brokerage_cap": 20.0, "stt_sell_pct": 0.0005,
            "exchange_pct": 0.0000173, "ipft_pct": 0.000001, "sebi_pct": 0.000001,
            "stamp_buy_pct": 0.00002, "gst_pct": 0.18},
    "opt": {"brokerage_pct": None, "brokerage_cap": 20.0, "stt_sell_pct": 0.0015,
            "exchange_pct": 0.0003503, "ipft_pct": 0.000005, "sebi_pct": 0.000001,
            "stamp_buy_pct": 0.00003, "gst_pct": 0.18},
}
COST_KEYS = ("brokerage", "stt", "exchange", "sebi", "stamp", "gst", "total")


def _r2(x):
    """Round half up to paise, on the float's exact value (as JS toFixed(2))."""
    return float(Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _r0(x):
    """Round half up to the rupee (as JS Math.round)."""
    return float(Decimal(_r2(x)).quantize(Decimal("1"), ROUND_HALF_UP))


def _rates(segment, rates):
    table = rates or RATES
    if segment not in table or segment == "checked":
        raise ValueError("unknown segment %r: use eq_intraday, fut or opt" % segment)
    return table[segment]


def _brokerage(r, value):
    if not value:
        return 0.0
    if r["brokerage_pct"] is None:
        return r["brokerage_cap"]
    raw = value * r["brokerage_pct"]
    return r["brokerage_cap"] if raw > r["brokerage_cap"] else _r2(raw)


def _costs(r, buy_value, sell_value):
    turnover = _r2(buy_value + sell_value)
    brokerage = _r2(_brokerage(r, buy_value) + _brokerage(r, sell_value))
    stt = _r0(sell_value * r["stt_sell_pct"])
    sebi = _r2(turnover * r["sebi_pct"])
    exchange = _r2(_r2(turnover * r["exchange_pct"]) + _r2(turnover * r["ipft_pct"]))
    gst = _r2(r["gst_pct"] * (brokerage + exchange + sebi))
    stamp = _r0(buy_value * r["stamp_buy_pct"])
    total = _r2(brokerage + stt + exchange + gst + sebi + stamp)
    return {"brokerage": brokerage, "stt": stt, "exchange": exchange, "sebi": sebi,
            "stamp": stamp, "gst": gst, "total": total}


def leg_costs(segment, side, qty, price, rates=None):
    """Charges on one executed order, in rupees. side is "buy" or "sell"."""
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell, not %r" % side)
    value = qty * price
    r = _rates(segment, rates)
    return _costs(r, value if side == "buy" else 0.0, value if side == "sell" else 0.0)


def round_trip(segment, qty, buy, sell, rates=None):
    """Charges on a buy and a sell of qty, in rupees, rounded the way
    Zerodha's calculator rounds a round trip (on the combined turnover)."""
    return _costs(_rates(segment, rates), qty * buy, qty * sell)


def inr(x, paise=None):
    """Rupees the Indian way: Rs 2,00,000 and Rs 1,227.80. paise=None shows
    them only when there are any."""
    x = float(x)
    sign = "-" if x < 0 else ""
    x = abs(x)
    if paise is None:
        paise = abs(x - round(x)) >= 0.005
    whole, frac = ("%.2f" % x).split(".") if paise else (str(int(round(x))), "")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return "%sRs %s%s" % (sign, whole, ("." + frac) if paise else "")


# ----------------------------------------------------------------- prices

def tick_round(price, tick=0.05, mode="nearest"):
    """Round a price to the exchange tick. mode: nearest, down or up."""
    how = {"nearest": ROUND_HALF_UP, "down": ROUND_FLOOR, "up": ROUND_CEILING}[mode]
    t = Decimal(str(tick))
    q = (Decimal(str(price)) / t).quantize(Decimal("1"), how)
    return float(q * t)


def band_ok(price, prev_close, band_pct):
    """True when price is inside the daily price band. band_pct None = no band."""
    if band_pct is None:
        return True
    lo = tick_round(prev_close * (1 - band_pct / 100.0), mode="up")
    hi = tick_round(prev_close * (1 + band_pct / 100.0), mode="down")
    return lo <= price <= hi


# ------------------------------------------------------------------ fetch

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TOOL_UA = "Mozilla/5.0 (compatible; india-trader-skill/0.1)"  # Yahoo 429s browser agents


class NSEError(Exception):
    def __init__(self, url, reason):
        Exception.__init__(self, "NSE fetch failed for %s: %s" % (url, reason))
        self.url = url
        self.reason = reason


_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_warmed = []
SLEEP = _time.sleep


def nse_get(url, timeout=20, opener=None, warm=True, want_json=True):
    """GET an NSE URL. Warms cookies on the home page once (best effort: it
    can 403 itself), sends a browser User-Agent, retries 3 times with backoff
    on 401/403/429/5xx. Raises NSEError when it gives up, or on an HTML page
    where JSON was wanted."""
    op = opener or _opener
    if warm and not _warmed:
        _warmed.append(True)
        try:
            op.open(urllib.request.Request("https://www.nseindia.com/", headers={"User-Agent": BROWSER_UA}),
                    timeout=timeout).read()
        except Exception:
            pass
    headers = {"User-Agent": BROWSER_UA, "Referer": "https://www.nseindia.com/",
               "Accept": "application/json" if want_json else "*/*",
               "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip"}
    last = "no answer"
    for attempt in range(3):
        try:
            with op.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                body = r.read()
                if (getattr(r, "headers", None) or {}).get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code in (401, 403, 429) or e.code >= 500:
                SLEEP(2 ** attempt)
                continue
            raise NSEError(url, last)
        except (urllib.error.URLError, OSError) as e:
            last = str(getattr(e, "reason", e))
            SLEEP(2 ** attempt)
            continue
        if want_json and body.lstrip()[:1] == b"<":
            raise NSEError(url, "got an HTML page, not JSON (NSE blocked the request)")
        return body
    raise NSEError(url, last)
