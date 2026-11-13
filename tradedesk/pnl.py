"""Realised and unrealised profit and loss across segments, from Upstox's P&L report.

Upstox's trade-wise P&L report pairs each sell with its buy (FIFO) and gives
buy/sell dates and amounts. From that we work out, for a chosen period:

- realised P&L per segment: equity delivery (short- and long-term), intraday,
  futures, options, commodity and currency;
- charges per segment (Upstox's own charges report), so we can show net P&L;
- month-by-month and stock-by-stock breakdowns.

Unrealised P&L on what you still hold comes from the Portfolio table.
The report is updated by Upstox at the end of each day (T+1), so today's
trades show up tomorrow.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

SEGMENTS = {"EQ": "Equity", "FO": "F&O", "COM": "Commodity", "CD": "Currency"}

# Bucket order used everywhere on the page.
BUCKETS = ["Delivery (long-term)", "Delivery (short-term)", "Intraday", "Futures", "Options",
           "Commodity futures", "Commodity options", "Currency futures", "Currency options"]

TAX_NOTE = {
    "Delivery (long-term)": "LTCG: held over 12 months",
    "Delivery (short-term)": "STCG: held 12 months or less",
    "Intraday": "Speculative business income",
    "Futures": "Non-speculative business income",
    "Options": "Non-speculative business income",
}


@dataclass(frozen=True)
class Period:
    label: str
    start: dt.date
    end: dt.date

    def chunks(self) -> list[tuple[str, str, str]]:
        """Split into (Upstox FY code, from dd-mm-yyyy, to dd-mm-yyyy), one per financial year."""
        out, cur = [], self.start
        while cur <= self.end:
            fy_start = dt.date(cur.year if cur.month >= 4 else cur.year - 1, 4, 1)
            fy_end = dt.date(fy_start.year + 1, 3, 31)
            stop = min(fy_end, self.end)
            code = f"{fy_start.year % 100:02d}{(fy_start.year + 1) % 100:02d}"
            out.append((code, f"{cur:%d-%m-%Y}", f"{stop:%d-%m-%Y}"))
            cur = stop + dt.timedelta(days=1)
        return out


def periods(today: dt.date | None = None) -> list[Period]:
    today = today or dt.date.today()
    fy_start = dt.date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    prev_start = dt.date(fy_start.year - 1, 4, 1)
    return [
        Period(f"FY {fy_start.year}-{(fy_start.year + 1) % 100:02d} (1 Apr to today)", fy_start, today),
        Period(f"Calendar {today.year} (1 Jan to today)", dt.date(today.year, 1, 1), today),
        Period(f"Last year, FY {prev_start.year}-{(prev_start.year + 1) % 100:02d}", prev_start,
               dt.date(fy_start.year, 3, 31)),
    ]


def _date(v) -> pd.Timestamp:
    if v is None or v == "":
        return pd.NaT
    s = str(v)
    # Upstox uses dd-mm-yyyy; be lenient with ISO too.
    fmt = "%Y-%m-%d" if len(s) >= 10 and s[4] == "-" else "%d-%m-%Y"
    return pd.to_datetime(s[:10], format=fmt, errors="coerce")


def bucket(segment: str, trade_type: str, buy: pd.Timestamp, sell: pd.Timestamp) -> str:
    t = (trade_type or "").upper()
    if segment == "FO":
        return "Options" if t.startswith("OPT") or t in ("CE", "PE") else "Futures"
    if segment == "COM":
        return "Commodity options" if t.startswith("OPT") else "Commodity futures"
    if segment == "CD":
        return "Currency options" if t.startswith("OPT") else "Currency futures"
    if pd.notna(buy) and pd.notna(sell) and buy.date() == sell.date():
        return "Intraday"
    if pd.notna(buy) and pd.notna(sell) and (sell - buy).days > 365:
        return "Delivery (long-term)"
    return "Delivery (short-term)"


def trades_frame(trades_by_segment: dict[str, list[dict]]) -> pd.DataFrame:
    rows = []
    for seg, trades in trades_by_segment.items():
        for t in trades or []:
            buy, sell = _date(t.get("buy_date")), _date(t.get("sell_date"))
            buy_amt, sell_amt = float(t.get("buy_amount") or 0), float(t.get("sell_amount") or 0)
            rows.append({
                "segment": seg, "bucket": bucket(seg, t.get("trade_type", ""), buy, sell),
                "scrip": (t.get("scrip_name") or t.get("isin") or "?").strip(), "isin": t.get("isin"),
                "qty": float(t.get("quantity") or 0), "buy_date": buy, "sell_date": sell,
                "buy_avg": float(t.get("buy_average") or 0), "sell_avg": float(t.get("sell_average") or 0),
                "buy_amount": buy_amt, "sell_amount": sell_amt, "pnl": sell_amt - buy_amt,
            })
    df = pd.DataFrame(rows, columns=["segment", "bucket", "scrip", "isin", "qty", "buy_date", "sell_date",
                                     "buy_avg", "sell_avg", "buy_amount", "sell_amount", "pnl"])
    # A short sale closes on the buy date; use whichever date is later as the "booked" date.
    df["booked"] = df[["buy_date", "sell_date"]].max(axis=1)
    return df


def in_period(df: pd.DataFrame, period: Period) -> pd.DataFrame:
    if df.empty:
        return df
    start, end = pd.Timestamp(period.start), pd.Timestamp(period.end)
    return df[(df["booked"] >= start) & (df["booked"] <= end)]


def charges_total(ch: dict) -> float:
    if not ch:
        return 0.0
    if ch.get("total") is not None:
        return float(ch["total"])
    taxes, other = ch.get("taxes") or {}, ch.get("charges") or {}
    return float(ch.get("brokerage") or 0) + sum(float(v or 0) for v in taxes.values()) + \
        sum(float(v or 0) for v in other.values())


def summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per bucket: trades, wins, turnover and gross P&L. (Upstox reports charges per segment, not per bucket.)"""
    rows = []
    for b in BUCKETS:
        part = df[df["bucket"] == b]
        if part.empty:
            continue
        rows.append({"Segment": b, "Trades": len(part), "Winning": int((part["pnl"] > 0).sum()),
                     "Turnover": part["buy_amount"].sum() + part["sell_amount"].sum(),
                     "Gross P&L": part["pnl"].sum(), "Tax head": TAX_NOTE.get(b, "")})
    out = pd.DataFrame(rows, columns=["Segment", "Trades", "Winning", "Turnover", "Gross P&L", "Tax head"])
    out["Win rate"] = (out["Winning"] / out["Trades"] * 100).where(out["Trades"] > 0, 0.0)
    return out


