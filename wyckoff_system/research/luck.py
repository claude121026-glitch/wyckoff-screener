"""(a) Did springs beat a plain dip-buy in each period?  (b) Is a 37-trade slump to -0.19R plausible as bad luck?"""
import sys, glob, os
import numpy as np, pandas as pd
PROJ, SCR = sys.argv[1], sys.argv[2]
sys.path.insert(0, PROJ)
from run import UNIVERSES
H = 15
def load(sym):
    safe = sym.replace("^", "IDX_").replace("&", "and")
    f = sorted(glob.glob(os.path.join(PROJ, "data_cache", f"{safe}_1d_10y_*.csv")))[-1]
    d = pd.read_csv(f, index_col=0); d.index = pd.to_datetime(d.index, utc=True).tz_convert("Asia/Kolkata")
    return d.dropna(subset=["Open", "High", "Low", "Close"])
f = pd.read_csv(os.path.join(SCR, "spring_trades_enriched.csv"), parse_dates=["entry_time"])
data = {s: load(s) for s in UNIVERSES["nifty30"]}

# (a) same-horizon comparison: spring entry (next open) vs plain dip-buy entry (next open), 15 bars, % return
def fwd_from_open(d, i):
    j = i + H - 1
    return (d["Close"].iloc[j] / d["Open"].iloc[i] - 1) * 100 if j < len(d) else np.nan
f["fwd15"] = [fwd_from_open(data[r.symbol], data[r.symbol].index.get_loc(r.entry_time)) for r in f.itertuples()]
base = []
for s, d in data.items():
    c = d["Close"]; ma = c.rolling(100).mean(); lo, hi = d["Low"].rolling(40).min(), d["High"].rolling(40).max()
    sig = ((c - lo) / (hi - lo) < 0.33) & (c > ma)
    for i in np.flatnonzero(sig.to_numpy())[:-1]:
        base.append((d.index[i + 1], fwd_from_open(d, i + 1)))
b = pd.DataFrame(base, columns=["t", "fwd15"]).dropna()
cut = pd.Timestamp("2024-03-01", tz="Asia/Kolkata")
for name, m_s, m_b in [("2016-Feb24", f.entry_time < cut, b.t < cut), ("Mar24-now", f.entry_time >= cut, b.t >= cut)]:
    sp, bs = f.loc[m_s, "fwd15"].dropna(), b.loc[m_b, "fwd15"]
    rng = np.random.default_rng(1)
    boot = [rng.choice(sp.to_numpy(), len(sp)).mean() - bs.mean() for _ in range(5000)]
    lo90, hi90 = np.percentile(boot, [5, 95])
    print(f"{name}: spring 15d fwd mean {sp.mean():+.2f}% (n={len(sp)})  vs plain dip-buy {bs.mean():+.2f}% (n={len(bs)})"
          f"  -> spring excess {sp.mean()-bs.mean():+.2f}%  [90% CI {lo90:+.2f}, {hi90:+.2f}]")

# (b) bad-luck test
A = f.loc[f.entry_time < cut, "R"].to_numpy(); B = f.loc[f.entry_time >= cut, "R"].to_numpy()
rng = np.random.default_rng(2)
sims = np.array([rng.choice(A, len(B)).mean() for _ in range(20000)])
print(f"\nIf post-2024 trades were drawn from the pre-2024 distribution (mean {A.mean():+.2f}R):"
      f" P(37-trade mean <= {B.mean():+.2f}R) = {(sims <= B.mean()).mean():.3f}")
allR = f.sort_values("entry_time")["R"].to_numpy()
roll = pd.Series(allR[:len(A)]).rolling(len(B)).mean()
print(f"Worst rolling {len(B)}-trade average BEFORE Mar 2024: {roll.min():+.2f}R  (best {roll.max():+.2f}R)")
pooled = np.r_[A, B]; diff = A.mean() - B.mean()
perm = [(lambda p: p[:len(A)].mean() - p[len(A):].mean())(rng.permutation(pooled)) for _ in range(20000)]
print(f"Permutation test, A minus B = {diff:+.2f}R: p = {(np.array(perm) >= diff).mean():.3f}")
