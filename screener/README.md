# NSE Wyckoff Screener

Crawls every NSE-listed company, reads each chart with Wyckoff rules (from Villahermosa's and Weis's books), and produces a ranked screener with an HTML report and charts.

> **What the labels mean:** they sort charts for **manual review**. They are not buy or sell recommendations. The coded rules showed **no reliable edge** in 10 years of backtests (see `../wyckoff_system/README.md`). Treat every label as "worth a look", then make the decision yourself.

## Daily routine (run after 15:45 IST)

```bash
python -I fetch_data.py      # NSE listing + 2 years of daily prices for ~2,630 securities (~6 minutes)
python -I run_screener.py    # analyse ~900 liquid stocks + build the report (~1 minute)
```

Open `reports/<date>/report.html` in a browser. Options:
- `--min-turnover 10`: require ₹10 crore of median daily traded value instead of ₹5 crore
- `--min-price 20`
- `--charts 60`: chart more watchlist names

## How each chart is read

1. **Context (cycle stage).** *Markup*: price above a rising 200-day average, with the 50-day above the 200-day. *Markdown*: the mirror image. Anything else is *transition*.
2. **Structure.** Is the last 60 days a trading range (at most 12 ATR tall, with at least 3 crossings of its midpoint)? What was the trend over the 120 days before it?
3. **Effort vs. result.**
   - Volume over the last 20 days compared with the 40 days before (drying up = accumulation trait)
   - ATR contraction
   - Up-day volume compared with down-day volume (last 40 days)
   - Weis wave volumes (last 3 up-waves vs. 3 down-waves)
   - Shortening of the thrust
   - Rising lows or falling highs
4. **Events (last 10–15 days).**
   - Sign-of-strength and sign-of-weakness bars (wide range, high volume, strong close beyond the 20-day high or low)
   - Selling and buying climaxes
5. **Tested setup rules** from `wyckoff_system`: spring, upthrust, breakout test (BUEC/LPS), breakdown test (LPSY), each either *triggered* or *building*.
6. **Scores.** Accumulation evidence and distribution evidence, each 0–100. Net = accumulation − distribution.

| Action | Categories | Notes |
|---|---|---|
| **Review now** | Spring triggered; breakout test triggered | Net score must be ≥ +10 (volume confirms) and the stop must be ≤ 4 ATR away |
| **Watchlist** | Spring building; breakout awaiting pullback; markup quiet pullback; accumulation or re-accumulation candidate; triggered but volume not confirming or entry extended | |
| **Avoid longs** | Distribution warning; upthrust/LPSY triggered; markdown | |
| **Ignore** | No clear structure | |

## Decision checklist (from the books) before acting on any "Review now" stock

1. **Context:** is the larger structure (weekly chart, sector, Nifty) on your side?
2. **Structure:** can *you* see the range, the shakeout and the test on the chart? If you can't label it, skip it.
3. **Volume:** did the shakeout or test come on low volume, and the move up on rising volume?
4. **Location:** is there room to the next resistance (the 60-day high, a previous supply area) of at least 2× your risk?
5. **Stop:** below the spring or pullback low (the `setup_stop` column). If that's too far away for you, skip the trade.
6. **Size:** risk no more than 1% of your capital, so position size = (1% of capital) ÷ (entry − stop).
7. **Orders:** place the entry, stop and target together.

## Streamlit app

**Run it on your PC:**

```bash
cd C:\Users\Dell\Wcykoff
python -m streamlit run screener/app.py
```

It opens at http://localhost:8501 and has:
- **Filters:** report date, action, category, liquidity, net score, search
- **Screener table** with a CSV download button
- **Stock detail:** an interactive chart with the setup level, stop and range; the evidence explained in plain language; and a risk-based position-size calculator
- **Update data:** runs the crawler and the screener (local only)

**Host it free on Streamlit Community Cloud:**

You need a GitHub account and a Streamlit Community Cloud account (sign in with GitHub at share.streamlit.io).

1. Create a GitHub repository and push the `C:\Users\Dell\Wcykoff` folder to it. `.gitignore` already excludes the PDFs, the large price files and the chart images.
2. On share.streamlit.io, click **Create app**. Choose your repository and branch, and set the main file path to `screener/app.py`. Then deploy.
3. **Nightly refresh:** `.github/workflows/refresh.yml` reruns the crawler and screener at 19:00 IST every weekday and commits the new `screener.csv`. Streamlit Cloud then redeploys automatically.
   - Enable it under GitHub → your repo → **Actions**.
   - Use **Run workflow** to trigger it by hand.
4. **On the cloud, charts download each stock's history on demand** (cached for 6 hours), so the 31 MB price file never needs to be uploaded.

Privacy: a public repository makes your code and screener results visible to anyone. A private repository works too. Check who can view the app in the app's sharing settings on Streamlit Cloud.

## Files

| File | Contents |
|---|---|
| `fetch_data.py` | NSE equity list (EQUITY_L.csv) and Yahoo Finance daily bars, saved to `data/` |
| `wyckoff_screen.py` | The chart-reading logic and scoring for one stock |
| `run_screener.py` | Liquidity filter, the full run, charts and the HTML report |
| `reports/<date>/` | `report.html`, `screener.csv`, `charts/` |

## Limitations

- **Yahoo data:** the latest day is sometimes missing until Yahoo finalizes it. The screener aligns all stocks to the most common last date.
- **Coverage:** NSE only (BSE-only companies aren't included). Corporate actions rely on Yahoo's price adjustments.
- **Untested labels:** the categories and scores are untested heuristics. Only the four setup rules were backtested, and they showed no reliable edge.
