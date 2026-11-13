"""Flows tab: FII/DII cash flows, F&O positioning by participant, and option chains."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import demo, flows, market
from .filings import FilingError
from .theme import AMBER, BLUE, GREEN, MUTED, RED, bar, color, updown
from .upstox import Upstox, UpstoxError


@st.cache_data(ttl=30 * 60, show_spinner="Reading FII/DII figures from NSE…")
def load_fii_dii() -> tuple[pd.DataFrame, str | None]:
    try:
        return flows.fetch_fii_dii(), None
    except FilingError as e:
        return flows.fii_dii_frame([]), str(e)


@st.cache_data(ttl=6 * 3600, show_spinner="Reading participant open interest from NSE…")
def load_oi(days: int) -> tuple[pd.DataFrame, list[str]]:
    return flows.fetch_participant_oi(days, market.now_ist().date())


@st.cache_data(ttl=3600, show_spinner=False)
def load_expiries(token: str | None, symbol: str, key: str | None) -> tuple[list[str], str]:
    if token and key:
        try:
            return Upstox(token).option_expiries(key), "Upstox"
        except UpstoxError:
            pass
    try:
        return flows.nse_expiries(symbol), "NSE"
    except FilingError as e:
        return [], str(e)


@st.cache_data(ttl=60, show_spinner="Loading option chain…")
def load_chain(token: str | None, symbol: str, key: str | None, expiry: str, src: str):
    if src == "Upstox" and token and key:
        try:
            df, spot = flows.chain_from_upstox(Upstox(token).option_chain(key, expiry))
            return df, spot, "Upstox (live)", None
        except UpstoxError as e:
            err = str(e)
    else:
        err = None
    try:
        df, spot = flows.nse_chain(symbol, expiry)
        return df, spot, "NSE (delayed ~3 min)", None
    except FilingError as e:
        return pd.DataFrame(), None, "", err or str(e)


def _cash() -> None:
    today, err = load_fii_dii()
    if err:
        st.warning(f"NSE didn't answer ({str(err)[:90]}…). Showing **sample data** so you can see the layout.")
        today = flows.fii_dii_frame(demo.FII_DII)
        hist = today
    else:
        hist = flows.remember(today)
    if today.empty:
        st.info("NSE hasn't published today's FII/DII figures yet (usually out by 6–7 PM).")
        return
    d = today["Date"].max()
    row = {r.Who: r for r in today.itertuples()}
    cells = [("DATE", f"{d:%d %b %Y}", "amb")]
    for who in ("FII", "DII"):
        if who in row:
            n = row[who].Net
            cells.append((f"{who} NET", f"₹{n:+,.0f} cr", updown(n)))
    bar(cells)
    m = st.columns(4)
    for i, who in enumerate(("FII", "DII")):
        if who in row:
            m[i * 2].metric(f"{who} bought", f"₹{row[who].Buy:,.0f} cr")
            m[i * 2 + 1].metric(f"{who} sold", f"₹{row[who].Sell:,.0f} cr")
    if hist["Date"].nunique() > 1:
        s5, s20 = flows.flow_summary(hist, 5), flows.flow_summary(hist, 20)
        bar([(f"FII {s5['FII_days']}D", f"₹{s5['FII'] or 0:+,.0f} cr", updown(s5["FII"])),
             (f"DII {s5['DII_days']}D", f"₹{s5['DII'] or 0:+,.0f} cr", updown(s5["DII"])),
             (f"FII {s20['FII_days']}D", f"₹{s20['FII'] or 0:+,.0f} cr", updown(s20["FII"])),
             (f"DII {s20['DII_days']}D", f"₹{s20['DII'] or 0:+,.0f} cr", updown(s20["DII"]))])
        piv = hist.pivot_table(index="Date", columns="Who", values="Net").tail(30)
        fig = go.Figure()
        for who, c in (("FII", AMBER), ("DII", BLUE)):
            if who in piv:
                fig.add_bar(x=piv.index, y=piv[who], name=who, marker_color=c)
        fig.update_layout(barmode="group", height=280, yaxis_title="Net ₹ cr", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("History builds up from today: NSE only publishes the latest day, so the site keeps each day it "
                   "sees. To keep a longer record across restarts, the morning research job can append to "
                   "data/fii_dii.csv (columns Date, Who, Buy, Sell, Net).")
    st.markdown("<div class='td-src'>NSE provisional FII/FPI and DII cash-market figures, ₹ crore. Final NSDL FPI "
                "numbers can differ.</div>", unsafe_allow_html=True)


def _participants() -> None:
    days = st.radio("Days", [5, 10, 20], index=1, horizontal=True, key="fl_days", label_visibility="collapsed")
    df, errs = load_oi(days)
    if df.empty:
        st.warning("Couldn't read NSE's participant OI archive" + (f" ({errs[0][:90]}…)" if errs else "") +
                   ". Showing **sample data** so you can see the layout.")
        df = flows.positioning(flows.parse_participant_oi(demo.PARTICIPANT_OI)).assign(
            Date=pd.Timestamp(market.now_ist().date()))
    last = df[df["Date"] == df["Date"].max()]
    fii = last[last["Participant"].str.upper() == "FII"]
    if not fii.empty:
        f = fii.iloc[0]
        bar([("AS OF", f"{f['Date']:%d %b}", "amb"),
             ("FII INDEX FUT LONG %", f"{f['Index fut long %']:.0f}%", updown(f["Index fut long %"] - 50)),
             ("FII INDEX FUT NET", f"{f['Index fut net']:+,.0f}", updown(f["Index fut net"])),
             ("FII INDEX CALLS NET", f"{f['Index calls net']:+,.0f}", updown(f["Index calls net"])),
             ("FII INDEX PUTS NET", f"{f['Index puts net']:+,.0f}", updown(-f["Index puts net"]))])
    show = last.drop(columns=["Date"])
    st.dataframe(show.style.format({c: "{:+,.0f}" for c in show.columns if "net" in c} |
                                   {"Index fut long": "{:,.0f}", "Index fut short": "{:,.0f}",
                                    "Index fut long %": "{:.1f}%"}, na_rep="–")
                 .map(color, subset=[c for c in show.columns if "net" in c]), use_container_width=True, hide_index=True)
    if df["Date"].nunique() > 1:
        trend = df[df["Participant"].str.upper().isin(["FII", "CLIENT", "PRO", "DII"])]
        fig = go.Figure()
        for p, c in (("FII", AMBER), ("Client", GREEN), ("Pro", BLUE), ("DII", MUTED)):
            t = trend[trend["Participant"].str.lower() == p.lower()].sort_values("Date")
            fig.add_scatter(x=t["Date"], y=t["Index fut long %"], name=p, line=dict(color=c))
        fig.add_hline(y=50, line_dash="dot", line_color=MUTED)
        fig.update_layout(height=280, yaxis_title="Index futures long %", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Contracts, not rupees. FII index futures long % below ~30% has often marked heavy bearish "
               "positioning (and sometimes a short-covering bounce); above ~60% is bullish. Calls net long and puts "
               "net short both lean bullish. Source: NSE participant-wise OI, published after market close.")


def _chain(token: str | None, table: pd.DataFrame) -> None:
    from .terminal import keys_for

    held = [s for s in dict.fromkeys(table["symbol"].dropna())] if not table.empty else []
    opts = list(flows.INDEX_UNDERLYINGS) + [s for s in held if s not in flows.INDEX_UNDERLYINGS]
    c = st.columns([2, 2, 3])
    sym = c[0].selectbox("Underlying", opts, key="oc_sym",
                         help="Indices plus your holdings. Stocks without F&O have no chain.")
    other = c[0].text_input("Or type an F&O stock", key="oc_other", placeholder="e.g. TATAMOTORS").strip().upper()
    sym = other or sym
    key = flows.INDEX_UNDERLYINGS.get(sym) or (keys_for([sym], token).get(sym) if token else None)
    expiries, src = load_expiries(token, sym, key)
    if not expiries and src in ("Upstox", "NSE"):
        st.info(f"{sym} has no options listed.")
        return
    if not expiries:
        st.warning(f"Couldn't load expiries for {sym} ({src[:90]}…). Showing a **sample chain** so you can see the "
                   "layout.")
        chain, spot = flows.chain_from_upstox(demo.option_chain())
        where = "sample"
    else:
        exp = c[1].selectbox("Expiry", expiries, key="oc_exp")
        chain, spot, where, err = load_chain(token, sym, key, exp, src)
        if err:
            st.warning(f"Option chain unavailable: {err[:120]}")
            return
    s = flows.chain_stats(chain, spot)
    if not s:
        st.info("No option data for this expiry.")
        return
    bar([("SPOT", _f2(s.get("spot")), "amb"), ("PCR", f"{s['pcr']:.2f}" if s.get("pcr") else "–",
                                              updown((s.get("pcr") or 1) - 1)),
         ("MAX PAIN", _f2(s.get("max_pain")), ""), ("SUPPORT (PUT OI)", _f2(s.get("support")), "up"),
         ("RESISTANCE (CALL OI)", _f2(s.get("resistance")), "dn"),
         ("STRADDLE", f"{_f2(s.get('straddle'))} (±{s.get('implied_move_pct', 0):.1f}%)", "amb")])
    near = st.slider("Strikes either side of spot", 5, 40, 15, key="oc_n")
    if spot:
        i = (chain["strike"] - spot).abs().idxmin()
        chain = chain.iloc[max(0, i - near): i + near + 1]
    fig = go.Figure()
    fig.add_bar(x=chain["strike"], y=chain["call_oi"], name="Call OI", marker_color=RED)
    fig.add_bar(x=chain["strike"], y=chain["put_oi"], name="Put OI", marker_color=GREEN)
    fig.add_scatter(x=chain["strike"], y=chain["call_chg_oi"], name="Call OI change", mode="lines",
                    line=dict(color=RED, dash="dot"))
    fig.add_scatter(x=chain["strike"], y=chain["put_chg_oi"], name="Put OI change", mode="lines",
                    line=dict(color=GREEN, dash="dot"))
    if spot:
        fig.add_vline(x=spot, line_color=AMBER, annotation_text="spot")
    fig.update_layout(barmode="group", height=340, legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, use_container_width=True)
    show = chain.rename(columns={"strike": "Strike", "call_oi": "C OI", "call_chg_oi": "C ΔOI", "call_vol": "C Vol",
                                 "call_iv": "C IV", "call_ltp": "C LTP", "put_ltp": "P LTP", "put_iv": "P IV",
                                 "put_vol": "P Vol", "put_chg_oi": "P ΔOI", "put_oi": "P OI"})
    big = {k: "{:,.0f}" for k in ("C OI", "C Vol", "P Vol", "P OI")}
    st.dataframe(show.style.format(big | {"C ΔOI": "{:+,.0f}", "P ΔOI": "{:+,.0f}", "C IV": "{:.1f}",
                                          "P IV": "{:.1f}", "C LTP": "{:,.2f}", "P LTP": "{:,.2f}",
                                          "Strike": "{:,.0f}"}, na_rep="–")
                 .map(color, subset=["C ΔOI", "P ΔOI"])
                 .apply(lambda r: ["background-color: #1f1606" if spot and abs(r["Strike"] - spot) <=
                                   (chain["strike"].diff().median() or 1) / 2 else "" for _ in r], axis=1),
                 use_container_width=True, hide_index=True, height=min(38 + 35 * len(show), 600))
    st.caption(f"Source: {where}. PCR = put OI ÷ call OI (above 1 leans bullish, as writers sell puts they expect "
               "to expire). Max pain = the expiry price where option buyers collectively lose most. Straddle = ATM "
               "call + put, the move the market is pricing in by expiry. Contracts in Upstox OI are in shares on "
               "some underlyings.")


def _f2(v) -> str:
    return "–" if v is None else f"{v:,.2f}"


def render(token: str | None, table: pd.DataFrame) -> None:
    st.markdown("## FII / DII cash flows")
    _cash()
    st.divider()
    st.markdown("## F&O positioning by participant")
    _participants()
    st.divider()
    st.markdown("## Option chain")
    _chain(token, table)
