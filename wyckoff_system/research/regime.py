"""Is the post-2024 slump spring-specific, or did buying dips in these stocks stop working in general?"""
import sys, glob, os
import numpy as np, pandas as pd
PROJ = sys.argv[1]
sys.path.insert(0, PROJ)
from run import UNIVERSES

def load(sym):
    safe = sym.replace("^", "IDX_").replace("&", "and")
    f = sorted(glob.glob(os.path.join(PROJ, "data_cache", f"{safe}_1d_10y_*.csv")))[-1]
    d = pd.read_csv(f, index_col=0)
    d.index = pd.to_datetime(d.index, utc=True).tz_convert("Asia/Kolkata")
    return d.dropna(subset=["Open", "High", "Low", "Close"])

H = 15   # forward horizon in bars (springs held ~15 bars on average)
rows = []
for sym in UNIVERSES["nifty30"]:
    d = load(sym); c = d["Close"]
    ma = c.rolling(100).mean(); lo, hi = d["Low"].rolling(40).min(), d["High"].rolling(40).max()
    pos = (c - lo) / (hi - lo)
    fwd = (c.shift(-H) / c - 1) * 100
    # forward best and worst move, in % of price
    fmax = (d["High"][::-1].rolling(H).max()[::-1].shift(-1) / c - 1) * 100
    fmin = (d["Low"][::-1].rolling(H).min()[::-1].shift(-1) / c - 1) * 100
    x = pd.DataFrame(dict(sym=sym, fwd=fwd, fmax=fmax, fmin=fmin, up=c > ma, dip=(pos < 0.33) & (c > ma)))
    rows.append(x)
X = pd.concat(rows).dropna()
X["period"] = np.where(X.index < pd.Timestamp("2024-03-01", tz="Asia/Kolkata"), "A: 2016-Feb24", "B: Mar24-now")
def summ(m, label):
    g = X[m].groupby("period").agg(days=("fwd", "size"), fwd_mean=("fwd", "mean"), fwd_med=("fwd", "median"),
        pos_share=("fwd", lambda s: (s > 0).mean() * 100), best_med=("fmax", "median"), worst_med=("fmin", "median"))
    print(f"\n--- {label}: {H}-day forward return, % ---"); print(g.round(2).to_string())
summ(X.index == X.index, "all stock-days")
summ(X["up"], "stock above its 100-day MA")
summ(X["dip"], "plain dip-buy: above 100-day MA and in bottom third of 40-day range")

# year-by-year: equal-weight basket and Nifty
n = load("^NSEI")["Close"]
basket = pd.concat([load(s)["Close"].pct_change().rename(s) for s in UNIVERSES["nifty30"]], axis=1).mean(axis=1)
yr = pd.DataFrame({"Nifty %": n.groupby(n.index.year).apply(lambda s: (s.iloc[-1] / s.iloc[0] - 1) * 100),
                   "30-stock basket %": basket.groupby(basket.index.year).apply(lambda r: ((1 + r.fillna(0)).prod() - 1) * 100),
                   "Nifty daily vol %": n.pct_change().groupby(n.index.year).std() * np.sqrt(252) * 100})
dip = X[X["dip"]]
yr["dip-buy fwd15 mean %"] = dip.groupby(dip.index.year)["fwd"].mean()
yr["dip-buy days"] = dip.groupby(dip.index.year)["fwd"].size()
print("\n--- by year ---"); print(yr.round(1).T.to_string())
