"""Made-up sample data so the app can be tried before logging in to Upstox."""
import math

HOLDINGS = [
    {"tradingsymbol": "TCS", "exchange": "NSE", "quantity": 5, "average_price": 3900.0,
     "last_price": 3725.0, "close_price": 3740.0, "instrument_token": "NSE_EQ|INE467B01029"},
    {"tradingsymbol": "ITC", "exchange": "NSE", "quantity": 120, "average_price": 402.0,
     "last_price": 418.5, "close_price": 415.0, "instrument_token": "NSE_EQ|INE154A01025"},
]
MTF = [
    {"trading_symbol": "BHARTIARTL", "exchange": "NSE", "product": "MTF", "quantity": 20,
     "average_price": 2050.0, "buy_price": 2050.0, "last_price": 2092.0, "close_price": 2109.0,
     "instrument_token": "NSE_EQ|INE397D01024"},
]
POSITIONS = []
FUNDS = {"equity": {"available_margin": 25000.0, "used_margin": 41000.0}}
CHARGES = {"total": 1840.5, "brokerage": 520.0,
           "taxes": {"gst": 160.2, "stt": 980.0, "stamp_duty": 96.0},
           "charges": {"transaction": 44.1, "clearing": 0, "ipft": 0.2, "others": 0,
                       "sebi_turnover": 1.5, "demat_transaction": 38.5}}


def candles(last: float, trend: float, n: int = 80) -> list[float]:
    """Synthetic closing prices ending at `last`."""
    return [last * (1 - trend * (n - i) / n) + last * 0.01 * math.sin(i / 3) for i in range(n)]


# Realised trades in Upstox P&L report format, for the P&L tab's sample view.
PNL_TRADES = {
    "EQ": [
        {"scrip_name": "TCS", "isin": "INE467B01029", "quantity": 4, "trade_type": "EQ", "buy_date": "15-03-2025",
         "buy_average": 3480.0, "buy_amount": 13920.0, "sell_date": "22-04-2026", "sell_average": 3890.0, "sell_amount": 15560.0},
        {"scrip_name": "HINDALCO", "isin": "INE038A01020", "quantity": 50, "trade_type": "EQ", "buy_date": "05-05-2026",
         "buy_average": 640.0, "buy_amount": 32000.0, "sell_date": "18-07-2026", "sell_average": 702.5, "sell_amount": 35125.0},
        {"scrip_name": "SBIN", "isin": "INE062A01020", "quantity": 30, "trade_type": "EQ", "buy_date": "12-06-2026",
         "buy_average": 812.0, "buy_amount": 24360.0, "sell_date": "12-06-2026", "sell_average": 805.4, "sell_amount": 24162.0},
        {"scrip_name": "MINDACORP", "isin": "INE842C01021", "quantity": 40, "trade_type": "EQ", "buy_date": "01-08-2026",
         "buy_average": 590.0, "buy_amount": 23600.0, "sell_date": "30-09-2026", "sell_average": 655.0, "sell_amount": 26200.0},
        {"scrip_name": "INFY", "isin": "INE009A01021", "quantity": 15, "trade_type": "EQ", "buy_date": "02-09-2026",
         "buy_average": 1620.0, "buy_amount": 24300.0, "sell_date": "21-10-2026", "sell_average": 1540.0, "sell_amount": 23100.0},
        {"scrip_name": "RELIANCE", "isin": "INE002A01018", "quantity": 20, "trade_type": "EQ", "buy_date": "14-10-2026",
         "buy_average": 1395.0, "buy_amount": 27900.0, "sell_date": "14-10-2026", "sell_average": 1408.0, "sell_amount": 28160.0},
    ],
    "FO": [
        {"scrip_name": "NIFTY 25000 CE", "isin": "", "quantity": 75, "trade_type": "OPT", "buy_date": "10-07-2026",
         "buy_average": 120.0, "buy_amount": 9000.0, "sell_date": "10-07-2026", "sell_average": 158.0, "sell_amount": 11850.0},
        {"scrip_name": "BANKNIFTY 56000 PE", "isin": "", "quantity": 35, "trade_type": "OPT", "buy_date": "20-08-2026",
         "buy_average": 210.0, "buy_amount": 7350.0, "sell_date": "21-08-2026", "sell_average": 95.0, "sell_amount": 3325.0},
        {"scrip_name": "RELIANCE FUT", "isin": "", "quantity": 500, "trade_type": "FUT", "buy_date": "03-10-2026",
         "buy_average": 1380.0, "buy_amount": 690000.0, "sell_date": "09-10-2026", "sell_average": 1392.0, "sell_amount": 696000.0},
    ],
}
PNL_CHARGES = {"EQ": 612.4, "FO": 388.9}

