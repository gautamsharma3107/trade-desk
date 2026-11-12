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
