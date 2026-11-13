"""Trade Desk: a daily view of an Upstox portfolio, charges, sell checks and research ideas, plus a Trade tab.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import hmac
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from tradedesk import demo, earnings_page, flows_page, news_page, terminal, theme, trade_page
from tradedesk.charges import PRODUCTS, RATES, RATES_CHECKED_ON, round_trip, mtf_interest
from tradedesk.portfolio import build_table, closed_today, review
from tradedesk.upstox import Upstox, UpstoxError, exchange_code, financial_year, login_url, token_expiry

st.set_page_config(page_title="Trade Desk", page_icon="📈", layout="wide")
theme.apply()
IDEAS_FILE = Path(__file__).parent / "data" / "ideas.json"
INR = "₹{:,.0f}".format


def secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:  # no secrets file
        return default


# ---------------------------------------------------------------- password gate
def password_ok() -> bool:
    pw = secret("APP_PASSWORD")
    if not pw or st.session_state.get("pw_ok"):
        return True
    entered = st.text_input("Password", type="password")
    if entered and hmac.compare_digest(entered, pw):
        st.session_state.pw_ok = True
        st.rerun()
    elif entered:
        st.error("Wrong password.")
    return False


if not password_ok():
    st.stop()


# ---------------------------------------------------------------- Upstox login
@st.cache_resource
def token_store() -> dict:
    """Kept in server memory only (never written to disk), until Upstox expires it at 3:30 AM IST."""
    return {}


def current_token() -> str | None:
    store = token_store()
    exp = store.get("expires")
    if exp and dt.datetime.now(exp.tzinfo) < exp:
        return store.get("token")
    store.clear()
    return None


def save_token(token: str) -> None:
    token_store().update(token=token, expires=token_expiry())


API_KEY, API_SECRET, REDIRECT = secret("UPSTOX_API_KEY"), secret("UPSTOX_API_SECRET"), secret("UPSTOX_REDIRECT_URI")

code = st.query_params.get("code")
if code and API_KEY and API_SECRET:
    try:
        save_token(exchange_code(code, API_KEY, API_SECRET, REDIRECT)["access_token"])
        st.query_params.clear()
        st.rerun()
    except UpstoxError as e:
        st.query_params.clear()
        st.error(str(e))

token = current_token()

with st.sidebar:
    st.title("📈 Trade Desk")
    if token:
        exp = token_store()["expires"]
        st.success(f"Connected to Upstox until {exp:%d %b, %I:%M %p} IST")
        if st.button("Log out"):
            token_store().clear()
            st.rerun()
    else:
        if API_KEY and REDIRECT:
            st.link_button("Login with Upstox", login_url(API_KEY, REDIRECT), type="primary",
                           use_container_width=True)
        else:
            st.info("Add your Upstox API key to the app secrets to enable login (see README).")
        with st.expander("Or paste an access token"):
            t = st.text_input("Access token", type="password")
            if st.button("Use token") and t:
                save_token(t.strip())
                st.rerun()
    demo_mode = not token
    if demo_mode:
        st.warning("Showing **sample data**. Log in to see your account.")
    st.caption("Orders are placed only from the Trade tab, after you confirm them.")


# ---------------------------------------------------------------- data
@st.cache_data(ttl=60, show_spinner="Loading your account…")
def load_account(tok: str) -> dict:
    u = Upstox(tok)
    out = {"errors": []}
    for name, fn in [("holdings", u.holdings), ("mtf", u.mtf_positions), ("positions", u.positions),
                     ("funds", u.funds)]:
        try:
            out[name] = fn()
        except UpstoxError as e:
            out[name] = [] if name != "funds" else {}
            out["errors"].append(f"{name}: {e}")
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def load_closes(tok: str, key: str) -> list[float]:
    try:
        return [c[4] for c in Upstox(tok).daily_candles(key)]
    except UpstoxError:
        return []


@st.cache_data(ttl=3600, show_spinner="Fetching charges from Upstox…")
def load_charges(tok: str, fy: str) -> dict:
    return Upstox(tok).charges_breakdown(fy)


def load_ideas() -> dict:
    try:
        return json.loads(IDEAS_FILE.read_text())
    except (OSError, ValueError):
        return {}


if demo_mode:
    acct = {"holdings": demo.HOLDINGS, "mtf": demo.MTF, "positions": demo.POSITIONS, "funds": demo.FUNDS, "errors": []}
else:
    acct = load_account(token)
for err in acct["errors"]:
    st.warning(f"Couldn't load {err}")
    if "401" in err or "Unauthorized" in err:
        token_store().clear()

table = build_table(acct["holdings"], acct["mtf"], acct["positions"])
ideas = load_ideas()

terminal.header(token)
earnings_page.alert_banner(table, ideas)
(tab_port, tab_pnl, tab_mkt, tab_co, tab_earn, tab_news, tab_flows, tab_charges, tab_sell, tab_ideas,
 tab_trade) = st.tabs(["Portfolio", "P&L", "Markets", "Company", "Earnings", "News", "Flows", "Charges",
                       "Sell check", "Daily ideas", "Trade"])

with tab_pnl:
    terminal.render_pnl(token, table, demo_mode)
with tab_mkt:
    terminal.render_markets(token, table, ideas)
with tab_co:
    terminal.render_company(token, table, secret("ANTHROPIC_API_KEY"))
with tab_earn:
    earnings_page.render(token, table, ideas)
with tab_news:
    news_page.render(table, ideas)
with tab_flows:
    flows_page.render(token, table)

# ---------------------------------------------------------------- Portfolio
with tab_port:
    invested, value = table["invested"].sum(), table["current_value"].sum()
    pnl = value - invested
    day = (table["current_value"] * table["day_change_pct"] / (100 + table["day_change_pct"])).sum() if len(table) else 0
    eq = (acct.get("funds") or {}).get("equity", {})
    c = st.columns(5)
    c[0].metric("Invested", INR(invested))
    c[1].metric("Current value", INR(value))
    c[2].metric("Total P&L", INR(pnl), f"{(pnl / invested * 100) if invested else 0:.2f}%")
    c[3].metric("Today", INR(day))
    c[4].metric("Cash available", INR(eq.get("available_margin", 0)))

    if table.empty:
        st.info("No open holdings or positions.")
    else:
        show = table.drop(columns=["instrument_key"]).rename(columns={
            "symbol": "Stock", "type": "Type", "exchange": "Exch", "qty": "Qty", "avg_price": "Avg",
            "ltp": "LTP", "invested": "Invested", "current_value": "Value", "pnl": "P&L",
            "pnl_pct": "P&L %", "day_change_pct": "Day %"})
        st.dataframe(
            show.style.format({"Avg": "₹{:,.2f}", "LTP": "₹{:,.2f}", "Invested": "₹{:,.0f}", "Value": "₹{:,.0f}",
                               "P&L": "₹{:,.0f}", "P&L %": "{:+.2f}%", "Day %": "{:+.2f}%"})
            .map(lambda v: f"color: {'#16a34a' if v > 0 else '#dc2626' if v < 0 else ''}",
                 subset=["P&L", "P&L %", "Day %"]),
            use_container_width=True, hide_index=True)
        fig = px.bar(table.sort_values("pnl"), x="pnl", y="symbol", orientation="h", color="type",
                     labels={"pnl": "P&L (₹)", "symbol": ""}, height=60 + 40 * len(table))
        st.plotly_chart(fig, use_container_width=True)

    closed = closed_today(acct["mtf"], acct["positions"])
    if not closed.empty:
        st.subheader("Closed today")
        st.dataframe(closed, use_container_width=True, hide_index=True)
        st.caption(f"Realised today: {INR(closed['realised'].sum())} (before charges)")

# ---------------------------------------------------------------- Charges
with tab_charges:
    st.subheader("Charges you've paid this financial year")
    fy = financial_year()
    if demo_mode:
        ch = demo.CHARGES
    else:
        try:
            ch = load_charges(token, fy)["charges_breakdown"]
        except (UpstoxError, KeyError) as e:
            ch = None
            st.warning(f"Couldn't load charges from Upstox: {e}")
    if ch:
        taxes, other = ch.get("taxes", {}), ch.get("charges", {})
        rows = {"Brokerage": ch.get("brokerage", 0), "STT": taxes.get("stt", 0), "GST": taxes.get("gst", 0),
                "Stamp duty": taxes.get("stamp_duty", 0), "Exchange transaction": other.get("transaction", 0),
                "DP (demat) charges": other.get("demat_transaction", 0), "SEBI": other.get("sebi_turnover", 0),
                "Clearing": other.get("clearing", 0), "IPFT": other.get("ipft", 0), "Other": other.get("others", 0)}
        rows = {k: float(v or 0) for k, v in rows.items() if v}
        cc = st.columns([1, 2])
        cc[0].metric(f"Total, FY 20{fy[:2]}-{fy[2:]}", INR(ch.get("total", sum(rows.values()))))
        cc[0].caption("Equity segment, from Upstox. MTF interest is billed separately and isn't in this total.")
        pie = px.pie(names=list(rows), values=list(rows.values()), hole=0.5, height=300)
        pie.update_traces(textposition="inside", textinfo="percent")
        pie.update_layout(uniformtext_minsize=10, uniformtext_mode="hide", margin=dict(t=10, b=10))
        cc[1].plotly_chart(pie, use_container_width=True)

    mtf_rows = table[table["type"] == "MTF"]
    if not mtf_rows.empty:
        st.subheader("MTF interest on open positions")
        margin = st.slider("Your margin on MTF trades (%)", 20, 100, 25, 5, key="mtf_m1",
                           help="The share of the buy value you paid yourself. Upstox funds the rest.")
        recs = []
        for _, r in mtf_rows.iterrows():
            per_day, funded, slabs = mtf_interest(r["invested"], margin, 1)
            recs.append({"Stock": r["symbol"], "Buy value": INR(r["invested"]), "Funded by Upstox": INR(funded),
                         "₹40k slabs": slabs, "Interest / day": INR(per_day), "Interest / month (30d)": INR(per_day * 30)})
        st.dataframe(pd.DataFrame(recs), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Charges calculator")
    st.caption(f"Upstox rates checked on {RATES_CHECKED_ON}. Estimates; your contract note is final.")
    a, b, c3 = st.columns(3)
    product = a.radio("Product", PRODUCTS, horizontal=True)
    exchange = a.radio("Exchange", ("NSE", "BSE"), horizontal=True)
    qty = b.number_input("Quantity", 1, 1_000_000, 10)
    buy_price = b.number_input("Buy price (₹)", 0.01, 1e7, 1000.0, step=1.0)
    sell_price = c3.number_input("Sell price (₹)", 0.01, 1e7, 1050.0, step=1.0)
    days = c3.number_input("Days held (MTF)", 0, 3650, 5) if product == "MTF" else 0
    margin = c3.slider("Your margin (%)", 20, 100, 25, 5) if product == "MTF" else 25
    rt = round_trip(product, buy_price, sell_price, int(qty), exchange, int(days), margin)

    m = st.columns(4)
    m[0].metric("Total charges", f"₹{rt['total_charges']:,.2f}")
    m[1].metric("Gross P&L", f"₹{rt['gross_pnl']:,.2f}")
    m[2].metric("Net P&L", f"₹{rt['net_pnl']:,.2f}")
    m[3].metric("Breakeven sell price", f"₹{rt['breakeven_sell_price']:,.2f}")
    buy_rows, sell_rows = dict(rt["buy"].as_rows()), dict(rt["sell"].as_rows())
    names = [n for n in dict.fromkeys(list(buy_rows) + list(sell_rows)) if n != "Total"]
    breakdown = pd.DataFrame({"Charge": names + ["Total"],
                              "Buy": [buy_rows.get(n, 0.0) for n in names] + [buy_rows["Total"]],
                              "Sell": [sell_rows.get(n, 0.0) for n in names] + [sell_rows["Total"]]})
    if product == "MTF":
        breakdown.loc[len(breakdown)] = [f"MTF interest ({days} days, {rt['mtf_slabs']} slab(s) of ₹40k)",
                                         rt["mtf_interest"], 0.0]
    st.dataframe(breakdown.style.format({"Buy": "₹{:,.2f}", "Sell": "₹{:,.2f}"}),
                 use_container_width=True, hide_index=True)
    for note in dict.fromkeys(rt["buy"].notes + rt["sell"].notes):
        st.caption(note)

    if not demo_mode:
        with st.expander("Check this against Upstox's own calculator"):
            key = st.text_input("Instrument key", "NSE_EQ|INE397D01024", help="e.g. NSE_EQ|<ISIN>")
            if st.button("Get exact charges"):
                code_map = {"Delivery": "D", "Intraday": "I", "MTF": "MTF"}
                try:
                    u = Upstox(token)
                    for side, px_ in (("BUY", buy_price), ("SELL", sell_price)):
                        st.write(side, u.brokerage(key, int(qty), code_map[product], side, px_))
                except UpstoxError as e:
                    st.error(str(e))

# ---------------------------------------------------------------- Sell check
with tab_sell:
    st.subheader("Should I sell anything?")
    st.caption("Rule-based flags to help you decide. They are prompts to look closer, not orders.")
    s = st.columns(3)
    stop = s[0].slider("Stop-loss (%)", 2, 30, 8)
    target = s[1].slider("Profit target (%)", 5, 100, 15)
    mtf_margin = s[2].slider("MTF margin (%)", 20, 100, 25, 5, key="mtf_m2")
    notes = ideas.get("portfolio_notes", {})
    if table.empty:
        st.info("Nothing open to check.")
    for _, r in table.iterrows():
        if demo_mode:
            closes = demo.candles(r["ltp"], 0.08 if r["pnl"] >= 0 else -0.06)
        else:
            closes = load_closes(token, r["instrument_key"]) if r["instrument_key"] else []
        flag = review(r.to_dict(), closes, stop, target, mtf_margin, notes.get(r["symbol"]))
        icon = {"SELL?": "🔴", "REVIEW": "🟠", "HOLD": "🟢"}[flag.level]
        with st.container(border=True):
            h = st.columns([3, 1])
            h[0].markdown(f"**{icon} {r['symbol']}** · {r['type']} · {r['qty']} @ ₹{r['avg_price']:,.2f} → "
                          f"₹{r['ltp']:,.2f} ({r['pnl_pct']:+.2f}%)")
            h[1].markdown(f"**{flag.level}**")
            for reason in flag.reasons:
                st.markdown(f"- {reason}")
            if closes:
                lf = px.line(y=closes[-60:], height=150, labels={"y": "", "x": ""})
                lf.update_layout(margin=dict(l=0, r=0, t=0, b=0), xaxis_visible=False)
                st.plotly_chart(lf, use_container_width=True, key=f"line_{r['symbol']}_{r['type']}")

# ---------------------------------------------------------------- Daily ideas
with tab_ideas:
    if not ideas:
        st.info("No research file yet.")
    else:
        st.subheader(f"Research for {ideas.get('date', '?')}")
        st.write(ideas.get("market_summary", ""))
        st.warning(ideas.get("disclaimer", "Ideas, not advice."))
        held = set(table["symbol"])
        for i in ideas.get("buy_ideas", []):
            up = (i["target"] / i["approx_price"] - 1) * 100 if i.get("target") and i.get("approx_price") else None
            with st.container(border=True):
                st.markdown(f"**{i['symbol']}** · {i.get('name', '')}" + ("  ·  _you hold this_" if i["symbol"] in held else ""))
                cols = st.columns(3)
                cols[0].metric("Approx price", INR(i.get("approx_price", 0)))
                cols[1].metric(f"Target ({i.get('target_source', 'analyst')})", INR(i.get("target", 0)))
                cols[2].metric("Upside", f"{up:.0f}%" if up is not None else "–")
                st.markdown(f"**Why:** {i.get('thesis', '')}")
                st.markdown(f"**Risks:** {i.get('risks', '')}")
                if i.get("sources"):
                    st.caption(" · ".join(f"[source {n + 1}]({u})" for n, u in enumerate(i["sources"])))
        if ideas.get("avoid"):
            st.subheader("Avoid / don't chase")
            for a_ in ideas["avoid"]:
                st.markdown(f"- **{a_['symbol']}**: {a_['reason']}")
        if ideas.get("watch_today"):
            st.subheader("Results to watch")
            st.write(", ".join(ideas["watch_today"]))

# ---------------------------------------------------------------- Trade
with tab_trade:
    trade_page.render(token, table, secret, acct.get("funds"))
