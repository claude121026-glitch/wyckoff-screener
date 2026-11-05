"""Control: plain dip-buys pushed through the SAME engine, stop size, 2R target, time stop and costs as springs."""
import sys, glob, os
import numpy as np, pandas as pd
PROJ = sys.argv[1]
sys.path.insert(0, PROJ)
from run import UNIVERSES
from config import DAILY
from signals import add_indicators
from backtest import backtest
def load(sym):
    safe = sym.replace("^", "IDX_").replace("&", "and")
    f = sorted(glob.glob(os.path.join(PROJ, "data_cache", f"{safe}_1d_10y_*.csv")))[-1]
    d = pd.read_csv(f, index_col=0); d.index = pd.to_datetime(d.index, utc=True).tz_convert("Asia/Kolkata")
    return d.dropna(subset=["Open", "High", "Low", "Close"])
trades = []
for s in UNIVERSES["nifty30"]:
    d = add_indicators(load(s), DAILY)
    c = d["Close"]; lo, hi = d["Low"].rolling(40).min(), d["High"].rolling(40).max()
    dip = (((c - lo) / (hi - lo)) < 0.33) & (c > d["ctx"])
    sigs = [dict(i=i, time=d.index[i], setup="DIP", side=1, stop=float(c.iloc[i] - 2.07 * d["atr"].iloc[i]),
                 level=float(lo.iloc[i]), note="control") for i in np.flatnonzero(dip.to_numpy())]
    trades += backtest(d, sigs, DAILY, s)
t = pd.DataFrame(trades)
cut = pd.Timestamp("2024-03-01", tz="Asia/Kolkata")
for name, m in [("2016-Feb24", t.entry_time < cut), ("Mar24-now", t.entry_time >= cut), ("all", t.entry_time == t.entry_time)]:
    R = t.loc[m, "R"]
    print(f"plain dip-buy control {name:10s}: n={len(R):4d}  avgR={R.mean():+.3f}  win={100*(R>0).mean():.1f}%  PF={R[R>0].sum()/-R[R<=0].sum():.2f}")
