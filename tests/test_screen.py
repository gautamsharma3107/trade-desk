import pandas as pd

from tradedesk import demo, market, screen


def _sc():
    q = pd.DataFrame({f"Q{i}": [str(100 + 10 * i), str(10 + i * (1 if i < 8 else 2)), "20"] for i in range(9)},
                     index=pd.Index(["Sales", "Net Profit", "OPM %"], name="Item"))
    sh = pd.DataFrame({"Q1": ["50.0%", "20%"], "Q2": ["50.1%", "19%"], "Q3": ["50.1%", "19%"], "Q4": ["50.2%", "18%"],
                       "Q5": ["51.0%", "18.5%"]}, index=pd.Index(["Promoters", "FIIs"], name="Item"))
    return {"ratios": {"Market Cap": "₹ 50,000 Cr.", "Current Price": "₹ 500", "Stock P/E": "20.0",
                       "Book Value": "₹ 100", "ROCE": "22 %", "ROE": "18 %", "Dividend Yield": "1.0 %"},
            "quarters": q, "shareholding": sh}


def test_metrics_from_screener_page():
    m = screen.metrics(_sc())
    assert m["Mcap (₹ cr)"] == 50000 and m["P/B"] == 5 and m["ROCE %"] == 22
    assert round(m["Sales YoY %"], 1) == round((180 - 140) / 140 * 100, 1)
    assert m["Profit growth qtrs (of 4)"] == 4
    assert round(m["Promoter chg QoQ"], 2) == 0.8 and round(m["Promoter chg 1Y"], 2) == 1.0
    assert m["FII chg QoQ"] == 0.5
    assert m["Quality score"] >= 8


def test_metrics_with_fixture_page_does_not_crash():
    html = open("tests/fixtures/screener_sample.html").read()
    m = screen.metrics(market.parse_screener(html))
    assert m["P/E"] == 24.6 and "Sales YoY %" not in m  # only 2 quarters in the fixture
    assert round(m["Promoter chg QoQ"], 2) == -0.28


def test_apply_filters_and_presets():
    df = pd.DataFrame(demo.screen_rows(["A", "B", "C", "D", "E", "F"]))
    hit = screen.apply_filters(df, {"P/E": (None, 30), "ROE %": (10, None)})
    assert ((hit["P/E"] <= 30) & (hit["ROE %"] >= 10)).all()
    assert screen.apply_filters(df, {"Missing": (1, None)}).empty
    for rules in screen.PRESETS.values():
        screen.apply_filters(df, rules)
