"""Earnings tab: results calendar (and, below it, the results feed and scorecard)."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from . import demo, earnings, filings, market
from .filings import FilingError
from .theme import bar

TAG = {"held": "● HELD", "idea": "◆ IDEA", "watchlist": "○ WATCH"}


# ---------------------------------------------------------------- cached loaders
@st.cache_data(ttl=3 * 3600, show_spinner="Reading the NSE results calendar…")
def load_calendar(start: dt.date, end: dt.date) -> tuple[pd.DataFrame, str | None]:
    try:
        return earnings.fetch_calendar(start, end), None
    except FilingError as e:
        return earnings.calendar_rows([]), str(e)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_results(symbol: str) -> tuple[pd.DataFrame, str | None]:
    try:
        return filings.results_frame(filings.NSEClient().results(symbol)), None
    except FilingError as e:
        return pd.DataFrame(), str(e)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def load_estimates(symbol: str) -> dict:
    return earnings.yahoo_estimates(market.yahoo_symbol(symbol))


def _stocks(table: pd.DataFrame, ideas: dict) -> dict[str, str]:
    held = list(dict.fromkeys(table["symbol"].dropna())) if not table.empty else []
    return earnings.my_stocks(held, ideas, st.session_state.get("custom_watch", []))


# ---------------------------------------------------------------- calendar
def _bar_numbers(symbol: str, meeting: pd.Timestamp) -> dict:
    res, _ = load_results(symbol)
    b = earnings.year_ago_bar(res, meeting)
    est = load_estimates(symbol)
    ya, lq = b.get("year_ago", {}), b.get("last_q", {})
    return {"Qtr": b.get("quarter", ""), "Yr-ago revenue (₹ cr)": ya.get("revenue"),
            "Yr-ago profit (₹ cr)": ya.get("profit"), "Last qtr profit (₹ cr)": lq.get("profit"),
            "Yr-ago EPS": ya.get("eps"), "EPS est.": est.get("eps_est"),
            "Revenue est. (₹ cr)": est.get("revenue_est_cr"), "Out?": "yes" if b.get("reported") else ""}


def render_calendar(table: pd.DataFrame, ideas: dict) -> None:
    today = market.now_ist().date()
    c = st.columns([3, 2, 2])
    span = c[0].radio("When", ["This week", "Next week", "Next 30 days", "Last 7 days"], horizontal=True,
                      key="ec_span", label_visibility="collapsed")
    if span == "This week":
        start, end = earnings.week_bounds(today)
    elif span == "Next week":
        start, end = earnings.week_bounds(today, 1)
    elif span == "Next 30 days":
        start, end = today, today + dt.timedelta(days=30)
    else:
        start, end = today - dt.timedelta(days=7), today
    only_mine = c[1].toggle("Only my stocks", key="ec_mine",
                            help="Holdings, today's ideas, data/watchlist.txt and your Markets custom list.")
    with_numbers = c[2].toggle("Add last-year numbers", value=True, key="ec_nums",
                               help="Fetches each company's last 5 quarters from NSE. Done for your stocks; "
                                    "for everyone else only when 'Only my stocks' is off and the list is short.")

    cal, err = load_calendar(start, end)
    sample = False
    if err:
        st.warning(f"NSE didn't answer ({err}). Showing **sample data** so you can see the layout.")
        cal, sample = earnings.calendar_rows(demo.EARNINGS_CALENDAR), True
    mine = _stocks(table, ideas)
    cal = cal.assign(Yours=cal["Symbol"].map(lambda s: TAG.get(mine.get(s, ""), "")))
    yours = cal[cal["Yours"] != ""]
    bar([("RANGE", f"{start:%d %b} → {end:%d %b}", "amb"), ("REPORTING", str(len(cal)), ""),
         ("YOURS", str(len(yours)), "amb" if len(yours) else ""),
         ("TODAY", str(int((cal["Date"].dt.date == today).sum())), "")])

    held_soon = cal[(cal["Yours"] == TAG["held"]) & (cal["Date"].dt.date >= today)]
    if not held_soon.empty:
        st.info("You hold stocks reporting soon: " + ", ".join(
            f"**{r.Symbol}** ({r.Date:%a %d %b})" for r in held_soon.itertuples()) +
            ". Results move prices a lot in a day; check the scorecard below for how each usually reacts.")

    show = yours if only_mine else cal
    if show.empty:
        st.info("No results meetings in this range" + (" for your stocks." if only_mine else "."))
        return
    show = show.copy()
    if with_numbers and not sample:
        targets = list(show[show["Yours"] != ""].index)
        if not only_mine and len(show) <= 40:
            targets = list(show.index)
        prog = st.progress(0.0, text="Fetching last year's numbers…") if len(targets) > 3 else None
        for n, i in enumerate(targets):
            for k, v in _bar_numbers(show.at[i, "Symbol"], show.at[i, "Date"]).items():
                show.loc[i, k] = v
            if prog:
                prog.progress((n + 1) / len(targets), text=f"Fetching last year's numbers… {show.at[i, 'Symbol']}")
        if prog:
            prog.empty()
    show.insert(1, "Day", show["Date"].dt.strftime("%a"))
    num = {c_: "{:,.0f}" for c_ in ("Yr-ago revenue (₹ cr)", "Yr-ago profit (₹ cr)", "Last qtr profit (₹ cr)",
                                     "Revenue est. (₹ cr)")}
    num.update({"Yr-ago EPS": "{:,.2f}", "EPS est.": "{:,.2f}", "Date": "{:%d %b %Y}"})
    cols = ["Date", "Day", "Symbol", "Company", "Yours", "Qtr", "Yr-ago revenue (₹ cr)", "Yr-ago profit (₹ cr)",
            "Last qtr profit (₹ cr)", "Yr-ago EPS", "EPS est.", "Revenue est. (₹ cr)", "Out?", "Purpose"]
    show = show[[x for x in cols if x in show]]
    st.dataframe(show.style.format({k: v for k, v in num.items() if k in show}, na_rep="–")
                 .apply(lambda r: ["background-color: #1f1606" if r.get("Yours") else "" for _ in r], axis=1),
                 use_container_width=True, hide_index=True, height=min(38 + 35 * len(show), 640))
    st.download_button("Download CSV", show.to_csv(index=False).encode(), f"results_{start:%Y%m%d}.csv", "text/csv",
                       key="ec_csv")
    st.markdown("<div class='td-src'>Dates: NSE event calendar / board meetings (companies can move them). "
                "Last-year numbers: NSE results comparison, ₹ crore, standalone or consolidated as filed. "
                "Estimates: Yahoo Finance analyst consensus where it has coverage (often blank for mid and small "
                f"caps). Fetched {market.now_ist():%d %b %H:%M} IST. "
                "Add stocks to watch in data/watchlist.txt.</div>", unsafe_allow_html=True)


def render(token: str | None, table: pd.DataFrame, ideas: dict) -> None:
    st.markdown("## Results calendar")
    render_calendar(table, ideas)
