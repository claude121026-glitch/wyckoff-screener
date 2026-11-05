"""Grid search over Wyckoff rule variants with an honest design:
   choose on TRAIN (2016-2021, universe 1) -> check on VALIDATE (2022-Feb24), TEST (Mar24-now) and universe 2."""
import sys, glob, os, itertools, time
from dataclasses import replace
import numpy as np, pandas as pd
PROJ, C2, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
MODE = sys.argv[4] if len(sys.argv) > 4 else "grid"
sys.path.insert(0, PROJ)
from config import DAILY
from signals import add_indicators, generate_signals
from run import UNIVERSES
U1 = UNIVERSES["nifty30"]
U2 = [os.path.basename(f).split("_1d_")[0] for f in sorted(glob.glob(os.path.join(C2, "*_1d_10y_*.csv")))]
TZ = "Asia/Kolkata"
T_VAL, T_TEST = pd.Timestamp("2022-01-01", tz=TZ), pd.Timestamp("2024-03-01", tz=TZ)

def load(sym):
    safe = sym.replace("^", "IDX_").replace("&", "and")
    files = sorted(glob.glob(os.path.join(PROJ, "data_cache", f"{safe}_1d_10y_*.csv"))) or \
            sorted(glob.glob(os.path.join(C2, f"{safe}_1d_10y_*.csv")))
    d = pd.read_csv(files[-1], index_col=0); d.index = pd.to_datetime(d.index, utc=True).tz_convert(TZ)
    return d.dropna(subset=["Open", "High", "Low", "Close"])

nifty = load("^NSEI")["Close"]
mkt_up = (nifty > nifty.rolling(200).mean()).astype(float).where(nifty.rolling(200).mean().notna())
mkt_up.index = mkt_up.index.date
RAW = {s: load(s) for s in U1 + U2}

def fast_bt(d, sigs, rmult, hold, cost=DAILY.cost_bps / 1e4, p=DAILY):
    o, h, l, c, atr = d["_o"], d["_h"], d["_l"], d["_c"], d["_atr"]; n = len(o)
    out, free, seen = [], 0, set()
    for s in sigs:
        if s["i"] in seen: continue
        seen.add(s["i"])
        i = s["i"] + 1
        if i < free or i >= n: continue
        side, stop, entry = s["side"], s["stop"], o[i]
        risk = (entry - stop) * side; a = atr[i - 1]
        if not (risk > 0 and np.isfinite(a) and p.min_risk_atr * a <= risk <= p.max_risk_atr * a
                and 2 * cost * entry <= p.max_cost_frac * risk):
            continue
        tgt = entry + side * rmult * risk
        e = min(i + hold - 1, n - 1)
        L, H, O = l[i:e + 1], h[i:e + 1], o[i:e + 1]
        sh = (L <= stop) if side == 1 else (H >= stop)
        th = (H >= tgt) if side == 1 else (L <= tgt)
        hit = np.flatnonzero(sh | th)
        if len(hit):
            k = hit[0]; j = i + k
            if sh[k]: px = O[k] if (side == 1 and O[k] <= stop) or (side == -1 and O[k] >= stop) else stop
            else:     px = O[k] if (side == 1 and O[k] >= tgt) or (side == -1 and O[k] <= tgt) else tgt
        else:
            j, px = e, c[e]
        R = side * (px * (1 - side * cost) - entry * (1 + side * cost)) / risk
        out.append((d["_t"][i], R)); free = j + 1
    return out

GEN = dict(range_len=[20, 40, 60], quiet=[0.8, 1.0], sos_rv=[1.2, 1.5], direct=[True, False])
GROUPS = {"SPRING": {"SPRING"}, "BUEC": {"BUEC"}, "SPRING+BUEC": {"SPRING", "BUEC"}, "UPTHRUST": {"UPTHRUST"},
          "LPSY": {"LPSY"}, "UT+LPSY": {"UPTHRUST", "LPSY"}, "ALL": {"SPRING", "BUEC", "UPTHRUST", "LPSY"}}