def segment_totals(df: pd.DataFrame, charges_by_segment: dict[str, float]) -> pd.DataFrame:
    rows = []
    for seg, name in SEGMENTS.items():
        part = df[df["segment"] == seg]
        ch = float(charges_by_segment.get(seg) or 0)
        if part.empty and not ch:
            continue
        gross = part["pnl"].sum()
        rows.append({"Segment": name, "Trades": len(part), "Gross P&L": gross, "Charges": ch, "Net P&L": gross - ch})
    return pd.DataFrame(rows, columns=["Segment", "Trades", "Gross P&L", "Charges", "Net P&L"])


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["month", "bucket", "pnl"])
    m = df.assign(month=df["booked"].dt.to_period("M").dt.to_timestamp())
    return m.groupby(["month", "bucket"], as_index=False)["pnl"].sum()


def by_stock(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["scrip", "trades", "pnl"])
    g = df.groupby("scrip", as_index=False).agg(trades=("pnl", "size"), turnover=("sell_amount", "sum"),
                                                 pnl=("pnl", "sum"))
    return g.sort_values("pnl", ascending=False)


def max_drawdown(df: pd.DataFrame) -> float:
    """Largest fall in cumulative realised P&L, by booking date."""
    if df.empty:
        return 0.0
    cum = df.sort_values("booked")["pnl"].cumsum()
    return float((cum - cum.cummax()).min())
