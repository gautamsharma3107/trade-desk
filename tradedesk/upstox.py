"""Small read-only client for the Upstox developer API (v2/v3).

Only GET endpoints for account data, plus the OAuth token exchange. This app
never places, changes or cancels orders.
"""
from __future__ import annotations

import datetime as dt
from urllib.parse import quote, urlencode

import requests

BASE = "https://api.upstox.com"
TIMEOUT = 15


class UpstoxError(RuntimeError):
    pass


def login_url(api_key: str, redirect_uri: str, state: str = "tradedesk") -> str:
    q = urlencode({"client_id": api_key, "redirect_uri": redirect_uri,
                   "response_type": "code", "state": state})
    return f"{BASE}/v2/login/authorization/dialog?{q}"


def exchange_code(code: str, api_key: str, api_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(
        f"{BASE}/v2/login/authorization/token",
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        data={"code": code, "client_id": api_key, "client_secret": api_secret,
              "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
        timeout=TIMEOUT,
    )
    body = _json(resp)
    if "access_token" not in body:
        raise UpstoxError(f"Login failed: {body}")
    return body


def token_expiry(now: dt.datetime | None = None) -> dt.datetime:
    """Upstox tokens expire at 3:30 AM IST the next day."""
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    now = (now or dt.datetime.now(ist)).astimezone(ist)
    expiry = now.replace(hour=3, minute=30, second=0, microsecond=0)
    if now >= expiry:
        expiry += dt.timedelta(days=1)
    return expiry


def financial_year(today: dt.date | None = None) -> str:
    """Upstox FY code, e.g. '2627' for April 2026 to March 2027."""
    today = today or dt.date.today()
    start = today.year if today.month >= 4 else today.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def _json(resp: requests.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        raise UpstoxError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400 or body.get("status") == "error":
        errs = body.get("errors") or body
        raise UpstoxError(f"HTTP {resp.status_code}: {errs}")
    return body


class Upstox:
    def __init__(self, access_token: str):
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json", "Authorization": f"Bearer {access_token}"})

    def _get(self, path: str, **params) -> dict:
        return _json(self.s.get(f"{BASE}{path}", params=params or None, timeout=TIMEOUT))

    def profile(self) -> dict:
        return self._get("/v2/user/profile")["data"]

    def holdings(self) -> list[dict]:
        return self._get("/v2/portfolio/long-term-holdings")["data"] or []

    def positions(self) -> list[dict]:
        return self._get("/v2/portfolio/short-term-positions")["data"] or []

    def mtf_positions(self) -> list[dict]:
        return self._get("/v3/portfolio/mtf-positions")["data"] or []

    def funds(self) -> dict:
        return self._get("/v2/user/get-funds-and-margin", segment="SEC")["data"]

    def trades_today(self) -> list[dict]:
        return self._get("/v2/order/trades/get-trades-for-day")["data"] or []

    def charges_breakdown(self, fy: str, segment: str = "EQ") -> dict:
        return self._get("/v2/trade/profit-loss/charges", segment=segment, financial_year=fy)["data"]

    def brokerage(self, instrument_token: str, qty: int, product: str, side: str, price: float) -> dict:
        return self._get("/v2/charges/brokerage", instrument_token=instrument_token, quantity=qty,
                         product=product, transaction_type=side, price=price)["data"]["charges"]

    def daily_candles(self, instrument_key: str, days: int = 120) -> list[list]:
        to = dt.date.today()
        frm = to - dt.timedelta(days=days)
        key = quote(instrument_key, safe="")
        data = self._get(f"/v3/historical-candle/{key}/days/1/{to:%Y-%m-%d}/{frm:%Y-%m-%d}")["data"]
        # Newest first from the API; return oldest first.
        return list(reversed(data.get("candles") or []))
