# Trade Desk

A private daily dashboard for an Upstox account. It has four tabs:

- **Portfolio:** delivery holdings, MTF positions and open positions, with live P&L and anything closed today.
- **Charges:** what you've paid this financial year (brokerage, STT, GST, stamp duty, exchange, DP, SEBI), straight from Upstox. It also shows MTF interest on open positions and has a calculator for delivery, intraday and MTF round trips, including the breakeven sell price.
- **Sell check:** flags each holding as HOLD, REVIEW or SELL? using your stop-loss and target, its 20- and 50-day averages, MTF interest drag and the daily research notes.
- **Daily ideas:** earnings-based buy ideas, stocks to avoid and results to watch, read from `data/ideas.json`. A scheduled research job updates that file every weekday morning.

The app is **read-only**. It never places, changes or cancels orders. Ideas are research, not advice. Check the live price and your own risk before trading.

## 1. Get an Upstox API key (one time)

1. Go to <https://account.upstox.com/developer/apps> and create a new app.
2. Set the **Redirect URL** to the address where the app runs:
   - for Streamlit Cloud, the app URL, e.g. `https://trade-desk-yourname.streamlit.app`
   - to run it on your own computer, `http://localhost:8501`
3. Copy the **API key** and **API secret**.

## 2. Host it on Streamlit Community Cloud (free, private)

1. Sign in at <https://share.streamlit.io> with GitHub.
2. Click **Create app**, pick this repo, branch `main`, file `app.py`.
3. Under **Advanced settings → Secrets**, paste:

   ```toml
   UPSTOX_API_KEY = "..."
   UPSTOX_API_SECRET = "..."
   UPSTOX_REDIRECT_URI = "https://<your-app>.streamlit.app"
   APP_PASSWORD = "..."   # optional second lock
   ```

4. Deploy. Because the repo is private, the app is private too. Only viewers you invite (under **Share**) can open it.
5. Put the final app URL into the Upstox app's Redirect URL if it differs from what you entered.

## 3. Daily use

Open the app and click **Login with Upstox**. Upstox tokens expire at 3:30 AM IST, so you log in once each morning. The token stays in the app's memory only and is never saved to disk or to the repo.

## Run locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # fill in your keys
streamlit run app.py
```

With no keys, the app runs on made-up sample data.

## Charges: how they're worked out

Rates come from <https://upstox.com/brokerage-charges/> (checked 12 Nov 2026) and live in `tradedesk/charges.py`:

| Charge | Delivery | Intraday | MTF |
|---|---|---|---|
| Brokerage | ₹20/order | ₹20 or 0.1%, whichever is lower | ₹20/order |
| STT | 0.1% buy and sell | 0.025% sell | 0.1% buy and sell |
| Exchange (NSE) | 0.00307% | 0.00307% | 0.00307% |
| Stamp duty | 0.015% buy | 0.003% buy | 0.015% buy |
| SEBI | ₹10/crore | ₹10/crore | ₹10/crore |
| DP | ₹20 + GST per stock, on sell | none | ₹20 + GST per stock, on sell |
| Pledge/unpledge | none | none | ₹20 + GST per stock |
| Interest | none | none | ₹20/day per ₹40,000 funded |
| GST | 18% on brokerage, exchange, DP, pledge | same | same |

The "Charges you've paid" section uses Upstox's own `trade/profit-loss/charges` API, so it is exact. The calculator gives estimates. Your contract note is the final word.

## Daily ideas file

`data/ideas.json` has `date`, `market_summary`, `buy_ideas[]` (symbol, name, approx_price, target, target_source, thesis, risks, sources), `avoid[]`, `watch_today[]`, `portfolio_notes{SYMBOL: note}` and `disclaimer`. When the file is pushed, Streamlit Cloud picks up the change on its own.

## Tests

```bash
pip install pytest && python -m pytest -q
```
