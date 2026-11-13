import json

import pandas as pd

from tradedesk import demo, journal, pnl


def _df():
    return pnl.trades_frame(demo.PNL_TRADES)


def test_stats_on_sample_trades():
    s = journal.stats(_df())
    assert s["trades"] == 9 and s["wins"] == 6 and s["losses"] == 3
    assert round(s["win_rate"]) == 67
    assert s["avg_loss"] < 0 < s["avg_win"] and s["payoff"] > 0
    assert s["best"] == 6000 and s["worst"] == -4025


def test_enrich_and_by_type():
    e = journal.enrich(_df())
    tcs = e[e["scrip"] == "TCS"].iloc[0]
    assert tcs["days"] == 403 and round(tcs["ret_pct"], 1) == 11.8
    bt = journal.by_type(_df())
    assert set(bt["Type"]) >= {"Intraday", "Options", "Futures"}


def test_lessons_flags_holding_losers():
    s = {"trades": 10, "win_rate": 40, "avg_win": 1000, "avg_loss": -2000, "payoff": 0.5, "days_win": 3,
         "days_loss": 12, "expectancy": -800, "profit_factor": 0.3, "loss_streak": 5}
    text = " ".join(journal.lessons(s))
    assert "bigger than your average win" in text and "selling winners early" in text and "losing run" in text


def test_ideas_history_and_scoring(tmp_path):
    (tmp_path / "2026-11-12.json").write_text(json.dumps(
        {"date": "2026-11-12", "buy_ideas": [{"symbol": "AAA", "approx_price": 100, "target": 110}],
         "avoid": [{"symbol": "BBB", "reason": "weak"}]}))
    cur = {"date": "2026-11-13", "buy_ideas": [{"symbol": "AAA", "approx_price": 101, "target": 110},
                                               {"symbol": "CCC", "approx_price": 50}]}
    hist = journal.load_ideas_history(cur, tmp_path)
    df = journal.ideas_frame(hist)
    assert list(df["Symbol"]) == ["AAA", "BBB", "CCC"]  # AAA kept from its first day
    idx = pd.to_datetime(["2026-11-11", "2026-11-12", "2026-11-13"])
    px = pd.DataFrame({"Close": [95, 100, 108], "High": [96, 104, 112], "Low": [94, 98, 105]}, index=idx)
    r = journal.score_idea(df.iloc[0].to_dict(), px, {"AAA"})
    assert round(r["Return %"], 1) == 8.0 and r["Target hit"] == "13 Nov" and r["Worked"] == "yes"
    assert r["Acted on"] == "yes" and round(r["Worst %"], 1) == -2.0
    avoid = journal.score_idea(df.iloc[1].to_dict(), px, set())
    assert avoid["Worked"] == "no"


def test_repo_ideas_history_loads():
    hist = journal.load_ideas_history()
    assert [h["date"] for h in hist][:2] == ["2026-11-12", "2026-11-13"]