CTX, MKT, RM, HOLD = [0, 50, 100, 200], [False, True], [1.5, 2.0, 3.0], [10, 25, 40]

def signals_for(sym, gp):
    d = add_indicators(RAW[sym], gp)
    sigs, _ = generate_signals(d, gp)
    c = d["Close"].to_numpy()
    smas = {k: d["Close"].rolling(k).mean().to_numpy() for k in (50, 100, 200)}
    dates = d.index.date
    for s in sigs:
        i = s["i"]
        s["ctx"] = {0: True, **{k: (np.isfinite(smas[k][i]) and ((c[i] > smas[k][i]) if s["side"] == 1 else (c[i] < smas[k][i])))
                                 for k in smas}}
        m = mkt_up.get(dates[i], np.nan)
        s["mkt"] = bool(np.isfinite(m) and ((m > 0.5) if s["side"] == 1 else (m < 0.5)))
    arr = {"_o": d["Open"].to_numpy(), "_h": d["High"].to_numpy(), "_l": d["Low"].to_numpy(), "_c": c,
           "_atr": d["atr"].to_numpy(), "_t": d.index}
    return arr, sigs

def stats(R):
    R = np.asarray(R)
    if len(R) == 0: return 0, np.nan, np.nan
    neg = -R[R <= 0].sum()
    return len(R), R.mean(), (R[R > 0].sum() / neg if neg > 0 else np.inf)

if MODE == "verify":
    gp = replace(DAILY, ctx_len=0)
    allR = []
    for s in U1:
        arr, sigs = signals_for(s, gp)
        sel = [x for x in sigs if x["setup"] == "SPRING" and x["ctx"][100]]
        allR += [r for _, r in fast_bt(arr, sel, 2.0, 25)]
    n, m, pf = stats(allR); print(f"verify: n={n} avgR={m:+.3f} PF={pf:.2f}  (engine: n=140 avgR=+0.212 PF=1.46)"); sys.exit()

t0 = time.time(); rows = []
for rl, q, sv, dr in itertools.product(*GEN.values()):
    gp = replace(DAILY, ctx_len=0, range_len=rl, test_rv=q, pb_rv=q, sos_rv=sv, direct_low_vol=dr)
    pre = {s: signals_for(s, gp) for s in U1 + U2}
    for (gname, gset), ctx, mk, rm, hd in itertools.product(GROUPS.items(), CTX, MKT, RM, HOLD):
        res = {"U1": [], "U2": []}
        for uni, syms in (("U1", U1), ("U2", U2)):
            for s in syms:
                arr, sigs = pre[s]
                sel = [x for x in sigs if x["setup"] in gset and x["ctx"][ctx] and (x["mkt"] or not mk)]
                res[uni] += fast_bt(arr, sel, rm, hd)
        row = dict(range_len=rl, quiet=q, sos_rv=sv, direct=dr, setups=gname, ctx=ctx, mkt=mk, rmult=rm, hold=hd)
        for uni in ("U1", "U2"):
            tr = res[uni]
            for per, f in (("train", lambda t: t < T_VAL), ("val", lambda t: T_VAL <= t < T_TEST), ("test", lambda t: t >= T_TEST),
                           ("all", lambda t: True)):
                n, m, pf = stats([r for t, r in tr if f(t)])
                row[f"{uni}_{per}_n"], row[f"{uni}_{per}_R"], row[f"{uni}_{per}_PF"] = n, m, pf
        rows.append(row)
    print(f"gen rl={rl} q={q} sos={sv} direct={dr} done, {len(rows)} combos, {time.time()-t0:.0f}s", flush=True)
pd.DataFrame(rows).to_csv(os.path.join(OUT, "grid_results.csv"), index=False)
print("saved", len(rows), "combos")
