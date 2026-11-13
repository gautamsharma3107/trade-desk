"""Trade journal: how your closed trades went, and whether the daily ideas worked.

Trades come from Upstox's trade-wise P&L report (pnl.trades_frame). Idea
history comes from data/ideas_history/*.json (one copy of data/ideas.json per
day, saved by tools/archive_ideas.py) plus today's data/ideas.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
IDEAS_DIR = DATA / "ideas_history"


# ---------------------------------------------------------------- your trades
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add return %, days held and win/loss to trades_frame rows."""
    if df.empty:
        return df.assign(ret_pct=pd.Series(dtype=float), days=pd.Series(dtype=float), result=pd.Series(dtype=str))
    cost = df[["buy_amount", "sell_amount"]].min(axis=1).where(lambda s: s > 0, df["buy_amount"])
    out = df.assign(ret_pct=(df["pnl"] / cost * 100).where(cost > 0),
                    days=(df["sell_date"] - df["buy_date"]).abs().dt.days,
                    result=df["pnl"].map(lambda v: "Win" if v > 0 else "Loss" if v < 0 else "Flat"))
    return out


def _streak(signs: list[int], want: int) -> int:
    best = cur = 0
    for s in signs:
        cur = cur + 1 if s == want else 0
        best = max(best, cur)
    return best


def stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    d = enrich(df).sort_values("booked")
    wins, losses = d[d["pnl"] > 0], d[d["pnl"] < 0]
    avg_win = float(wins["pnl"].mean()) if len(wins) else 0.0
    avg_loss = float(losses["pnl"].mean()) if len(losses) else 0.0
    win_rate = len(wins) / len(d)
    gross_win, gross_loss = float(wins["pnl"].sum()), float(-losses["pnl"].sum())
    signs = [1 if v > 0 else -1 if v < 0 else 0 for v in d["pnl"]]
    return {
        "trades": len(d), "wins": len(wins), "losses": len(losses), "win_rate": win_rate * 100,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "avg_win_pct": float(wins["ret_pct"].mean()) if len(wins) else None,
        "avg_loss_pct": float(losses["ret_pct"].mean()) if len(losses) else None,
        "payoff": (avg_win / -avg_loss) if avg_loss else None,
        "expectancy": float(d["pnl"].mean()),
        "profit_factor": (gross_win / gross_loss) if gross_loss else None,
        "days_win": float(wins["days"].mean()) if len(wins) else None,
        "days_loss": float(losses["days"].mean()) if len(losses) else None,
        "best": float(d["pnl"].max()), "worst": float(d["pnl"].min()),
        "win_streak": _streak(signs, 1), "loss_streak": _streak(signs, -1),
    }


