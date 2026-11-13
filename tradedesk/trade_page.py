"""The Trade tab: buy or sell a stock through Upstox, with a review-and-confirm step.

Modes (picked at the top of the tab):
- Paper:   the default. Simulated fills, nothing is sent to Upstox.
- Sandbox: Upstox's test environment. Needs UPSTOX_SANDBOX_TOKEN in secrets.
- Live:    real orders. Needs LIVE_TRADING = true and a TRADE_PIN in secrets, an
           Upstox login, and the PIN typed in for every order.
"""
from __future__ import annotations

import hmac
import json
import secrets as pysecrets
from dataclasses import asdict
from typing import Callable

import pandas as pd
import streamlit as st

from tradedesk.orders import (DEFAULT_MAX_ORDER_VALUE, ORDER_TYPES, PRODUCTS, GttTicket, Ticket, Trader, check,
                              check_gtt, simulate_fill, simulate_gtt)
from tradedesk.upstox import UpstoxError

# Used for picking a stock before logging in (paper mode on sample data). Logged in, search covers all NSE/BSE stocks.
POPULAR = {
    "RELIANCE": "NSE_EQ|INE002A01018", "TCS": "NSE_EQ|INE467B01029", "HDFCBANK": "NSE_EQ|INE040A01034",
    "INFY": "NSE_EQ|INE009A01021", "ICICIBANK": "NSE_EQ|INE090A01021", "ITC": "NSE_EQ|INE154A01025",
    "SBIN": "NSE_EQ|INE062A01020", "BHARTIARTL": "NSE_EQ|INE397D01024", "LT": "NSE_EQ|INE018A01030",
    "HINDUNILVR": "NSE_EQ|INE030A01027",
}
PAPER, SANDBOX, LIVE = "Paper", "Sandbox", "Live"
NOW, RULE = "Order now", "Automatic rule (GTT)"


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _state() -> dict:
    ss = st.session_state
    ss.setdefault("trade_log", [])        # orders sent this session (all modes)
    ss.setdefault("trade_pending", None)  # ticket waiting for confirmation
    ss.setdefault("gtt_pending", None)    # GTT rule waiting for confirmation
    ss.setdefault("gtt_paper", [])        # paper GTT rules
    return ss


def _held(table: pd.DataFrame, key: str, product: str) -> int:
    if table.empty:
        return 0
    rows = table[table["instrument_key"] == key]
    kinds = {"D": ("Delivery", "Position"), "MTF": ("MTF",), "I": ("Intraday",)}[product]
    return int(rows[rows["type"].isin(kinds)]["qty"].sum())


@st.cache_data(ttl=300, show_spinner=False)
def _search(tok: str, q: str) -> list[dict]:
    return Trader(tok).search(q)


@st.cache_data(ttl=5, show_spinner=False)
def _ltp(tok: str, key: str) -> float | None:
    try:
        prices = Trader(tok).ltp([key])
    except UpstoxError:
        return None
    # The response is keyed by "NSE_EQ:SYMBOL"; with one key asked, take the one value.
    return prices.get(key) or (next(iter(prices.values())) if prices else None)


def _pick_stock(token: str | None, table: pd.DataFrame) -> tuple[str, str, float | None]:
    """Returns (instrument_key, symbol, last price or None)."""
    options: dict[str, tuple[str, str]] = {}
    for _, r in table.drop_duplicates("instrument_key").iterrows():
        if r["instrument_key"]:
            options[f"{r['symbol']} · you hold this"] = (r["instrument_key"], r["symbol"])
    if token:
        q = st.text_input("Search NSE / BSE stocks", key="tr_search", placeholder="Name, symbol or ISIN, e.g. Tata Motors")
        if q.strip():
            try:
                for i in _search(token, q.strip()):
                    label = f"{i.get('trading_symbol')} · {i.get('exchange')} · {i.get('name', '')}"
                    options[label] = (i["instrument_key"], i.get("trading_symbol", ""))
            except UpstoxError as e:
                st.warning(f"Search failed: {e}")
    else:
        for sym, key in POPULAR.items():
            options.setdefault(sym, (key, sym))
    if not options:
        st.info("Search for a stock to trade.")
        return "", "", None
    label = st.selectbox("Stock", list(options), key="tr_stock")
    key, sym = options[label]
    ltp = _ltp(token, key) if token else None
    if ltp is None and not table.empty:
        held = table[table["instrument_key"] == key]
        ltp = float(held["ltp"].iloc[0]) if len(held) else None
    return key, sym, ltp


