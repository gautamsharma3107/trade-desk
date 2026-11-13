import datetime as dt

import pandas as pd

from tradedesk import demo, pnl, tax


def test_heads_on_sample_trades():
    h = tax.heads(pnl.trades_frame(demo.PNL_TRADES), fo_charges=388.9).set_index("Head")
    assert h.loc["LTCG", "Net"] == 1640
    assert h.loc["STCG", "Net"] == 3125 + 2600 - 1200
    assert h.loc["Speculative", "Net"] == -198 + 260
    assert round(h.loc["F&O", "Net"], 1) == round(2850 - 4025 + 6000 - 388.9, 1)


def test_set_off_rules():
    taxable, cf, notes = tax.set_off({"STCG": -50_000, "LTCG": 30_000, "Speculative": -2_000, "F&O": -10_000})
    assert taxable == {"STCG": 0.0, "LTCG": 0.0, "Speculative": 0.0, "F&O": 0.0}
    assert cf == {"STCG": 20_000, "Speculative": 2_000, "F&O": 10_000}
    taxable, cf, _ = tax.set_off({"STCG": 40_000, "LTCG": -5_000, "Speculative": 0, "F&O": -15_000})
    assert taxable["STCG"] == 25_000 and cf == {"LTCG": 5_000}


def test_estimate_uses_ltcg_exemption_and_cess():
    est = tax.estimate({"STCG": 100_000, "LTCG": 200_000, "Speculative": 10_000, "F&O": 0}, 0.30)
    assert est["by_head"]["STCG"] == 20_000 and est["by_head"]["LTCG"] == 75_000 * 0.125
    assert est["ltcg_exempt_left"] == 0
    assert round(est["total"], 2) == round((20_000 + 9_375 + 3_000) * 1.04, 2)


def test_advance_tax_schedule():
    s = tax.advance_tax_schedule(100_000, 2026, dt.date(2026, 11, 14))
    assert list(s["Cumulative amount"]) == [15_000, 45_000, 75_000, 100_000]
    assert s.iloc[3]["Due by"] == dt.date(2027, 3, 15) and list(s["Status"])[:3] == ["past", "past", "upcoming"]


def test_harvest():
    table = pd.DataFrame([
        {"symbol": "AAA", "type": "Delivery", "qty": 10, "avg_price": 100, "ltp": 80, "pnl": -200.0},
        {"symbol": "BBB", "type": "Intraday", "qty": 10, "avg_price": 100, "ltp": 50, "pnl": -500.0},
        {"symbol": "CCC", "type": "MTF", "qty": 10, "avg_price": 100, "ltp": 130, "pnl": 300.0}])
    losers, winners = tax.harvest(table, {"STCG": 150.0, "LTCG": 1000.0, "Speculative": 0, "F&O": 0}, 125_000)
    assert list(losers["Stock"]) == ["AAA"]
    assert round(losers.iloc[0]["Tax saved (approx)"], 2) == round((150 * 0.2 + 50 * 0.125) * 1.04, 2)
    assert winners.iloc[0]["Tax-free if long-term"] == 300
