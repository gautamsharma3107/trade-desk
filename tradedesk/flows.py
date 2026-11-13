"""Money flows and derivatives positioning for the Flows tab.

- FII/FPI and DII cash-market buying and selling: NSE `api/fiidiiTradeReact`
  (today's provisional figures, ₹ crore). NSE has no public history endpoint, so
  each day seen is also kept in a small CSV (see HISTORY_FILES).
- Participant-wise open interest: NSE's daily archive
  `fao_participant_oi_DDMMYYYY.csv` (clients, DIIs, FIIs and prop desks; index
  and stock futures and options, long and short contracts).
- Option chain: Upstox's option-chain API when logged in, else NSE's
  `option-chain-v3`. From it: put-call ratio, max pain, the strikes with the
  most call and put open interest, and the move the ATM straddle prices in.
"""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import pandas as pd
import requests

from .earnings import _date
from .filings import NSE_HEADERS, FilingError, NSEClient, _f

ARCHIVE = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d:%d%m%Y}.csv"
HISTORY_FILES = [Path(__file__).resolve().parent.parent / "data" / "fii_dii.csv",  # optional, kept in the repo
                 Path.home() / ".trade-desk" / "fii_dii.csv"]  # what this server has seen
INDEX_UNDERLYINGS = {  # NSE symbol -> Upstox instrument key
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
}


# ---------------------------------------------------------------- FII / DII cash
def fii_dii_frame(raw: list[dict]) -> pd.DataFrame:
    rows = []
    for r in raw or []:
        cat = str(r.get("category") or "").upper()
        who = "FII" if "FII" in cat or "FPI" in cat else "DII" if "DII" in cat else None
        when = _date(r.get("date"))
        if not who or pd.isna(when):
            continue
        rows.append({"Date": when.normalize(), "Who": who, "Buy": _f(r.get("buyValue")),
                     "Sell": _f(r.get("sellValue")), "Net": _f(r.get("netValue"))})
    return pd.DataFrame(rows, columns=["Date", "Who", "Buy", "Sell", "Net"])


def fetch_fii_dii(client: NSEClient | None = None) -> pd.DataFrame:
    c = client or NSEClient()
    data = c.get("fiidiiTradeReact")
    return fii_dii_frame(data if isinstance(data, list) else (data or {}).get("data", []))


def load_history() -> pd.DataFrame:
    frames = []
    for f in HISTORY_FILES:
        try:
            frames.append(pd.read_csv(f, parse_dates=["Date"]))
        except (OSError, ValueError):
            continue
    if not frames:
        return fii_dii_frame([])
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(["Date", "Who"], keep="last").sort_values("Date").reset_index(drop=True)


def remember(today: pd.DataFrame) -> pd.DataFrame:
    """Add today's figures to this server's history file and return the full history."""
    hist = pd.concat([load_history(), today], ignore_index=True)
    hist = hist.drop_duplicates(["Date", "Who"], keep="last").sort_values("Date").reset_index(drop=True)
    try:
        HISTORY_FILES[1].parent.mkdir(parents=True, exist_ok=True)
        hist.to_csv(HISTORY_FILES[1], index=False)
    except OSError:
        pass
    return hist


def flow_summary(hist: pd.DataFrame, days: int) -> dict:
    """Net FII and DII buying over the last `days` trading days in the history."""
    out = {}
    for who in ("FII", "DII"):
        part = hist[hist["Who"] == who].sort_values("Date").tail(days)
        out[who] = float(part["Net"].sum()) if not part.empty else None
        out[f"{who}_days"] = len(part)
    return out


# ---------------------------------------------------------------- participant open interest
def parse_participant_oi(text: str) -> pd.DataFrame:
    """NSE participant OI CSV -> one row per participant (Client, DII, FII, Pro, TOTAL)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    start = next((i for i, ln in enumerate(lines) if ln.lower().startswith("client type")), None)
    if start is None:
        raise FilingError("Participant OI file has no header row")
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={df.columns[0]: "Participant"})
    df["Participant"] = df["Participant"].astype(str).str.strip()
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "").str.strip(), errors="coerce")
    return df.dropna(subset=[df.columns[1]]).reset_index(drop=True)


def positioning(oi: pd.DataFrame) -> pd.DataFrame:
    """Net long contracts per participant in index futures, index calls and index puts."""
    def col(*names):
        for n in names:
            for c in oi.columns:
                if c.lower().replace(" ", "") == n.lower().replace(" ", ""):
                    return oi[c]
        return pd.Series(0, index=oi.index)

    fl, fs = col("Future Index Long"), col("Future Index Short")
    out = pd.DataFrame({
        "Participant": oi["Participant"],
        "Index fut long": fl, "Index fut short": fs, "Index fut net": fl - fs,
        "Index fut long %": (fl / (fl + fs) * 100).where((fl + fs) > 0),
        "Index calls net": col("Option Index Call Long") - col("Option Index Call Short"),
        "Index puts net": col("Option Index Put Long") - col("Option Index Put Short"),
        "Stock fut net": col("Future Stock Long") - col("Future Stock Short"),
    })
    return out[out["Participant"].str.upper() != "TOTAL"].reset_index(drop=True)


def fetch_participant_oi(days: int = 10, today: dt.date | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Positioning for the last `days` trading days found in NSE's archive (holidays are skipped)."""
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    day, frames, errors, tried = (today or dt.date.today()), [], [], 0
    while len(frames) < days and tried < days * 2 + 6:
        tried += 1
        if day.weekday() < 5:
            try:
                r = s.get(ARCHIVE.format(d=day), timeout=15)
                if r.status_code == 200 and "Client Type" in r.text:
                    frames.append(positioning(parse_participant_oi(r.text)).assign(Date=pd.Timestamp(day)))
                elif r.status_code not in (404, 403):
                    errors.append(f"{day:%d %b}: HTTP {r.status_code}")
            except (requests.RequestException, FilingError, ValueError) as e:
                errors.append(f"{day:%d %b}: {e}")
                if isinstance(e, requests.ConnectionError):
                    break
        day -= dt.timedelta(days=1)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return df, errors