def _modes(token: str | None, secret: Callable[[str, str], str]) -> tuple[list[str], list[str]]:
    modes, why_not = [PAPER], []
    if secret("UPSTOX_SANDBOX_TOKEN", ""):
        modes.append(SANDBOX)
    if not _truthy(secret("LIVE_TRADING", "")):
        why_not.append("`LIVE_TRADING = true` is not set in the app secrets")
    if not secret("TRADE_PIN", ""):
        why_not.append("no `TRADE_PIN` is set in the app secrets")
    if not token:
        why_not.append("you're not logged in to Upstox")
    if not why_not:
        modes.append(LIVE)
    return modes, why_not


def _ticket_form(key: str, sym: str, ltp: float | None) -> Ticket:
    a, b, c = st.columns(3)
    side = a.radio("Buy or sell", ("BUY", "SELL"), horizontal=True, key="tr_side")
    product = PRODUCTS[a.radio("Product", list(PRODUCTS), horizontal=True, key="tr_product")]
    order_type = b.selectbox("Order type", ORDER_TYPES, key="tr_type",
                             help="LIMIT: only at your price or better. MARKET: at the current price. "
                                  "SL: a limit order that wakes up when the trigger price trades. "
                                  "SL-M: a market order that wakes up at the trigger price.")
    qty = int(b.number_input("Quantity", min_value=1, max_value=100_000, value=1, step=1, key="tr_qty"))
    default_px = round(ltp, 2) if ltp else 0.0
    price = c.number_input("Limit price (₹)", min_value=0.0, value=default_px, step=0.05, format="%.2f", key=f"tr_px_{key}",
                           disabled=order_type in ("MARKET", "SL-M"))
    trigger = c.number_input("Trigger price (₹)", min_value=0.0, value=default_px, step=0.05, format="%.2f", key=f"tr_trig_{key}",
                             disabled=order_type not in ("SL", "SL-M"))
    with st.expander("More options"):
        validity = st.radio("Validity", ("DAY", "IOC"), horizontal=True, key="tr_validity",
                            help="DAY stays open until the close. IOC fills what it can right away and cancels the rest.")
        amo = st.checkbox("After-market order (AMO)", key="tr_amo", help="Queue it outside market hours for the next session.")
    return Ticket(instrument_key=key, symbol=sym, side=side, qty=qty, product=product, order_type=order_type,
                  price=float(price), trigger_price=float(trigger), validity=validity, is_amo=amo)


