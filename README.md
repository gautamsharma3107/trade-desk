# Trade Desk

A private, Bloomberg-style terminal for an Upstox account: black and amber, dense tables, a live index strip (Nifty, Sensex, Bank Nifty, VIX, USD/INR, Brent, gold, US markets) across the top. Tabs:

- **Portfolio:** delivery holdings, MTF positions and open positions, with live P&L and anything closed today.
- **P&L:** realised profit and loss for this financial year (switch to calendar year or last FY) across every segment: delivery (long- and short-term), intraday, futures, options, commodity and currency, with charges per segment, net P&L, unrealised P&L on open holdings, month-by-month chart, best/worst stocks and a CSV of every closed trade. Comes from Upstox's P&L report, which updates end of day.
- **Markets:** a stock list (Nifty 50, your holdings, the daily ideas, or your own list) with LTP, change, day range, volume, 52-week range, 1M/1Y returns, a sector heatmap and top gainers/losers.
- **Company:** search any NSE stock. Price chart with 50/200-day averages, valuation (market cap, P/E, P/B, ROE, ROCE, dividend yield), **what it sells and to whom, what it buys and from whom**, **who owns it** (promoters, FIIs, DIIs, government, public by quarter, plus named large holders), quarterly results as filed with NSE, links to annual reports, BRSR and SEBI filings, and a business description.
- **Earnings:** **results out** (every quarterly result filed on NSE, with a STRONG / GOOD / MIXED / WEAK / POOR verdict from growth vs a year ago, margins and analyst estimates), the **results calendar** (who reports this week, next week or in 30 days, with last year's numbers and estimates), and an **earnings scorecard** (how each stock moved after its last 8 results). When one of your stocks reports, a banner at the top of every page says so with its verdict.
- **News:** NSE announcements (sorted into results, orders, dividends, acquisitions, ratings, legal…), bulk and block deals with the client's name, and insider trades with net promoter buying, for your stocks, one stock or the whole market.
- **Flows:** FII and DII cash buying and selling, F&O positioning by participant (FII index futures long %), and option chains for the indices and F&O stocks with PCR, max pain, OI support/resistance and the move the straddle prices in.
- **Screener:** filter Nifty 50 to Nifty 500, your stocks or a typed list by sales and profit growth, consecutive growth quarters, margins, P/E, P/B, ROE, ROCE, dividend yield, and promoter/FII/DII holding changes, with presets and a quality score.
- **Journal:** win rate, average win and loss, payoff, profit per trade, streaks, days held for winners vs losers, patterns worth a look, and whether each daily idea worked.
- **Tax:** this year's short- and long-term capital gains, intraday and F&O income, set-off of losses, estimated tax with cess, advance tax dates, and tax-loss harvesting suggestions.
- **Charges:** what you've paid this financial year (brokerage, STT, GST, stamp duty, exchange, DP, SEBI), straight from Upstox. It also shows MTF interest on open positions and has a calculator for delivery, intraday and MTF round trips, including the breakeven sell price.
- **Sell check:** flags each holding as HOLD, REVIEW or SELL? using your stop-loss and target, its 20- and 50-day averages, MTF interest drag and the daily research notes.
- **Daily ideas:** earnings-based buy ideas, stocks to avoid and results to watch, read from `data/ideas.json`. A scheduled research job updates that file every weekday morning.
- **Trade:** buy or sell a stock through Upstox, either now or with an automatic rule (GTT) that fires when the price hits your level. It starts in **paper mode** (simulated, nothing is sent). Live orders are off until you turn them on (see below).

Only the Trade tab can place or cancel orders, and only after a review-and-confirm step. Ideas are research, not advice. Check the live price and your own risk before trading.

## Where the data comes from

| What | Source | Freshness |
|---|---|---|
| Prices when logged in | Upstox market-quote API | Live |
| Prices when not logged in, 52-week range, history | Yahoo Finance (`yfinance`) | Up to ~15 min delayed |
| Ratios, quarterly results, shareholding pattern, named holders | Screener.in public pages (from exchange filings) | Quarterly; cached 6 hours |
| Full NSE stock list | NSE's daily `EQUITY_L.csv` | Daily |
| Results calendar, filed results, announcements, bulk/block deals, insider trades, FII/DII, index members | NSE public APIs (`event-calendar`, `corporates-financial-results`, `results-comparision`, `corporate-announcements`, `historical/bulk-deals`, `corporates-pit`, `fiidiiTradeReact`, `equity-stockIndices`) | Cached 15 min to 24 h |
| Participant open interest | NSE archive `fao_participant_oi_DDMMYYYY.csv` | After market close |
| Option chain | Upstox option-chain API when logged in, else NSE `option-chain-v3` | Live / ~3 min |
| Analyst estimates, past earnings dates | Yahoo Finance | Daily |
| Shareholding (promoter vs public), quarterly results, annual reports, BRSR | NSE corporate filings APIs | As filed; cached 6 hours |
| What a company sells/buys and to/from whom | `data/companies.json` (hand-written, 27 companies); for any other stock, a button has Claude read its annual report, BRSR, investor presentations and rating reports (needs `ANTHROPIC_API_KEY`) | Hand-written: edit the file. Researched: kept on the app server until it restarts; download the JSON to add it to the file |
| Realised P&L and charges | Upstox P&L report API | End of day (T+1) |

Each page shows its source and fetch time, and a failing source shows a note instead of breaking the page. Nifty 50 members are in `data/nifty50.csv` (as of mid-2026).

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

**"Invalid Auth code" (UDAPI100057)?** The code Upstox hands back after login works once, for a few minutes. The app now uses it once and then clears it from the address bar, so reloading the page or opening an old tab just asks you to log in again. If it still appears straight after a fresh login, the Redirect URL doesn't match: the sidebar shows the one the app sends, and it must be identical (same `https://`, no trailing `/`, no spaces) to the Redirect URL in your Upstox developer app and to `UPSTOX_REDIRECT_URI` in Streamlit Secrets.

## Trading from the app

The Trade tab has three modes:

| Mode | What happens | Needs |
|---|---|---|
| Paper | Orders are simulated in the app. Nothing is sent to Upstox. | Nothing (the default) |
| Sandbox | Orders go to Upstox's test system, not the exchange. | `UPSTOX_SANDBOX_TOKEN` from the Sandbox section of your Upstox developer apps page |
| Live | Real orders on NSE/BSE through your account. | `LIVE_TRADING = true`, a `TRADE_PIN`, and an Upstox login that day |

Every order goes through the same steps: pick a stock (search covers all NSE/BSE equities once you're logged in), choose buy or sell, delivery/intraday/MTF, LIMIT/MARKET/SL/SL-M, quantity and price. **Review order** runs the checks, then a confirm box shows the order in plain words and the exact request sent to Upstox. You tick "I've checked…" and, in live mode, type your trading PIN before **Place** is enabled.

Safety checks:

- An order above `MAX_ORDER_VALUE` (default ₹50,000) is blocked.
- You can't sell more delivery or MTF shares than you hold.
- Stop-loss price and trigger must be on the right side of each other.
- Warnings for market orders, limits more than 5% from the last price, intraday auto square-off and MTF interest.
- Changing anything after review, or switching mode, cancels the review. A placed order can't be sent twice by a refresh.

The order book (live mode) shows today's orders with their status and lets you cancel an open one.

### Automatic rules (GTT)

Pick **Automatic rule (GTT)** on the Trade tab to set an order that waits on Upstox's servers and fires by itself when the price crosses your level, even when this site is closed. A rule lasts up to a year, until it fires, or until you cancel it.

- **Entry:** buy (or sell) when the price goes BELOW a level (buy the dip), ABOVE a level (breakout), or IMMEDIATE (enter now).
- **Target and stop-loss (optional):** once the entry fills, Upstox sells at whichever comes first. The stop-loss can trail the price by a fixed rupee gap.
- **Selling shares you hold:** use a single rule (no target or stop-loss), e.g. "sell 10 ITC if it falls below ₹400".

The same checks apply (per-order value cap, can't sell more than you hold, target and stop-loss on the right sides of the entry), with the same review, tick and PIN. Triggered orders go out as market orders, so fills can differ a little from the trigger. The rules list shows your active rules and lets you cancel one. Upstox's sandbox has no GTT, so try rules in Paper mode first.

To turn live trading on, add to the app secrets:

```toml
LIVE_TRADING = true
TRADE_PIN = "a PIN only you know"   # typed in for every live order
MAX_ORDER_VALUE = 50000             # optional, ₹ per order
APP_PASSWORD = "..."                # strongly recommended so nobody else can open the app
```

Upstox's API terms apply to orders sent this way. Orders above the regular-algo rate limit (10 per second) are rejected by Upstox.

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

## Your stocks and watchlist

The Earnings, News and Screener tabs flag "your stocks": your holdings (HELD), today's daily ideas (IDEA), and anything in `data/watchlist.txt` or the Markets tab's custom list (WATCH). Edit `data/watchlist.txt` (one NSE symbol per line) to add more.

## Daily ideas file

`data/ideas.json` has `date`, `market_summary`, `buy_ideas[]` (symbol, name, approx_price, target, target_source, thesis, risks, sources), `avoid[]`, `watch_today[]`, `portfolio_notes{SYMBOL: note}` and `disclaimer`. When the file is pushed, Streamlit Cloud picks up the change on its own.

After updating it, run `python tools/archive_ideas.py` and commit `data/ideas_history/<date>.json` too: the Journal tab uses that history to check how each idea did. Optionally, append the day's FII/DII figures to `data/fii_dii.csv` (columns `Date, Who, Buy, Sell, Net`) to keep a longer flows history than the app can on its own.

## Tests

```bash
pip install pytest && python -m pytest -q   # includes parsers for Screener/NSE data and the P&L maths
```
