"""Why did the spring edge fade after Mar 2024? Enrich every spring trade with
path and context features, then compare periods."""
import sys, glob, os
import numpy as np, pandas as pd
PROJ, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, PROJ)
from config import DAILY
from signals import add_indicators

def load(sym):
    safe = sym.replace("^", "IDX_").replace("&", "and")
    f = sorted(glob.glob(os.path.join(PROJ, "data_cache", f"{safe}_1d_10y_*.csv")))[-1]
    d = pd.read_csv(f, index_col=0)
    d.index = pd.to_datetime(d.index, utc=True).tz_convert("Asia/Kolkata")
    return d.dropna(subset=["Open", "High", "Low", "Close"])

t = pd.read_csv(os.path.join(PROJ, "results", "trades_daily_long_10bps_spring.csv"),
                parse_dates=["entry_time", "exit_time"])
nifty = load("^NSEI"); nc = nifty["Close"]
n_ret20 = nc.pct_change(20); n_vol20 = nc.pct_change().rolling(20).std() * np.sqrt(252)
n_sma200 = nc.rolling(200).mean()
nd = lambda s: s.set_axis(s.index.date)
n_ret20, n_vol20, n_above = nd(n_ret20), nd(n_vol20), nd((nc > n_sma200).astype(float))

rows, cache = [], {}
for r in t.itertuples():
    if r.symbol not in cache:
        cache[r.symbol] = add_indicators(load(r.symbol), DAILY)
    d = cache[r.symbol]
    i0 = d.index.get_loc(r.entry_time); i1 = d.index.get_loc(r.exit_time)
    seg = d.iloc[i0:i1 + 1]
    sig = d.iloc[i0 - 1]                       # signal bar
    mfe = (seg["High"].max() - r.entry) / r.risk
    mae = (r.entry - seg["Low"].min()) / r.risk
    # forward path regardless of exit: best/worst over 25 bars
    fw = d.iloc[i0:i0 + 25]
    mfe25 = (fw["High"].max() - r.entry) / r.risk
    ret25 = (fw["Close"].iloc[-1] / r.entry - 1) * 100 if len(fw) else np.nan
    dd = r.entry_time.date()
    rows.append(dict(
        symbol=r.symbol, entry_time=r.entry_time, R=r.R, reason=r.reason, bars=r.bars,
        direct=int("direct" in r.note),
        risk_atr=r.risk / sig["atr"], risk_pct=r.risk / r.entry * 100,
        sig_rv=sig["rv"], range_h_atr=(sig["res"] - sig["sup"]) / sig["atr"],
        stock_vs_ma100=(sig["Close"] / sig["ctx"] - 1) * 100,
        stock_ret20=(sig["Close"] / d["Close"].iloc[i0 - 21] - 1) * 100,
        atr_pct=sig["atr"] / sig["Close"] * 100,
        nifty_ret20=n_ret20.get(dd, np.nan) * 100, nifty_vol20=n_vol20.get(dd, np.nan) * 100,
        nifty_above200=n_above.get(dd, np.nan),
        mfe_R=mfe, mae_R=mae, mfe25_R=mfe25, ret25_pct=ret25,
        hit1R=int(seg["High"].max() >= r.entry + r.risk)))
f = pd.DataFrame(rows)
cut = pd.Timestamp("2024-03-01", tz=f.entry_time.iloc[0].tz)
f["period"] = np.where(f.entry_time < cut, "A: 2016-Feb24", "B: Mar24-now")
f.to_csv(os.path.join(OUT, "spring_trades_enriched.csv"), index=False)

pd.set_option("display.width", 220)
print("=== 1. Outcome mix ===")
print(f.groupby("period").agg(n=("R", "size"), avgR=("R", "mean"), win=("R", lambda x: (x > 0).mean() * 100),
      hit1R=("hit1R", "mean"), mfe_R=("mfe_R", "median"), mae_R=("mae_R", "median"),
      mfe25_R=("mfe25_R", "median"), ret25=("ret25_pct", "median"), bars=("bars", "mean")).round(2).to_string())
print(pd.crosstab(f.period, f.reason, normalize="index").round(2).to_string())
print("\n=== 2. Entry traits (medians) ===")
cols = ["direct", "risk_atr", "risk_pct", "sig_rv", "range_h_atr", "stock_vs_ma100", "stock_ret20", "atr_pct",
        "nifty_ret20", "nifty_vol20", "nifty_above200"]
print(f.groupby("period")[cols].median().round(2).T.to_string())
print("\nmeans of direct-entry share:", f.groupby("period").direct.mean().round(2).to_dict())
print("\n=== 3. Avg R by entry type and period ===")
print(f.groupby(["period", "direct"]).R.agg(["count", "mean"]).round(2).to_string())
print("\n=== 4. Avg R by feature tercile (all trades) ===")
for c in ["risk_atr", "sig_rv", "range_h_atr", "stock_vs_ma100", "stock_ret20", "atr_pct", "nifty_ret20", "nifty_vol20"]:
    q = pd.qcut(f[c], 3, labels=["low", "mid", "high"], duplicates="drop")
    g = f.groupby(q, observed=True).R.agg(["count", "mean"]).round(2)
    share_B = f.groupby(q, observed=True).period.apply(lambda s: (s.str.startswith("B")).mean()).round(2)
    print(f"{c:15s}", " | ".join(f"{k}: n={g.loc[k,'count']:.0f} R={g.loc[k,'mean']:+.2f} B-share={share_B.loc[k]:.2f}" for k in g.index))
