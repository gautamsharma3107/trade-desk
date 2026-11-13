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
