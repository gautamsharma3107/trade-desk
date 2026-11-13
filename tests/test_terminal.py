import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from tradedesk import demo, market, pnl

FIX = Path(__file__).parent / "fixtures"


def test_period_chunks_split_by_financial_year():
    p = pnl.Period("cal", dt.date(2026, 1, 1), dt.date(2026, 11, 13))
    assert p.chunks() == [("2526", "01-01-2026", "31-03-2026"), ("2627", "01-04-2026", "13-11-2026")]
    labels = [x.label for x in pnl.periods(dt.date(2026, 11, 13))]
    assert labels[0].startswith("FY 2026-27")


def test_buckets():
    d = pd.Timestamp
    assert pnl.bucket("EQ", "EQ", d("2026-06-12"), d("2026-06-12")) == "Intraday"
    assert pnl.bucket("EQ", "EQ", d("2025-03-15"), d("2026-04-22")) == "Delivery (long-term)"
    assert pnl.bucket("EQ", "EQ", d("2026-05-05"), d("2026-07-18")) == "Delivery (short-term)"
    assert pnl.bucket("FO", "OPT", d("2026-07-10"), d("2026-07-10")) == "Options"
    assert pnl.bucket("FO", "FUT", d("2026-07-10"), d("2026-07-11")) == "Futures"


def test_pnl_summary_from_demo():
    df = pnl.trades_frame(demo.PNL_TRADES)
    fy = pnl.periods(dt.date(2026, 11, 13))[0]
    df = pnl.in_period(df, fy)
    assert len(df) == 9
    seg = pnl.segment_totals(df, demo.PNL_CHARGES).set_index("Segment")
    assert round(seg.loc["Equity", "Gross P&L"]) == 1640 + 3125 - 198 + 2600 - 1200 + 260
    assert seg.loc["F&O", "Net P&L"] == seg.loc["F&O", "Gross P&L"] - 388.9
    sm = pnl.summary(df).set_index("Segment")
    assert sm.loc["Intraday", "Trades"] == 2
    assert pnl.max_drawdown(df) < 0
    assert not pnl.monthly(df).empty and pnl.by_stock(df).iloc[0]["scrip"] == "RELIANCE FUT"


def test_charges_total():
    assert pnl.charges_total(demo.CHARGES) == 1840.5
    assert pnl.charges_total({"brokerage": 10, "taxes": {"gst": 1.8}, "charges": {"sebi_turnover": 0.2}}) == 12.0
    assert pnl.charges_total({}) == 0


def test_parse_screener():
    d = market.parse_screener((FIX / "screener_sample.html").read_text())
    assert d["name"] == "Sample Industries Ltd"
    assert d["warehouse_id"] == "6598251"
    assert market.ratio_number(d["ratios"], "Market Cap") == 1905420
    assert market.ratio_number(d["ratios"], "Stock P/E") == 24.6
    assert market.ratio_number(d["ratios"], "High / Low") == 1609
    assert "widgets" in d["about"] and "Key Points" in d["key_points"]
    assert list(d["quarters"].index) == ["Sales", "Net Profit"]
    long = market.shareholding_long(d["shareholding"])
    assert set(long["Category"]) == {"Promoters", "FIIs", "DIIs", "Government", "Public"}
    latest = long[long["Quarter"] == "Sep 2026"].set_index("Category")["Percent"]
    assert latest["Promoters"] == 50.11 and round(latest.sum(), 2) == 100.0


def test_parse_holders():
    payload = {"Life Insurance Corporation of India": {"Jun 2026": "6.10", "Sep 2026": "6.25", "setAttributes": {}},
               "bad": "x"}
    rows = market.parse_holders(payload, "DIIs")
    assert rows == [{"Category": "DIIs", "Holder": "Life Insurance Corporation of India", "Stake %": 6.25,
                     "As of": "Sep 2026"}]


def test_parse_equity_list():
    text = ("SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
            "RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10\n"
            "SOMEBOND,Some Bond,N1,01-JAN-2020,1000,1,INE000X01010,1000\n")
    df = market.parse_equity_list(text)
    assert list(df["symbol"]) == ["RELIANCE"]
    assert df.iloc[0]["instrument_key"] == "NSE_EQ|INE002A01018"


def test_stats_from_history():
    idx = pd.bdate_range("2025-11-13", periods=250)
    close = pd.Series(np.linspace(100, 150, 250), index=idx)
    h = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": 1000})
    s = market.stats_from_history(h)
    assert round(s["ltp"]) == 150 and s["high_52w"] == 151 and s["low_52w"] == 99
    assert s["change_pct"] > 0 and round(s["ret_1y"]) == 50


def test_market_status():
    ist = market.IST
    assert market.market_status(dt.datetime(2026, 11, 13, 10, 0, tzinfo=ist)) == "OPEN"
    assert market.market_status(dt.datetime(2026, 11, 13, 16, 0, tzinfo=ist)) == "CLOSED"
    assert market.market_status(dt.datetime(2026, 11, 14, 10, 0, tzinfo=ist)) == "CLOSED"


def test_bundled_lists():
    n = market.nifty50()
    assert len(n) == 50 and len({r["symbol"] for r in n}) == 50
    notes = market.company_notes()
    for sym, c in notes.items():
        if sym.startswith("_"):
            continue
        assert c["sells"] and c["buys"], sym
        assert all("what" in x and "to" in x for x in c["sells"]), sym
        assert all("what" in x and "from" in x for x in c["buys"]), sym
