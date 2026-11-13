"""News tab: exchange announcements, bulk and block deals, and insider trades for your stocks."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from . import demo, market, news
from .filings import FilingError
from .theme import bar, color
from .earnings_page import TAG, _stocks


@st.cache_data(ttl=15 * 60, show_spinner="Reading NSE announcements…")
def load_announcements(start: dt.date, end: dt.date, symbol: str | None) -> tuple[pd.DataFrame, str | None]:
    try:
        return news.fetch_announcements(start, end, symbol), None
    except FilingError as e:
        return news.announcements_frame([]), str(e)


@st.cache_data(ttl=30 * 60, show_spinner="Reading bulk and block deals…")
def load_deals(start: dt.date, end: dt.date) -> tuple[pd.DataFrame, list[str]]:
    return news.fetch_deals(start, end)


@st.cache_data(ttl=30 * 60, show_spinner="Reading insider trades…")
def load_insider(start: dt.date, end: dt.date, symbol: str | None) -> tuple[pd.DataFrame, str | None]:
    try:
        return news.fetch_insider(start, end, symbol), None
    except FilingError as e:
        return news.insider_frame([]), str(e)


def _sample_note(err: str) -> None:
    st.warning(f"NSE didn't answer ({str(err)[:90]}…). Showing **sample data** so you can see the layout.")


def render(table: pd.DataFrame, ideas: dict) -> None:
    from .terminal import equity_list

    today = market.now_ist().date()
    mine = _stocks(table, ideas)
    c = st.columns([2, 3, 2])
    scope = c[0].radio("Whose news", ["My stocks", "All companies", "One stock"], horizontal=True, key="nw_scope",
                       label_visibility="collapsed")
    days = c[1].radio("Days", [1, 3, 7, 30, 90], index=2, horizontal=True, key="nw_days",
                      format_func=lambda d: "Today" if d == 1 else f"{d} days", label_visibility="collapsed")
    one = None
    if scope == "One stock":
        eq, _ = equity_list()
        opts = sorted(set(eq["symbol"]) | set(mine))
        default = next(iter(mine), "RELIANCE")
        one = c[2].selectbox("Stock", opts, index=opts.index(default) if default in opts else 0, key="nw_one")
    elif scope == "All companies" and days > 7:
        c[2].caption("All companies is limited to 7 days of announcements (it's thousands of filings).")
    start = today - dt.timedelta(days=days - 1)

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        if scope == "My stocks":
            df = df[df["Symbol"].isin(mine)]
        elif scope == "One stock":
            df = df[df["Symbol"] == one]
        return df.assign(Yours=df["Symbol"].map(lambda s: TAG.get(mine.get(s, ""), "")))

    t_ann, t_deals, t_ins = st.tabs(["Announcements", "Bulk & block deals", "Insider trades"])

    with t_ann:
        a_start = max(start, today - dt.timedelta(days=6)) if scope == "All companies" else start
        ann, err = load_announcements(a_start, today, one)
        if err:
            _sample_note(err)
            ann = news.announcements_frame(demo.ANNOUNCEMENTS)
        ann = keep(ann)
        cats = sorted(ann["Category"].unique()) if not ann.empty else []
        f = st.columns([1, 3])
        important = f[0].toggle("Important only", value=scope == "All companies", key="nw_imp",
                                help="Results, orders, acquisitions, buybacks, fund raising, ratings, dividends, "
                                     "legal.")
        pick = f[1].multiselect("Categories", cats, key="nw_cats", placeholder="All categories")
        if important:
            ann = ann[ann["Important"]]
        if pick:
            ann = ann[ann["Category"].isin(pick)]
        bar([("FILINGS", str(len(ann)), "amb"), ("COMPANIES", str(ann["Symbol"].nunique()) if len(ann) else "0", ""),
             ("RESULTS", str(int((ann["Category"] == "Results").sum())) if len(ann) else "0", ""),
             ("ORDERS", str(int((ann["Category"] == "Order / contract").sum())) if len(ann) else "0", "")])
        if ann.empty:
            st.info("No announcements match.")
        else:
            st.dataframe(ann[["Time", "Symbol", "Yours", "Category", "Subject", "Details", "Link"]]
                         .style.format({"Time": "{:%d %b %H:%M}"}),
                         column_config={"Link": st.column_config.LinkColumn("PDF", display_text="open"),
                                        "Details": st.column_config.TextColumn(width="large")},
                         use_container_width=True, hide_index=True, height=min(38 + 35 * len(ann), 640))

    with t_deals:
        deals, errs = load_deals(start, today)
        if errs and deals.empty:
            _sample_note(errs[0])
            deals = news.deals_frame(demo.BULK_DEALS, "Bulk")
        deals = keep(deals)
        if deals.empty:
            st.info("No bulk or block deals" + (" in your stocks" if scope == "My stocks" else "") +
                    " in this period. Switch to All companies to see the whole market.")
        else:
            buys = deals[deals["Side"] == "BUY"]["Value (₹ cr)"].sum()
            sells = deals[deals["Side"] == "SELL"]["Value (₹ cr)"].sum()
            bar([("DEALS", str(len(deals)), "amb"), ("BOUGHT", f"₹{buys:,.0f} cr", "up"),
                 ("SOLD", f"₹{sells:,.0f} cr", "dn")])
            st.dataframe(deals.style.format({"Date": "{:%d %b}", "Qty": "{:,.0f}", "Price": "₹{:,.2f}",
                                             "Value (₹ cr)": "{:,.1f}"}, na_rep="–")
                         .map(lambda v: color(1 if v == "BUY" else -1 if v == "SELL" else 0), subset=["Side"]),
                         use_container_width=True, hide_index=True, height=min(38 + 35 * len(deals), 560))
        st.caption("Bulk deal: one client trading over 0.5% of a company's shares in a day. Block deal: a single "
                   "trade of ₹10 crore or more in the special block window. A named fund buying is often watched "
                   "as a signal, but funds also trade for their own reasons.")

    with t_ins:
        ins, err = load_insider(start, today, one)
        if err:
            _sample_note(err)
            ins = news.insider_frame(demo.INSIDER)
        ins = keep(ins)
        promoters = st.toggle("Promoters only", key="nw_prom")
        net = news.insider_net(ins, promoters)
        if not net.empty:
            st.markdown("#### Net open-market buying by insiders")
            st.dataframe(net.style.format({"Net buy (₹ cr)": "{:+,.2f}"}).map(color, subset=["Net buy (₹ cr)"]),
                         use_container_width=True, hide_index=True, height=min(38 + 35 * len(net), 360))
        if ins.empty:
            st.info("No insider trades disclosed in this period" + (" for your stocks." if scope == "My stocks" else "."))
        else:
            show = ins[ins["Category"].str.lower().str.contains("promoter", na=False)] if promoters else ins
            st.markdown("#### All disclosures")
            st.dataframe(show.drop(columns=["Signed value (₹ cr)"]).style.format(
                {"Disclosed": "{:%d %b %Y}", "Shares": "{:,.0f}", "Value (₹ cr)": "{:,.2f}",
                 "Holding before %": "{:.2f}", "Holding after %": "{:.2f}"}, na_rep="–"),
                use_container_width=True, hide_index=True, height=min(38 + 35 * len(show), 520))
        st.caption("Insider trades are disclosures under SEBI's insider-trading rules, filed within two trading days. "
                   "Net buying counts open-market trades only (not gifts, ESOPs or pledges). Promoters buying with "
                   "their own money is the classic positive signal.")
    st.markdown(f"<div class='td-src'>NSE corporate announcements, bulk/block deals and PIT disclosures · fetched "
                f"{market.now_ist():%d %b %H:%M} IST · your stocks = holdings, ideas, data/watchlist.txt and the "
                f"Markets custom list ({len(mine)} stocks)</div>", unsafe_allow_html=True)