def by_type(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for b, part in enrich(df).groupby("bucket"):
        s = stats(part)
        rows.append({"Type": b, "Trades": s["trades"], "Win rate %": s["win_rate"],
                     "Avg win": s["avg_win"] if s["wins"] else None,
                     "Avg loss": s["avg_loss"] if s["losses"] else None, "Payoff": s["payoff"], "Per trade": s["expectancy"],
                     "Total": float(part["pnl"].sum()), "Days held (avg)": float(part["days"].mean())})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    for c in out.columns[1:]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.sort_values("Total", ascending=False)


def lessons(s: dict) -> list[str]:
    """Plain-language patterns worth a look. Prompts, not rules."""
    out = []
    if not s or s["trades"] < 5:
        return ["Fewer than 5 closed trades in this period, so patterns aren't meaningful yet."]
    if s.get("payoff") is not None and s["payoff"] < 1 and s["win_rate"] < 60:
        out.append(f"Your average loss (₹{-s['avg_loss']:,.0f}) is bigger than your average win (₹{s['avg_win']:,.0f}) "
                   f"and you win {s['win_rate']:.0f}% of the time. A tighter stop-loss or letting winners run longer "
                   "would change the maths most.")
    if s.get("days_win") is not None and s.get("days_loss") is not None and s["days_loss"] > s["days_win"] * 1.5:
        out.append(f"You hold losers for {s['days_loss']:.0f} days on average but winners for only "
                   f"{s['days_win']:.0f}: the classic pattern of selling winners early and hoping on losers.")
    if s["expectancy"] > 0 and s.get("profit_factor") and s["profit_factor"] >= 1.5:
        out.append(f"Each trade made ₹{s['expectancy']:,.0f} on average (profit factor {s['profit_factor']:.1f}). "
                   "What you're doing is working; position size is the lever.")
    elif s["expectancy"] < 0:
        out.append(f"Each trade lost ₹{-s['expectancy']:,.0f} on average before charges. Check which type below "
                   "is dragging and consider pausing it.")
    if s["loss_streak"] >= 4:
        out.append(f"Longest losing run: {s['loss_streak']} trades in a row. A rule like 'stop for the day after 3 "
                   "losses' limits tilt.")
    return out or ["No warning signs in this period."]


# ---------------------------------------------------------------- daily ideas
def load_ideas_history(current: dict | None = None, folder: Path | None = None) -> list[dict]:
    """Every saved day of ideas, oldest first, de-duplicated by date."""
    days: dict[str, dict] = {}
    for f in sorted((folder or IDEAS_DIR).glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if d.get("date"):
            days[d["date"]] = d
    if current and current.get("date"):
        days[current["date"]] = current
    return [days[k] for k in sorted(days)]


def ideas_frame(history: list[dict]) -> pd.DataFrame:
    rows = []
    for day in history:
        when = pd.to_datetime(day.get("date"), errors="coerce")
        for i in day.get("buy_ideas", []) or []:
            rows.append({"Date": when, "Kind": "Buy", "Symbol": i.get("symbol"), "Name": i.get("name", ""),
                         "Price then": i.get("approx_price"), "Target": i.get("target"),
                         "Source": i.get("target_source", "")})
        for a in day.get("avoid", []) or []:
            rows.append({"Date": when, "Kind": "Avoid", "Symbol": a.get("symbol"), "Name": "",
                         "Price then": None, "Target": None, "Source": a.get("reason", "")[:80]})
    df = pd.DataFrame(rows, columns=["Date", "Kind", "Symbol", "Name", "Price then", "Target", "Source"])
    # The same stock often repeats for days; keep its first appearance per kind.
    return df.dropna(subset=["Date", "Symbol"]).sort_values("Date").drop_duplicates(["Kind", "Symbol"]) \
        .reset_index(drop=True)


def score_idea(row: dict, prices: pd.DataFrame | None, traded: set[str]) -> dict:
    """How an idea did from the day it was given until now."""
    out = {"Acted on": "yes" if row["Symbol"] in traded else ""}
    if prices is None or prices.empty:
        return out
    px = prices.dropna(subset=["Close"])
    since = px[px.index.normalize() >= pd.Timestamp(row["Date"]).normalize()]
    if since.empty:
        return out
    given = pd.to_numeric(row.get("Price then"), errors="coerce")
    entry = float(given) if pd.notna(given) and given > 0 else float(since["Close"].iloc[0])
    now = float(since["Close"].iloc[-1])
    out.update({"Price now": now, "Return %": (now / entry - 1) * 100,
                "Best %": (float(since["High"].max()) / entry - 1) * 100,
                "Worst %": (float(since["Low"].min()) / entry - 1) * 100, "Days": len(since)})
    tgt = row.get("Target")
    if tgt and tgt == tgt:
        hit = since[since["High"] >= float(tgt)]
        out["Target hit"] = f"{hit.index[0]:%d %b}" if not hit.empty else ""
    if row["Kind"] == "Avoid":
        out["Worked"] = "yes" if out["Return %"] < 0 else "no"
    else:
        out["Worked"] = "yes" if out["Return %"] > 0 else "no"
    return out


def traded_symbols(trades: pd.DataFrame, held: list[str]) -> set[str]:
    names = set(held)
    if not trades.empty:
        names |= {str(s).split()[0].upper() for s in trades["scrip"].dropna()}
    return names