def _confirm(mode: str, trader: Trader | None, ltp: float | None, secret: Callable[[str, str], str]) -> None:
    ss = _state()
    p = ss.trade_pending
    t = Ticket(**p["ticket"])
    colour = {LIVE: "red", SANDBOX: "orange", PAPER: "blue"}[mode]
    with st.container(border=True):
        st.markdown(f"### Confirm :{colour}[{mode.upper()}] order")
        st.markdown(f"**{t.summary()}**")
        est = t.value(ltp)
        st.markdown(f"Estimated value: **₹{est:,.2f}**" + (f" · last price ₹{ltp:,.2f}" if ltp else ""))
        for w in p["warnings"]:
            st.warning(w)
        with st.expander("Exact request that will be sent to Upstox"):
            st.code(json.dumps(t.payload(), indent=2), language="json")
        if mode == LIVE:
            st.error("This is a real order with real money. It can't be undone once it fills.")
        sure = st.checkbox("I've checked the stock, side, quantity and price", key=f"sure_{p['nonce']}")
        pin = st.text_input("Trading PIN", type="password", key=f"pin_{p['nonce']}") if mode == LIVE else ""
        b1, b2 = st.columns(2)
        go = b1.button(f"Place {t.side} order", type="primary", disabled=not sure, use_container_width=True,
                       key=f"go_{p['nonce']}")
        if b2.button("Cancel", use_container_width=True, key=f"back_{p['nonce']}"):
            ss.trade_pending = None
            st.rerun()
    if not go:
        return
    if mode == LIVE and not hmac.compare_digest(pin.encode(), secret("TRADE_PIN", "").encode()):
        st.error("Wrong trading PIN. Nothing was sent.")
        return
    # Clear the pending ticket before sending, so a rerun or double click can't send it twice.
    ss.trade_pending = None
    if mode == PAPER:
        row = simulate_fill(t, ltp)
        ss.trade_log.insert(0, {"mode": PAPER, **row})
        st.success(f"Paper order {row['order_id']} recorded ({row['status']}). Nothing was sent to Upstox.")
        return
    try:
        ids = trader.place(t)
    except UpstoxError as e:
        st.error(f"Upstox rejected the order: {e}")
        return
    for oid in ids:
        ss.trade_log.insert(0, {"mode": mode, "order_id": oid, "trading_symbol": t.symbol,
                                "transaction_type": t.side, "quantity": t.qty, "order_type": t.order_type,
                                "price": t.price, "status": "sent", "ticket": asdict(t)})
    st.success(f"{mode} order sent. Upstox order id: {', '.join(ids)}. Check its status below.")


def _order_book(mode: str, trader: Trader | None) -> None:
    ss = _state()
    st.subheader("Orders")
    if mode == LIVE:
        if st.button("Refresh order book", key="tr_refresh"):
            st.rerun()
        try:
            book = trader.order_book()
        except UpstoxError as e:
            st.warning(f"Couldn't load the order book: {e}")
            book = []
        if not book:
            st.caption("No orders today.")
            return
        df = pd.DataFrame(book)
        cols = [c for c in ("order_timestamp", "trading_symbol", "transaction_type", "quantity", "filled_quantity",
                            "product", "order_type", "price", "trigger_price", "average_price", "status",
                            "status_message", "order_id") if c in df]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
        open_ = [o for o in book if str(o.get("status", "")).lower() in
                 ("open", "trigger pending", "after market order req received", "put order req received",
                  "validation pending", "open pending", "modify pending")]
        if open_:
            labels = {f"{o['trading_symbol']} {o['transaction_type']} {o['quantity']} @ {o.get('price')} "
                      f"({o['order_id']})": o["order_id"] for o in open_}
            pick = st.selectbox("Cancel an open order", list(labels), key="tr_cancel_pick")
            sure = st.checkbox("Yes, cancel this order", key=f"cancel_sure_{labels[pick]}")
            if st.button("Cancel order", disabled=not sure, key="tr_cancel_go"):
                try:
                    trader.cancel(labels[pick])
                    st.success("Cancel request sent.")
                except UpstoxError as e:
                    st.error(f"Couldn't cancel: {e}")
        return
    log = [o for o in ss.trade_log if o["mode"] == mode]
    if not log:
        st.caption(f"No {mode.lower()} orders yet this session.")
        return
    df = pd.DataFrame(log).drop(columns=["ticket", "mode", "instrument_token"], errors="ignore")
    st.dataframe(df, use_container_width=True, hide_index=True)
    if mode == SANDBOX:
        st.caption("The Upstox sandbox accepts orders but has no order book to read back, "
                   "so this lists the order ids it returned.")
    if st.button(f"Clear {mode.lower()} orders", key="tr_clear"):
        ss.trade_log = [o for o in ss.trade_log if o["mode"] != mode]
        st.rerun()


