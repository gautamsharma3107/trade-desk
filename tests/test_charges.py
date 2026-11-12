import datetime as dt

from tradedesk.charges import mtf_interest, order_charges, round_trip
from tradedesk.portfolio import build_table, review
from tradedesk.upstox import financial_year, token_expiry


def test_delivery_buy_100k():
    c = order_charges("Delivery", "BUY", 1000, 100)
    assert c.brokerage == 20
    assert c.stt == 100          # 0.1%
    assert c.stamp_duty == 15    # 0.015%
    assert c.dp_charges == 0
    assert round(c.exchange_txn, 2) == 3.07


def test_delivery_sell_has_dp_and_no_stamp():
    c = order_charges("Delivery", "SELL", 1000, 100)
    assert c.dp_charges == 20 and c.stamp_duty == 0 and c.stt == 100


def test_intraday_small_order_brokerage_capped_by_pct():
    c = order_charges("Intraday", "BUY", 100, 10)   # ₹1,000 -> 0.1% = ₹1
    assert c.brokerage == 1
    assert c.stt == 0
    s = order_charges("Intraday", "SELL", 1000, 100)
    assert s.brokerage == 20 and s.stt == 25


def test_mtf_interest_slabs():
    interest, funded, slabs = mtf_interest(131166, 25, 10)
    assert funded == 98374.5
    assert slabs == 3
    assert interest == 600


def test_round_trip_breakeven_covers_charges():
    rt = round_trip("Delivery", 1000, 1000, 100)
    assert rt["net_pnl"] == -rt["total_charges"]
    assert rt["breakeven_sell_price"] > 1000


def test_financial_year_and_expiry():
    assert financial_year(dt.date(2026, 11, 12)) == "2627"
    assert financial_year(dt.date(2027, 2, 1)) == "2627"
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    exp = token_expiry(dt.datetime(2026, 11, 12, 9, 0, tzinfo=ist))
    assert exp == dt.datetime(2026, 11, 13, 3, 30, tzinfo=ist)


def test_review_flags_stop_loss():
    t = build_table([{"tradingsymbol": "X", "exchange": "NSE", "quantity": 10, "average_price": 100,
                      "last_price": 85, "close_price": 86, "instrument_token": "k"}], [], [])
    flag = review(t.iloc[0].to_dict(), [100.0] * 60 + [85.0], 8, 15, 25)
    assert flag.level in ("SELL?", "REVIEW")
    assert any("stop-loss" in r for r in flag.reasons)
