"""Order tickets, safety checks and the Upstox order calls.

Everything that can send an order lives here, kept apart from the read-only
client in upstox.py. Three modes:

- paper:   nothing leaves the app; fills are simulated at the limit/last price.
- sandbox: orders go to Upstox's sandbox (api-sandbox.upstox.com) with a sandbox token.
- live:    real orders on api-hft.upstox.com.

The page decides which modes are allowed. This module only builds, checks and sends.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from urllib.parse import quote

import requests

from tradedesk.upstox import BASE, TIMEOUT, UpstoxError, _json

LIVE_ORDER_HOST = "https://api-hft.upstox.com"
SANDBOX_HOST = "https://api-sandbox.upstox.com"

PRODUCTS = {"Delivery": "D", "Intraday": "I", "MTF": "MTF"}
ORDER_TYPES = ("LIMIT", "MARKET", "SL", "SL-M")
SIDES = ("BUY", "SELL")
DEFAULT_MAX_ORDER_VALUE = 50_000.0   # ₹ per order unless MAX_ORDER_VALUE is set in secrets
FAR_FROM_LTP_PCT = 5.0               # warn when a limit is this far from the last price
TAG = "tradedesk"


@dataclass
class Ticket:
    instrument_key: str
    symbol: str
    side: str = "BUY"            # BUY / SELL
    qty: int = 1
    product: str = "D"           # D / I / MTF
    order_type: str = "LIMIT"    # LIMIT / MARKET / SL / SL-M
    price: float = 0.0           # limit price (0 for MARKET / SL-M)
    trigger_price: float = 0.0   # for SL / SL-M
    validity: str = "DAY"        # DAY / IOC
    is_amo: bool = False         # after-market order

    def payload(self) -> dict:
        """Body for POST /v3/order/place."""
        limit = self.order_type in ("LIMIT", "SL")
        trig = self.order_type in ("SL", "SL-M")
        return {
            "quantity": int(self.qty),
            "product": self.product,
            "validity": self.validity,
            "price": round(float(self.price), 2) if limit else 0,
            "tag": TAG,
            "instrument_token": self.instrument_key,
            "order_type": self.order_type,
            "transaction_type": self.side,
            "disclosed_quantity": 0,
            "trigger_price": round(float(self.trigger_price), 2) if trig else 0,
            "is_amo": bool(self.is_amo),
            "slice": False,
        }

    def ref_price(self, ltp: float | None) -> float:
        """Price used to estimate the order value."""
        if self.order_type in ("LIMIT", "SL") and self.price > 0:
            return float(self.price)
        if self.order_type == "SL-M" and self.trigger_price > 0:
            return float(self.trigger_price)
        return float(ltp or 0)

    def value(self, ltp: float | None) -> float:
        return self.ref_price(ltp) * int(self.qty)

    def summary(self, ltp: float | None = None) -> str:
        product = {v: k for k, v in PRODUCTS.items()}.get(self.product, self.product)
        if self.order_type == "LIMIT":
            how = f"at ₹{self.price:,.2f} limit"
        elif self.order_type == "MARKET":
            how = "at market price"
        elif self.order_type == "SL":
            how = f"stop-loss: trigger ₹{self.trigger_price:,.2f}, limit ₹{self.price:,.2f}"
        else:
            how = f"stop-loss market: trigger ₹{self.trigger_price:,.2f}"
        amo = " (after-market order)" if self.is_amo else ""
        return f"{self.side} {self.qty} × {self.symbol} {how}, {product}, {self.validity}{amo}"


@dataclass
class Check:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check(t: Ticket, ltp: float | None = None, held_qty: int | None = None,
          max_value: float = DEFAULT_MAX_ORDER_VALUE) -> Check:
    """Hard errors block the order; warnings are shown on the confirm step."""
    c = Check()
    if "|" not in (t.instrument_key or ""):
        c.errors.append("Pick a stock first.")
    if t.side not in SIDES:
        c.errors.append(f"Side must be BUY or SELL, not {t.side!r}.")
    if t.product not in PRODUCTS.values():
        c.errors.append(f"Unknown product {t.product!r}.")
    if t.order_type not in ORDER_TYPES:
        c.errors.append(f"Unknown order type {t.order_type!r}.")
    if t.validity not in ("DAY", "IOC"):
        c.errors.append(f"Validity must be DAY or IOC, not {t.validity!r}.")
    if int(t.qty) != t.qty or t.qty <= 0:
        c.errors.append("Quantity must be a whole number above zero.")
    if t.order_type in ("LIMIT", "SL") and t.price <= 0:
        c.errors.append("Enter a limit price above zero.")
    if t.order_type in ("SL", "SL-M") and t.trigger_price <= 0:
        c.errors.append("Enter a trigger price above zero for a stop-loss order.")
    if t.order_type == "SL" and t.price > 0 and t.trigger_price > 0:
        if t.side == "BUY" and t.price < t.trigger_price:
            c.errors.append("For a stop-loss BUY, the limit price must be at or above the trigger price.")
        if t.side == "SELL" and t.price > t.trigger_price:
            c.errors.append("For a stop-loss SELL, the limit price must be at or below the trigger price.")
    if t.is_amo and t.order_type in ("SL", "SL-M"):
        c.warnings.append("Upstox may reject stop-loss orders placed after market hours.")

    value = t.value(ltp)
    if max_value and value > max_value:
        c.errors.append(f"Order value ₹{value:,.0f} is above your per-order limit of ₹{max_value:,.0f}. "
                        "Lower the quantity, or raise MAX_ORDER_VALUE in the app secrets.")
    if t.order_type == "MARKET" and not ltp:
        c.warnings.append("No last price available, so the order value can't be checked against your limit.")

    if t.side == "SELL" and t.product in ("D", "MTF"):
        if not held_qty:
            c.errors.append(f"You don't hold {t.symbol} as {'delivery' if t.product == 'D' else 'MTF'}, "
                            "so there is nothing to sell. (Short selling is only possible intraday.)")
        elif t.qty > held_qty:
            c.errors.append(f"You hold {held_qty} {t.symbol}; you can't sell {t.qty}.")

    if t.order_type == "MARKET":
        c.warnings.append("Market order: it fills at whatever the price is when it reaches the exchange. "
                          "A limit order gives you control over the price.")
    if ltp and t.order_type in ("LIMIT", "SL") and t.price > 0:
        gap = (t.price / ltp - 1) * 100
        if abs(gap) >= FAR_FROM_LTP_PCT:
            c.warnings.append(f"Your limit ₹{t.price:,.2f} is {gap:+.1f}% from the last price ₹{ltp:,.2f}. "
                              "Check for a typo.")
        if t.order_type == "LIMIT" and ((t.side == "BUY" and gap > 0) or (t.side == "SELL" and gap < 0)):
            c.warnings.append("This limit is on the other side of the last price, so it will likely fill straight away.")
    if t.product == "I":
        c.warnings.append("Intraday: Upstox squares this off automatically before the close if you don't.")
    if t.product == "MTF" and t.side == "BUY":
        c.warnings.append("MTF: Upstox funds part of this and charges interest daily until you sell.")
    return c


def simulate_fill(t: Ticket, ltp: float | None, now: dt.datetime | None = None) -> dict:
    """A paper-trading order-book row. Nothing is sent anywhere."""
    now = now or dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    px_ = t.ref_price(ltp)
    fills = t.order_type == "MARKET" or (
        ltp and t.order_type == "LIMIT" and ((t.side == "BUY" and t.price >= ltp) or
                                             (t.side == "SELL" and t.price <= ltp)))
    if t.order_type == "MARKET" and ltp:
        px_ = float(ltp)
    return {
        "order_id": f"PAPER-{now:%H%M%S%f}",
        "order_timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "trading_symbol": t.symbol,
        "transaction_type": t.side,
        "quantity": t.qty,
        "product": t.product,
        "order_type": t.order_type,
        "price": t.price,
        "trigger_price": t.trigger_price,
        "average_price": px_ if fills else 0.0,
        "status": "complete" if fills else "open",
        "status_message": "Paper trade (nothing sent to Upstox)",
        "instrument_token": t.instrument_key,
        "ticket": asdict(t),
    }


class Trader:
    """Order calls for one access token. sandbox=True sends to Upstox's sandbox instead."""

    def __init__(self, access_token: str, sandbox: bool = False):
        self.sandbox = sandbox
        self.order_host = SANDBOX_HOST if sandbox else LIVE_ORDER_HOST
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json", "Content-Type": "application/json",
                               "Authorization": f"Bearer {access_token}"})

    # ---- order writes (sandbox or live)
    def place(self, t: Ticket) -> list[str]:
        body = _json(self.s.post(f"{self.order_host}/v3/order/place", json=t.payload(), timeout=TIMEOUT))
        data = body.get("data") or {}
        ids = data.get("order_ids") or ([data["order_id"]] if data.get("order_id") else [])
        if not ids:
            raise UpstoxError(f"Upstox accepted the request but returned no order id: {body}")
        return ids

    def cancel(self, order_id: str) -> dict:
        return _json(self.s.delete(f"{self.order_host}/v3/order/cancel", params={"order_id": order_id},
                                   timeout=TIMEOUT)).get("data") or {}

    # ---- reads (live API; the sandbox only supports order writes)
    def _get(self, path: str, **params) -> dict:
        return _json(self.s.get(f"{BASE}{path}", params=params or None, timeout=TIMEOUT))

    def order_book(self) -> list[dict]:
        return self._get("/v2/order/retrieve-all")["data"] or []

    def search(self, query: str, records: int = 15) -> list[dict]:
        return self._get("/v2/instruments/search", query=query[:50], exchanges="NSE,BSE",
                         segments="EQ", records=records)["data"] or []

    def ltp(self, instrument_keys: list[str]) -> dict[str, float]:
        if not instrument_keys:
            return {}
        data = self._get("/v3/market-quote/ltp", instrument_key=",".join(instrument_keys))["data"] or {}
        out = {}
        for k, v in data.items():
            key = v.get("instrument_token") or k
            out[key] = float(v.get("last_price") or 0)
        return out

    def margin(self, t: Ticket) -> dict:
        body = {"instruments": [{"instrument_key": t.instrument_key, "quantity": int(t.qty),
                                 "transaction_type": t.side, "product": t.product,
                                 "price": t.ref_price(None)}]}
        return _json(self.s.post(f"{BASE}/v2/charges/margin", json=body, timeout=TIMEOUT))["data"]


def chart_key(instrument_key: str) -> str:
    return quote(instrument_key, safe="")