# ---------------------------------------------------------------- automatic rules (GTT)
def _gtt_form(key: str, sym: str, ltp: float | None) -> GttTicket:
    a, b, c = st.columns(3)
    side = a.radio("Buy or sell", ("BUY", "SELL"), horizontal=True, key="gtt_side")
    product = PRODUCTS[a.radio("Product", list(PRODUCTS), horizontal=True, key="gtt_product")]
    qty = int(a.number_input("Quantity", min_value=1, max_value=100_000, value=1, step=1, key="gtt_qty"))
    default_trig = "BELOW" if side == "BUY" else "ABOVE"
    trig = b.selectbox("Enter when the price goes", ("BELOW", "ABOVE", "IMMEDIATE"),
                       index=("BELOW", "ABOVE", "IMMEDIATE").index(default_trig), key=f"gtt_trig_{side}",
                       help="BELOW: buy the dip / sell on a fall. ABOVE: buy a breakout / sell into strength. "
                            "IMMEDIATE: enter now and let the rule manage only the exit.")
    base = round(ltp, 2) if ltp else 0.0
    entry = b.number_input("Entry price (₹)", min_value=0.0, value=base, step=0.05, format="%.2f",
                           key=f"gtt_entry_{key}")
    use_t = c.checkbox("Add a target (take profit)", value=side == "BUY", key=f"gtt_use_t_{side}")
    target = c.number_input("Target (₹)", min_value=0.0, step=0.05, format="%.2f", key=f"gtt_target_{key}_{side}",
                            value=round(base * (1.10 if side == "BUY" else 0.90), 2), disabled=not use_t)
    use_sl = c.checkbox("Add a stop-loss", value=side == "BUY", key=f"gtt_use_sl_{side}")
    stoploss = c.number_input("Stop-loss (₹)", min_value=0.0, step=0.05, format="%.2f", key=f"gtt_sl_{key}_{side}",
                              value=round(base * (0.95 if side == "BUY" else 1.05), 2), disabled=not use_sl)
    trail = c.number_input("Trailing gap (₹, optional)", min_value=0.0, value=0.0, step=0.05, format="%.2f",
                           key="gtt_trail", disabled=not use_sl,
                           help="Moves the stop-loss up behind the price by this many rupees as it rises.")
    return GttTicket(instrument_key=key, symbol=sym, side=side, qty=qty, product=product, trigger_type=trig,
                     entry_price=float(entry), target=float(target) if use_t else 0.0,
                     stoploss=float(stoploss) if use_sl else 0.0,
                     trailing_gap=float(trail) if use_sl else 0.0)


def _confirm_gtt(mode: str, trader: Trader | None, secret: Callable[[str, str], str]) -> None:
    ss = _state()
    p = ss.gtt_pending
    g = GttTicket(**p["ticket"])
    colour = {LIVE: "red", PAPER: "blue"}[mode]
    with st.container(border=True):
        st.markdown(f"### Confirm :{colour}[{mode.upper()}] automatic rule")
        st.markdown(f"**{g.summary()}.**")
        st.caption("The rule stays on Upstox for up to a year, or until it fires or you cancel it.")
        for w in p["warnings"]:
            st.warning(w)
        with st.expander("Exact request that will be sent to Upstox"):
            st.code(json.dumps(g.payload(), indent=2), language="json")
        if mode == LIVE:
            st.error("This sets up real orders with real money that will fire on their own when the price hits.")
        sure = st.checkbox("I've checked the stock, side, quantity and prices", key=f"gsure_{p['nonce']}")
        pin = st.text_input("Trading PIN", type="password", key=f"gpin_{p['nonce']}") if mode == LIVE else ""
        b1, b2 = st.columns(2)
        go = b1.button("Create rule", type="primary", disabled=not sure, use_container_width=True,
                       key=f"ggo_{p['nonce']}")
        if b2.button("Cancel", use_container_width=True, key=f"gback_{p['nonce']}"):
            ss.gtt_pending = None
            st.rerun()
    if not go:
        return
    if mode == LIVE and not hmac.compare_digest(pin.encode(), secret("TRADE_PIN", "").encode()):
        st.error("Wrong trading PIN. Nothing was sent.")
        return
    ss.gtt_pending = None   # cleared before sending, so a rerun can't send it twice
    if mode == PAPER:
        row = simulate_gtt(g)
        ss.gtt_paper.insert(0, row)
        st.success(f"Paper rule {row['gtt_order_id']} saved. Nothing was sent to Upstox.")
        return
    try:
        ids = trader.place_gtt(g)
    except UpstoxError as e:
        st.error(f"Upstox rejected the rule: {e}")
        return
    st.success(f"Rule created on Upstox. GTT id: {', '.join(ids)}.")


