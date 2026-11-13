from unittest import mock

import pytest

from tradedesk import orders
from tradedesk.orders import Ticket, Trader, check, simulate_fill

KEY = "NSE_EQ|INE002A01018"


def ticket(**kw):
    base = dict(instrument_key=KEY, symbol="RELIANCE", side="BUY", qty=2, product="D",
                order_type="LIMIT", price=1500.0)
    base.update(kw)
    return Ticket(**base)


def test_payload_limit():
    p = ticket().payload()
    assert p == {"quantity": 2, "product": "D", "validity": "DAY", "price": 1500.0, "tag": "tradedesk",
                 "instrument_token": KEY, "order_type": "LIMIT", "transaction_type": "BUY",
                 "disclosed_quantity": 0, "trigger_price": 0, "is_amo": False, "slice": False}


def test_payload_zeroes_unused_prices():
    assert ticket(order_type="MARKET", price=1500, trigger_price=1490).payload()["price"] == 0
    assert ticket(order_type="MARKET", trigger_price=1490).payload()["trigger_price"] == 0
    p = ticket(order_type="SL-M", side="SELL", trigger_price=1490).payload()
    assert p["price"] == 0 and p["trigger_price"] == 1490


def test_ok_limit_buy():
    c = check(ticket(), ltp=1500)
    assert c.ok, c.errors


def test_value_cap_blocks():
    c = check(ticket(qty=100), ltp=1500, max_value=50_000)
    assert not c.ok and "per-order limit" in c.errors[0]


def test_cannot_sell_what_you_dont_hold():
    assert not check(ticket(side="SELL"), ltp=1500, held_qty=0).ok
    assert not check(ticket(side="SELL", qty=5), ltp=1500, held_qty=3).ok
    assert check(ticket(side="SELL", qty=3), ltp=1500, held_qty=3).ok
    # intraday short is allowed
    assert check(ticket(side="SELL", product="I"), ltp=1500, held_qty=0).ok


def test_stop_loss_rules():
    assert not check(ticket(order_type="SL", trigger_price=0), ltp=1500).ok
    assert not check(ticket(order_type="SL", side="SELL", price=1500, trigger_price=1490), ltp=1510,
                     held_qty=5).ok
    assert check(ticket(order_type="SL", side="SELL", price=1480, trigger_price=1490), ltp=1510,
                 held_qty=5).ok
    assert not check(ticket(order_type="SL", side="BUY", price=1500, trigger_price=1510), ltp=1490).ok


def test_bad_inputs():
    assert not check(ticket(qty=0), ltp=1500).ok
    assert not check(ticket(price=0), ltp=1500).ok
    assert not check(ticket(instrument_key=""), ltp=1500).ok
    assert not check(ticket(product="X"), ltp=1500).ok


def test_warnings():
    w = " ".join(check(ticket(price=1700), ltp=1500).warnings)
    assert "+13.3%" in w and "fill straight away" in w
    assert any("Market order" in x for x in check(ticket(order_type="MARKET"), ltp=1500).warnings)


def test_paper_fill():
    assert simulate_fill(ticket(price=1510), ltp=1500)["status"] == "complete"
    assert simulate_fill(ticket(price=1490), ltp=1500)["status"] == "open"
    row = simulate_fill(ticket(order_type="MARKET", price=0), ltp=1500)
    assert row["status"] == "complete" and row["average_price"] == 1500


def _resp(body, status=200):
    r = mock.Mock(status_code=status)
    r.json.return_value = body
    return r


@pytest.mark.parametrize("sandbox,host", [(False, orders.LIVE_ORDER_HOST), (True, orders.SANDBOX_HOST)])
def test_place_hits_right_host(sandbox, host):
    tr = Trader("tok", sandbox=sandbox)
    with mock.patch.object(tr.s, "post", return_value=_resp(
            {"status": "success", "data": {"order_ids": ["1"]}})) as post:
        assert tr.place(ticket()) == ["1"]
    url = post.call_args.args[0]
    assert url == f"{host}/v3/order/place"
    assert post.call_args.kwargs["json"]["instrument_token"] == KEY


def test_place_error_raises():
    tr = Trader("tok")
    with mock.patch.object(tr.s, "post", return_value=_resp(
            {"status": "error", "errors": [{"message": "Insufficient funds"}]}, 400)):
        with pytest.raises(orders.UpstoxError, match="Insufficient"):
            tr.place(ticket())


def test_ltp_keyed_by_instrument():
    tr = Trader("tok")
    with mock.patch.object(tr.s, "get", return_value=_resp(
            {"status": "success", "data": {"NSE_EQ:RELIANCE": {"last_price": 1501.5, "instrument_token": KEY}}})):
        assert tr.ltp([KEY]) == {KEY: 1501.5}
