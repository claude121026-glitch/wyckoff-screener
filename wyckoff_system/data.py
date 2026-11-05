"""Download and cache OHLCV data from Yahoo Finance (via yfinance)."""
import os
from datetime import date

import pandas as pd
import yfinance as yf

TZ = "Asia/Kolkata"
COLS = ["Open", "High", "Low", "Close", "Volume"]


def _read_cache(path):
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(TZ)
    return df


def _download(symbol, interval, period):
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data for {symbol} ({interval}, {period})")
    df = df[COLS].copy()
    df.index = df.index.tz_convert(TZ)
    return df


def _fill_opening_volume(df, symbol, cache_dir):
    """Yahoo often reports 0 volume for the first intraday bar.
    Fill it with (daily volume - sum of the other bars that day)."""
    daily = fetch(symbol, "1d", "3mo", cache_dir)
    dvol = daily["Volume"].groupby(daily.index.date).sum()
    dates = df.index.date
    for d in pd.unique(dates):
        mask = dates == d
        zero = mask & (df["Volume"].to_numpy() == 0)
        if zero.sum() == 1 and d in dvol.index:
            rest = df.loc[mask & ~zero, "Volume"].sum()
            df.loc[zero, "Volume"] = max(float(dvol[d]) - float(rest), 0.0)
    return df


def fetch(symbol, interval="1d", period="10y", cache_dir="data_cache",
          volume_from=None, refresh=False):
    """Return an OHLCV DataFrame indexed by IST timestamps.

    volume_from: take volume from another symbol (e.g. NIFTYBEES.NS for ^NSEI,
    because Yahoo has no volume for the index itself).
    """
    os.makedirs(cache_dir, exist_ok=True)
    safe = symbol.replace("^", "IDX_").replace("&", "and")
    path = os.path.join(cache_dir, f"{safe}_{interval}_{period}_{date.today():%Y%m%d}.csv")
    if os.path.exists(path) and not refresh:
        df = _read_cache(path)
    else:
        df = _download(symbol, interval, period)
        df.to_csv(path)

    intraday = interval.endswith("m") or interval.endswith("h")
    if volume_from:
        vsrc = fetch(volume_from, interval, period, cache_dir, refresh=refresh)
        df = df.join(vsrc[["Volume"]].rename(columns={"Volume": "V2"}), how="inner")
        df["Volume"] = df.pop("V2")
        if intraday:
            df = _fill_opening_volume(df, volume_from, cache_dir)
    elif intraday:
        df = _fill_opening_volume(df, symbol, cache_dir)

    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    # Never treat a still-forming bar as complete: drop today's daily bar before 15:45 IST.
    if interval == "1d" and len(df):
        now = pd.Timestamp.now(tz=TZ)
        if df.index[-1].date() == now.date() and (now.hour, now.minute) < (15, 45):
            df = df.iloc[:-1]
    return df
