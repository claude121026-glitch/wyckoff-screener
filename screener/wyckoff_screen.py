"""Wyckoff chart reading for one stock -> a row of screener evidence.

Everything uses only data up to the last completed bar. The categories are
screening labels for manual review, not buy/sell recommendations.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "wyckoff_system"))
from config import DAILY                                   # noqa: E402
from signals import add_indicators, generate_signals      # noqa: E402

RANGE_BARS = 60          # the "current structure" window
PRIOR_BARS = 120         # the trend that led into it


def zigzag(close, atr, k=1.5):
    """Weis-style waves on closes; a wave ends when price reverses k*ATR from its extreme."""
    waves, n = [], len(close)
    start, ext, d = 0, 0, 0
    for i in range(1, n):
        a = atr[i] if np.isfinite(atr[i]) else np.nan
        if not np.isfinite(a):
            continue
        if d == 0:
            if abs(close[i] - close[start]) >= k * a:
                d, ext = (1 if close[i] > close[start] else -1), i
            continue
        if (d == 1 and close[i] >= close[ext]) or (d == -1 and close[i] <= close[ext]):
            ext = i
        elif abs(close[i] - close[ext]) >= k * a:
            waves.append((start, ext, d)); start, ext, d = ext, i, -d
    if d != 0:
        waves.append((start, ext, d))
    return waves


def analyze(df):
    """df: Open/High/Low/Close/Volume indexed by date (>= ~260 bars). Returns a dict."""
    d = add_indicators(df, DAILY)
    c, h, l, v = (d[k].to_numpy(float) for k in ("Close", "High", "Low", "Volume"))
    atr, rv, rr, cp = (d[k].to_numpy(float) for k in ("atr", "rv", "rr", "cp"))
    n = len(d)
    last, a = c[-1], atr[-1]
    out = {"date": d.index[-1].date(), "close": round(last, 2), "atr_pct": round(100 * a / last, 2)}

    # liquidity: median daily traded value over 50 days, Rs crore
    out["turnover_cr"] = round(float(np.nanmedian((c * v)[-50:])) / 1e7, 2)

    # ---- cycle stage (context) ----
    ma50 = pd.Series(c).rolling(50).mean().to_numpy()
    ma200 = pd.Series(c).rolling(200).mean().to_numpy()
    slope200 = 100 * (ma200[-1] / ma200[-21] - 1) if np.isfinite(ma200[-21]) else np.nan
    out.update(ma50=round(ma50[-1], 2), ma200=round(ma200[-1], 2), ma200_slope_pct=round(slope200, 2),
               vs_ma200_pct=round(100 * (last / ma200[-1] - 1), 1))
    hi52, lo52 = h[-250:].max(), l[-250:].min()
    out["pos_52w"] = round((last - lo52) / (hi52 - lo52), 2) if hi52 > lo52 else np.nan
    if last > ma200[-1] and slope200 > 0 and ma50[-1] > ma200[-1]:
        stage = "markup"
    elif last < ma200[-1] and slope200 < 0 and ma50[-1] < ma200[-1]:
        stage = "markdown"
    else:
        stage = "transition"
    out["stage"] = stage

    # ---- current structure: is price in a trading range? ----
    sup, res = l[-RANGE_BARS:].min(), h[-RANGE_BARS:].max()
    height_atr = (res - sup) / a
    mid = (sup + res) / 2
    sgn = np.sign(c[-RANGE_BARS:] - mid); sgn = sgn[sgn != 0]
    crosses = int(np.count_nonzero(np.diff(sgn)))
    in_range = height_atr <= 12 and crosses >= 3
    prior = 100 * (c[-RANGE_BARS - 1] / c[-RANGE_BARS - PRIOR_BARS - 1] - 1) if n > RANGE_BARS + PRIOR_BARS else np.nan
    out.update(in_range=bool(in_range), range_low=round(sup, 2), range_high=round(res, 2),
               range_height_atr=round(height_atr, 1), pos_in_range=round((last - sup) / (res - sup), 2),
               prior_move_pct=round(prior, 1))

    # ---- effort vs result ----
    vol_dry = np.nanmean(v[-20:]) / np.nanmean(v[-60:-20])
    atr_contract = a / atr[-41] if np.isfinite(atr[-41]) else np.nan
    up = c[-40:] > c[-41:-1]
    vu, vd = v[-40:][up].sum(), v[-40:][~up].sum()
    ud_ratio = vu / vd if vd > 0 else np.nan
    out.update(vol_dryup=round(vol_dry, 2), atr_contraction=round(atr_contract, 2), updown_vol=round(ud_ratio, 2))

    waves = zigzag(c, atr)
    wv = [(s, e, dr, c[e] - c[s], v[s + 1:e + 1].sum()) for s, e, dr in waves if e > s]
    upw = [w for w in wv if w[2] == 1][-3:]
    dnw = [w for w in wv if w[2] == -1][-3:]
    wave_ratio = (np.mean([w[4] for w in upw]) / np.mean([w[4] for w in dnw])) if upw and dnw else np.nan
    sot_down = len(dnw) >= 2 and abs(dnw[-1][3]) < abs(dnw[-2][3])   # selling thrust shortening (bullish)
    sot_up = len(upw) >= 2 and upw[-1][3] < upw[-2][3]               # buying thrust shortening (bearish)
    lows = [c[e] for s, e, dr, *_ in wv if dr == -1][-3:]
    highs = [c[e] for s, e, dr, *_ in wv if dr == 1][-3:]
    higher_lows = len(lows) >= 2 and all(np.diff(lows) > 0)
    lower_highs = len(highs) >= 2 and all(np.diff(highs) < 0)
    out.update(wave_vol_ratio=round(wave_ratio, 2) if np.isfinite(wave_ratio) else np.nan,
               sot_down=sot_down, sot_up=sot_up, higher_lows=higher_lows, lower_highs=lower_highs)

    # ---- recent events (last 10 bars) ----
    hi20 = pd.Series(h).rolling(20).max().shift(1).to_numpy()
    lo20 = pd.Series(l).rolling(20).min().shift(1).to_numpy()
    rec = range(n - 10, n)
    sos = [i for i in rec if rr[i] >= 1.5 and rv[i] >= 1.5 and cp[i] >= 0.7 and c[i] > hi20[i]]
    sow = [i for i in rec if rr[i] >= 1.5 and rv[i] >= 1.5 and cp[i] <= 0.3 and c[i] < lo20[i]]
    clim = [i for i in range(n - 15, n) if rv[i] >= 3 and rr[i] >= 2]
    sc = [i for i in clim if c[i] < c[i - 20] * 0.9]       # climax after a >10% fall
    bc = [i for i in clim if c[i] > c[i - 20] * 1.1]       # climax after a >10% rise
    fmt = lambda xs: d.index[xs[-1]].strftime("%d %b") if xs else ""
    out.update(sos_bar=fmt(sos), sow_bar=fmt(sow), selling_climax=fmt(sc), buying_climax=fmt(bc))

    # ---- tested setup rules ----
    sigs, armed = generate_signals(d, DAILY)
    trig = [s for s in sigs if s["i"] >= n - 2]           # fired on the last 2 bars
    out["triggered"] = ", ".join(sorted({s["setup"] for s in trig}))
    out["building"] = ", ".join(sorted({s["setup"] for s in armed}))
    stop = next((s["stop"] for s in reversed(trig)), np.nan)
    level = next((s["level"] for s in reversed(trig)), next((s["level"] for s in armed), np.nan))
    out["setup_stop"] = round(stop, 2) if np.isfinite(stop) else np.nan
    out["setup_level"] = round(level, 2) if np.isfinite(level) else np.nan
    out["risk_pct"] = round(100 * abs(last - stop) / last, 1) if np.isfinite(stop) else np.nan
    out["risk_atr"] = round(abs(last - stop) / a, 1) if np.isfinite(stop) else np.nan
    names_t, names_b = set(out["triggered"].split(", ")), set(out["building"].split(", "))

    # ---- evidence scores (0-100) ----
    acc = dist = 0
    if in_range and prior <= -15: acc += 20
    if in_range and prior >= 15: dist += 15
    if stage == "markup": acc += 10
    if stage == "markdown": dist += 15
    if vol_dry < 0.8: acc += 10
    if vol_dry > 1.3 and in_range: dist += 5
    if np.isfinite(atr_contract) and atr_contract < 0.85: acc += 5
    if ud_ratio > 1.2: acc += 15
    elif ud_ratio > 1.0: acc += 5
    if ud_ratio < 0.83: dist += 15
    elif ud_ratio < 1.0: dist += 5
    if np.isfinite(wave_ratio) and wave_ratio > 1.15: acc += 10
    if np.isfinite(wave_ratio) and wave_ratio < 0.87: dist += 10
    if sot_down: acc += 5
    if sot_up: dist += 5
    if higher_lows: acc += 10
    if lower_highs: dist += 10
    if sos: acc += 10
    if sow: dist += 10
    if sc: acc += 5
    if bc: dist += 5
    acc += 20 if "SPRING" in names_t else 10 if "SPRING" in names_b else 0
    acc += 15 if "BUEC" in names_t else 5 if "BUEC" in names_b else 0
    dist += 20 if "UPTHRUST" in names_t else 10 if "UPTHRUST" in names_b else 0
    dist += 15 if "LPSY" in names_t else 5 if "LPSY" in names_b else 0
    out["acc_score"], out["dist_score"] = min(acc, 100), min(dist, 100)
    out["net_score"] = out["acc_score"] - out["dist_score"]

    # ---- category (screening label, not a recommendation) ----
    quiet_pullback = (stage == "markup" and last >= ma50[-1] - 0.5 * a and last <= ma50[-1] + 1.5 * a
                      and np.nanmean(rv[-5:]) < 0.85 and c[-1] < c[-6])
    if "SPRING" in names_t:
        cat, act = "Phase C: spring triggered", "Review now"
    elif "BUEC" in names_t:
        cat, act = "Phase D: breakout test (LPS/BUEC) triggered", "Review now"
    elif "UPTHRUST" in names_t or "LPSY" in names_t:
        cat, act = "Distribution: upthrust / LPSY triggered", "Avoid longs"
    elif "SPRING" in names_b:
        cat, act = "Phase C: spring building (awaiting test)", "Watchlist"
    elif "BUEC" in names_b:
        cat, act = "Phase D: breakout, awaiting quiet pullback", "Watchlist"
    elif quiet_pullback and out["net_score"] > 0:
        cat, act = "Phase E markup: quiet pullback (LPS zone)", "Watchlist"
    elif in_range and prior <= -15 and out["acc_score"] >= 50 and out["net_score"] >= 20:
        cat, act = "Accumulation candidate (Phase B)", "Watchlist"
    elif in_range and stage == "markup" and out["acc_score"] >= 50 and out["net_score"] >= 20:
        cat, act = "Re-accumulation candidate", "Watchlist"
    elif out["dist_score"] >= 50 and out["net_score"] <= -20:
        cat, act = "Distribution warning", "Avoid longs"
    elif stage == "markdown":
        cat, act = "Markdown (downtrend)", "Avoid longs"
    else:
        cat, act = "No clear structure", "Ignore"
    # Effort vs result must confirm a long trigger (Law of Effort and Result): weak evidence -> watch only
    if act == "Review now" and out["net_score"] < 10:
        cat, act = cat.replace("triggered", "triggered, volume not confirming"), "Watchlist"
    # Same risk rule as the backtest engine: a stop more than 4 ATR away means the entry is extended
    elif act == "Review now" and out["risk_atr"] > DAILY.max_risk_atr:
        cat, act = cat.replace("triggered", "triggered, extended (stop > 4 ATR)"), "Watchlist"
    out["category"], out["action"] = cat, act
    return out