# ---------------------------------------------------------------- option chain
CHAIN_COLS = ["strike", "call_oi", "call_chg_oi", "call_vol", "call_iv", "call_ltp",
              "put_ltp", "put_iv", "put_vol", "put_chg_oi", "put_oi"]


def chain_from_upstox(rows: list[dict]) -> tuple[pd.DataFrame, float | None]:
    out, spot = [], None
    for r in rows or []:
        spot = spot or _f(r.get("underlying_spot_price"))
        rec = {"strike": _f(r.get("strike_price"))}
        for side in ("call", "put"):
            o = r.get(f"{side}_options") or {}
            md, gk = o.get("market_data") or {}, o.get("option_greeks") or {}
            oi, prev = _f(md.get("oi")), _f(md.get("prev_oi"))
            rec.update({f"{side}_oi": oi, f"{side}_chg_oi": (oi - prev) if oi is not None and prev is not None else None,
                        f"{side}_vol": _f(md.get("volume")), f"{side}_iv": _f(gk.get("iv")),
                        f"{side}_ltp": _f(md.get("ltp"))})
        out.append(rec)
    df = pd.DataFrame(out, columns=CHAIN_COLS)
    return df.dropna(subset=["strike"]).sort_values("strike").reset_index(drop=True), spot


def chain_from_nse(data: dict, expiry: str | None = None) -> tuple[pd.DataFrame, float | None]:
    rec = (data or {}).get("records") or {}
    spot = _f(rec.get("underlyingValue"))
    out = []
    for r in rec.get("data") or (data or {}).get("filtered", {}).get("data") or []:
        exp = r.get("expiryDate") or r.get("expiryDates")
        if expiry and exp and str(exp).lower() != expiry.lower():
            continue
        row = {"strike": _f(r.get("strikePrice"))}
        for side, key in (("call", "CE"), ("put", "PE")):
            o = r.get(key) or {}
            spot = spot or _f(o.get("underlyingValue"))
            row.update({f"{side}_oi": _f(o.get("openInterest")), f"{side}_chg_oi": _f(o.get("changeinOpenInterest")),
                        f"{side}_vol": _f(o.get("totalTradedVolume")), f"{side}_iv": _f(o.get("impliedVolatility")),
                        f"{side}_ltp": _f(o.get("lastPrice"))})
        out.append(row)
    df = pd.DataFrame(out, columns=CHAIN_COLS)
    return df.dropna(subset=["strike"]).sort_values("strike").reset_index(drop=True), spot


def max_pain(chain: pd.DataFrame) -> float | None:
    """Expiry price at which option buyers, in total, would get the least."""
    c = chain.fillna({"call_oi": 0, "put_oi": 0})
    if c.empty or (c["call_oi"].sum() + c["put_oi"].sum()) == 0:
        return None
    strikes = c["strike"].to_numpy()
    pain = [((s - strikes).clip(min=0) * c["call_oi"]).sum() + ((strikes - s).clip(min=0) * c["put_oi"]).sum()
            for s in strikes]
    return float(strikes[int(pd.Series(pain).idxmin())])


def chain_stats(chain: pd.DataFrame, spot: float | None) -> dict:
    if chain.empty:
        return {}
    c = chain.fillna(0)
    call_oi, put_oi = c["call_oi"].sum(), c["put_oi"].sum()
    out = {"pcr": put_oi / call_oi if call_oi else None, "max_pain": max_pain(chain),
           "resistance": float(c.loc[c["call_oi"].idxmax(), "strike"]) if call_oi else None,
           "support": float(c.loc[c["put_oi"].idxmax(), "strike"]) if put_oi else None,
           "call_oi": call_oi, "put_oi": put_oi, "spot": spot}
    if spot:
        atm = c.iloc[(c["strike"] - spot).abs().argsort().iloc[0]]
        straddle = float(atm["call_ltp"] + atm["put_ltp"])
        out.update(atm=float(atm["strike"]), straddle=straddle, implied_move_pct=straddle / spot * 100)
    return out


def nse_expiries(symbol: str, client: NSEClient | None = None) -> list[str]:
    c = client or NSEClient()
    data = c.get("option-chain-contract-info", symbol=symbol)
    return list((data or {}).get("expiryDates") or [])


def nse_chain(symbol: str, expiry: str, client: NSEClient | None = None) -> tuple[pd.DataFrame, float | None]:
    c = client or NSEClient()
    kind = "Indices" if symbol in INDEX_UNDERLYINGS else "Equity"
    return chain_from_nse(c.get("option-chain-v3", type=kind, symbol=symbol, expiry=expiry), expiry)
