"""Market data for the terminal: quotes, price history, fundamentals and shareholders.

Sources, in order of preference:

- **Upstox market-quote API** (when you're logged in): live NSE/BSE prices.
- **Yahoo Finance** via `yfinance` (no login): prices delayed by up to ~15
  minutes in market hours, daily history, 52-week range, valuation and a
  business description.
- **Screener.in** public company pages (no login): key ratios, quarterly
  results and the shareholding pattern filed with the exchanges each quarter
  (promoters, FIIs, DIIs, government, public), plus named large holders.
- **data/companies.json** (in this repo): hand-written notes on what each
  company sells and to whom, and what it buys and from whom.

Every fetch is wrapped so a failing source shows a note instead of breaking
the page.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36", "Accept-Language": "en-IN,en;q=0.9"}
TIMEOUT = 20

INDICES = [  # (label, Upstox key, Yahoo symbol)
    ("NIFTY 50", "NSE_INDEX|Nifty 50", "^NSEI"),
    ("SENSEX", "BSE_INDEX|SENSEX", "^BSESN"),
    ("BANK NIFTY", "NSE_INDEX|Nifty Bank", "^NSEBANK"),
    ("NIFTY IT", "NSE_INDEX|Nifty IT", "^CNXIT"),
    ("MIDCAP 100", "NSE_INDEX|NIFTY MIDCAP 100", "NIFTY_MIDCAP_100.NS"),
    ("INDIA VIX", "NSE_INDEX|India VIX", "^INDIAVIX"),
]
GLOBAL = [("USD/INR", "INR=X"), ("BRENT", "BZ=F"), ("GOLD", "GC=F"), ("S&P 500", "^GSPC"), ("NASDAQ", "^IXIC")]


class SourceError(RuntimeError):
    pass


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def market_status(now: dt.datetime | None = None) -> str:
    """NSE cash market hours, ignoring exchange holidays."""
    now = (now or now_ist()).astimezone(IST)
    if now.weekday() >= 5:
        return "CLOSED"
    t = now.time()
    if dt.time(9, 0) <= t < dt.time(9, 15):
        return "PRE-OPEN"
    if dt.time(9, 15) <= t < dt.time(15, 30):
        return "OPEN"
    return "CLOSED"


# ---------------------------------------------------------------- lists bundled in the repo
def nifty50() -> list[dict]:
    with open(DATA / "nifty50.csv", newline="") as f:
        return list(csv.DictReader(f))


def company_notes() -> dict:
    try:
        return json.loads((DATA / "companies.json").read_text())
    except (OSError, ValueError):
        return {}


def yahoo_symbol(symbol: str, exchange: str = "NSE") -> str:
    return f"{symbol}.{'BO' if exchange == 'BSE' else 'NS'}"


# ---------------------------------------------------------------- Yahoo Finance
def _yf():
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise SourceError("yfinance is not installed") from e
    return yf


def yahoo_history(symbols: list[str], period: str = "1y", interval: str = "1d") -> dict[str, pd.DataFrame]:
    """Daily OHLCV per Yahoo symbol, one request for the whole list."""
    if not symbols:
        return {}
    yf = _yf()
    try:
        raw = yf.download(symbols, period=period, interval=interval, group_by="ticker", auto_adjust=False,
                          progress=False, threads=True)
    except Exception as e:
        raise SourceError(f"Yahoo Finance: {e}") from e
    out = {}
    if raw is None or raw.empty:
        return out
    for s in symbols:
        try:
            df = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        df = df.dropna(how="all")
        if not df.empty:
            out[s] = df
    return out


def stats_from_history(df: pd.DataFrame) -> dict:
    closes = df["Close"].dropna()
    if closes.empty:
        return {}
    last, prev = float(closes.iloc[-1]), float(closes.iloc[-2]) if len(closes) > 1 else float(closes.iloc[-1])
    hi, lo = float(df["High"].max()), float(df["Low"].min())
    year_ago = float(closes.iloc[0])
    month_ago = float(closes.iloc[-22]) if len(closes) > 22 else year_ago
    row = df.iloc[-1]
    return {
        "ltp": last, "prev_close": prev, "change": last - prev, "change_pct": (last / prev - 1) * 100 if prev else 0,
        "open": float(row.get("Open", float("nan"))), "high": float(row.get("High", float("nan"))),
        "low": float(row.get("Low", float("nan"))), "volume": float(row.get("Volume", 0) or 0),
        "high_52w": hi, "low_52w": lo, "from_high_pct": (last / hi - 1) * 100 if hi else 0,
        "ret_1m": (last / month_ago - 1) * 100 if month_ago else 0,
        "ret_1y": (last / year_ago - 1) * 100 if year_ago else 0,
        "as_of": closes.index[-1],
    }


def yahoo_profile(symbol: str) -> dict:
    yf = _yf()
    t = yf.Ticker(symbol)
    try:
        info = t.info or {}
    except Exception as e:
        raise SourceError(f"Yahoo Finance: {e}") from e
    holders = {}
    for name in ("major_holders", "institutional_holders", "mutualfund_holders"):
        try:
            v = getattr(t, name)
            if isinstance(v, pd.DataFrame) and not v.empty:
                holders[name] = v
        except Exception:
            pass
    return {"info": info, "holders": holders}


# ---------------------------------------------------------------- Screener.in
SCREENER = "https://www.screener.in"


def _num(s: str) -> float | None:
    s = (s or "").replace(",", "").replace("₹", "").replace("%", "").replace("Cr.", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _table(section) -> pd.DataFrame:
    """Turn a Screener data table into a frame with the row label as index."""
    table = section.find("table") if section is not None else None
    if table is None:
        return pd.DataFrame()
    head = [th.get_text(" ", strip=True) for th in table.find("thead").find_all("th")] if table.find("thead") else []
    rows = []
    for tr in table.find("tbody").find_all("tr") if table.find("tbody") else []:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if cells:
            rows.append(cells)
    if not rows:
        return pd.DataFrame()
    width = max(len(r) for r in rows)
    cols = (head + [f"c{i}" for i in range(len(head), width)])[:width]
    df = pd.DataFrame([r + [""] * (width - len(r)) for r in rows], columns=cols)
    first = df.columns[0]
    df[first] = df[first].str.replace(r"\s*\+$", "", regex=True).str.strip()
    return df.set_index(first).rename_axis("Item")


def parse_screener(html: str) -> dict:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out: dict = {"ratios": {}, "about": "", "key_points": "", "quarters": pd.DataFrame(),
                 "shareholding": pd.DataFrame(), "warehouse_id": None, "name": ""}
    h1 = soup.find("h1")
    out["name"] = h1.get_text(" ", strip=True) if h1 else ""
    for li in soup.select("#top-ratios li"):
        name, val = li.select_one(".name"), li.select_one(".value") or li.select_one(".number")
        if name and val:
            out["ratios"][name.get_text(" ", strip=True)] = re.sub(r"\s+", " ", val.get_text(" ", strip=True))
    about = soup.select_one(".company-profile .about") or soup.select_one(".about")
    if about:
        out["about"] = about.get_text(" ", strip=True)
    kp = soup.select_one(".company-profile .commentary")
    if kp:
        out["key_points"] = kp.get_text("\n", strip=True)
    out["quarters"] = _table(soup.find("section", id="quarters"))
    sh = soup.find("section", id="shareholding")
    if sh is not None:
        quarterly = sh.find(id="quarterly-shp") or sh
        out["shareholding"] = _table(quarterly)
    tag = soup.find(attrs={"data-warehouse-id": True})
    if tag:
        out["warehouse_id"] = tag["data-warehouse-id"]
    return out


def screener_company(symbol: str) -> dict:
    s = requests.Session()
    s.headers.update(UA)
    last_err = None
    for path in (f"/company/{symbol}/consolidated/", f"/company/{symbol}/"):
        try:
            r = s.get(SCREENER + path, timeout=TIMEOUT)
        except requests.RequestException as e:
            last_err = e
            continue
        if r.status_code == 200 and "top-ratios" in r.text:
            data = parse_screener(r.text)
            # Standalone page when the consolidated one is empty.
            if data["ratios"] or path.endswith(f"/{symbol}/"):
                data["url"] = SCREENER + path
                data["holders"] = screener_holders(s, data.get("warehouse_id"))
                return data
        last_err = f"HTTP {r.status_code}"
    raise SourceError(f"Screener.in: couldn't load {symbol} ({last_err})")


HOLDER_CLASSES = {"promoters": "Promoters", "foreign_institutions": "FIIs",
                  "domestic_institutions": "DIIs", "government": "Government", "public": "Public (named, over 1%)"}


def parse_holders(payload: dict, category: str) -> list[dict]:
    """Screener's investor API maps holder name -> {quarter: percent, ...}. Keep the latest value."""
    rows = []
    for name, series in (payload or {}).items():
        if not isinstance(series, dict):
            continue
        vals = [(k, _num(str(v))) for k, v in series.items() if k != "setAttributes" and _num(str(v)) is not None]
        if not vals:
            continue
        period, pct = vals[-1]
        rows.append({"Category": category, "Holder": name, "Stake %": pct, "As of": period})
    return rows