def _gtt_list(mode: str, trader: Trader | None) -> None:
    ss = _state()
    st.subheader("Your automatic rules")
    if mode == PAPER:
        rules = [{k: v for k, v in r.items() if k != "ticket"} for r in ss.gtt_paper]
        cancel = lambda gid: ss.__setitem__("gtt_paper", [r for r in ss.gtt_paper if r["gtt_order_id"] != gid])
    else:
        try:
            raw = trader.gtt_orders()
        except UpstoxError as e:
            st.warning(f"Couldn't load your GTT rules: {e}")
            return
        rules = []
        for r in raw:
            legs = {x.get("strategy"): x for x in r.get("rules") or []}
            def leg(name, legs=legs):
                x = legs.get(name)
                return f"₹{x.get('trigger_price')} ({str(x.get('status', '')).lower()})" if x else ""
            entry = legs.get("ENTRY") or {}
            rules.append({"gtt_order_id": r.get("gtt_order_id"), "trading_symbol": r.get("trading_symbol"),
                          "side": entry.get("transaction_type"), "qty": r.get("quantity"),
                          "product": r.get("product"),
                          "entry": f"{entry.get('trigger_type', '')} " + leg("ENTRY"),
                          "target": leg("TARGET"), "stop-loss": leg("STOPLOSS")})
        cancel = trader.cancel_gtt
    if not rules:
        st.caption("No rules yet." if mode == LIVE else "No paper rules yet this session.")
        return
    st.dataframe(pd.DataFrame(rules), use_container_width=True, hide_index=True)
    labels = {f"{r['trading_symbol']} ({r['gtt_order_id']})": r["gtt_order_id"] for r in rules}
    pick = st.selectbox("Cancel a rule", list(labels), key="gtt_cancel_pick")
    sure = st.checkbox("Yes, cancel this rule", key=f"gtt_cancel_sure_{labels[pick]}")
    if st.button("Cancel rule", disabled=not sure, key="gtt_cancel_go"):
        try:
            cancel(labels[pick])
            st.success("Rule cancelled." if mode == PAPER else "Cancel request sent to Upstox.")
            if mode == PAPER:
                st.rerun()
        except UpstoxError as e:
            st.error(f"Couldn't cancel: {e}")


def _gtt_section(mode, trader, key, sym, ltp, table, max_value, secret, held_slot) -> None:
    ss = _state()
    if mode == SANDBOX:
        st.info("Upstox's sandbox doesn't support automatic (GTT) rules. Use Paper to try them, or Live.")
        return
    g = _gtt_form(key, sym, ltp)
    held = _held(table, key, g.product)
    held_slot.metric(f"You hold ({ {'D': 'delivery', 'I': 'intraday', 'MTF': 'MTF'}[g.product]})", held)
    result = check_gtt(g, ltp, held, max_value)
    for e in result.errors:
        st.error(e)
    if st.button("Review rule", type="primary", disabled=not result.ok, key="gtt_review"):
        ss.gtt_pending = {"ticket": asdict(g), "warnings": result.warnings, "nonce": pysecrets.token_hex(4)}
    if ss.gtt_pending:
        if ss.gtt_pending["ticket"] != asdict(g):
            st.info("You changed the rule after reviewing it. Review it again.")
            ss.gtt_pending = None
        else:
            _confirm_gtt(mode, trader, secret)
    st.divider()
    _gtt_list(mode, trader)


