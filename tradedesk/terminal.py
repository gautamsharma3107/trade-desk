"""Terminal pages: market strip, stock list, company view and year-to-date P&L.

Each `render_*` function draws one tab. app.py passes in the Upstox token (or
None in sample mode), the holdings table and the daily ideas.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from . import demo, filings, market, pnl
from .market import SourceError
from .theme import AMBER, GREEN, MUTED, RED, bar, color, updown
from .upstox import Upstox, UpstoxError

INR = "₹{:,.0f}".format


def _fmt(v, spec="{:,.2f}", dash="–"):
    try:
        return dash if v is None or v != v else spec.format(v)
    except (TypeError, ValueError):
        return dash


def _cr(v):
    """Rupees to a short crore string."""
    if v is None or v != v:
        return "–"
    cr = v / 1e7
    return f"₹{cr / 1e5:,.2f} L Cr" if cr >= 1e5 else f"₹{cr:,.0f} Cr"


# ---------------------------------------------------------------- cached loaders
@st.cache_data(ttl=12 * 3600, show_spinner=False)
def equity_list() -> tuple[pd.DataFrame, str]:
    """All NSE equities (symbol, name, ISIN, Upstox key). Falls back to the bundled Nifty 50 list."""
    try:
        return market.nse_equity_list(), "NSE equity list"
    except SourceError as e:
        df = pd.DataFrame(market.nifty50())[["symbol", "name"]]
        df["isin"], df["instrument_key"] = None, None
        return df, f"bundled Nifty 50 list ({e})"


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def resolve_keys(token: str, symbols: tuple[str, ...]) -> dict[str, str]:
    """Upstox instrument keys for symbols the NSE list didn't give us (needs login)."""
    out, u = {}, Upstox(token)
    for s in symbols:
        try:
            for r in u.search_equity(s, records=5):
                if r.get("trading_symbol") == s:
                    out[s] = r["instrument_key"]
                    break
        except UpstoxError:
            break
    return out


@st.cache_data(ttl=15 * 60, show_spinner="Fetching prices…")
def yahoo_history(symbols: tuple[str, ...], period: str = "1y") -> tuple[dict, str | None]:
    try:
        return market.yahoo_history(list(symbols), period), None
    except SourceError as e:
        return {}, str(e)


@st.cache_data(ttl=30, show_spinner=False)
def live_quotes(token: str, keys: tuple[str, ...]) -> tuple[dict, str | None]:
    try:
        return Upstox(token).quotes(list(keys)), None
    except UpstoxError as e:
        return {}, str(e)


@st.cache_data(ttl=6 * 3600, show_spinner="Reading company data…")
def screener(symbol: str) -> tuple[dict, str | None]:
    try:
        return market.screener_company(symbol), None
    except Exception as e:  # network, parsing
        return {}, str(e)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def yahoo_profile(ysym: str) -> tuple[dict, str | None]:
    try:
        return market.yahoo_profile(ysym), None
    except Exception as e:
        return {}, str(e)


@st.cache_data(ttl=6 * 3600, show_spinner="Reading NSE filings…")
def nse_filings(symbol: str) -> tuple[dict, list[str]]:
    """Shareholding, results, annual reports and BRSR filings from NSE. Each part fails on its own."""
    c, out, errs = filings.NSEClient(), {}, []
    for key, fn in (("shareholding", c.shareholding), ("results", c.results),
                    ("annual_reports", c.annual_reports), ("brsr", c.brsr)):
        try:
            out[key] = fn(symbol)
        except filings.FilingError as e:
            errs.append(f"{key}: {e}")
            if "unreachable" in str(e):
                break
    return out, errs


def keys_for(symbols: list[str], token: str | None) -> dict[str, str]:
    eq, _ = equity_list()
    known = {r.symbol: r.instrument_key for r in eq.itertuples() if r.instrument_key}
    missing = tuple(s for s in symbols if s not in known)
    if missing and token:
        known.update(resolve_keys(token, missing))
    return {s: known[s] for s in symbols if s in known}


