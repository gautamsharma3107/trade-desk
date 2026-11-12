"""Turn Upstox responses into one table, and flag holdings worth reviewing.

The flags are simple rules (stop-loss, profit target, moving averages, MTF
interest drag, notes from the daily research). They are prompts to look
closer, not instructions to sell.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .charges import RATES, mtf_interest

COLUMNS = ["symbol", "type", "exchange", "qty", "avg_price", "ltp", "invested",
           "current_value", "pnl", "pnl_pct", "day_change_pct", "instrument_key"]


def _row(symbol, kind, exchange, qty, avg, ltp, close, key):
    invested = qty * avg
    value = qty * ltp
    pnl = value - invested
    return {
        "symbol": symbol, "type": kind, "exchange": exchange, "qty": qty,
        "avg_price": avg, "ltp": ltp, "invested": invested, "current_value": value,
        "pnl": pnl, "pnl_pct": (pnl / invested * 100) if invested else 0.0,
        "day_change_pct": ((ltp - close) / close * 100) if close else 0.0,
        "instrument_key": key,
    }


def build_table(holdings: list[dict], mtf: list[dict], positions: list[dict]) -> pd.DataFrame:
    rows = []
    for h in holdings:
        qty = int(h.get("quantity") or 0)
        if qty:
            rows.append(_row(h.get("tradingsymbol") or h.get("trading_symbol"), "Delivery",
                             h.get("exchange"), qty, float(h.get("average_price") or 0),
                             float(h.get("last_price") or 0), float(h.get("close_price") or 0),
                             h.get("instrument_token")))
    for p in mtf:
        qty = int(p.get("quantity") or 0)
        if qty:
            rows.append(_row(p.get("trading_symbol"), "MTF", p.get("exchange"), qty,
                             float(p.get("average_price") or p.get("buy_price") or 0),
                             float(p.get("last_price") or 0), float(p.get("close_price") or 0),
                             p.get("instrument_token")))
    for p in positions:
        qty = int(p.get("quantity") or 0)
        if qty and p.get("product") != "MTF":
            kind = "Intraday" if p.get("product") == "I" else "Position"
            rows.append(_row(p.get("trading_symbol") or p.get("tradingsymbol"), kind, p.get("exchange"),
                             qty, float(p.get("average_price") or p.get("buy_price") or 0),
                             float(p.get("last_price") or 0), float(p.get("close_price") or 0),
                             p.get("instrument_token")))
    return pd.DataFrame(rows, columns=COLUMNS)


def closed_today(mtf: list[dict], positions: list[dict]) -> pd.DataFrame:
    """Positions bought and fully sold today, with realised P&L."""
    rows = []
    for p in list(mtf) + list(positions):
        if int(p.get("quantity") or 0) == 0 and (p.get("day_sell_quantity") or 0):
            rows.append({"symbol": p.get("trading_symbol"), "product": p.get("product"),
                         "qty": p.get("day_sell_quantity"), "buy_price": p.get("buy_price"),
                         "sell_price": p.get("sell_price"), "realised": p.get("realised") or p.get("pnl")})
    return pd.DataFrame(rows)


def sma(closes: list[float], n: int) -> float | None:
    return sum(closes[-n:]) / n if len(closes) >= n else None


@dataclass
class Flag:
    level: str   # "SELL?" | "REVIEW" | "HOLD"
    reasons: list[str]


def review(row: dict, closes: list[float] | None, stop_pct: float, target_pct: float,
           mtf_margin_pct: float, note: str | None = None) -> Flag:
    reasons, score = [], 0
    pnl_pct = row["pnl_pct"]
    if pnl_pct <= -stop_pct:
        score += 2
        reasons.append(f"Down {pnl_pct:.1f}%, past your {stop_pct:.0f}% stop-loss.")
    elif pnl_pct >= target_pct:
        score += 1
        reasons.append(f"Up {pnl_pct:.1f}%, past your {target_pct:.0f}% target. Consider booking part of the profit.")

    if closes:
        ltp = row["ltp"] or closes[-1]
        s20, s50 = sma(closes, 20), sma(closes, 50)
        if s20 and s50 and ltp < s20 < s50:
            score += 2
            reasons.append(f"Price ₹{ltp:,.1f} is below its 20-day (₹{s20:,.0f}) and 50-day (₹{s50:,.0f}) averages: downtrend.")
        elif s50 and ltp < s50:
            score += 1
            reasons.append(f"Price is below its 50-day average (₹{s50:,.0f}).")
        elif s20 and s50 and ltp > s20 > s50:
            reasons.append("Price is above its 20- and 50-day averages: uptrend.")

    if row["type"] == "MTF":
        per_day, funded, _ = mtf_interest(row["invested"], mtf_margin_pct, 1)
        if per_day:
            weekly_pct = per_day * 7 / row["invested"] * 100
            reasons.append(f"MTF interest about ₹{per_day:,.0f}/day on ₹{funded:,.0f} funded, "
                           f"so the stock must rise about {weekly_pct:.2f}% a week just to cover it.")
            if pnl_pct < 0:
                score += 1

    if note:
        reasons.append(f"Research note: {note}")
        if any(w in note.lower() for w in ("exit", "sell", "avoid", "miss")):
            score += 1

    level = "SELL?" if score >= 3 else "REVIEW" if score >= 1 else "HOLD"
    if not reasons:
        reasons.append("Nothing unusual.")
    return Flag(level, reasons)


__all__ = ["build_table", "closed_today", "review", "Flag", "sma", "RATES"]
