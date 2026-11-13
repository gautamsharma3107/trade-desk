import pandas as pd

from tradedesk import demo, flows


def test_fii_dii_frame():
    df = flows.fii_dii_frame(demo.FII_DII)
    fii = df[df["Who"] == "FII"].iloc[0]
    assert fii["Net"] == 7831.08 and fii["Date"] == pd.Timestamp("2026-11-12")


def test_history_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(flows, "HISTORY_FILES", [tmp_path / "repo.csv", tmp_path / "srv.csv"])
    flows.remember(flows.fii_dii_frame(demo.FII_DII))
    later = [dict(r, date="13-Nov-2026", netValue="100") for r in demo.FII_DII]
    hist = flows.remember(flows.fii_dii_frame(later))
    assert len(hist) == 4
    s = flows.flow_summary(hist, 5)
    assert round(s["FII"], 2) == 7931.08 and s["FII_days"] == 2


def test_participant_positioning():
    pos = flows.positioning(flows.parse_participant_oi(demo.PARTICIPANT_OI))
    assert list(pos["Participant"]) == ["Client", "DII", "FII", "Pro"]
    fii = pos[pos["Participant"] == "FII"].iloc[0]
    assert fii["Index fut net"] == -145000 and round(fii["Index fut long %"], 1) == 28.4
    assert fii["Index calls net"] == 170000 and fii["Index puts net"] == 260000


def test_chain_stats_from_upstox_sample():
    chain, spot = flows.chain_from_upstox(demo.option_chain(spot=25300))
    s = flows.chain_stats(chain, spot)
    assert s["spot"] == 25300 and s["atm"] == 25300
    assert s["resistance"] > 25300 > s["support"]
    assert 0.5 < s["pcr"] < 2 and s["straddle"] > 0
    assert chain["call_chg_oi"].iloc[0] > 0


def test_max_pain_simple():
    chain = pd.DataFrame({"strike": [90.0, 100.0, 110.0], "call_oi": [0, 100, 0], "put_oi": [0, 100, 0]})
    assert flows.max_pain(chain) == 100


def test_chain_from_nse_shape():
    data = {"records": {"underlyingValue": 25310.5, "data": [
        {"strikePrice": 25300, "expiryDates": "18-Nov-2026",
         "CE": {"openInterest": 1000, "changeinOpenInterest": 50, "lastPrice": 120, "impliedVolatility": 11},
         "PE": {"openInterest": 1500, "changeinOpenInterest": -20, "lastPrice": 110, "impliedVolatility": 12}},
        {"strikePrice": 25300, "expiryDates": "25-Nov-2026", "CE": {"openInterest": 9}, "PE": {}}]}}
    df, spot = flows.chain_from_nse(data, "18-Nov-2026")
    assert spot == 25310.5 and len(df) == 1 and df.iloc[0]["put_oi"] == 1500
