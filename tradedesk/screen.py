"""Stock screener: growth, valuation, promoter buying and results quality.

Universes come from the bundled Nifty 50 list, NSE's index constituents
(`api/equity-stockIndices`), your holdings and watchlist, or a typed list.
Fundamentals come from each company's Screener.in page (already parsed by
market.parse_screener and cached for 6 hours), so a big universe takes a while
the first time and is quick after that.
"""
from __future__ import annotations

import pandas as pd

from .filings import FilingError, NSEClient
from .market import _num, ratio_number

INDICES = ["NIFTY 50", "NIFTY NEXT 50", "NIFTY 100", "NIFTY 200", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250",
           "NIFTY 500"]


def index_members(index: str, client: NSEClient | None = None) -> list[dict]:
    """Constituents of an NSE index: symbol, company, industry."""
    c = client or NSEClient()
    data = c.get("equity-stockIndices", index=index)
    out = []
    for r in (data or {}).get("data", []):
        sym = r.get("symbol")
        if not sym or sym == index or r.get("priority") == 1:  # first row is the index itself
            continue
        meta = r.get("meta") or {}
        out.append({"symbol": sym, "name": meta.get("companyName", ""), "sector": meta.get("industry", "")})
    if not out:
        raise FilingError(f"NSE returned no members for {index}")
    return out


def _row(df: pd.DataFrame, *names: str) -> list[float | None] | None:
    if df is None or df.empty:
        return None
    for n in names:
        for idx in df.index:
            if str(idx).lower().startswith(n.lower()):
                return [_num(v) for v in df.loc[idx].tolist()]
    return None


def _growth(new, old) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


def metrics(sc: dict) -> dict:
    """One row of screening numbers from a parsed Screener.in page."""
    r = sc.get("ratios") or {}
    price = ratio_number(r, "Current Price")
    book = ratio_number(r, "Book Value")
    out = {"Mcap (₹ cr)": ratio_number(r, "Market Cap"), "Price": price, "P/E": ratio_number(r, "Stock P/E"),
           "P/B": (price / book) if price and book else None, "ROE %": ratio_number(r, "ROE"),
           "ROCE %": ratio_number(r, "ROCE"), "Div yield %": ratio_number(r, "Dividend Yield")}
    q = sc.get("quarters")
    sales = _row(q, "Sales", "Revenue")
    profit = _row(q, "Net Profit")
    opm = _row(q, "OPM", "Financing Margin")
    if sales and len(sales) >= 5:
        out["Sales YoY %"] = _growth(sales[-1], sales[-5])
    if profit and len(profit) >= 5:
        out["Profit YoY %"] = _growth(profit[-1], profit[-5])
        streak = 0
        for i in range(1, 5):  # how many of the last 4 quarters grew profit year on year
            if len(profit) >= i + 4:
                g = _growth(profit[-i], profit[-i - 4])
                if g is not None and g > 0:
                    streak += 1
        out["Profit growth qtrs (of 4)"] = streak
    if sales and len(sales) >= 2:
        out["Sales QoQ %"] = _growth(sales[-1], sales[-2])
    if opm and len(opm) >= 5 and opm[-1] is not None and opm[-5] is not None:
        out["OPM chg (pts)"] = opm[-1] - opm[-5]
    sh = sc.get("shareholding")
    prom = _row(sh, "Promoters")
    if prom:
        out["Promoter %"] = prom[-1]
        if len(prom) >= 2 and prom[-2] is not None and prom[-1] is not None:
            out["Promoter chg QoQ"] = prom[-1] - prom[-2]
        if len(prom) >= 5 and prom[-5] is not None and prom[-1] is not None:
            out["Promoter chg 1Y"] = prom[-1] - prom[-5]
    for name, key in (("FIIs", "FII chg QoQ"), ("DIIs", "DII chg QoQ")):
        v = _row(sh, name)
        if v and len(v) >= 2 and v[-1] is not None and v[-2] is not None:
            out[key] = v[-1] - v[-2]
    out["Quality score"] = quality_score(out)
    return out


def quality_score(m: dict) -> int:
    """0–10: steady profit growth, decent returns on capital, margins not shrinking, promoters not selling."""
    s = 0
    s += min(int(m.get("Profit growth qtrs (of 4)") or 0), 4)
    s += 2 if (m.get("ROCE %") or 0) >= 18 else 1 if (m.get("ROCE %") or 0) >= 12 else 0
    s += 1 if (m.get("Sales YoY %") or 0) >= 10 else 0
    s += 1 if (m.get("OPM chg (pts)") or 0) >= 0 and m.get("OPM chg (pts)") is not None else 0
    s += 1 if (m.get("Promoter chg 1Y") or 0) >= 0 and m.get("Promoter chg 1Y") is not None else 0
    s += 1 if (m.get("P/E") or 999) <= 40 and m.get("P/E") is not None and m["P/E"] > 0 else 0
    return s


PRESETS = {
    "No filter": {},
    "Growth at a fair price": {"Sales YoY %": (10, None), "Profit YoY %": (15, None), "P/E": (0.01, 35),
                               "ROCE %": (12, None)},
    "Promoter buying": {"Promoter chg QoQ": (0.25, None)},
    "Consistent compounders": {"Profit growth qtrs (of 4)": (4, None), "ROCE %": (18, None), "ROE %": (15, None)},
    "Results momentum": {"Profit YoY %": (25, None), "Sales YoY %": (15, None), "OPM chg (pts)": (0, None)},
    "Cheap and profitable": {"P/E": (0.01, 15), "ROE %": (12, None), "Div yield %": (1, None)},
}


def apply_filters(df: pd.DataFrame, rules: dict[str, tuple[float | None, float | None]]) -> pd.DataFrame:
    """Keep rows inside every (min, max) range; a stock missing a filtered number is dropped."""
    keep = pd.Series(True, index=df.index)
    for col, (lo, hi) in rules.items():
        if col not in df:
            return df.iloc[0:0]
        v = pd.to_numeric(df[col], errors="coerce")
        cond = v.notna()
        if lo is not None:
            cond &= v >= lo
        if hi is not None:
            cond &= v <= hi
        keep &= cond
    return df[keep]