# ---------------------------------------------------------------- header strip
def header(token: str | None) -> None:
    now = market.now_ist()
    status = market.market_status(now)
    cells = [("IST", f"{now:%d %b %Y %H:%M}", "amb"),
             ("NSE", status, "up" if status == "OPEN" else "dn" if status == "CLOSED" else "amb")]
    got = {}
    if token:
        q, _ = live_quotes(token, tuple(k for _, k, _ in market.INDICES))
        for label, key, _ in market.INDICES:
            v = q.get(key)
            if v and v.get("last_price"):
                last, chg = float(v["last_price"]), float(v.get("net_change") or 0)
                prev = last - chg
                got[label] = (last, (chg / prev * 100) if prev else 0)
    need = [(lbl, y) for lbl, _, y in market.INDICES if lbl not in got] + list(market.GLOBAL)
    hist, _ = yahoo_history(tuple(y for _, y in need), "5d")
    for lbl, y in need:
        if y in hist:
            s = market.stats_from_history(hist[y])
            if s:
                got[lbl] = (s["ltp"], s["change_pct"])
    for lbl in [i[0] for i in market.INDICES] + [g[0] for g in market.GLOBAL]:
        if lbl in got:
            last, pct = got[lbl]
            cells.append((lbl, f"{last:,.2f} {pct:+.2f}%", updown(pct)))
    bar(cells)


# ---------------------------------------------------------------- stock list
def _watch_universe(choice: str, table: pd.DataFrame, ideas: dict) -> pd.DataFrame:
    n50 = pd.DataFrame(market.nifty50())
    sectors = dict(zip(n50["symbol"], n50["sector"]))
    if choice == "Nifty 50":
        df = n50
    elif choice == "My holdings":
        syms = list(dict.fromkeys(table["symbol"].dropna())) if not table.empty else []
        df = pd.DataFrame({"symbol": syms})
    elif choice == "Daily ideas":
        syms = [i["symbol"] for i in ideas.get("buy_ideas", [])] + [a["symbol"] for a in ideas.get("avoid", [])] + \
            list(ideas.get("watch_today", []))
        df = pd.DataFrame({"symbol": list(dict.fromkeys(syms))})
    else:
        df = pd.DataFrame({"symbol": st.session_state.get("custom_watch", [])})
    eq, _ = equity_list()
    names = dict(zip(eq["symbol"], eq["name"]))
    df = df.copy()
    df["name"] = df["symbol"].map(lambda s: names.get(s) or dict(zip(n50["symbol"], n50["name"])).get(s, ""))
    df["sector"] = df["symbol"].map(lambda s: sectors.get(s, "Other"))
    return df[["symbol", "name", "sector"]]


def quote_table(universe: pd.DataFrame, token: str | None) -> tuple[pd.DataFrame, list[str]]:
    syms = list(universe["symbol"])
    notes = []
    ys = {s: market.yahoo_symbol(s) for s in syms}
    hist, err = yahoo_history(tuple(ys.values()), "1y")
    if err:
        notes.append(f"Yahoo Finance unavailable: {err}")
    rows = []
    for r in universe.itertuples():
        s = market.stats_from_history(hist[ys[r.symbol]]) if ys[r.symbol] in hist else {}
        rows.append({"Symbol": r.symbol, "Name": r.name, "Sector": r.sector, **s, "src": "Yahoo (delayed)" if s else ""})
    df = pd.DataFrame(rows)
    if token and not df.empty:
        keys = keys_for(syms, token)
        q, qerr = live_quotes(token, tuple(keys.values()))
        if qerr:
            notes.append(f"Upstox quotes unavailable: {qerr}")
        for i, r in df.iterrows():
            v = q.get(keys.get(r["Symbol"], ""))
            if not v or not v.get("last_price"):
                continue
            last, chg = float(v["last_price"]), float(v.get("net_change") or 0)
            o = v.get("ohlc") or {}
            df.loc[i, ["ltp", "change", "prev_close"]] = [last, chg, last - chg]
            df.loc[i, "change_pct"] = chg / (last - chg) * 100 if last - chg else 0
            df.loc[i, ["open", "high", "low"]] = [o.get("open"), o.get("high"), o.get("low")]
            df.loc[i, "volume"] = v.get("volume")
            if pd.notna(df.loc[i].get("high_52w")):
                df.loc[i, "from_high_pct"] = (last / max(df.loc[i, "high_52w"], last) - 1) * 100
            df.loc[i, "src"] = "Upstox (live)"
    return df, notes