def screener_holders(session: requests.Session, warehouse_id) -> list[dict]:
    if not warehouse_id:
        return []
    rows: list[dict] = []
    for cls, label in HOLDER_CLASSES.items():
        try:
            r = session.get(f"{SCREENER}/api/3/{warehouse_id}/investors/{cls}/quarterly/", timeout=TIMEOUT,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if r.status_code == 200:
                rows.extend(parse_holders(r.json(), label))
        except (requests.RequestException, ValueError):
            continue
    return rows


def shareholding_long(df: pd.DataFrame) -> pd.DataFrame:
    """Shareholding table (categories x quarters) to long form with numbers."""
    if df.empty:
        return pd.DataFrame(columns=["Category", "Quarter", "Percent"])
    keep = [i for i in df.index if not str(i).lower().startswith("no. of")]
    wide = df.loc[keep].rename_axis("Category").reset_index()
    long = wide.melt(id_vars="Category", var_name="Quarter", value_name="Percent")
    long["Percent"] = long["Percent"].map(_num)
    return long.dropna(subset=["Percent"])


def ratio_number(ratios: dict, *names: str) -> float | None:
    for n in names:
        for k, v in ratios.items():
            if k.lower().startswith(n.lower()):
                return _num(v.split("/")[0])
    return None


NSE_EQUITY_LIST = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def nse_equity_list() -> pd.DataFrame:
    """Every NSE-listed equity (about 2,000 rows): symbol, name, ISIN. Published daily by NSE."""
    last_err = None
    for url in (NSE_EQUITY_LIST, NSE_EQUITY_LIST.replace("nsearchives", "archives")):
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            if r.status_code == 200 and "SYMBOL" in r.text[:200]:
                return parse_equity_list(r.text)
            last_err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last_err = e
    raise SourceError(f"NSE equity list: {last_err}")


def parse_equity_list(text: str) -> pd.DataFrame:
    from io import StringIO

    df = pd.read_csv(StringIO(text))
    df.columns = [c.strip().upper() for c in df.columns]
    if "SERIES" in df.columns:
        df = df[df["SERIES"].astype(str).str.strip().isin(["EQ", "BE", "BZ", "SM", "ST"])]
    out = pd.DataFrame({"symbol": df["SYMBOL"].astype(str).str.strip(),
                        "name": df["NAME OF COMPANY"].astype(str).str.strip(),
                        "isin": df["ISIN NUMBER"].astype(str).str.strip()})
    out["instrument_key"] = "NSE_EQ|" + out["isin"]
    return out.reset_index(drop=True)