# NSE event-calendar rows, shown on the Earnings tab only when NSE can't be reached.
EARNINGS_CALENDAR = [
    {"symbol": "HINDALCO", "company": "Hindalco Industries Limited", "purpose": "Financial Results",
     "bm_desc": "To consider and approve the unaudited financial results for the quarter ended September 30, 2026",
     "date": "14-Nov-2026"},
    {"symbol": "SBIN", "company": "State Bank of India", "purpose": "Financial Results/Dividend",
     "bm_desc": "Quarterly results", "date": "17-Nov-2026"},
    {"symbol": "MINDACORP", "company": "Minda Corporation Limited", "purpose": "Financial Results",
     "bm_desc": "Quarterly results", "date": "18-Nov-2026"},
    {"symbol": "EICHERMOT", "company": "Eicher Motors Limited", "purpose": "Financial Results",
     "bm_desc": "Quarterly results", "date": "19-Nov-2026"},
    {"symbol": "ABC", "company": "Sample Ltd", "purpose": "Fund Raising", "bm_desc": "Raise funds via QIP",
     "date": "19-Nov-2026"},
]

# NSE financial-results filings and results comparisons, for the results feed's sample view.
RESULTS_FILED = [
    {"symbol": "HINDALCO", "companyName": "Hindalco Industries Limited", "broadCastDate": "13-Nov-2026 16:42:10",
     "toDate": "30-Sep-2026", "consolidated": "Consolidated", "audited": "Un-Audited"},
    {"symbol": "APOLLOHOSP", "companyName": "Apollo Hospitals Enterprise Limited",
     "broadCastDate": "12-Nov-2026 15:58:31", "toDate": "30-Sep-2026", "consolidated": "Consolidated",
     "audited": "Un-Audited"},
    {"symbol": "INFY", "companyName": "Infosys Limited", "broadCastDate": "12-Nov-2026 18:05:00",
     "toDate": "30-Sep-2026", "consolidated": "Consolidated", "audited": "Un-Audited"},
]


def _cmp(rows):
    return {"resCmpData": [{"re_to_dt": d, "re_net_sale": str(s * 100), "re_net_profit": str(p * 100),
                            "re_basic_eps": str(e), "re_res_type": "U"} for d, s, p, e in rows]}


RESULTS_CMP = {  # ₹ crore, converted to NSE's ₹ lakh above
    "HINDALCO": _cmp([("30-SEP-2025", 58203, 4741, 21.3), ("31-DEC-2025", 58390, 3735, 16.8),
                      ("31-MAR-2026", 64890, 5283, 23.8), ("30-JUN-2026", 61202, 4004, 18.0),
                      ("30-SEP-2026", 66320, 7533, 33.9)]),
    "APOLLOHOSP": _cmp([("30-SEP-2025", 5589, 379, 26.4), ("31-DEC-2025", 5527, 372, 25.9),
                        ("31-MAR-2026", 5592, 390, 27.1), ("30-JUN-2026", 5842, 433, 30.1),
                        ("30-SEP-2026", 6763, 500, 34.8)]),
    "INFY": _cmp([("30-SEP-2025", 40986, 6506, 15.7), ("31-DEC-2025", 41764, 6806, 16.4),
                  ("31-MAR-2026", 40925, 7033, 16.9), ("30-JUN-2026", 42279, 6921, 16.7),
                  ("30-SEP-2026", 43010, 6380, 15.4)]),
}


