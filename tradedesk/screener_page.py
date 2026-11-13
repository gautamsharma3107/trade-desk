"""Screener tab: filter a universe of stocks by growth, valuation, promoter buying and results quality."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import demo, market, screen
from .filings import FilingError
from .theme import bar, color
from .earnings_page import TAG, _stocks

MAX_STOCKS = 250
FILTER_COLS = ["Sales YoY %", "Profit YoY %", "Profit growth qtrs (of 4)", "OPM chg (pts)", "P/E", "P/B", "ROE %",
               "ROCE %", "Div yield %", "Mcap (₹ cr)", "Promoter %", "Promoter chg QoQ", "Promoter chg 1Y",
               "FII chg QoQ", "DII chg QoQ", "Quality score"]


@st.cache_data(ttl=24 * 3600, show_spinner="Reading index members from NSE…")
def load_index(index: str) -> tuple[list[dict], str | None]:
    try:
        return screen.index_members(index), None
    except FilingError as e:
        return [], str(e)


def _universe(table: pd.DataFrame, ideas: dict) -> tuple[list[str], dict[str, str]]:
    c = st.columns([3, 3])
    kind = c[0].radio("Universe", ["Index", "My stocks", "Typed list"], horizontal=True, key="sr_kind")
    sectors: dict[str, str] = {}
    if kind == "Index":
        idx = c[1].selectbox("Index", screen.INDICES, key="sr_idx")
        if idx == "NIFTY 50":
            rows = market.nifty50()
        else:
            rows, err = load_index(idx)
            if err:
                st.warning(f"NSE didn't give the {idx} list ({err[:80]}…); using the bundled Nifty 50 instead.")
                rows = market.nifty50()
        sectors = {r["symbol"]: r.get("sector", "") for r in rows}
        return [r["symbol"] for r in rows], sectors
    if kind == "My stocks":
        return list(_stocks(table, ideas)), sectors
    typed = c[1].text_area("Symbols", "RELIANCE, TCS, HDFCBANK, INFY, ITC", key="sr_typed", height=70)
    return [s.strip().upper() for s in typed.replace("\n", ",").split(",") if s.strip()], sectors


def _filters() -> dict:
    preset = st.selectbox("Preset", list(screen.PRESETS), index=1, key="sr_preset")
    rules = dict(screen.PRESETS[preset])
    with st.expander("Edit filters", expanded=False):
        st.caption("Leave a box empty for no limit. A stock missing a number you filter on is left out.")
        edited = {}
        for i, col in enumerate(FILTER_COLS):
            if i % 4 == 0:
                cols = st.columns(4)
            lo, hi = rules.get(col, (None, None))
            box = cols[i % 4]
            box.markdown(f"**{col}**")
            a, b = box.columns(2)
            lo = a.number_input("min", value=lo, key=f"sr_lo_{preset}_{col}", label_visibility="collapsed",
                                placeholder="min")
            hi = b.number_input("max", value=hi, key=f"sr_hi_{preset}_{col}", label_visibility="collapsed",
                                placeholder="max")
            if lo is not None or hi is not None:
                edited[col] = (lo, hi)
        rules = edited
    return rules


def render(table: pd.DataFrame, ideas: dict) -> None:
    from .terminal import screener

    symbols, sectors = _universe(table, ideas)
    rules = _filters()
    if len(symbols) > MAX_STOCKS:
        st.caption(f"Screening the first {MAX_STOCKS} of {len(symbols)} stocks to keep it quick.")
        symbols = symbols[:MAX_STOCKS]
    if st.button(f"Run screen on {len(symbols)} stocks", type="primary", key="sr_run"):
        rows, fails = [], []
        prog = st.progress(0.0, text="Reading company pages…")
        for n, s in enumerate(symbols):
            sc, err = screener(s)
            if err or not sc:
                fails.append(s)
            else:
                rows.append({"Symbol": s, **screen.metrics(sc)})
            prog.progress((n + 1) / len(symbols), text=f"Reading company pages… {s}")
        prog.empty()
        st.session_state.sr_rows, st.session_state.sr_fails = rows, fails
    rows = st.session_state.get("sr_rows")
    if rows is None:
        st.info("Pick a universe and a preset, then **Run screen**. The first run reads one Screener.in page per "
                "stock (about a second each); results are kept for 6 hours.")
        return
    fails = st.session_state.get("sr_fails", [])
    sample = not rows and fails
    if sample:
        st.warning("Screener.in didn't answer for any stock. Showing **sample data** so you can see the layout.")
        rows = demo.screen_rows(fails)
        for r in rows:
            r["Quality score"] = screen.quality_score(r)
    df = pd.DataFrame(rows)
    mine = _stocks(table, ideas)
    df.insert(1, "Yours", df["Symbol"].map(lambda s: TAG.get(mine.get(s, ""), "")))
    if sectors:
        df.insert(2, "Sector", df["Symbol"].map(sectors))
    hits = screen.apply_filters(df, rules).sort_values("Quality score", ascending=False)
    bar([("SCREENED", str(len(df)), "amb"), ("PASSED", str(len(hits)), "up" if len(hits) else ""),
         ("NO DATA", str(len(fails)) if not sample else "–", "dn" if fails and not sample else "")])
    if hits.empty:
        st.info("Nothing passes these filters. Loosen one in **Edit filters**.")
    pct = [c for c in df.columns if c.endswith("%") and c not in ("Promoter %",)] + \
        ["OPM chg (pts)", "Promoter chg QoQ", "Promoter chg 1Y", "FII chg QoQ", "DII chg QoQ"]
    fmt = {c: "{:+.1f}" for c in pct if c in df} | {"Mcap (₹ cr)": "{:,.0f}", "Price": "₹{:,.1f}", "P/E": "{:.1f}",
                                                   "P/B": "{:.1f}", "ROE %": "{:.1f}", "ROCE %": "{:.1f}",
                                                   "Div yield %": "{:.2f}", "Promoter %": "{:.1f}",
                                                   "Profit growth qtrs (of 4)": "{:.0f}", "Quality score": "{:.0f}"}
    show = hits if not hits.empty else df.iloc[0:0]
    st.dataframe(show.style.format({k: v for k, v in fmt.items() if k in show}, na_rep="–")
                 .map(color, subset=[c for c in ("Sales YoY %", "Profit YoY %", "OPM chg (pts)", "Promoter chg QoQ",
                                                 "Promoter chg 1Y", "FII chg QoQ", "DII chg QoQ") if c in show]),
                 use_container_width=True, hide_index=True, height=min(38 + 35 * len(show), 640))
    if not show.empty:
        st.download_button("Download CSV", show.to_csv(index=False).encode(), "screen.csv", "text/csv", key="sr_csv")
    with st.expander(f"All {len(df)} screened stocks"):
        st.dataframe(df.style.format({k: v for k, v in fmt.items() if k in df}, na_rep="–"),
                     use_container_width=True, hide_index=True)
    if fails and not sample:
        st.caption("No data for: " + ", ".join(fails))
    st.markdown("<div class='td-src'>Fundamentals: Screener.in company pages (consolidated where available), from "
                "exchange filings. YoY = latest quarter vs the same quarter a year earlier. Profit growth qtrs = how "
                "many of the last 4 quarters grew profit year on year. Promoter changes are percentage points. "
                "Quality score (0–10): profit-growth quarters (up to 4), ROCE ≥12% (+1) or ≥18% (+2), sales growth "
                "≥10%, margins steady or better, promoters not selling over a year, P/E under 40.</div>",
                unsafe_allow_html=True)
