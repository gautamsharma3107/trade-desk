"""Earnings tab: results calendar (and, below it, the results feed and scorecard)."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import demo, earnings, filings, market
from .filings import FilingError
from .theme import AMBER, GREEN, RED, bar, color

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
        st.warning(f"NSE didn't answer ({str(err)[:90]}…). Showing **sample data** so you can see the layout.")
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


# ---------------------------------------------------------------- results feed
@st.cache_data(ttl=20 * 60, show_spinner="Checking NSE for new results…")
def load_filed(start: dt.date, end: dt.date) -> tuple[pd.DataFrame, str | None]:
    try:
        return earnings.fetch_filed(start, end), None
    except FilingError as e:
        return earnings.filed_rows([]), str(e)


def _feed(start: dt.date, end: dt.date) -> tuple[pd.DataFrame, bool, str | None]:
    """Filed results, or the sample feed when NSE can't be reached. Returns (rows, is_sample, error)."""
    df, err = load_filed(start, end)
    if err:
        return earnings.filed_rows(demo.RESULTS_FILED), True, err
    return df, False, None


def score(symbol: str, sample: bool, quarter=None) -> dict:
    if sample:
        res = filings.results_frame(demo.RESULTS_CMP.get(symbol, {}))
        est = {}
    else:
        res, _ = load_results(symbol)
        est = load_estimates(symbol)
    v = earnings.verdict(res, est)
    if quarter is not None and pd.notna(quarter) and v.get("quarter") and v["quarter"] != f"{quarter:%b %Y}":
        v["reasons"] = [f"NSE's comparison table doesn't have the {quarter:%b %Y} quarter yet; "
                        f"this verdict is for {v['quarter']}."] + v["reasons"]
        v["stale"] = True
    return v


LEVEL_ICON = {"STRONG": "🟢", "GOOD": "🟢", "MIXED": "🟡", "WEAK": "🟠", "POOR": "🔴", "NO DATA": "⚪"}


def alert_banner(table: pd.DataFrame, ideas: dict) -> None:
    """Shown above the tabs: your stocks that filed results in the last 3 days, with a verdict."""
    today = market.now_ist().date()
    df, err = load_filed(today - dt.timedelta(days=3), today)
    if err or df.empty:
        return
    mine = _stocks(table, ideas)
    df = df[df["Symbol"].isin(mine)]
    if df.empty:
        return
    parts = []
    for r in df.itertuples():
        v = score(r.Symbol, False, r.Quarter)
        parts.append(f"{LEVEL_ICON.get(v['level'], '')} **{r.Symbol}** {v['level']} ({r.Filed:%d %b %H:%M})")
    st.info("**Results out for your stocks:** " + " · ".join(parts) + "  ·  details in the Earnings tab.")


