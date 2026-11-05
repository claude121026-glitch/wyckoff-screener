"""Crawl the NSE equity list and download daily OHLCV for every listed company.

  python -I fetch_data.py            # refresh listing + prices (2 years, daily)
  python -I fetch_data.py --listing  # listing only

Sources: NSE's public equity list (EQUITY_L.csv) and Yahoo Finance via yfinance.
Output: data/listing/EQUITY_L.csv and data/prices/prices_<YYYYMMDD>.csv.gz (long format).
"""
import argparse
import os
import time
import urllib.request

import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
LIST_DIR = os.path.join(HERE, "data", "listing")
PRICE_DIR = os.path.join(HERE, "data", "prices")
LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "text/csv,*/*"}
TZ = "Asia/Kolkata"


def fetch_listing():
    os.makedirs(LIST_DIR, exist_ok=True)
    path = os.path.join(LIST_DIR, "EQUITY_L.csv")
    data = urllib.request.urlopen(urllib.request.Request(LIST_URL, headers=UA), timeout=30).read()
    with open(path, "wb") as f:
        f.write(data)
    return load_listing()


def load_listing():
    d = pd.read_csv(os.path.join(LIST_DIR, "EQUITY_L.csv"))
    d.columns = [c.strip() for c in d.columns]
    d = d.rename(columns={"NAME OF COMPANY": "name", "SYMBOL": "symbol", "SERIES": "series",
                          "DATE OF LISTING": "listed"})
    d["symbol"] = d["symbol"].str.strip()
    d["series"] = d["series"].str.strip()
    return d[["symbol", "name", "series", "listed"]]


def fetch_prices(symbols, period="2y", batch=150, pause=2.0):
    os.makedirs(PRICE_DIR, exist_ok=True)
    frames, failed = [], []
    tickers = [s + ".NS" for s in symbols]
    for k in range(0, len(tickers), batch):
        chunk = tickers[k:k + batch]
        for attempt in range(3):
            try:
                raw = yf.download(chunk, period=period, interval="1d", group_by="ticker",
                                  auto_adjust=True, threads=True, progress=False)
                break
            except Exception as e:                       # network hiccup: wait and retry
                print(f"  batch {k}: {e}; retrying"); time.sleep(10 * (attempt + 1))
        else:
            failed += chunk; continue
        for t in chunk:
            try:
                df = raw[t].dropna(subset=["Open", "High", "Low", "Close"])
            except KeyError:
                failed.append(t); continue
            if df.empty:
                failed.append(t); continue
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df["symbol"] = t[:-3]
            frames.append(df)
        print(f"  {min(k + batch, len(tickers))}/{len(tickers)} tickers fetched", flush=True)
        time.sleep(pause)
    px = pd.concat(frames)
    px.index.name = "date"
    px = px.reset_index()
    px["date"] = pd.to_datetime(px["date"]).dt.tz_localize(None).dt.normalize()
    # never keep a still-forming daily bar
    now = pd.Timestamp.now(tz=TZ)
    if (now.hour, now.minute) < (15, 45):
        px = px[px["date"] < pd.Timestamp(now.date())]
    path = os.path.join(PRICE_DIR, f"prices_{now:%Y%m%d}.csv.gz")
    px.to_csv(path, index=False)
    return path, failed


def latest_prices():
    files = sorted(f for f in os.listdir(PRICE_DIR) if f.startswith("prices_"))
    if not files:
        raise FileNotFoundError("no price file; run fetch_data.py first")
    px = pd.read_csv(os.path.join(PRICE_DIR, files[-1]), parse_dates=["date"])
    return px, files[-1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listing", action="store_true", help="refresh the listing only")
    ap.add_argument("--period", default="2y")
    a = ap.parse_args()
    lst = fetch_listing()
    print(f"listing: {len(lst)} securities ({lst.series.value_counts().to_dict()})")
    if not a.listing:
        path, failed = fetch_prices(lst["symbol"].tolist(), a.period)
        print(f"saved {path}; {len(failed)} tickers had no data on Yahoo")
        with open(os.path.join(PRICE_DIR, "failed.txt"), "w") as f:
            f.write("\n".join(failed))
