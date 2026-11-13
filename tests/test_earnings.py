import datetime as dt

import pandas as pd

from tradedesk import demo, earnings, filings


def test_calendar_keeps_only_results_meetings_sorted():
    df = earnings.calendar_rows(demo.EARNINGS_CALENDAR)
    assert list(df["Symbol"]) == ["HINDALCO", "SBIN", "MINDACORP", "EICHERMOT"]
    assert df.iloc[0]["Date"] == pd.Timestamp("2026-11-14")


def test_calendar_reads_board_meeting_shape():
    rows = [{"bm_symbol": "TCS", "sm_name": "Tata Consultancy", "bm_purpose": "Board Meeting",
             "bm_desc": "To consider financial results for the quarter", "bm_date": "09-JAN-2027"}]
    df = earnings.calendar_rows(rows)
    assert df.iloc[0]["Symbol"] == "TCS" and df.iloc[0]["Date"] == pd.Timestamp("2027-01-09")


def test_quarter_end_before_meeting():
    assert earnings.quarter_end_before(dt.date(2026, 11, 14)) == pd.Timestamp("2026-09-30")
    assert earnings.quarter_end_before(dt.date(2026, 9, 30)) == pd.Timestamp("2026-06-30")
    assert earnings.quarter_end_before(dt.date(2027, 1, 9)) == pd.Timestamp("2026-12-31")


RES5 = {"resCmpData": [
    {"re_to_dt": d, "re_net_sale": str(s), "re_net_profit": str(p), "re_basic_eps": str(e), "re_res_type": "U"}
    for d, s, p, e in [("30-SEP-2025", 1000000, 100000, 5.0), ("31-DEC-2025", 1050000, 105000, 5.2),
                       ("31-MAR-2026", 1100000, 110000, 5.5), ("30-JUN-2026", 1150000, 120000, 6.0)]]}


def test_year_ago_bar_picks_same_quarter_last_year():
    res = filings.results_frame(RES5)
    b = earnings.year_ago_bar(res, dt.date(2026, 11, 14))
    assert b["quarter"] == "Sep 2026" and not b["reported"]
    assert b["year_ago"]["revenue"] == 10000 and b["year_ago"]["profit"] == 1000
    assert b["last_q"]["profit"] == 1200


def test_my_stocks_tags_holdings_first(tmp_path, monkeypatch):
    f = tmp_path / "w.txt"
    f.write_text("# comment\ntcs\nSBIN  # bank\n")
    monkeypatch.setattr(earnings, "WATCHLIST_FILE", f)
    got = earnings.my_stocks(["SBIN"], {"buy_ideas": [{"symbol": "HINDALCO"}]})
    assert got == {"SBIN": "held", "HINDALCO": "idea", "TCS": "watchlist"}


def test_parse_yahoo_calendar_converts_revenue_to_crore():
    got = earnings.parse_yahoo_calendar({"Earnings Date": [dt.date(2026, 11, 14)], "Earnings Average": 6.1,
                                         "Revenue Average": 1.2e11})
    assert got["eps_est"] == 6.1 and got["revenue_est_cr"] == 12000


def test_filed_rows_keeps_latest_filing_per_company():
    raw = demo.RESULTS_FILED + [{"symbol": "INFY", "companyName": "Infosys Limited",
                                 "broadCastDate": "12-Nov-2026 18:01:00", "toDate": "30-Sep-2026",
                                 "consolidated": "Non-Consolidated", "audited": "Un-Audited"}]
    df = earnings.filed_rows(raw)
    assert list(df["Symbol"]) == ["HINDALCO", "INFY", "APOLLOHOSP"]
    assert df.iloc[1]["Type"].startswith("Consolidated")
    assert df.iloc[0]["Quarter"] == pd.Timestamp("2026-09-30")


def test_filed_rows_skips_non_results_announcements():
    raw = [{"symbol": "X", "desc": "Change in Director", "an_dt": "13-Nov-2026 10:00:00"},
           {"symbol": "Y", "desc": "Financial Result Updates", "an_dt": "13-Nov-2026 10:00:00"}]
    assert list(earnings.filed_rows(raw)["Symbol"]) == ["Y"]


def test_verdict_strong_for_big_growth():
    v = earnings.verdict(filings.results_frame(demo.RESULTS_CMP["HINDALCO"]))
    assert v["quarter"] == "Sep 2026" and v["level"] == "STRONG"
    assert round(v["profit_yoy"]) == 59 and round(v["rev_yoy"]) == 14


def test_verdict_weak_when_profit_falls_and_estimate_missed():
    v = earnings.verdict(filings.results_frame(demo.RESULTS_CMP["INFY"]), {"eps_est": 17.0})
    assert v["profit_yoy"] < 0 and round(v["eps_vs_est"]) == -9
    assert v["level"] in ("WEAK", "POOR")


def test_verdict_loss_swing_and_no_data():
    res = filings.results_frame({"resCmpData": [
        {"re_to_dt": "30-SEP-2025", "re_net_sale": "1000", "re_net_profit": "-50"},
        {"re_to_dt": "30-SEP-2026", "re_net_sale": "1200", "re_net_profit": "80"}]})
    v = earnings.verdict(res)
    assert any("Swung to a profit" in r for r in v["reasons"]) and v["score"] >= 2
    assert earnings.verdict(pd.DataFrame())["level"] == "NO DATA"
