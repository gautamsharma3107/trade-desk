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

from tradedesk import demo, earnings_page, flows_page, journal_page, news_page, screener_page, tax_page, terminal, theme, trade_page
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
    st.title("Trade Desk")
    if token:
        exp = token_store()["expires"]
        st.success(f"Connected to Upstox until {exp:%d %b, %I:%M %p} IST")
        if st.button("Log out"):
            token_store().clear()
            st.rerun()
    else:
        if API_KEY and REDIRECT:
            st.link_button("Log in with Upstox", login_url(API_KEY, REDIRECT), type="primary",
                           use_container_width=True)
        else:
            st.info("Add your Upstox API key to the app secrets to enable login (see README).")
        with st.expander("Or paste an access token"):
            t = st.text_input("Access token", type="password")
            if st.button("Use token") and t:
                save_token(t.strip())
                st.rerun()
    demo_mode = not token
    st.caption("Orders are placed only from the Trade page, after you confirm them.")


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


def page_title(title: str, subtitle: str = "") -> None:
    """Large page title, with a quiet note when the page shows sample data."""
    st.title(title)
    note = "Sample data. Log in with Upstox (in the side menu) to see your account." if demo_mode else ""
    line = " · ".join(x for x in (subtitle, note) if x)
    if line:
        st.caption(line)
    st.markdown("<div class='td-phone-only'>Tap <b>»</b> at the top left for all pages and to log in.</div>",
                unsafe_allow_html=True)
    earnings_page.alert_banner(table, ideas)


def money(v: float, sign: bool = False) -> str:
    s = f"₹{abs(v):,.0f}"
    if sign:
        return ("+" if v > 0 else "−" if v < 0 else "") + s
    return ("−" if v < 0 else "") + s