def render_feed(table: pd.DataFrame, ideas: dict) -> None:
    today = market.now_ist().date()
    c = st.columns([3, 2, 2])
    span = c[0].radio("Filed", ["Today", "Last 3 days", "Last 7 days", "Last 30 days"], index=1, horizontal=True,
                      key="rf_span", label_visibility="collapsed")
    days = {"Today": 0, "Last 3 days": 3, "Last 7 days": 7, "Last 30 days": 30}[span]
    only_mine = c[1].toggle("Only my stocks", key="rf_mine")
    score_all = c[2].toggle("Score every company", key="rf_all",
                            help="Your stocks are always scored. Scoring everyone fetches each company from NSE "
                                 "(up to 60, newest first), which takes a while in results season.")
    df, sample, err = _feed(today - dt.timedelta(days=days), today)
    if sample:
        st.warning(f"NSE didn't answer ({str(err)[:90]}…). Showing **sample data** so you can see the layout.")
    mine = _stocks(table, ideas)
    df = df.assign(Yours=df["Symbol"].map(lambda s: TAG.get(mine.get(s, ""), "")))
    if only_mine:
        df = df[df["Yours"] != ""]
    if df.empty:
        st.info("No results filed in this range" + (" by your stocks." if only_mine else "."))
        return
    to_score = [i for i in df.index if df.at[i, "Yours"] or sample] + \
        ([i for i in df.index if not df.at[i, "Yours"]][:60] if score_all else [])
    verdicts = {}
    prog = st.progress(0.0, text="Scoring results…") if len(to_score) > 3 else None
    for n, i in enumerate(to_score):
        verdicts[i] = score(df.at[i, "Symbol"], sample, df.at[i, "Quarter"])
        if prog:
            prog.progress((n + 1) / len(to_score), text=f"Scoring results… {df.at[i, 'Symbol']}")
    if prog:
        prog.empty()
    levels = [v["level"] for v in verdicts.values()]
    bar([("FILED", str(len(df)), "amb"), ("SCORED", str(len(verdicts)), ""),
         ("STRONG/GOOD", str(sum(x in ("STRONG", "GOOD") for x in levels)), "up"),
         ("MIXED", str(levels.count("MIXED")), "amb"),
         ("WEAK/POOR", str(sum(x in ("WEAK", "POOR") for x in levels)), "dn")])

    rows = []
    for i, r in df.iterrows():
        v = verdicts.get(i, {})
        rows.append({"Filed": r["Filed"], "Symbol": r["Symbol"], "Company": r["Company"], "Yours": r["Yours"],
                     "Verdict": (LEVEL_ICON.get(v.get("level"), "") + " " + v.get("level", "")).strip() or "–",
                     "Qtr": v.get("quarter", ""), "Revenue (₹ cr)": v.get("revenue"), "Rev YoY %": v.get("rev_yoy"),
                     "Profit (₹ cr)": v.get("profit"), "Profit YoY %": v.get("profit_yoy"),
                     "Profit QoQ %": v.get("profit_qoq"), "Margin %": v.get("margin"),
                     "Margin chg (pts)": v.get("margin_chg"), "EPS vs est %": v.get("eps_vs_est"),
                     "Filing": r["Link"] or None})
    out = pd.DataFrame(rows)
    pct = ["Rev YoY %", "Profit YoY %", "Profit QoQ %", "EPS vs est %", "Margin chg (pts)"]
    st.dataframe(out.style.format({"Filed": "{:%d %b %H:%M}", "Revenue (₹ cr)": "{:,.0f}", "Profit (₹ cr)": "{:,.0f}",
                                   "Margin %": "{:.1f}", **{k: "{:+.1f}" for k in pct}}, na_rep="–")
                 .map(color, subset=pct),
                 column_config={"Filing": st.column_config.LinkColumn("Filing", display_text="open")},
                 use_container_width=True, hide_index=True, height=min(38 + 35 * len(out), 560))

    for i in [i for i in to_score if df.at[i, "Yours"] or sample]:
        v, r = verdicts[i], df.loc[i]
        with st.expander(f"{LEVEL_ICON.get(v['level'], '')} {r['Symbol']} · {v['level']} · {v.get('quarter', '')}"):
            for reason in v["reasons"]:
                st.markdown(f"- {reason}")
    st.markdown("<div class='td-src'>Filings: NSE corporate financial results (falls back to corporate "
                "announcements). Numbers: NSE results comparison, ₹ crore. Verdict = one point each for revenue "
                "growth ≥10% YoY, profit growth ≥15% YoY, net margin up ≥1 pt, EPS beat ≥5% vs Yahoo consensus, "
                "minus one for each falling/missing; ≥2 STRONG, 1 GOOD, 0 MIXED, −1 WEAK, ≤−2 POOR. It reads "
                "the headline numbers only; one-offs, guidance and the conference call can change the story.</div>",
                unsafe_allow_html=True)


# ---------------------------------------------------------------- scorecard
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_filing_times(symbol: str) -> tuple[list, str]:
    try:
        times = earnings.fetch_filing_times(symbol)
        if times:
            return times, "NSE filing times"
    except FilingError:
        pass
    times = earnings.yahoo_earnings_dates(market.yahoo_symbol(symbol))
    return times, "Yahoo earnings dates" if times else "none found"


