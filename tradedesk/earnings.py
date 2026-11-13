"""Earnings: who reports when, what they need to beat, and a verdict once results are out.

Data (all public, no login):

- NSE event calendar (`api/event-calendar`) and board-meeting list
  (`api/corporate-board-meetings`): upcoming board meetings whose purpose is
  financial results.
- NSE results comparison (`api/results-comparision`, parsed in filings.py):
  the last ~5 reported quarters, used for the "same quarter last year" bar.
- Yahoo Finance consensus (`Ticker.calendar`): analyst EPS and revenue
  estimates where Yahoo has them. Coverage of Indian mid and small caps is thin,
  so a blank estimate is normal.

Every function that touches the network raises FilingError or returns an empty
result; the page shows a note instead of breaking.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .filings import FilingError, NSEClient, _f

DATA = Path(__file__).resolve().parent.parent / "data"
WATCHLIST_FILE = DATA / "watchlist.txt"
RESULT_WORDS = ("financial result", "results", "quarterly result", "audited", "unaudited")


# ---------------------------------------------------------------- my stocks
def watchlist() -> list[str]:
    """Symbols from data/watchlist.txt (one per line, # for comments)."""
    try:
        lines = WATCHLIST_FILE.read_text().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        s = ln.split("#", 1)[0].strip().upper()
        if s:
            out.append(s)
    return list(dict.fromkeys(out))


def my_stocks(held: list[str], ideas: dict, extra: list[str] | None = None) -> dict[str, str]:
    """Symbol -> why it's on the list (held / idea / watchlist). Held wins."""
    out: dict[str, str] = {}
    for s in held:
        out.setdefault(s, "held")
    for i in ideas.get("buy_ideas", []) or []:
        out.setdefault(i.get("symbol", ""), "idea")
    for s in ideas.get("watch_today", []) or []:
        out.setdefault(s, "idea")
    for s in watchlist() + list(extra or []):
        out.setdefault(s, "watchlist")
    out.pop("", None)
    return out


# ---------------------------------------------------------------- calendar
def _date(v) -> pd.Timestamp:
    """NSE dates: '14-Nov-2026', '14-NOV-2026 18:45:12', '14-11-2026', or ISO."""
    s = str(v or "").strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return pd.Timestamp(dt.datetime.strptime(s.title() if "%b" in fmt else s, fmt))
        except ValueError:
            continue
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def is_results_meeting(purpose: str) -> bool:
    p = (purpose or "").lower()
    return any(w in p for w in RESULT_WORDS)


def calendar_rows(raw: list[dict]) -> pd.DataFrame:
    """NSE event-calendar or board-meeting rows -> Date, Symbol, Company, Purpose (results meetings only)."""
    rows = []
    for r in raw or []:
        sym = r.get("symbol") or r.get("bm_symbol")
        purpose = r.get("purpose") or r.get("bm_purpose") or ""
        desc = r.get("bm_desc") or r.get("desc") or ""
        when = _date(r.get("date") or r.get("bm_date"))
        if not sym or pd.isna(when) or not (is_results_meeting(purpose) or is_results_meeting(desc)):
            continue
        rows.append({"Date": when.normalize(), "Symbol": sym.strip().upper(),
                     "Company": (r.get("company") or r.get("sm_name") or "").strip(),
                     "Purpose": purpose.strip() or "Financial Results", "Details": desc.strip()})
    df = pd.DataFrame(rows, columns=["Date", "Symbol", "Company", "Purpose", "Details"])
    if df.empty:
        return df
    return df.sort_values(["Date", "Symbol"]).drop_duplicates(["Date", "Symbol"]).reset_index(drop=True)


def fetch_calendar(start: dt.date, end: dt.date, client: NSEClient | None = None) -> pd.DataFrame:
    """Results board meetings between two dates, from NSE. Tries the event calendar, then board meetings."""
    c = client or NSEClient()
    params = {"index": "equities", "from_date": f"{start:%d-%m-%Y}", "to_date": f"{end:%d-%m-%Y}"}
    errors = []
    for path in ("event-calendar", "corporate-board-meetings"):
        try:
            data = c.get(path, **params)
        except FilingError as e:
            errors.append(str(e))
            if "unreachable" in str(e):
                break
            continue
        rows = data.get("data", []) if isinstance(data, dict) else data
        df = calendar_rows(rows)
        df = df[(df["Date"] >= pd.Timestamp(start)) & (df["Date"] <= pd.Timestamp(end))]
        if not df.empty:
            return df.reset_index(drop=True)
    if errors:
        raise FilingError("; ".join(errors))
    return calendar_rows([])


def quarter_end_before(day: dt.date | pd.Timestamp) -> pd.Timestamp:
    """The last calendar quarter end strictly before a meeting date (the quarter being reported)."""
    return (pd.Timestamp(day).normalize() - pd.offsets.QuarterEnd(1)).normalize()


def year_ago_bar(results: pd.DataFrame, meeting: dt.date | pd.Timestamp) -> dict:
    """What the company did in the same quarter last year and last quarter (from results_frame).

    These are the numbers a quarter gets compared with when it's out: year-on-year
    growth is how Indian results are usually judged.
    """
    if results is None or results.empty:
        return {}
    q = quarter_end_before(meeting)
    df = results.assign(_d=pd.to_datetime(results["Quarter ending"], format="%d-%b-%Y", errors="coerce"))
    out = {"quarter": f"{q:%b %Y}"}
    for label, target in (("year_ago", q - pd.DateOffset(years=1)), ("last_q", q - pd.offsets.QuarterEnd(1))):
        hit = df[(df["_d"] - target).abs() <= pd.Timedelta(days=5)]
        if not hit.empty:
            r = hit.iloc[-1]
            out[label] = {"quarter": f"{r['_d']:%b %Y}", "revenue": r.get("Revenue (₹ cr)"),
                          "profit": r.get("Net profit (₹ cr)"), "eps": r.get("EPS (₹)"),
                          "margin": r.get("Net margin %")}
    already = df[(df["_d"] - q).abs() <= pd.Timedelta(days=5)]
    out["reported"] = not already.empty
    return out


# ---------------------------------------------------------------- consensus estimates
def yahoo_estimates(yahoo_symbol: str) -> dict:
    """Analyst consensus for the next report from Yahoo Finance, if it has any."""
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover
        return {}
    try:
        cal = yf.Ticker(yahoo_symbol).calendar or {}
    except Exception:  # yfinance raises many kinds of errors for missing data
        return {}
    return parse_yahoo_calendar(cal)


def parse_yahoo_calendar(cal: dict) -> dict:
    out = {}
    dates = cal.get("Earnings Date") or []
    if dates:
        out["date"] = pd.Timestamp(dates[0])
    for src, dst in (("Earnings Average", "eps_est"), ("Earnings Low", "eps_low"), ("Earnings High", "eps_high"),
                     ("Revenue Average", "revenue_est")):
        v = _f(cal.get(src))
        if v is not None:
            out[dst] = v
    if "revenue_est" in out:  # Yahoo gives rupees; show crore like the rest of the site
        out["revenue_est_cr"] = out.pop("revenue_est") / 1e7
    return out


def week_bounds(today: dt.date, weeks_ahead: int = 0) -> tuple[dt.date, dt.date]:
    monday = today - dt.timedelta(days=today.weekday()) + dt.timedelta(weeks=weeks_ahead)
    return monday, monday + dt.timedelta(days=6)
