import pandas as pd

from tradedesk import demo, news


def test_categories():
    assert news.category("Financial Result Updates") == "Results"
    assert news.category("Awarding of order / Receipt of order") == "Order / contract"
    assert news.category("General Updates", "improved operating margin") == "Other"
    assert news.category("Updates", "received a Letter of Award worth Rs 200 crore") == "Order / contract"
    assert news.category("Analysts/Institutional Investor Meet/Con. Call Updates") == "Analyst / investor meet"
    assert news.category("Credit Rating", "ICRA reaffirmed") == "Credit rating"


def test_announcements_frame_newest_first_with_flags():
    df = news.announcements_frame(demo.ANNOUNCEMENTS)
    assert list(df["Symbol"]) == ["HINDALCO", "SBIN", "MINDACORP", "TCS"]
    assert df.iloc[0]["Important"] and not df.iloc[2]["Important"]


def test_deals_frame_value_in_crore():
    df = news.deals_frame(demo.BULK_DEALS, "Bulk")
    top = df.iloc[0]
    assert top["Symbol"] == "MINDACORP" and top["Side"] == "BUY"
    assert round(top["Value (₹ cr)"], 1) == 106.9


def test_insider_net_counts_open_market_only():
    raw = demo.INSIDER + [{"symbol": "MINDACORP", "company": "Minda Corporation Limited", "acqName": "X",
                           "personCategory": "Promoter", "tdpTransactionType": "Buy", "acqMode": "Gift",
                           "secVal": "999000000", "intimDt": "12-Nov-2026"}]
    df = news.insider_frame(raw)
    net = news.insider_net(df)
    m = net[net["Symbol"] == "MINDACORP"].iloc[0]
    assert round(m["Net buy (₹ cr)"], 1) == 17.8 and m["Buys"] == 1
    assert net[net["Symbol"] == "INFY"].iloc[0]["Net buy (₹ cr)"] < 0
    assert list(news.insider_net(df, promoters_only=True)["Symbol"]) == ["MINDACORP"]


def test_empty_frames_have_columns():
    assert "Symbol" in news.announcements_frame([]).columns
    assert news.insider_net(pd.DataFrame()).empty
