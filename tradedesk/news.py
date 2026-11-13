"""Exchange news for the News tab: announcements, bulk and block deals, insider trades.

All from NSE's public APIs (through filings.NSEClient, which handles cookies):

- corporate-announcements: every filing a company makes (results, orders,
  dividends, acquisitions, credit ratings, analyst meets, ...)
- historical/bulk-deals and historical/block-deals: large trades with the
  buyer or seller's name
- corporates-pit: insider trading disclosures under SEBI's PIT rules
  (promoters, directors, key staff and their relatives)
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from .earnings import _date
from .filings import NSEClient, _f

# First match wins; checked against the subject and text of each announcement.
CATEGORIES = [
    ("Results", ("financial result", "quarterly result", "audited result", "unaudited")),
    ("Dividend / bonus / split", ("dividend", "bonus", "split", "sub-division", "record date")),
    ("Buyback", ("buyback", "buy back", "buy-back")),
    ("Legal / regulatory", ("litigation", "penalty", "show cause", "sebi order", "court", "tribunal", "nclt",
                            "income tax", "gst demand", "tax demand")),
    ("Order / contract", ("order", "orders", "contract", "letter of award", "loa", "bagged", "work order")),
    ("Acquisition / merger", ("acquisition", "acquire", "amalgamation", "merger", "demerger", "scheme of arrangement",
                              "stake")),
    ("Fund raising", ("qip", "preferential", "rights issue", "fund raising", "ncd", "debenture", "warrants")),
    ("Credit rating", ("credit rating", "crisil", "icra", "care ratings", "india ratings")),
    ("Insider / SAST", ("sast", "regulation 29", "regulation 7", "insider", "pledge", "encumbrance")),
    ("Management change", ("resignation", "appointment", "cessation", "director", "ceo", "cfo", "auditor")),
    ("Analyst / investor meet", ("analyst", "analysts", "investor meet", "conference call", "earnings call", "investor presentation",
                                 "transcript")),
    ("Board meeting", ("board meeting", "outcome of board")),
    ("Press release", ("press release", "media release")),
]
IMPORTANT = {"Results", "Order / contract", "Acquisition / merger", "Buyback", "Fund raising", "Credit rating",
             "Legal / regulatory", "Dividend / bonus / split"}


_PATTERNS = [(name, re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b")) for name, words in CATEGORIES]


def category(subject: str, text: str = "") -> str:
    """Subject decides first (it's NSE's own label); the free text only if the subject says nothing."""
    for s in (subject.lower(), f"{subject} {text}".lower()):
        for name, pat in _PATTERNS:
            if pat.search(s):
                return name
    return "Other"


def _rows(data) -> list[dict]:
    return (data.get("data", []) if isinstance(data, dict) else data) or []


# ---------------------------------------------------------------- announcements
def announcements_frame(raw: list[dict]) -> pd.DataFrame:
    rows = []
    for r in raw or []:
        when = _date(r.get("an_dt") or r.get("sort_date") or r.get("exchdisstime"))
        sym = (r.get("symbol") or "").upper()
        if not sym or pd.isna(when):
            continue
        subj, text = (r.get("desc") or "").strip(), (r.get("attchmntText") or "").strip()
        cat = category(subj, text)
        rows.append({"Time": when, "Symbol": sym, "Company": (r.get("sm_name") or "").strip(), "Category": cat,
                     "Important": cat in IMPORTANT, "Subject": subj, "Details": text,
                     "Link": r.get("attchmntFile") or ""})
    df = pd.DataFrame(rows, columns=["Time", "Symbol", "Company", "Category", "Important", "Subject", "Details",
                                     "Link"])
    return df.sort_values("Time", ascending=False).reset_index(drop=True) if not df.empty else df


def fetch_announcements(start: dt.date, end: dt.date, symbol: str | None = None,
                        client: NSEClient | None = None) -> pd.DataFrame:
    c = client or NSEClient()
    params = {"index": "equities", "from_date": f"{start:%d-%m-%Y}", "to_date": f"{end:%d-%m-%Y}"}
    if symbol:
        params["symbol"] = symbol
    return announcements_frame(_rows(c.get("corporate-announcements", **params)))


# ---------------------------------------------------------------- bulk and block deals
def deals_frame(raw: list[dict], kind: str) -> pd.DataFrame:
    rows = []
    for r in raw or []:
        g = lambda *ks: next((r[k] for k in ks if r.get(k) not in (None, "")), None)  # noqa: E731
        when = _date(g("BD_DT_DATE", "date", "mTIMESTAMP"))
        sym = (g("BD_SYMBOL", "symbol") or "").upper()
        qty, price = _f(g("BD_QTY_TRD", "qty", "quantity")), _f(g("BD_TP_WATP", "watp", "tradePrice"))
        if not sym or pd.isna(when):
            continue
        side = str(g("BD_BUY_SELL", "buySell") or "").strip().upper()
        rows.append({"Date": when.normalize(), "Kind": kind, "Symbol": sym,
                     "Company": (g("BD_SCRIP_NAME", "name") or "").strip(),
                     "Client": (g("BD_CLIENT_NAME", "clientName") or "").strip(),
                     "Side": "BUY" if side.startswith("B") else "SELL" if side.startswith("S") else side,
                     "Qty": qty, "Price": price, "Value (₹ cr)": (qty * price / 1e7) if qty and price else None,
                     "Remarks": (g("BD_REMARKS", "remarks") or "").strip(" -")})
    df = pd.DataFrame(rows, columns=["Date", "Kind", "Symbol", "Company", "Client", "Side", "Qty", "Price",
                                     "Value (₹ cr)", "Remarks"])
    return df.sort_values(["Date", "Value (₹ cr)"], ascending=False).reset_index(drop=True) if not df.empty else df


def fetch_deals(start: dt.date, end: dt.date, client: NSEClient | None = None) -> tuple[pd.DataFrame, list[str]]:
    from .filings import FilingError

    c = client or NSEClient()
    frames, errors = [], []
    for kind, path in (("Bulk", "historical/bulk-deals"), ("Block", "historical/block-deals")):
        try:
            frames.append(deals_frame(_rows(c.get(path, **{"from": f"{start:%d-%m-%Y}", "to": f"{end:%d-%m-%Y}"})),
                                      kind))
        except FilingError as e:
            errors.append(f"{kind} deals: {e}")
            if "unreachable" in str(e):
                break
    frames = [f for f in frames if not f.empty]
    df = pd.concat(frames, ignore_index=True) if frames else deals_frame([], "")
    return df, errors


# ---------------------------------------------------------------- insider trades
def insider_frame(raw: list[dict]) -> pd.DataFrame:
    rows = []
    for r in raw or []:
        sym = (r.get("symbol") or "").upper()
        when = _date(r.get("intimDt") or r.get("date") or r.get("acqtoDt"))
        if not sym or pd.isna(when):
            continue
        txn = str(r.get("tdpTransactionType") or r.get("acqMode") or "").strip()
        sign = 1 if txn.lower().startswith(("buy", "acq", "purchase")) else -1 if txn.lower().startswith(
            ("sell", "sale", "dispos")) else 0
        value = _f(r.get("secVal"))
        rows.append({"Disclosed": when, "Symbol": sym, "Company": (r.get("company") or "").strip(),
                     "Person": (r.get("acqName") or "").strip(), "Category": (r.get("personCategory") or "").strip(),
                     "Type": txn or "–", "Mode": (r.get("acqMode") or "").strip(), "Shares": _f(r.get("secAcq")),
                     "Value (₹ cr)": value / 1e7 if value is not None else None,
                     "Signed value (₹ cr)": sign * value / 1e7 if value is not None else None,
                     "Holding before %": _f(r.get("befAcqSharesPer")),
                     "Holding after %": _f(r.get("afterAcqSharesPer")),
                     "Traded": f"{r.get('acqfromDt') or ''} – {r.get('acqtoDt') or ''}".strip(" –")})
    cols = ["Disclosed", "Symbol", "Company", "Person", "Category", "Type", "Mode", "Shares", "Value (₹ cr)",
            "Signed value (₹ cr)", "Holding before %", "Holding after %", "Traded"]
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values("Disclosed", ascending=False).reset_index(drop=True) if not df.empty else df


def fetch_insider(start: dt.date, end: dt.date, symbol: str | None = None,
                  client: NSEClient | None = None) -> pd.DataFrame:
    c = client or NSEClient()
    params = {"index": "equities", "from_date": f"{start:%d-%m-%Y}", "to_date": f"{end:%d-%m-%Y}"}
    if symbol:
        params["symbol"] = symbol
    return insider_frame(_rows(c.get("corporates-pit", **params)))


def insider_net(df: pd.DataFrame, promoters_only: bool = False) -> pd.DataFrame:
    """Net insider buying per company, open-market trades only (drops gifts, ESOPs, pledges)."""
    if df.empty:
        return pd.DataFrame(columns=["Symbol", "Company", "Net buy (₹ cr)", "Buys", "Sells", "People"])
    d = df[df["Mode"].str.lower().str.contains("market", na=False) | (df["Mode"] == "")]
    if promoters_only:
        d = d[d["Category"].str.lower().str.contains("promoter", na=False)]
    d = d.dropna(subset=["Signed value (₹ cr)"])
    if d.empty:
        return pd.DataFrame(columns=["Symbol", "Company", "Net buy (₹ cr)", "Buys", "Sells", "People"])
    g = d.groupby(["Symbol", "Company"]).agg(**{
        "Net buy (₹ cr)": ("Signed value (₹ cr)", "sum"),
        "Buys": ("Signed value (₹ cr)", lambda s: int((s > 0).sum())),
        "Sells": ("Signed value (₹ cr)", lambda s: int((s < 0).sum())),
        "People": ("Person", "nunique")}).reset_index()
    return g.sort_values("Net buy (₹ cr)", ascending=False).reset_index(drop=True)
