"""Tax view for Indian traders: capital gains, trading income, set-off and loss harvesting.

Rates as in force from 23 July 2024 (Finance Act 2024), used for FY 2024-25 sales after that date and later
years:

- Listed equity held 12 months or less (sec 111A, STT paid): 20%.
- Listed equity held over 12 months (sec 112A): 12.5% on gains above ₹1.25 lakh a year.
- Intraday equity: speculative business income, taxed at your slab rate.
- Futures and options: non-speculative business income, at your slab rate; charges are deductible.
- Health and education cess of 4% on the tax. Surcharge is not included.

Set-off within the year (sec 70, 71, 73, 74): a short-term capital loss can reduce short- or long-term gains;
a long-term loss only long-term gains; a speculative loss only speculative income; an F&O loss can reduce any
income except salary, so also capital gains. What's left carries forward (8 years; speculative 4) if you file
your return on time.

This is an estimate to plan with, not tax advice.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

STCG_RATE, LTCG_RATE, LTCG_EXEMPT, CESS = 0.20, 0.125, 125_000.0, 0.04
SLABS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
ADVANCE_TAX = [(6, 15, 0.15), (9, 15, 0.45), (12, 15, 0.75), (3, 15, 1.00)]  # (month, day, cumulative share)

HEADS = {
    "Delivery (short-term)": "STCG",
    "Delivery (long-term)": "LTCG",
    "Intraday": "Speculative",
    "Futures": "F&O",
    "Options": "F&O",
    "Commodity futures": "F&O",
    "Commodity options": "F&O",
    "Currency futures": "F&O",
    "Currency options": "F&O",
}
HEAD_LABEL = {"STCG": "Short-term capital gains (sec 111A)", "LTCG": "Long-term capital gains (sec 112A)",
              "Speculative": "Intraday: speculative business income", "F&O": "F&O: non-speculative business income"}


def heads(trades: pd.DataFrame, fo_charges: float = 0.0) -> pd.DataFrame:
    """Gains, losses and net per tax head. F&O charges are deducted as business expenses."""
    rows = []
    t = trades.assign(head=trades["bucket"].map(HEADS)) if not trades.empty else trades.assign(head=[])
    for h in ("STCG", "LTCG", "Speculative", "F&O"):
        part = t[t["head"] == h] if not t.empty else t
        gains = float(part.loc[part["pnl"] > 0, "pnl"].sum()) if len(part) else 0.0
        losses = abs(float(part.loc[part["pnl"] < 0, "pnl"].sum())) if len(part) else 0.0
        exp = float(fo_charges) if h == "F&O" else 0.0
        rows.append({"Head": h, "Label": HEAD_LABEL[h], "Trades": len(part), "Gains": gains, "Losses": losses,
                     "Expenses": exp, "Net": gains - losses - exp,
                     "Turnover": float(part["pnl"].abs().sum()) if len(part) else 0.0})
    return pd.DataFrame(rows)


def set_off(net: dict[str, float]) -> tuple[dict[str, float], dict[str, float], list[str]]:
    """Apply the set-off rules. Returns (taxable per head, carried forward per head, notes)."""
    st, lt, spec, fo = (net.get(k, 0.0) for k in ("STCG", "LTCG", "Speculative", "F&O"))
    notes, cf = [], {}
    if st < 0 and lt > 0:  # within capital gains first (sec 70)
        used = min(lt, -st)
        st += used
        lt -= used
        notes.append(f"Short-term capital loss of ₹{used:,.0f} set off against long-term gains.")
    if fo < 0:  # then a business loss against capital gains (sec 71)
        for name in ("STCG", "LTCG"):
            gain = st if name == "STCG" else lt
            if fo < 0 and gain > 0:
                used = min(gain, -fo)
                fo += used
                if name == "STCG":
                    st -= used
                else:
                    lt -= used
                notes.append(f"F&O loss of ₹{used:,.0f} set off against {name}.")
    if st < 0:
        cf["STCG"] = -st
        st = 0.0
    if lt < 0:
        cf["LTCG"] = -lt
        lt = 0.0
        notes.append("A long-term capital loss can only be set off against long-term gains.")
    if spec < 0:
        cf["Speculative"] = -spec
        spec = 0.0
        notes.append("An intraday (speculative) loss can only be set off against speculative income.")
    if fo < 0:
        cf["F&O"] = -fo
        fo = 0.0
    if cf:
        notes.append("Losses carry forward (capital and F&O: 8 years; speculative: 4) only if you file your return "
                     "by the due date, usually 31 July (or 31 October if your F&O needs a tax audit).")
    return {"STCG": st, "LTCG": lt, "Speculative": spec, "F&O": fo}, cf, notes


def estimate(taxable: dict[str, float], slab: float) -> dict:
    lt_taxable = max(taxable["LTCG"] - LTCG_EXEMPT, 0.0)
    parts = {"STCG": taxable["STCG"] * STCG_RATE, "LTCG": lt_taxable * LTCG_RATE,
             "Speculative": taxable["Speculative"] * slab, "F&O": taxable["F&O"] * slab}
    base = sum(parts.values())
    return {"by_head": parts, "ltcg_exempt_used": min(taxable["LTCG"], LTCG_EXEMPT),
            "ltcg_exempt_left": max(LTCG_EXEMPT - taxable["LTCG"], 0.0), "tax": base, "cess": base * CESS,
            "total": base * (1 + CESS)}


def advance_tax_schedule(total: float, fy_start_year: int, today: dt.date | None = None) -> pd.DataFrame:
    """Cumulative advance tax due by each instalment date, if the whole year's tax were known now.

    Capital gains are only counted for instalments after the gain is made, so the real amounts can be lower;
    tax under ₹10,000 for the year needs no advance tax.
    """
    today = today or dt.date.today()
    rows = []
    for m, d, share in ADVANCE_TAX:
        when = dt.date(fy_start_year + (1 if m <= 3 else 0), m, d)
        rows.append({"Due by": when, "Cumulative share": share * 100, "Cumulative amount": total * share,
                     "Status": "past" if when < today else "upcoming"})
    return pd.DataFrame(rows)


def harvest(table: pd.DataFrame, taxable: dict[str, float], ltcg_left: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Holdings you could sell to book a loss (cutting tax), and gains that could use the LTCG exemption.

    Upstox's holdings don't include the buy date, so whether a position is short- or long-term isn't known here.
    """
    if table is None or table.empty:
        return pd.DataFrame(), pd.DataFrame()
    t = table[table["type"].isin(["Delivery", "MTF"])]
    gains_to_cover = taxable["STCG"] + taxable["LTCG"]
    losers = t[t["pnl"] < 0].sort_values("pnl")
    rows, left = [], gains_to_cover
    for r in losers.itertuples():
        loss = -float(r.pnl)
        use = min(loss, left) if left > 0 else 0.0
        st_rate_gain = min(use, taxable["STCG"])
        saving = (st_rate_gain * STCG_RATE + (use - st_rate_gain) * LTCG_RATE) * (1 + CESS)
        left -= use
        rows.append({"Stock": r.symbol, "Type": r.type, "Qty": r.qty, "Avg": r.avg_price, "LTP": r.ltp,
                     "Unrealised loss": loss, "Offsets gains": use, "Tax saved (approx)": saving})
    winners = t[t["pnl"] > 0].sort_values("pnl", ascending=False)
    wrows, left = [], ltcg_left
    for r in winners.itertuples():
        g = float(r.pnl)
        use = min(g, left) if left > 0 else 0.0
        left -= use
        wrows.append({"Stock": r.symbol, "Type": r.type, "Qty": r.qty, "Unrealised gain": g,
                      "Tax-free if long-term": use})
    return pd.DataFrame(rows), pd.DataFrame(wrows)
