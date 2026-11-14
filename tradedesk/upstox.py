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


def is_auth_failure(message: str) -> bool:
    """True when Upstox rejected the access token itself (so the user has to log in again)."""
    m = message.lower()
    return "http 401" in m or "unauthorized" in m or "udapi100050" in m


def login_problem(message: str) -> str:
    """Turn an Upstox login error into a plain-language next step."""
    m = message.lower()
    if "udapi100057" in m or "invalid auth code" in m:
        return ("That Upstox login link has expired or was already used. Login codes work only once and only for "
                "a few minutes. Click **Login with Upstox** again. If this keeps happening straight after "
                "logging in, the Redirect URL in Streamlit Secrets and in your Upstox developer app don't match.")
    if "redirect" in m:
        return ("Upstox says the Redirect URL doesn't match. UPSTOX_REDIRECT_URI in Streamlit Secrets must be "
                "exactly the Redirect URL in your Upstox developer app, then log in again.")
    if "client_id" in m or "client_secret" in m or "udapi100016" in m or "invalid credentials" in m:
        return ("Upstox didn't accept the API key or secret. Copy them again from your Upstox developer app "
                "into Streamlit Secrets, then log in again.")
    return "Upstox login didn't work. Click **Login with Upstox** to try again."


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

    # ---------------------------------------------------------------- market data and P&L reports (read-only)
    def quotes(self, instrument_keys: list[str]) -> dict[str, dict]:
        """Full market quotes, keyed by instrument key (e.g. 'NSE_EQ|INE002A01018'). Max 500 per call."""
        out: dict[str, dict] = {}
        keys = [k for k in dict.fromkeys(instrument_keys) if k]
        for i in range(0, len(keys), 500):
            data = self._get("/v2/market-quote/quotes", instrument_key=",".join(keys[i:i + 500]))["data"] or {}
            for name, q in data.items():
                out[q.get("instrument_token") or name.replace(":", "|")] = q
        return out

    def pnl_meta(self, segment: str, fy: str, from_date: str | None = None, to_date: str | None = None) -> dict:
        params = {"segment": segment, "financial_year": fy}
        if from_date and to_date:
            params.update(from_date=from_date, to_date=to_date)
        return self._get("/v2/trade/profit-loss/metadata", **params)["data"] or {}

    def pnl_trades(self, segment: str, fy: str, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
        """Every realised trade (buy matched to sell) for one segment, all pages. Dates are dd-mm-yyyy."""
        params = {"segment": segment, "financial_year": fy}
        if from_date and to_date:
            params.update(from_date=from_date, to_date=to_date)
        meta = self.pnl_meta(segment, fy, from_date, to_date)
        count = int(meta.get("trades_count") or 0)
        size = int(meta.get("page_size_limit") or 500) or 500
        rows: list[dict] = []
        page = 1
        while len(rows) < count and page <= 200:
            batch = self._get("/v2/trade/profit-loss/data", page_number=page, page_size=size, **params)["data"] or []
            if not batch:
                break
            rows.extend(batch)
            page += 1
        return rows

    def charges_for(self, segment: str, fy: str, from_date: str | None = None, to_date: str | None = None) -> dict:
        params = {"segment": segment, "financial_year": fy}
        if from_date and to_date:
            params.update(from_date=from_date, to_date=to_date)
        return (self._get("/v2/trade/profit-loss/charges", **params)["data"] or {}).get("charges_breakdown") or {}

    def search_equity(self, query: str, exchange: str = "NSE", records: int = 10) -> list[dict]:
        """Upstox instrument search, equities only."""
        return self._get("/v2/instruments/search", query=query[:50], exchanges=exchange, segments="EQ",
                         records=records)["data"] or []


    def option_expiries(self, instrument_key: str) -> list[str]:
        """Expiry dates (YYYY-MM-DD) of the option contracts on an index or stock."""
        rows = self._get("/v2/option/contract", instrument_key=instrument_key)["data"] or []
        return sorted({r["expiry"] for r in rows if r.get("expiry")})

    def option_chain(self, instrument_key: str, expiry: str) -> list[dict]:
        """Put/call option chain with OI, volume, LTP and greeks for one expiry (YYYY-MM-DD)."""
        return self._get("/v2/option/chain", instrument_key=instrument_key, expiry_date=expiry)["data"] or []
