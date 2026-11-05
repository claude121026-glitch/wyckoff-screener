import sys, glob, os
import numpy as np, pandas as pd
PROJ = sys.argv[1]; sys.path.insert(0, PROJ)
from run import UNIVERSES
def load(sym):
    safe = sym.replace("^", "IDX_").replace("&", "and")
    f = sorted(glob.glob(os.path.join(PROJ, "data_cache", f"{safe}_1d_10y_*.csv")))[-1]
    d = pd.read_csv(f, index_col=0); d.index = pd.to_datetime(d.index, utc=True).tz_convert("Asia/Kolkata")
    return d.dropna(subset=["Open", "High", "Low", "Close"])
cut = pd.Timestamp("2024-03-01", tz="Asia/Kolkata")
n = load("^NSEI")["Close"]
def nstats(s):
    r = s.pct_change().dropna(); yrs = len(r) / 252
    dd = (s / s.cummax() - 1).min() * 100
    sma = n.rolling(200).mean().reindex(s.index)
    return {"CAGR %": ((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1) * 100, "vol %": r.std() * np.sqrt(252) * 100,
            "max drawdown %": dd, "days above 200d %": (s > sma).mean() * 100,
            "15-day windows up %": (s.pct_change(15) > 0).mean() * 100,
            "lag-1 autocorr of 15d returns": s.pct_change(15)[::15].autocorr()}
A, B = n[n.index < cut], n[n.index >= cut]
print(pd.DataFrame({"2016-Feb24": nstats(A), "Mar24-now": nstats(B)}).round(2).to_string())
# Nifty path since 2024
s = B; pk = s.idxmax(); tr = s[pk:].idxmin()
print(f"\nNifty since Mar 2024: start {s.iloc[0]:,.0f} | peak {s.max():,.0f} on {pk:%d %b %Y} | low after peak {s[pk:].min():,.0f} on {tr:%d %b %Y} ({(s[pk:].min()/s.max()-1)*100:.1f}%) | now {s.iloc[-1]:,.0f} on {s.index[-1]:%d %b %Y}")
m = B.resample("QE").last(); print("Nifty quarter-end closes:", " ".join(f"{i:%b%y}:{v:,.0f}" for i, v in m.items()))
# stock-level behaviour
closes = pd.concat([load(x)["Close"].rename(x) for x in UNIVERSES["nifty30"]], axis=1)
lows = pd.concat([load(x)["Low"].rename(x) for x in UNIVERSES["nifty30"]], axis=1)
above = (closes > closes.rolling(100).mean())
ma_slope = closes.rolling(100).mean().pct_change(20) * 100
lo40 = lows.rolling(40).min()
dip = above & (((closes - lo40) / (closes.rolling(40).max() - lo40)) < 0.33)
brk = (lows[::-1].rolling(15).min()[::-1].shift(-1) < lo40)          # next 15 days undercut the 40-day low
r60 = closes.pct_change(60) * 100
rows = {}
for name, m_ in [("2016-Feb24", closes.index < cut), ("Mar24-now", closes.index >= cut)]:
    rows[name] = {"stocks above 100d MA, avg %": above[m_].mean(axis=1).mean() * 100,
                  "100d MA slope (20d % change), median": np.nanmedian(ma_slope[m_].to_numpy()),
                  "dips that break the 40-day low within 15d %": brk[m_][dip[m_]].stack().mean() * 100,
                  "dispersion: cross-stock std of 60d return": r60[m_].std(axis=1).mean(),
                  "share of stocks beating Nifty over the period %": np.nan}
for name, m_ in [("2016-Feb24", closes.index < cut), ("Mar24-now", closes.index >= cut)]:
    c = closes[m_].dropna(axis=1, how="all"); nn = n.reindex(c.index).dropna()
    sr = c.iloc[-1] / c.bfill().iloc[0] - 1; nr = nn.iloc[-1] / nn.iloc[0] - 1
    rows[name]["share of stocks beating Nifty over the period %"] = (sr > nr).mean() * 100
print("\n" + pd.DataFrame(rows).round(2).to_string())