def render(token: str | None, table: pd.DataFrame, secret: Callable[[str, str], str],
           funds: dict | None = None) -> None:
    ss = _state()
    st.subheader("Buy or sell")
    modes, why_not = _modes(token, secret)
    mode = st.radio("Mode", modes, horizontal=True, key="trade_mode",
                    help="Paper is simulated. Sandbox is Upstox's test system. Live sends real orders.")
    if LIVE not in modes:
        st.caption("Live trading is off because " + ", and ".join(why_not) + ". See the README to turn it on.")
    if ss.get("trade_mode_was") != mode:   # switching modes drops an unconfirmed ticket
        ss.trade_pending = None
        ss.gtt_pending = None
        ss.trade_mode_was = mode
    {PAPER: st.info, SANDBOX: st.warning, LIVE: st.error}[mode](
        {PAPER: "Paper mode: orders are simulated here. Nothing is sent to Upstox.",
         SANDBOX: "Sandbox mode: orders go to Upstox's test system, not the exchange. No real money.",
         LIVE: "Live mode: orders go to the exchange through your Upstox account."}[mode])

    trader = None
    if mode == SANDBOX:
        trader = Trader(secret("UPSTOX_SANDBOX_TOKEN", ""), sandbox=True)
    elif mode == LIVE:
        trader = Trader(token)

    key, sym, ltp = _pick_stock(token, table)
    if not key:
        return
    m = st.columns(3)
    m[0].metric("Last price", f"₹{ltp:,.2f}" if ltp else "–")
    avail = ((funds or {}).get("equity") or {}).get("available_margin")
    m[1].metric("Cash available", f"₹{float(avail):,.0f}" if avail is not None else "–")

    try:
        max_value = float(secret("MAX_ORDER_VALUE", "") or DEFAULT_MAX_ORDER_VALUE)
    except ValueError:
        max_value = DEFAULT_MAX_ORDER_VALUE

    kind = st.radio("What do you want to do?", (NOW, RULE), horizontal=True, key="tr_kind",
                    help="Order now sends one order straight away. An automatic rule (GTT) waits on Upstox's "
                         "servers until the price hits your level, then buys or sells, even with this site closed.")
    if kind == RULE:
        _gtt_section(mode, trader, key, sym, ltp, table, max_value, secret, m[2])
        return

    t = _ticket_form(key, sym, ltp)
    held = _held(table, key, t.product)
    m[2].metric(f"You hold ({ {'D': 'delivery', 'I': 'intraday', 'MTF': 'MTF'}[t.product]})", held)
    st.caption(f"Estimated value ₹{t.value(ltp):,.2f} · per-order limit ₹{max_value:,.0f}")
    if token and mode != PAPER and st.button("Check margin needed", key="tr_margin"):
        try:
            mg = Trader(token).margin(t)
            st.write(f"Required margin: ₹{float(mg.get('required_margin', 0)):,.2f}  ·  "
                     f"final margin: ₹{float(mg.get('final_margin', 0)):,.2f}")
        except UpstoxError as e:
            st.warning(f"Couldn't get margin: {e}")

    result = check(t, ltp, held, max_value)
    for e in result.errors:
        st.error(e)
    if st.button("Review order", type="primary", disabled=not result.ok, key="tr_review"):
        ss.trade_pending = {"ticket": asdict(t), "warnings": result.warnings, "nonce": pysecrets.token_hex(4)}
    if ss.trade_pending:
        if ss.trade_pending["ticket"] != asdict(t):
            st.info("You changed the order after reviewing it. Review it again.")
            ss.trade_pending = None
        else:
            _confirm(mode, trader, ltp, secret)

    st.divider()
    _order_book(mode, trader)