def render_scorecard(table: pd.DataFrame, ideas: dict) -> None:
    from .terminal import equity_list, yahoo_history

    mine = list(_stocks(table, ideas))
    eq, _ = equity_list()
    opts = sorted(set(eq["symbol"]) | set(mine))
    if "sc_pick" not in st.session_state:
        st.session_state.sc_pick = mine[:10]
    picked = st.multiselect("Stocks", opts, key="sc_pick", placeholder="Add stocks, e.g. TCS")
    if not picked:
        st.info("Pick some stocks to see how they moved after results.")
        return
    ys = {s: market.yahoo_symbol(s) for s in picked}
    hist, herr = yahoo_history(tuple(ys.values()), "5y")
    sample = not hist
    if sample:
        st.warning(f"Couldn't get price history ({herr or 'no data'}). Showing **sample data** so you can see "
                   "the layout.")
    cards, rows = {}, []
    for n, s in enumerate(picked):
        if sample:
            prices, times, src = demo.price_history(n + 1), demo.sample_result_times(), "sample"
        else:
            prices = hist.get(ys[s], pd.DataFrame())
            times, src = load_filing_times(s)
        df, summ = earnings.scorecard(prices, times)
        cards[s] = df
        if not summ:
            rows.append({"Stock": s, "Results": 0, "Dates from": src})
            continue
        rows.append({"Stock": s, "Results": summ["results"], "Rose after": f"{summ['up']}/{summ['results']}",
                     "Avg 1-day %": summ["avg_d1"], "Avg size of move %": summ["avg_abs_d1"],
                     "Best 1-day %": summ["best_d1"], "Worst 1-day %": summ["worst_d1"],
                     "Avg 5-day %": summ["avg_d5"], "Follow-through %": summ["follow_through"], "Dates from": src})
    out = pd.DataFrame(rows)
    pct = [c_ for c_ in ("Avg 1-day %", "Best 1-day %", "Worst 1-day %", "Avg 5-day %", "Follow-through %")
           if c_ in out]
    st.dataframe(out.style.format({k: "{:+.1f}" for k in pct} | {"Avg size of move %": "{:.1f}"}, na_rep="–")
                 .map(color, subset=pct), use_container_width=True, hide_index=True)
    st.caption("1-day: last close before the news could trade → close of the first session after it. 5-day: to the "
               "5th session. Avg size of move ignores direction: how much the stock usually swings on results. "
               "Follow-through: positive means the first day's move usually kept going over the week; negative "
               "means it usually reversed. Past reactions don't predict the next one.")

    one = st.selectbox("Quarter by quarter", [s for s in picked if not cards[s].empty] or picked, key="sc_one")
    df = cards.get(one, pd.DataFrame())
    if df.empty:
        st.info(f"No past results dates found for {one}.")
        return
    d = df.sort_values("filed").assign(label=lambda x: x["filed"].dt.strftime("%b %Y"))
    fig = go.Figure()
    fig.add_bar(x=d["label"], y=d["d1"], name="1-day %", marker_color=[GREEN if v > 0 else RED for v in d["d1"]])
    fig.add_scatter(x=d["label"], y=d["d5"], name="5-day %", mode="markers+lines",
                    line=dict(color=AMBER, width=1), marker=dict(size=8))
    fig.update_layout(height=300, legend=dict(orientation="h", y=1.1), yaxis_title="%")
    st.plotly_chart(fig, use_container_width=True)
    show = d[["filed", "reaction_day", "base", "gap", "d1", "d5", "d20"]].rename(columns={
        "filed": "Results filed", "reaction_day": "Reaction day", "base": "Close before", "gap": "Gap at open %",
        "d1": "1-day %", "d5": "5-day %", "d20": "20-day %"}).sort_values("Results filed", ascending=False)
    pc = ["Gap at open %", "1-day %", "5-day %", "20-day %"]
    st.dataframe(show.style.format({"Results filed": "{:%d %b %Y %H:%M}", "Reaction day": "{:%d %b %Y}",
                                    "Close before": "₹{:,.2f}", **{k: "{:+.1f}" for k in pc}}, na_rep="–")
                 .map(color, subset=pc), use_container_width=True, hide_index=True)
    st.markdown("<div class='td-src'>Results times: NSE financial-results filings (falls back to Yahoo earnings "
                "dates). Prices: Yahoo Finance daily closes, not adjusted for dividends.</div>",
                unsafe_allow_html=True)


def render(token: str | None, table: pd.DataFrame, ideas: dict) -> None:
    st.markdown("## Results out")
    render_feed(table, ideas)
    st.divider()
    st.markdown("## Results calendar")
    render_calendar(table, ideas)
    st.divider()
    st.markdown("## Earnings scorecard · how the price moved after past results")
    render_scorecard(table, ideas)