# ---------------------------------------------------------------- Portfolio
def page_portfolio() -> None:
    page_title("Portfolio")
    terminal.header(token)
    invested, value = table["invested"].sum(), table["current_value"].sum()
    pnl = value - invested
    pnl_pct = (pnl / invested * 100) if invested else 0
    day = (table["current_value"] * table["day_change_pct"] / (100 + table["day_change_pct"])).sum() if len(table) else 0
    day_pct = (day / (value - day) * 100) if value - day else 0
    eq = (acct.get("funds") or {}).get("equity", {})
    cls = theme.updown
    st.markdown(
        f"<div class='td-hero'><div class='lbl'>Current value</div><div class='big'>{money(value)}</div>"
        f"<div class='row'><span class='{cls(pnl)}'>{money(pnl, True)} ({pnl_pct:+.2f}%)<span class='k'>all time</span></span>"
        f"<span class='{cls(day)}'>{money(day, True)} ({day_pct:+.2f}%)<span class='k'>today</span></span></div></div>",
        unsafe_allow_html=True)
    stats = [("Invested", INR(invested)), ("Cash available", INR(eq.get("available_margin", 0))),
             ("Stocks held", f"{table['symbol'].nunique() if len(table) else 0}")]
    st.markdown("<div class='td-stats'>" + "".join(f"<div><div class='lbl'>{k}</div><div class='val'>{v}</div></div>"
                                                   for k, v in stats) + "</div>", unsafe_allow_html=True)

    st.subheader("Your stocks")
    if table.empty:
        st.info("No open holdings or positions.")
    else:
        show = table.drop(columns=["instrument_key"]).rename(columns={
            "symbol": "Stock", "type": "Type", "exchange": "Exchange", "qty": "Qty", "avg_price": "Avg price",
            "ltp": "Price now", "invested": "Invested", "current_value": "Value", "pnl": "P&L",
            "pnl_pct": "P&L %", "day_change_pct": "Today %"})
        order = ["Stock", "Value", "P&L", "P&L %", "Today %", "Qty", "Avg price", "Price now", "Invested", "Type",
                 "Exchange"]
        show = show[[c_ for c_ in order if c_ in show.columns]].sort_values("Value", ascending=False)
        st.dataframe(
            show.style.format({"Avg price": "₹{:,.2f}", "Price now": "₹{:,.2f}", "Invested": "₹{:,.0f}",
                               "Value": "₹{:,.0f}", "P&L": money, "P&L %": "{:+.2f}%", "Today %": "{:+.2f}%"})
            .map(theme.color, subset=["P&L", "P&L %", "Today %"]),
            use_container_width=True, hide_index=True,
            column_config={"Stock": st.column_config.TextColumn(pinned=True)})
        st.caption("Tap a column name to sort. Swipe sideways on a phone to see more columns.")
        st.subheader("Profit and loss by stock")
        d = table.sort_values("pnl")
        fig = px.bar(d, x="pnl", y="symbol", orientation="h",
                     labels={"pnl": "P&L (₹)", "symbol": ""}, height=80 + 44 * len(table))
        fig.update_traces(marker_color=[theme.GREEN if v >= 0 else theme.RED for v in d["pnl"]],
                          marker_cornerradius=6, hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

    closed = closed_today(acct["mtf"], acct["positions"])
    if not closed.empty:
        st.subheader("Closed today")
        st.dataframe(closed, use_container_width=True, hide_index=True)
        st.caption(f"Realised today: {INR(closed['realised'].sum())} (before charges)")


# ---------------------------------------------------------------- Charges
def page_charges() -> None:
    page_title("Charges", "What you've paid Upstox and the government, and a calculator for your next trade")
    st.subheader("Paid this financial year")
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
def page_sell() -> None:
    page_title("Sell check", "Simple rule-based flags to help you decide. They are prompts to look closer, not orders.")
    with st.expander("Your rules", expanded=False, icon=":material/tune:"):
        s = st.columns(3)
        stop = s[0].slider("Stop-loss (%)", 2, 30, 8, key="sc_stop")
        target = s[1].slider("Profit target (%)", 5, 100, 15, key="sc_target")
        mtf_margin = s[2].slider("MTF margin (%)", 20, 100, 25, 5, key="mtf_m2")
    notes = ideas.get("portfolio_notes", {})
    if table.empty:
        st.info("Nothing open to check.")
        return
    flagged = []
    for _, r in table.iterrows():
        if demo_mode:
            closes = demo.candles(r["ltp"], 0.08 if r["pnl"] >= 0 else -0.06)
        else:
            closes = load_closes(token, r["instrument_key"]) if r["instrument_key"] else []
        flagged.append((r, closes, review(r.to_dict(), closes, stop, target, mtf_margin, notes.get(r["symbol"]))))
    rank = {"SELL?": 0, "REVIEW": 1, "HOLD": 2}
    counts = {k: sum(f.level == k for _, _, f in flagged) for k in rank}
    theme.bar([("Sell?", str(counts["SELL?"]), "dn" if counts["SELL?"] else ""),
               ("Review", str(counts["REVIEW"]), ""), ("Hold", str(counts["HOLD"]), "up" if counts["HOLD"] else "")])
    label = {"SELL?": ("Consider selling", "sell"), "REVIEW": ("Take a look", "review"), "HOLD": ("Hold", "hold")}
    for r, closes, flag in sorted(flagged, key=lambda x: rank[x[2].level]):
        text, css = label[flag.level]
        with st.container(border=True):
            st.markdown(
                f"<div class='td-card-head'><div><div class='t'>{r['symbol']}<span class='td-pill {css}'>{text}</span></div>"
                f"<div class='td-src'>{r['type']} · {r['qty']} shares · bought at ₹{r['avg_price']:,.2f}</div></div>"
                f"<div class='r'><div class='t'>₹{r['ltp']:,.2f}</div>"
                f"<div class='{theme.updown(r['pnl_pct'])}'>{r['pnl_pct']:+.2f}%</div></div></div>",
                unsafe_allow_html=True)
            for reason in flag.reasons:
                st.markdown(f"- {reason}")
            if closes:
                lf = px.line(y=closes[-60:], height=120, labels={"y": "", "x": ""})
                lf.update_traces(line_color=theme.GREEN if closes[-1] >= closes[-min(60, len(closes))] else theme.RED,
                                 line_width=2, hovertemplate="₹%{y:,.2f}<extra></extra>")
                lf.update_layout(margin=dict(l=0, r=0, t=0, b=0), xaxis_visible=False, yaxis_visible=False)
                st.plotly_chart(lf, use_container_width=True, key=f"line_{r['symbol']}_{r['type']}",
                                config={"displayModeBar": False})


# ---------------------------------------------------------------- Daily ideas
def page_ideas() -> None:
    try:
        when = dt.date.fromisoformat(ideas.get("date", "")).strftime("%A, %d %B %Y")
    except ValueError:
        when = ideas.get("date", "?")
    page_title("Daily ideas", f"Research for {when}" if ideas else "")
    if not ideas:
        st.info("No research file yet.")
        return
    if ideas.get("market_summary"):
        st.markdown(f"<div class='td-panel'>{ideas['market_summary']}</div>", unsafe_allow_html=True)
    st.caption(ideas.get("disclaimer", "Ideas, not advice."))
    held = set(table["symbol"])
    if ideas.get("buy_ideas"):
        st.subheader("Ideas to buy")
    for i in ideas.get("buy_ideas", []):
        up = (i["target"] / i["approx_price"] - 1) * 100 if i.get("target") and i.get("approx_price") else None
        with st.container(border=True):
            mine = "<span class='td-pill'>You hold this</span>" if i["symbol"] in held else ""
            st.markdown(f"<div style='font-size:1.15rem;font-weight:600'>{i['symbol']}{mine}</div>"
                        f"<div class='td-src'>{i.get('name', '')}</div>", unsafe_allow_html=True)
            cols = st.columns(3)
            cols[0].metric("Price about", INR(i.get("approx_price", 0)))
            cols[1].metric(f"Target ({i.get('target_source', 'analyst')})", INR(i.get("target", 0)))
            cols[2].metric("Upside", f"{up:.0f}%" if up is not None else "–")
            st.markdown(f"**Why:** {i.get('thesis', '')}")
            st.markdown(f"**Risks:** {i.get('risks', '')}")
            if i.get("sources"):
                st.caption(" · ".join(f"[Source {n + 1}]({u})" for n, u in enumerate(i["sources"])))
    if ideas.get("avoid"):
        st.subheader("Avoid for now")
        with st.container(border=True):
            for a_ in ideas["avoid"]:
                st.markdown(f"- **{a_['symbol']}**: {a_['reason']}")
    if ideas.get("watch_today"):
        st.subheader("Results to watch")
        st.markdown(" ".join(f"<span class='td-pill' style='margin:0 6px 6px 0'>{s}</span>"
                             for s in ideas["watch_today"]), unsafe_allow_html=True)


# ---------------------------------------------------------------- other pages
def page(title: str, subtitle: str, fn, *args, strip: bool = False):
    def run() -> None:
        page_title(title, subtitle)
        if strip:
            terminal.header(token)
        fn(*args)
    run.__name__ = "page_" + "".join(ch if ch.isalnum() else "_" for ch in title.lower())
    return run


P = st.Page
nav = st.navigation({
    "": [
        P(page_portfolio, title="Portfolio", icon=":material/account_balance_wallet:", default=True),
        P(page_sell, title="Sell check", icon=":material/fact_check:", url_path="sell-check"),
        P(page("Trade", "Orders go to Upstox only after you review and confirm them.", trade_page.render, token,
               table, secret, acct.get("funds")), title="Trade", icon=":material/currency_rupee:", url_path="trade"),
    ],
    "Ideas": [
        P(page_ideas, title="Daily ideas", icon=":material/lightbulb:", url_path="ideas"),
        P(page("Earnings", "Who reported, how good the results were, and who reports next",
               earnings_page.render, token, table, ideas),
          title="Earnings", icon=":material/campaign:", url_path="earnings"),
        P(page("News", "Company announcements, big deals and insider trades",
               news_page.render, table, ideas), title="News", icon=":material/newspaper:", url_path="news"),
    ],
    "Markets": [
        P(page("Markets", "", terminal.render_markets, token, table, ideas, strip=True),
          title="Markets", icon=":material/show_chart:", url_path="markets"),
        P(page("Company", "Look up any NSE stock", terminal.render_company, token, table,
               secret("ANTHROPIC_API_KEY")), title="Company", icon=":material/business:", url_path="company"),
        P(page("Screener", "Find stocks by growth, value and quality", screener_page.render, table, ideas),
          title="Screener", icon=":material/filter_alt:", url_path="screener"),
        P(page("Flows", "What big investors (FIIs and DIIs) are buying and selling, and option data",
               flows_page.render, token, table), title="Flows", icon=":material/swap_vert:", url_path="flows"),
    ],
    "Money": [
        P(page("Profit & loss", "Realised profit and loss across all your trades", terminal.render_pnl, token,
               table, demo_mode), title="Profit & loss", icon=":material/monitoring:", url_path="pnl"),
        P(page("Tax", "Estimated tax on this year's gains", tax_page.render, token, table, demo_mode),
          title="Tax", icon=":material/receipt_long:", url_path="tax"),
        P(page_charges, title="Charges", icon=":material/payments:", url_path="charges"),
        P(page("Journal", "How your trades and the daily ideas have done", journal_page.render, token, table,
               ideas, demo_mode), title="Journal", icon=":material/menu_book:", url_path="journal"),
    ],
}, position="top")
nav.run()
