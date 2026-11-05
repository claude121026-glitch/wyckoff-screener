# Wyckoff Methodology: NSE Screener and Research

Tools built from Rubén Villahermosa's *The Wyckoff Methodology in Depth* and David H. Weis's *Trades About to Happen*.

| Folder | What it is |
|---|---|
| [`screener/`](screener/README.md) | Crawls every NSE-listed company, reads each chart with Wyckoff rules, and shows the results in a **Streamlit app** (`streamlit run screener/app.py`) and an HTML report |
| [`wyckoff_system/`](wyckoff_system/README.md) | A rule-based backtester (spring, upthrust, breakout test, breakdown test), the research behind it, and a 12,096-combination grid search |

**Important:** in 10 years of backtests the coded rules showed **no reliable edge**. The screener's labels are for manual chart review. They are not buy or sell recommendations, and nothing here is investment advice.

## Quick start

```bash
pip install -r requirements.txt
python -I screener/fetch_data.py        # NSE list + 2 years of daily prices
python -I screener/run_screener.py      # Wyckoff analysis + report
python -m streamlit run screener/app.py # open the app
```

A GitHub Action (`.github/workflows/refresh.yml`) refreshes the screener every weekday at 19:00 IST when the repository is hosted on GitHub.
