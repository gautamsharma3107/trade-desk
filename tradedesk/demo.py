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
