from tradedesk import filings

SHP = [
    {"symbol": "ABC", "date": "30-SEP-2026", "pr_and_prgrp": "50.11", "public_val": "49.89", "employeeTrusts": "0",
     "submissionDate": "14-OCT-2026", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_2.xml"},
    {"symbol": "ABC", "date": "30-JUN-2026", "pr_and_prgrp": "50.39", "public_val": "49.61", "employeeTrusts": "0",
     "submissionDate": "15-JUL-2026", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1.xml"},
]
RES = {"resCmpData": [
    {"re_to_dt": "30-SEP-2026", "re_net_sale": "12826000", "re_total_inc": "13147400", "re_oth_tot_exp": "11987700",
     "re_pro_loss_bef_tax": "1159700", "re_net_profit": "872100", "re_basic_eps_for_cont_dic_opr": "6.44",
     "re_res_type": "U"},
    {"re_to_dt": "30-JUN-2026", "re_net_sale": "12000000", "re_net_profit": None, "re_con_pro_loss": "800000",
     "re_basic_eps": "5.9", "re_res_type": "A"},
]}


def test_shareholding_frame_sorted_oldest_first():
    df = filings.shareholding_frame(SHP)
    assert list(df["Quarter"]) == ["30-JUN-2026", "30-SEP-2026"]
    assert df.iloc[-1]["Promoters %"] == 50.11 and df.iloc[-1]["XBRL"].endswith("SHP_2.xml")


def test_results_frame_converts_lakh_to_crore():
    df = filings.results_frame(RES)
    assert list(df["Quarter ending"]) == ["30-JUN-2026", "30-SEP-2026"]
    last = df.iloc[-1]
    assert last["Revenue (₹ cr)"] == 128260 and last["Net profit (₹ cr)"] == 8721
    assert round(last["Net margin %"], 1) == 6.8 and last["Audited"] == "No"
    assert df.iloc[0]["Net profit (₹ cr)"] == 8000 and df.iloc[0]["EPS (₹)"] == 5.9


def test_links():
    ar = filings.annual_report_links([
        {"fromYr": "2024", "toYr": "2025", "broadcast_dttm": "18-JUL-2025 18:34:53", "fileName": "https://x/a.pdf"},
        {"fromYr": "2025", "toYr": "2026", "broadcast_dttm": "20-JUL-2026 10:00:00", "fileName": "https://x/b.pdf"}])
    assert ar[0] == {"Year": "FY 2025-26", "Filed": "20-JUL-2026", "Link": "https://x/b.pdf"}
    assert filings.brsr_links([{"fyFrom": "2025", "fyTo": "2026", "attachmentFile": "https://x/brsr.pdf",
                                "submissionDate": "21-JUL-2026"}])[0]["Year"] == "FY 2025-26"
    links = filings.official_links("M&M", "Mahindra & Mahindra")
    assert "symbol=M%26M" in links["NSE quote & filings"]


def test_extract_json_from_reply():
    d = filings._extract_json('Here you go:\n```json\n{"sells": [{"what": "cars", "to": "buyers"}], "buys": []}\n```')
    assert d["sells"][0]["what"] == "cars"