def price_history(seed: int, start: str = "2023-11-01", end: str = "2026-11-13", last: float = 1000.0):
    """A made-up daily OHLC series (weekdays) for sample charts when Yahoo can't be reached."""
    import numpy as np
    import pandas as pd

    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.014, len(idx))
    for d in sample_result_times():  # bigger moves on results days
        pos = idx.searchsorted(d.normalize() + pd.Timedelta(days=1))
        if pos < len(idx):
            rets[pos] += rng.normal(0, 0.05)
    close = last * np.exp(np.cumsum(rets) - np.cumsum(rets)[-1])
    opens = close / np.exp(rets) * (1 + rets * 0.6)
    return pd.DataFrame({"Open": opens, "High": np.maximum(opens, close) * 1.006,
                         "Low": np.minimum(opens, close) * 0.994, "Close": close, "Volume": 1e6}, index=idx)


def sample_result_times():
    import pandas as pd

    return [pd.Timestamp(f"{d} 16:30") for d in
            ("2026-11-12", "2026-08-11", "2026-05-20", "2026-02-12", "2025-11-13", "2025-08-12", "2025-05-21",
             "2025-02-13", "2024-11-12")]

# NSE-shaped rows for the News tab's sample view.
ANNOUNCEMENTS = [
    {"symbol": "HINDALCO", "sm_name": "Hindalco Industries Limited", "desc": "Financial Result Updates",
     "attchmntText": "Unaudited financial results for the quarter ended September 30, 2026",
     "an_dt": "13-Nov-2026 16:42:10", "attchmntFile": ""},
    {"symbol": "SBIN", "sm_name": "State Bank of India", "desc": "Credit Rating",
     "attchmntText": "CRISIL has reaffirmed AAA/Stable on the bank's bonds", "an_dt": "13-Nov-2026 11:05:00",
     "attchmntFile": ""},
    {"symbol": "MINDACORP", "sm_name": "Minda Corporation Limited", "desc": "Analysts/Institutional Investor Meet/Con. Call Updates",
     "attchmntText": "Schedule of analyst meet on 18 Nov 2026", "an_dt": "12-Nov-2026 19:20:00", "attchmntFile": ""},
    {"symbol": "TCS", "sm_name": "Tata Consultancy Services Limited", "desc": "Awarding of order / Receipt of order",
     "attchmntText": "Multi-year contract with a European retailer", "an_dt": "12-Nov-2026 09:12:00",
     "attchmntFile": ""},
]
BULK_DEALS = [
    {"BD_DT_DATE": "13-Nov-2026", "BD_SYMBOL": "MINDACORP", "BD_SCRIP_NAME": "Minda Corporation Limited",
     "BD_CLIENT_NAME": "SAMPLE MUTUAL FUND", "BD_BUY_SELL": "BUY", "BD_QTY_TRD": "1500000", "BD_TP_WATP": "712.40",
     "BD_REMARKS": "-"},
    {"BD_DT_DATE": "12-Nov-2026", "BD_SYMBOL": "ABCSMALL", "BD_SCRIP_NAME": "Abc Small Caps Ltd",
     "BD_CLIENT_NAME": "SAMPLE TRADING LLP", "BD_BUY_SELL": "SELL", "BD_QTY_TRD": "800000", "BD_TP_WATP": "54.10",
     "BD_REMARKS": "-"},
]
INSIDER = [
    {"symbol": "MINDACORP", "company": "Minda Corporation Limited", "acqName": "Sample Promoter Holdings",
     "personCategory": "Promoter Group", "tdpTransactionType": "Buy", "acqMode": "Market Purchase",
     "secAcq": "250000", "secVal": "178000000", "befAcqSharesPer": "64.10", "afterAcqSharesPer": "64.20",
     "acqfromDt": "10-Nov-2026", "acqtoDt": "11-Nov-2026", "intimDt": "12-Nov-2026"},
    {"symbol": "INFY", "company": "Infosys Limited", "acqName": "Sample Employee",
     "personCategory": "Key Managerial Personnel", "tdpTransactionType": "Sell", "acqMode": "Market Sale",
     "secAcq": "5000", "secVal": "8000000", "befAcqSharesPer": "0.01", "afterAcqSharesPer": "0.00",
     "acqfromDt": "07-Nov-2026", "acqtoDt": "07-Nov-2026", "intimDt": "10-Nov-2026"},
]