def render_markets(token: str | None, table: pd.DataFrame, ideas: dict) -> None:
    eq, eq_src = equity_list()
    top = st.columns([3, 2])
    choice = top[0].radio("List", ["Nifty 50", "My holdings", "Daily ideas", "Custom"], horizontal=True,
                          label_visibility="collapsed", key="mk_list")
    if choice == "Custom":
        qp = st.query_params.get("wl")
        if "custom_watch" not in st.session_state:
            st.session_state.custom_watch = [s for s in (qp or "").split(",") if s] or ["RELIANCE", "TCS", "HDFCBANK"]
        opts = sorted(set(eq["symbol"]) | set(st.session_state.custom_watch))
        picked = top[1].multiselect("Add stocks", opts, default=st.session_state.custom_watch,
                                    placeholder="Type a symbol, e.g. TATAPOWER")
        st.session_state.custom_watch = picked
        st.query_params["wl"] = ",".join(picked)
        top[1].caption("Bookmark this page to keep the list.")
    universe = _watch_universe(choice, table, ideas)
    if universe.empty:
        st.info("Nothing in this list yet.")
        return
    df, notes = quote_table(universe, token)
    for n in notes:
        st.caption(n)
    if df.empty or "ltp" not in df:
        st.warning("No prices came back from any source. Try again in a minute.")
        return

    have = df.dropna(subset=["ltp"])
    up, down = int((have["change_pct"] > 0).sum()), int((have["change_pct"] < 0).sum())
    bar([("STOCKS", str(len(have)), "amb"), ("ADVANCES", str(up), "up"), ("DECLINES", str(down), "dn"),
         ("AVG CHG", f"{have['change_pct'].mean():+.2f}%", updown(have["change_pct"].mean())),
         ("NEAR 52W HIGH (<3%)", str(int((have["from_high_pct"] > -3).sum())), "amb")])

    left, right = st.columns([3, 1])
    with left:
        show = df.rename(columns={"ltp": "LTP", "change": "Chg", "change_pct": "Chg %", "open": "Open", "high": "High",
                                  "low": "Low", "prev_close": "Prev", "volume": "Volume", "high_52w": "52W H",
                                  "low_52w": "52W L", "from_high_pct": "vs 52W H %", "ret_1m": "1M %",
                                  "ret_1y": "1Y %", "src": "Source"})
        cols = ["Symbol", "Name", "Sector", "LTP", "Chg", "Chg %", "Open", "High", "Low", "Prev", "Volume",
                "52W H", "52W L", "vs 52W H %", "1M %", "1Y %", "Source"]
        show = show[[c for c in cols if c in show]]
        num = {c: "{:,.2f}" for c in ["LTP", "Chg", "Open", "High", "Low", "Prev", "52W H", "52W L"]}
        num.update({c: "{:+.2f}%" for c in ["Chg %", "vs 52W H %", "1M %", "1Y %"]})
        num["Volume"] = "{:,.0f}"
        st.dataframe(show.style.format({k: v for k, v in num.items() if k in show}, na_rep="–")
                     .map(color, subset=[c for c in ["Chg", "Chg %", "1M %", "1Y %"] if c in show]),
                     use_container_width=True, hide_index=True, height=min(38 + 35 * len(show), 720))
    with right:
        for title, part in (("Top gainers", have.nlargest(6, "change_pct")), ("Top losers", have.nsmallest(6, "change_pct"))):
            st.markdown(f"#### {title}")
            rows = "".join(
                f"<tr><td>{r.Symbol}</td><td class='r'>{r.ltp:,.2f}</td>"
                f"<td class='r' style='color:{GREEN if r.change_pct > 0 else RED}'>{r.change_pct:+.2f}%</td></tr>"
                for r in part.itertuples())
            st.markdown(f"<table class='td-mini'>{rows}</table>", unsafe_allow_html=True)

    if len(have) > 3:
        hm = have.assign(size=1.0, label=have["Symbol"] + "<br>" + have["change_pct"].map("{:+.2f}%".format))
        fig = px.treemap(hm, path=[px.Constant("Market"), "Sector", "label"], values="size", color="change_pct",
                         color_continuous_scale=[[0, RED], [0.5, "#1a1a1a"], [1, GREEN]], color_continuous_midpoint=0,
                         range_color=[-3, 3], height=420)
        fig.update_traces(hovertemplate="%{label}<extra></extra>", textfont_family="IBM Plex Mono")
        fig.update_layout(coloraxis_showscale=False, margin=dict(l=0, r=0, t=10, b=0))
        st.markdown("#### Heatmap · change today")
        st.plotly_chart(fig, use_container_width=True)
    srcs = sorted(set(df["src"].dropna()) - {""})
    st.markdown(f"<div class='td-src'>Prices: {', '.join(srcs) or '–'} · fetched {market.now_ist():%H:%M:%S} IST · "
                f"stock list: {eq_src} · Nifty 50 members as of mid-2026 (edit data/nifty50.csv)</div>",
                unsafe_allow_html=True)


