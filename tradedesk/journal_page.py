"""Journal tab: your win rate, average gain and loss, habits, and whether the daily ideas worked."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from . import demo, journal, market, pnl
from .theme import AMBER, GREEN, RED, bar, color, updown

INR = "₹{:,.0f}".format


def _trades(token: str | None, demo_mode: bool, period: pnl.Period) -> pd.DataFrame:
    from .terminal import load_pnl

    if demo_mode:
        trades, errors = demo.PNL_TRADES, []
    else:
        trades, _, errors = load_pnl(token, tuple(period.chunks()))
    for e in errors:
        if "No data" not in e and "UDAPI100" not in e:
            st.caption(f"Couldn't load {e}")
    return pnl.in_period(pnl.trades_frame(trades), period)


def _your_trades(df: pd.DataFrame) -> None:
    s = journal.stats(df)
    if not s:
        st.info("No closed trades in this period.")
        return
    m = st.columns(6)
    m[0].metric("Win rate", f"{s['win_rate']:.0f}%", f"{s['wins']}W / {s['losses']}L", delta_color="off")
    m[1].metric("Avg win", INR(s["avg_win"]), f"{s['avg_win_pct']:+.1f}%" if s["avg_win_pct"] is not None else None)
    m[2].metric("Avg loss", INR(s["avg_loss"]),
                f"{s['avg_loss_pct']:+.1f}%" if s["avg_loss_pct"] is not None else None)
    m[3].metric("Payoff (win ÷ loss)", f"{s['payoff']:.2f}" if s["payoff"] else "–")
    m[4].metric("Per trade", INR(s["expectancy"]))
    m[5].metric("Profit factor", f"{s['profit_factor']:.2f}" if s["profit_factor"] else "–")
    bar([("BEST", INR(s["best"]), "up"), ("WORST", INR(s["worst"]), "dn"),
         ("WIN STREAK", str(s["win_streak"]), ""), ("LOSS STREAK", str(s["loss_streak"]), ""),
         ("DAYS HELD · WINNERS", f"{s['days_win']:.0f}" if s["days_win"] is not None else "–", ""),
         ("DAYS HELD · LOSERS", f"{s['days_loss']:.0f}" if s["days_loss"] is not None else "–", "")])
    st.markdown("#### What stands out")
    for line in journal.lessons(s):
        st.markdown(f"- {line}")
    bt = journal.by_type(df)
    a, b = st.columns([3, 2])
    with a:
        st.markdown("#### By type")
        st.dataframe(bt.style.format({"Win rate %": "{:.0f}", "Avg win": "₹{:,.0f}", "Avg loss": "₹{:,.0f}",
                                      "Payoff": "{:.2f}", "Per trade": "₹{:,.0f}", "Total": "₹{:,.0f}",
                                      "Days held (avg)": "{:.0f}"}, na_rep="–")
                     .map(color, subset=["Per trade", "Total"]), use_container_width=True, hide_index=True)
    with b:
        e = journal.enrich(df).dropna(subset=["ret_pct"])
        fig = px.scatter(e, x="days", y="ret_pct", color="result", hover_name="scrip", height=300,
                         color_discrete_map={"Win": GREEN, "Loss": RED, "Flat": AMBER},
                         labels={"days": "Days held", "ret_pct": "Return %", "result": ""})
        fig.add_hline(y=0, line_dash="dot")
        st.markdown("#### Return vs days held")
        st.plotly_chart(fig, use_container_width=True)
    with st.expander("Every trade"):
        e = journal.enrich(df).sort_values("sell_date", ascending=False)
        show = e[["scrip", "bucket", "buy_date", "sell_date", "days", "qty", "buy_avg", "sell_avg", "pnl", "ret_pct",
                  "result"]].rename(columns={"scrip": "Stock", "bucket": "Type", "buy_date": "Bought",
                                             "sell_date": "Sold", "days": "Days", "qty": "Qty", "buy_avg": "Buy",
                                             "sell_avg": "Sell", "pnl": "P&L", "ret_pct": "Return %",
                                             "result": "Result"})
        st.dataframe(show.style.format({"Bought": "{:%d %b %y}", "Sold": "{:%d %b %y}", "Qty": "{:,.0f}",
                                        "Buy": "₹{:,.2f}", "Sell": "₹{:,.2f}", "P&L": "₹{:,.0f}",
                                        "Return %": "{:+.1f}"}, na_rep="–")
                     .map(color, subset=["P&L", "Return %"]), use_container_width=True, hide_index=True)
        st.download_button("Download journal CSV", show.to_csv(index=False).encode(), "journal.csv", "text/csv",
                           key="jr_csv")


def _ideas(ideas: dict, df: pd.DataFrame, table: pd.DataFrame) -> None:
    from .terminal import yahoo_history

    hist = journal.load_ideas_history(ideas)
    idf = journal.ideas_frame(hist)
    if idf.empty:
        st.info("No saved ideas yet.")
        return
    ys = {s: market.yahoo_symbol(s) for s in idf["Symbol"].unique()}
    prices, err = yahoo_history(tuple(ys.values()), "1y")
    sample = not prices
    if sample:
        st.warning(f"Couldn't get prices ({(err or 'no data')[:80]}). Showing **sample prices** so you can see the "
                   "layout.")
    held = list(table["symbol"].dropna()) if not table.empty else []
    traded = journal.traded_symbols(df, held)
    rows = []
    for n, r in enumerate(idf.to_dict("records")):
        given = pd.to_numeric(r["Price then"], errors="coerce")
        p = demo.price_history(n + 1, start="2026-10-01", last=(given if given == given and given else 1000) * 1.03) \
            if sample \
            else prices.get(ys[r["Symbol"]])
        rows.append({**r, **journal.score_idea(r, p, traded)})
    out = pd.DataFrame(rows)
    for c in ("Price then", "Price now", "Return %", "Best %", "Worst %", "Target", "Days"):
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    buys = out[out["Kind"] == "Buy"]
    worked = buys["Worked"].eq("yes").sum() if "Worked" in buys else 0
    scored = buys["Worked"].isin(["yes", "no"]).sum() if "Worked" in buys else 0
    avg = buys["Return %"].mean() if "Return %" in buys else None
    hits = int((buys.get("Target hit", pd.Series(dtype=str)).fillna("") != "").sum())
    bar([("DAYS OF IDEAS", str(len(hist)), "amb"), ("BUY IDEAS", str(len(buys)), ""),
         ("IN PROFIT", f"{worked}/{scored}", "up" if scored and worked / scored >= 0.5 else "dn"),
         ("AVG RETURN", f"{avg:+.1f}%" if avg == avg and avg is not None else "–", updown(avg or 0)),
         ("TARGETS HIT", str(hits), ""), ("YOU ACTED ON", str(int((out["Acted on"] == "yes").sum())), "")])
    cols = ["Date", "Kind", "Symbol", "Name", "Price then", "Price now", "Return %", "Best %", "Worst %", "Target",
            "Target hit", "Days", "Worked", "Acted on", "Source"]
    show = out[[c for c in cols if c in out]]
    st.dataframe(show.style.format({"Date": "{:%d %b}", "Price then": "₹{:,.0f}", "Price now": "₹{:,.0f}",
                                    "Target": "₹{:,.0f}", "Return %": "{:+.1f}", "Best %": "{:+.1f}",
                                    "Worst %": "{:+.1f}", "Days": "{:.0f}"}, na_rep="–")
                 .map(color, subset=[c for c in ("Return %", "Best %", "Worst %") if c in show]),
                 use_container_width=True, hide_index=True, height=min(38 + 35 * len(show), 560))
    st.caption("Each idea is measured from the price given on the day it first appeared (or that day's close) to the "
               "latest close. Best/worst are the highest high and lowest low since. An avoid idea 'worked' if the "
               "stock fell. Acted on = you traded or hold it (matched on symbol). Ideas history lives in "
               "data/ideas_history/; the morning job should run tools/archive_ideas.py to add each day.")


def render(token: str | None, table: pd.DataFrame, ideas: dict, demo_mode: bool) -> None:
    ps = pnl.periods()
    labels = [p.label for p in ps]
    pick = st.radio("Period", labels, horizontal=True, label_visibility="collapsed", key="jr_period")
    period = ps[labels.index(pick)]
    df = _trades(token, demo_mode, period)
    st.markdown("## Your trades")
    if demo_mode:
        st.caption("Sample trades. Log in to see your own.")
    _your_trades(df)
    st.divider()
    st.markdown("## Did the daily ideas work?")
    _ideas(ideas, df, table)
