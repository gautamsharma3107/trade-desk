"""Estimate Upstox equity charges for delivery, intraday and MTF trades.

Rates come from https://upstox.com/brokerage-charges/ (read 12 Nov 2026).
They change from time to time, so every rate lives in RATES and the app shows
the date it was checked. When you are logged in, the app can also ask Upstox
for the exact figure through its brokerage API.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

RATES_CHECKED_ON = "12 Nov 2026"

RATES = {
    "brokerage_flat": 20.0,             # ₹ per executed order (delivery and MTF)
    "intraday_brokerage_pct": 0.001,    # 0.1%, or ₹20 if lower
    "stt_delivery": 0.001,              # 0.1% on buy and sell
    "stt_intraday_sell": 0.00025,       # 0.025% on sell only
    "txn_nse": 0.0000307,               # 0.00307% (from 1 Mar 2026)
    "txn_bse": 0.0000375,               # BSE varies by scrip group; A/B group rate
    "sebi": 10 / 1e7,                   # ₹10 per crore
    "stamp_delivery_buy": 0.00015,      # 0.015% on buy
    "stamp_intraday_buy": 0.00003,      # 0.003% on buy
    "gst": 0.18,
    "dp_per_scrip": 20.0,               # ₹20 + GST per scrip per day, on sell
    "pledge_per_scrip": 20.0,           # ₹20 + GST per scrip (MTF pledge/unpledge)
    "mtf_interest_per_slab_day": 20.0,  # ₹20/day for every ₹40,000 funded
    "mtf_slab": 40000.0,
}

PRODUCTS = ("Delivery", "Intraday", "MTF")
SIDES = ("BUY", "SELL")


@dataclass
class Charges:
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_txn: float = 0.0
    sebi: float = 0.0
    stamp_duty: float = 0.0
    dp_charges: float = 0.0
    pledge_charges: float = 0.0
    gst: float = 0.0
    mtf_interest: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(
            self.brokerage + self.stt + self.exchange_txn + self.sebi + self.stamp_duty
            + self.dp_charges + self.pledge_charges + self.gst + self.mtf_interest,
            2,
        )

    def as_rows(self) -> list[tuple[str, float]]:
        rows = [
            ("Brokerage", self.brokerage),
            ("STT", self.stt),
            ("Exchange transaction", self.exchange_txn),
            ("SEBI fee", self.sebi),
            ("Stamp duty", self.stamp_duty),
            ("DP charges", self.dp_charges),
            ("MTF pledge / unpledge", self.pledge_charges),
            ("GST (18%)", self.gst),
            ("MTF interest", self.mtf_interest),
        ]
        return [(name, round(v, 2)) for name, v in rows if v] + [("Total", self.total)]


def order_charges(product: str, side: str, price: float, qty: int, exchange: str = "NSE") -> Charges:
    """Charges for one executed order (one side of a trade)."""
    if product not in PRODUCTS:
        raise ValueError(f"product must be one of {PRODUCTS}")
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    r = RATES
    value = price * qty
    c = Charges()
    if value <= 0:
        return c

    if product == "Intraday":
        c.brokerage = min(r["brokerage_flat"], value * r["intraday_brokerage_pct"])
        c.stt = round(value * r["stt_intraday_sell"]) if side == "SELL" else 0.0
        c.stamp_duty = round(value * r["stamp_intraday_buy"]) if side == "BUY" else 0.0
    else:  # Delivery and MTF follow delivery rates
        c.brokerage = r["brokerage_flat"]
        c.stt = round(value * r["stt_delivery"])
        c.stamp_duty = round(value * r["stamp_delivery_buy"]) if side == "BUY" else 0.0
        if side == "SELL":
            c.dp_charges = r["dp_per_scrip"]
            c.notes.append("DP charge is per stock per day, so selling the same stock twice in a day is charged once.")
        if product == "MTF":
            # Bought shares are pledged as MTF collateral; selling releases the pledge.
            c.pledge_charges = r["pledge_per_scrip"]

    c.exchange_txn = value * (r["txn_bse"] if exchange.upper() == "BSE" else r["txn_nse"])
    c.sebi = value * r["sebi"]
    c.gst = (c.brokerage + c.exchange_txn + c.dp_charges + c.pledge_charges) * r["gst"]
    if exchange.upper() == "BSE":
        c.notes.append("BSE transaction charges vary by scrip group; the A/B group rate is used.")
    return c


def mtf_interest(buy_value: float, margin_pct: float, days: int) -> tuple[float, float, int]:
    """Return (interest ₹, funded amount ₹, slabs) for an MTF position held `days` days.

    Upstox charges ₹20 per day for every ₹40,000 slab it funds (or part of one).
    """
    funded = max(0.0, buy_value * (1 - margin_pct / 100))
    slabs = math.ceil(funded / RATES["mtf_slab"]) if funded else 0
    return slabs * RATES["mtf_interest_per_slab_day"] * max(days, 0), funded, slabs


def round_trip(product: str, buy_price: float, sell_price: float, qty: int, exchange: str = "NSE",
               days_held: int = 0, margin_pct: float = 25.0) -> dict:
    """Full buy + sell estimate, with net P&L and the breakeven sell price."""
    buy = order_charges(product, "BUY", buy_price, qty, exchange)
    sell = order_charges(product, "SELL", sell_price, qty, exchange)
    interest, funded, slabs = (0.0, 0.0, 0)
    if product == "MTF":
        interest, funded, slabs = mtf_interest(buy_price * qty, margin_pct, days_held)
    total = buy.total + sell.total + interest
    gross = (sell_price - buy_price) * qty
    return {
        "buy": buy,
        "sell": sell,
        "mtf_interest": interest,
        "mtf_funded": funded,
        "mtf_slabs": slabs,
        "total_charges": round(total, 2),
        "gross_pnl": round(gross, 2),
        "net_pnl": round(gross - total, 2),
        "breakeven_sell_price": round(buy_price + total / qty, 2) if qty else 0.0,
    }