# ---------------------------------------------------------------- company view
def _price_chart(hist: pd.DataFrame, name: str) -> go.Figure:
    h = hist.dropna(subset=["Close"])
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.02)
    fig.add_trace(go.Candlestick(x=h.index, open=h["Open"], high=h["High"], low=h["Low"], close=h["Close"], name=name,
                                 increasing_line_color=GREEN, decreasing_line_color=RED), row=1, col=1)
    for n, c in ((50, AMBER), (200, "#4da3ff")):
        if len(h) > n:
            fig.add_trace(go.Scatter(x=h.index, y=h["Close"].rolling(n).mean(), name=f"{n} DMA",
                                     line=dict(width=1, color=c)), row=1, col=1)
    fig.add_trace(go.Bar(x=h.index, y=h["Volume"], name="Volume", marker_color=MUTED), row=2, col=1)
    fig.update_layout(height=460, xaxis_rangeslider_visible=False, showlegend=True,
                      legend=dict(orientation="h", y=1.04, x=0), margin=dict(l=0, r=0, t=20, b=0))
    return fig


def _ratio_tiles(sc: dict, info: dict, price: float | None) -> list[tuple[str, str]]:
    r = sc.get("ratios") or {}
    mcap = market.ratio_number(r, "Market Cap")
    mcap = mcap * 1e7 if mcap else info.get("marketCap")
    pe = market.ratio_number(r, "Stock P/E") or info.get("trailingPE")
    book = market.ratio_number(r, "Book Value") or info.get("bookValue")
    pb = (price / book) if price and book else info.get("priceToBook")
    roe = market.ratio_number(r, "ROE")
    roe = roe if roe is not None else (info.get("returnOnEquity") or 0) * 100 or None
    roce = market.ratio_number(r, "ROCE")
    dy = market.ratio_number(r, "Dividend Yield")
    if dy is None and info.get("dividendYield") is not None:
        dy = float(info["dividendYield"])  # yfinance now reports this in percent
    return [("Market cap", _cr(mcap)), ("P/E", _fmt(pe, "{:.1f}")), ("P/B", _fmt(pb, "{:.1f}")),
            ("ROE", _fmt(roe, "{:.1f}%")), ("ROCE", _fmt(roce, "{:.1f}%")), ("Div yield", _fmt(dy, "{:.2f}%"))]


RESEARCH_CACHE = Path.home() / ".trade-desk" / "value_chain.json"


def _research_cache() -> dict:
    try:
        return json.loads(RESEARCH_CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _save_research(symbol: str, data: dict) -> None:
    cache = _research_cache()
    cache[symbol] = data
    try:
        RESEARCH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        RESEARCH_CACHE.write_text(json.dumps(cache, indent=1))
    except OSError:
        pass


def _show_chain(c: dict, source_note: str) -> None:
    if c.get("summary"):
        st.markdown(f"<div class='td-panel'>{c['summary']}</div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        st.markdown("#### Sells → to whom")
        sells = pd.DataFrame(c.get("sells", [])).rename(columns={"what": "Sells", "share": "Share of revenue",
                                                                  "to": "To whom"})
        st.dataframe(sells, use_container_width=True, hide_index=True)
        if c.get("customers"):
            st.markdown(f"<div class='td-panel'><span class='k'>Customers</span><br>{c['customers']}</div>",
                        unsafe_allow_html=True)
    with b:
        st.markdown("#### Buys ← from whom")
        st.dataframe(pd.DataFrame(c.get("buys", [])).rename(columns={"what": "Buys", "from": "From whom"}),
                     use_container_width=True, hide_index=True)
        for key, label in (("suppliers", "Suppliers"), ("related_parties", "Related parties"),
                           ("notes", "Ownership note")):
            if c.get(key):
                st.markdown(f"<div class='td-panel'><span class='k'>{label}</span><br>{c[key]}</div>",
                            unsafe_allow_html=True)
    srcs = [x for x in c.get("sources") or [] if isinstance(x, dict) and x.get("url")]
    if srcs:
        st.markdown("**Sources:** " + " · ".join(f"[{x.get('title') or 'source'}]({x['url']})" for x in srcs))
    st.markdown(f"<div class='td-src'>{source_note}</div>", unsafe_allow_html=True)


def _value_chain(symbol: str, name: str, notes: dict, about: str, docs: list[str], api_key: str) -> None:
    c = notes.get(symbol)
    if c:
        _show_chain(c, f"Hand-written from annual reports and investor presentations (data/companies.json, "
                       f"updated {notes.get('_updated', '?')}). Verify before relying on it.")
        return
    found = _research_cache().get(symbol)
    if found:
        _show_chain(found, f"Researched by Claude from the filings above ({found.get('as_of', 'latest')}, "
                           f"generated {found.get('generated_on', '?')}). AI-summarised: check the sources.")
        cols = st.columns(2)
        cols[0].download_button("Download as JSON (to add to data/companies.json)",
                                json.dumps({symbol: found}, indent=2), f"{symbol}_value_chain.json", "application/json")
        if not api_key or not cols[1].button("Research again", key=f"rr_{symbol}"):
            return
    elif api_key:
        st.info(f"No notes for {symbol} yet. Claude can read its annual report, BRSR, investor presentations "
                "and credit-rating reports and fill this in (takes about a minute, uses your Anthropic API credit).")
        if not st.button("Research sells & buys from filings", type="primary", key=f"r_{symbol}"):
            if about:
                st.markdown(f"<div class='td-panel'>{about}</div>", unsafe_allow_html=True)
            return
    else:
        st.info(f"No notes for {symbol} yet. To fill this in for any stock, add ANTHROPIC_API_KEY to the app's "
                "secrets: a button here will then have Claude read the company's filings. Until then, the business "
                "description and the official filings are below.")
        if about:
            st.markdown(f"<div class='td-panel'>{about}</div>", unsafe_allow_html=True)
        return
    with st.spinner(f"Reading {symbol}'s filings…"):
        try:
            data = filings.research_value_chain(symbol, name, docs, api_key)
        except filings.FilingError as e:
            st.error(str(e))
            return
    data["generated_on"] = f"{market.now_ist():%d %b %Y}"
    _save_research(symbol, data)
    st.rerun()


def _shareholders(sc: dict, yp: dict, nse: dict) -> None:
    official = filings.shareholding_frame(nse.get("shareholding") or [])
    if not official.empty:
        last = official.iloc[-1]
        st.markdown(f"#### Official filing (NSE) · as of {last['Quarter']}")
        m = st.columns(3)
        m[0].metric("Promoter & group", _fmt(last["Promoters %"], "{:.2f}%"))
        m[1].metric("Public (incl. FIIs, DIIs, retail)", _fmt(last["Public %"], "{:.2f}%"))
        m[2].metric("Filed", str(last["Filed"] or "–")[:11])
        with st.expander("All NSE shareholding filings (full XBRL has every category and holders over 1%)"):
            st.dataframe(official.iloc[::-1], use_container_width=True, hide_index=True,
                         column_config={"XBRL": st.column_config.LinkColumn("XBRL filing", display_text="open")})
    long = market.shareholding_long(sc.get("shareholding", pd.DataFrame()))
    if not long.empty:
        quarters = list(dict.fromkeys(long["Quarter"]))
        latest = long[long["Quarter"] == quarters[-1]].sort_values("Percent", ascending=False)
        a, b = st.columns([2, 3])
        with a:
            st.markdown(f"#### Who owns it · {quarters[-1]}")
            fig = px.bar(latest, x="Percent", y="Category", orientation="h", text=latest["Percent"].map("{:.2f}%".format),
                         height=260, color="Category")
            fig.update_layout(showlegend=False, yaxis_title="", xaxis_title="% of shares")
            st.plotly_chart(fig, use_container_width=True)
            retail = latest[latest["Category"].str.lower().str.startswith("public")]["Percent"].sum()
            st.caption(f"Non-retail (promoters, FIIs, DIIs, government): {100 - retail:.2f}%. "
                       "'Public' includes retail plus non-institutional holders such as HNIs and corporates.")
        with b:
            st.markdown("#### Trend by quarter")
            fig = px.line(long, x="Quarter", y="Percent", color="Category", markers=True, height=300)
            fig.update_layout(yaxis_title="%", xaxis_title="", legend=dict(orientation="h", y=-0.25))
            st.plotly_chart(fig, use_container_width=True)
    named = pd.DataFrame(sc.get("holders") or [])
    if not named.empty:
        named = named[~named["Category"].str.startswith("Public")].sort_values("Stake %", ascending=False)
        st.markdown("#### Named holders (non-retail)")
        st.dataframe(named.style.format({"Stake %": "{:.2f}%"}), use_container_width=True, hide_index=True,
                     height=min(38 + 35 * len(named), 420))
    for key, title in (("institutional_holders", "Institutions (Yahoo)"), ("mutualfund_holders", "Mutual funds (Yahoo)")):
        h = (yp.get("holders") or {}).get(key)
        if isinstance(h, pd.DataFrame) and not h.empty:
            with st.expander(title):
                st.dataframe(h, use_container_width=True, hide_index=True)
    if not long.empty or not named.empty:
        st.caption("Category split (FIIs, DIIs, government, public) and named holders: Screener.in, compiled from "
                   "the same quarterly exchange filings.")
    if long.empty and named.empty and official.empty:
        st.info("Shareholding data couldn't be loaded right now.")


def render_company(token: str | None, table: pd.DataFrame, anthropic_key: str = "") -> None:
    eq, _ = equity_list()
    names = dict(zip(eq["symbol"], eq["name"]))
    options = sorted(eq["symbol"])
    default = st.session_state.get("company") or (table["symbol"].iloc[0] if not table.empty else "RELIANCE")
    if default not in options:
        options = [default] + options
    sym = st.selectbox("Company", options, index=options.index(default),
                       format_func=lambda s: f"{s} · {names.get(s, '')}", key="company_pick",
                       placeholder="Search by symbol")
    st.session_state.company = sym
    ysym = market.yahoo_symbol(sym)

    rng = st.radio("Range", ["1M", "6M", "1Y", "3Y", "5Y"], index=2, horizontal=True, key="co_rng",
                   label_visibility="collapsed")
    hist_map, herr = yahoo_history((ysym,), "5y")
    hist = hist_map.get(ysym, pd.DataFrame())
    sc, scerr = screener(sym)
    yp, yperr = yahoo_profile(ysym)
    info = yp.get("info") or {}

    stats = market.stats_from_history(hist.tail(252)) if not hist.empty else {}
    price, chg_pct, src = stats.get("ltp"), stats.get("change_pct"), "Yahoo (delayed)"
    if token:
        k = keys_for([sym], token).get(sym)
        q, _ = live_quotes(token, (k,)) if k else ({}, None)
        v = q.get(k or "")
        if v and v.get("last_price"):
            price, chg = float(v["last_price"]), float(v.get("net_change") or 0)
            chg_pct, src = (chg / (price - chg) * 100) if price - chg else 0, "Upstox (live)"

    title = sc.get("name") or info.get("longName") or names.get(sym, sym)
    st.markdown(f"## {sym} · {title}")
    cells = [("LAST", _fmt(price), "amb"), ("CHG", _fmt(chg_pct, "{:+.2f}%"), updown(chg_pct)),
             ("52W H", _fmt(stats.get("high_52w")), ""), ("52W L", _fmt(stats.get("low_52w")), ""),
             ("1Y", _fmt(stats.get("ret_1y"), "{:+.1f}%"), updown(stats.get("ret_1y"))),
             ("SECTOR", info.get("sector") or "–", ""), ("SRC", src, "")]
    bar(cells)
    tiles = _ratio_tiles(sc, info, price)
    for col, (k, v) in zip(st.columns(len(tiles)), tiles):
        col.metric(k, v)

    if not hist.empty:
        days = {"1M": 22, "6M": 126, "1Y": 252, "3Y": 756, "5Y": 1260}[rng]
        st.plotly_chart(_price_chart(hist.tail(days), sym), use_container_width=True)
    elif herr:
        st.caption(f"Price history unavailable: {herr}")

    nse, nse_errs = nse_filings(sym)
    reports = filings.annual_report_links(nse.get("annual_reports") or [])
    brsr = filings.brsr_links(nse.get("brsr") or [])
    docs = [f"Annual report {r['Year']}: {r['Link']}" for r in reports[:1]] + \
        [f"BRSR {r['Year']}: {r['Link']}" for r in brsr[:1]]

    t_chain, t_hold, t_fin, t_files, t_about = st.tabs(
        ["Sells & buys", "Shareholders", "Quarterly results", "Filings", "About"])
    about = sc.get("about") or info.get("longBusinessSummary") or ""
    with t_chain:
        _value_chain(sym, title, market.company_notes(), about, docs, anthropic_key)
    with t_hold:
        _shareholders(sc, yp, nse)
    with t_fin:
        res = filings.results_frame(nse.get("results") or {})
        if not res.empty:
            st.markdown("#### As filed with NSE")
            money = {c: "{:,.0f}" for c in res.columns if "₹ cr" in c}
            st.dataframe(res.style.format({**money, "EPS (₹)": "{:.2f}", "Net margin %": "{:.1f}%"}, na_rep="–"),
                         use_container_width=True, hide_index=True)
            st.caption("Last five quarters from NSE's results filings, converted from ₹ lakh to ₹ crore.")
        q = sc.get("quarters", pd.DataFrame())
        if isinstance(q, pd.DataFrame) and not q.empty:
            with st.expander("Longer history (Screener.in)", expanded=res.empty):
                st.dataframe(q.iloc[:, -12:], use_container_width=True)
                st.caption("₹ crore. Consolidated where available.")
        elif res.empty:
            st.info("Quarterly results couldn't be loaded right now.")
    with t_files:
        if reports:
            st.markdown("#### Annual reports (NSE)")
            st.dataframe(pd.DataFrame(reports), use_container_width=True, hide_index=True,
                         column_config={"Link": st.column_config.LinkColumn("PDF", display_text="open")})
        if brsr:
            st.markdown("#### Business Responsibility & Sustainability Reports (NSE)")
            st.caption("BRSR Section A lists products sold, markets served and customer types; Principle 1 gives "
                       "how concentrated purchases and sales are.")
            st.dataframe(pd.DataFrame(brsr), use_container_width=True, hide_index=True,
                         column_config={"Link": st.column_config.LinkColumn("File", display_text="open")})
        st.markdown("#### Official pages")
        st.markdown("\n".join(f"- [{k}]({v})" for k, v in filings.official_links(sym, title).items()))
        if nse_errs:
            st.caption("NSE didn't answer for: " + "; ".join(nse_errs))
    with t_about:
        if about:
            st.markdown(f"<div class='td-panel'>{about}</div>", unsafe_allow_html=True)
        if sc.get("key_points"):
            st.markdown(f"<div class='td-panel'><span class='k'>Key points</span><br>"
                        f"{sc['key_points'].replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
        if info.get("website"):
            st.markdown(f"Website: {info['website']}")
    errs = [e for e in (scerr, yperr) if e]
    st.markdown(f"<div class='td-src'>Sources: {src} prices; NSE filings (shareholding, results, annual reports, BRSR); "
                f"Screener.in ratios and category split "
                f"({sc.get('url', 'unavailable')}); Yahoo Finance profile · fetched {market.now_ist():%d %b %H:%M} IST"
                + (f"<br>Issues: {' | '.join(errs)}" if errs else "") + "</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- P&L
@st.cache_data(ttl=3600, show_spinner="Fetching your P&L report from Upstox…")
def load_pnl(token: str, chunks: tuple[tuple[str, str, str], ...]) -> tuple[dict, dict, list[str]]:
    u = Upstox(token)
    trades: dict[str, list] = {s: [] for s in pnl.SEGMENTS}
    charges: dict[str, float] = {s: 0.0 for s in pnl.SEGMENTS}
    errors = []
    for seg in pnl.SEGMENTS:
        for fy, frm, to in chunks:
            try:
                trades[seg].extend(u.pnl_trades(seg, fy, frm, to))
                charges[seg] += pnl.charges_total(u.charges_for(seg, fy, frm, to))
            except UpstoxError as e:
                errors.append(f"{pnl.SEGMENTS[seg]} FY{fy}: {e}")
    return trades, charges, errors


def render_pnl(token: str | None, table: pd.DataFrame, demo_mode: bool) -> None:
    ps = pnl.periods()
    labels = [p.label for p in ps]
    pick = st.radio("Period", labels, horizontal=True, label_visibility="collapsed", key="pnl_period")
    period = ps[labels.index(pick)]
    if demo_mode:
        trades, errors = demo.PNL_TRADES, []
        booked = pnl.in_period(pnl.trades_frame(trades), period)
        charges = {k: v for k, v in demo.PNL_CHARGES.items() if k in set(booked["segment"])}
    else:
        trades, charges, errors = load_pnl(token, tuple(period.chunks()))
    for e in errors:
        if "No data" not in e and "UDAPI100" not in e:
            st.caption(f"Couldn't load {e}")

    df = pnl.in_period(pnl.trades_frame(trades), period)
    seg = pnl.segment_totals(df, charges)
    gross, ch_total = df["pnl"].sum(), sum(charges.values())
    net = gross - ch_total
    unreal = (table["pnl"].sum() if not table.empty else 0.0)
    wins = int((df["pnl"] > 0).sum())
    st.markdown(f"## Profit & loss · {period.start:%d %b %Y} to {period.end:%d %b %Y}")
    m = st.columns(6)
    m[0].metric("Realised (gross)", INR(gross))
    m[1].metric("Charges & taxes", INR(ch_total))
    m[2].metric("Realised (net)", INR(net))
    m[3].metric("Unrealised (open)", INR(unreal))
    m[4].metric("Net incl. open", INR(net + unreal))
    m[5].metric("Win rate", f"{wins / len(df) * 100:.0f}%" if len(df) else "–", f"{wins}/{len(df)} trades",
                delta_color="off")
    st.caption("Realised P&L is from Upstox's trade-wise P&L report, which updates at end of day, so today's trades "
               "appear tomorrow. Unrealised is today's P&L on everything you still hold (Portfolio tab). "
               "Charges include brokerage, STT, GST, stamp duty, exchange, SEBI and DP fees from Upstox's charges report.")
    if df.empty:
        st.info("No closed trades in this period.")
        return

    a, b = st.columns([2, 3])
    with a:
        st.markdown("#### By segment")
        st.dataframe(seg.style.format({"Gross P&L": "₹{:,.0f}", "Charges": "₹{:,.0f}", "Net P&L": "₹{:,.0f}"})
                     .map(color, subset=["Gross P&L", "Net P&L"]), use_container_width=True, hide_index=True)
        st.markdown("#### By type (for tax)")
        sm = pnl.summary(df)
        st.dataframe(sm[["Segment", "Trades", "Win rate", "Turnover", "Gross P&L", "Tax head"]]
                     .style.format({"Win rate": "{:.0f}%", "Turnover": "₹{:,.0f}", "Gross P&L": "₹{:,.0f}"})
                     .map(color, subset=["Gross P&L"]), use_container_width=True, hide_index=True)
    with b:
        mo = pnl.monthly(df)
        fig = px.bar(mo, x="month", y="pnl", color="bucket", height=320, labels={"pnl": "₹", "month": "", "bucket": ""})
        cum = df.sort_values("booked").assign(cum=lambda d: d["pnl"].cumsum())
        fig.add_trace(go.Scatter(x=cum["booked"], y=cum["cum"], name="Cumulative", line=dict(color=AMBER, width=2)))
        fig.update_layout(barmode="relative", legend=dict(orientation="h", y=-0.2), xaxis_tickformat="%b %y")
        st.markdown("#### Month by month")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Worst drawdown in realised P&L: {INR(pnl.max_drawdown(df))}")

    bs = pnl.by_stock(df)
    c1, c2 = st.columns(2)
    fmt = {"pnl": "₹{:,.0f}", "turnover": "₹{:,.0f}"}
    with c1:
        st.markdown("#### Best")
        st.dataframe(bs.head(10).style.format(fmt).map(color, subset=["pnl"]), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("#### Worst")
        st.dataframe(bs.sort_values("pnl").head(10).style.format(fmt).map(color, subset=["pnl"]),
                     use_container_width=True, hide_index=True)
    with st.expander(f"All {len(df)} closed trades"):
        out = df.drop(columns=["booked"]).sort_values("sell_date", ascending=False)
        st.dataframe(out.style.format({"buy_date": "{:%d %b %y}", "sell_date": "{:%d %b %y}", "pnl": "₹{:,.0f}",
                                       "buy_amount": "₹{:,.0f}", "sell_amount": "₹{:,.0f}"}, na_rep="–")
                     .map(color, subset=["pnl"]), use_container_width=True, hide_index=True)
        st.download_button("Download CSV", out.to_csv(index=False).encode(), f"pnl_{period.start:%Y%m%d}.csv",
                           "text/csv")
