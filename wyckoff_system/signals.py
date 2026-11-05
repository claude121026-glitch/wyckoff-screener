"""Wyckoff setups as explicit rules.

Four setups, each a small state machine that only uses information
available at the close of the current bar (no look-ahead):

  SPRING   (long)  washout below range support, recovery, quiet test, trigger
  UPTHRUST (short) mirror image above range resistance
  BUEC     (long)  sign-of-strength breakout above resistance, quiet pullback
                   that stays out of the range, trigger  (Back-Up / LPS)
  LPSY     (short) sign-of-weakness breakdown below support, quiet rally
                   that stays out of the range, trigger  (Last Point of Supply)

A signal on bar i means: enter at the OPEN of bar i+1.
"""
import numpy as np
import pandas as pd


def add_indicators(df, p):
    df = df.copy()
    h, l, c = df["High"], df["Low"], df["Close"]
    v = df["Volume"].astype(float).where(df["Volume"] > 0)  # 0 volume = missing
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(p.atr_len).mean()
    df["vavg"] = v.rolling(p.vol_len, min_periods=int(p.vol_len * 0.6)).mean().shift(1)
    df["rv"] = v / df["vavg"]                       # relative volume
    rng = h - l
    df["ravg"] = rng.rolling(p.vol_len).mean().shift(1)
    df["rr"] = rng / df["ravg"]                     # relative bar range (spread)
    df["cp"] = np.where(rng > 0, (c - l) / rng.where(rng > 0), 0.5)  # close position 0..1
    df["sup"] = l.rolling(p.range_len).min().shift(1)  # range of the PRIOR bars
    df["res"] = h.rolling(p.range_len).max().shift(1)
    df["ctx"] = c.rolling(p.ctx_len).mean() if p.ctx_len else np.nan

    # A range is "valid" when it is the right height and price swung across it.
    n, L = len(df), p.range_len
    sup, res, atr, cl = df["sup"].to_numpy(), df["res"].to_numpy(), df["atr"].to_numpy(), c.to_numpy()
    valid = np.zeros(n, dtype=bool)
    for i in range(L + 1, n):
        a = atr[i - 1]
        if not (np.isfinite(sup[i]) and np.isfinite(res[i]) and np.isfinite(a)) or a <= 0:
            continue
        hgt = res[i] - sup[i]
        if hgt < p.min_h_atr * a or hgt > p.max_h_atr * a:
            continue
        sgn = np.sign(cl[i - L:i] - (sup[i] + res[i]) / 2)
        sgn = sgn[sgn != 0]
        valid[i] = np.count_nonzero(np.diff(sgn)) >= p.min_cross
    df["valid"] = valid
    return df


def generate_signals(df, p):
    """Return (signals, armed). signals: list of dicts. armed: setups still in progress at the last bar."""
    o, h, l, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    rv, rr, cp = df["rv"].to_numpy(), df["rr"].to_numpy(), df["cp"].to_numpy()
    atr, sup, res, valid = df["atr"].to_numpy(), df["sup"].to_numpy(), df["res"].to_numpy(), df["valid"].to_numpy()
    ctx = df["ctx"].to_numpy()
    mkt = df["mkt"].to_numpy() if "mkt" in df.columns else None   # 1 = Nifty above its MA, 0 = below
    dates = df.index.date
    n = len(df)
    nz = lambda x: x if np.isfinite(x) else np.nan

    active = {}   # setup name -> state dict
    signals = []

    def ctx_ok(side, i):
        if p.market_filter:
            if mkt is None or not np.isfinite(mkt[i]):
                return False
            if (side == 1 and mkt[i] < 0.5) or (side == -1 and mkt[i] > 0.5):
                return False
        if not p.ctx_len or not np.isfinite(ctx[i]):
            return not p.ctx_len
        return c[i] > ctx[i] if side == 1 else c[i] < ctx[i]

    def emit(name, side, i, stop, level, note):
        if side == -1 and p.long_only:
            return
        if not ctx_ok(side, i):
            return
        signals.append(dict(i=i, time=df.index[i], setup=name, side=side,
                            stop=float(stop), level=float(level), note=note))

    for i in range(1, n):
        a = atr[i - 1]
        if not np.isfinite(a) or a <= 0:
            continue
        if p.reset_daily and dates[i] != dates[i - 1]:
            active.clear()

        # ---------- advance existing setups ----------
        for name in list(active):
            s = active[name]
            side = s["side"]
            done = False

            if name in ("SPRING", "UPTHRUST"):
                lvl = s["level"]
                if s["stage"] == "pen":
                    if side == 1:
                        s["ext"] = min(s["ext"], l[i])
                        too_deep = l[i] < lvl - p.max_pen_atr * s["atr0"]
                        recovered = c[i] > lvl
                    else:
                        s["ext"] = max(s["ext"], h[i])
                        too_deep = h[i] > lvl + p.max_pen_atr * s["atr0"]
                        recovered = c[i] < lvl
                    s["pen_rv"] = np.nanmax([s["pen_rv"], nz(rv[i])])
                    if too_deep:
                        done = True
                    elif recovered:
                        s["stage"], s["rec_i"] = "test", i
                        strong_close = cp[i] >= p.trig_cp if side == 1 else cp[i] <= 1 - p.trig_cp
                        if p.direct_low_vol and np.isfinite(s["pen_rv"]) and s["pen_rv"] < p.low_vol and strong_close:
                            stop = s["ext"] - side * p.stop_buf_atr * a
                            emit(name, side, i, stop, lvl, "shake on low volume (Spring/UT #3), direct entry")
                            done = True
                    elif i - s["i0"] >= p.rec_bars:
                        done = True
                else:  # waiting for a quiet test, then a trigger
                    failed = c[i] < s["ext"] if side == 1 else c[i] > s["ext"]
                    if failed or i - s["rec_i"] > p.test_bars:
                        done = True
                    else:
                        holds = l[i] > s["ext"] if side == 1 else h[i] < s["ext"]
                        near = (l[i] <= lvl + p.test_zone_atr * a) if side == 1 else (h[i] >= lvl - p.test_zone_atr * a)
                        quiet = np.isfinite(rv[i]) and rv[i] < p.test_rv and rr[i] < p.test_rr
                        if s.get("test_hi") is not None:
                            trig = (c[i] > s["test_hi"] and cp[i] >= p.trig_cp) if side == 1 else \
                                   (c[i] < s["test_lo"] and cp[i] <= 1 - p.trig_cp)
                            if trig:
                                stop = s["ext"] - side * p.stop_buf_atr * a
                                emit(name, side, i, stop, lvl, "quiet test held, trigger bar")
                                done = True
                        if not done and i > s["rec_i"] and holds and near and quiet:
                            s["test_hi"], s["test_lo"] = h[i], l[i]   # latest qualifying test bar

            else:  # BUEC / LPSY
                lvl = s["level"]
                back_in = c[i] < lvl - p.reentry_atr * a if side == 1 else c[i] > lvl + p.reentry_atr * a
                if back_in or i - s["i0"] > p.pb_max:
                    done = True
                else:
                    if side == 1:
                        s["pb_ext"] = min(s["pb_ext"], l[i])
                    else:
                        s["pb_ext"] = max(s["pb_ext"], h[i])
                    if not s["pulling"]:
                        if (side == 1 and c[i] < c[i - 1]) or (side == -1 and c[i] > c[i - 1]):
                            s["pulling"] = True
                            s["pb_rv"].append(nz(rv[i]))
                    else:
                        trig = (c[i] > h[i - 1] and cp[i] >= p.sos_cp) if side == 1 else \
                               (c[i] < l[i - 1] and cp[i] <= 1 - p.sos_cp)
                        pbv = np.nanmean(s["pb_rv"]) if np.any(np.isfinite(s["pb_rv"])) else np.nan
                        if trig and np.isfinite(pbv) and pbv < p.pb_rv:
                            inv = min(s["pb_ext"], lvl) if side == 1 else max(s["pb_ext"], lvl)
                            stop = inv - side * p.stop_buf_atr * a
                            emit(name, side, i, stop, lvl, "breakout held, quiet pullback, trigger bar")
                            done = True
                        else:
                            s["pb_rv"].append(nz(rv[i]))
            if done:
                del active[name]

        # ---------- detect new setups (need a valid range on this bar) ----------
        if not valid[i]:
            continue
        if "SPRING" not in active and l[i] < sup[i] and l[i] >= sup[i] - p.max_pen_atr * a and c[i] <= sup[i] + 0.0:
            active["SPRING"] = dict(side=1, stage="pen", level=sup[i], ext=l[i], i0=i, atr0=a, pen_rv=nz(rv[i]))
        elif "SPRING" not in active and l[i] < sup[i] and c[i] > sup[i] and l[i] >= sup[i] - p.max_pen_atr * a:
            # one-bar spring (hammer): penetrates and closes back inside on the same bar
            active["SPRING"] = dict(side=1, stage="pen", level=sup[i], ext=l[i], i0=i, atr0=a, pen_rv=nz(rv[i]))
            s = active["SPRING"]; s["stage"], s["rec_i"] = "test", i
            if p.direct_low_vol and np.isfinite(s["pen_rv"]) and s["pen_rv"] < p.low_vol and cp[i] >= p.trig_cp:
                emit("SPRING", 1, i, l[i] - p.stop_buf_atr * a, sup[i], "one-bar spring on low volume, direct entry")
                del active["SPRING"]
        if "UPTHRUST" not in active and h[i] > res[i] and h[i] <= res[i] + p.max_pen_atr * a:
            active["UPTHRUST"] = dict(side=-1, stage="pen", level=res[i], ext=h[i], i0=i, atr0=a, pen_rv=nz(rv[i]))
            if c[i] < res[i]:
                s = active["UPTHRUST"]; s["stage"], s["rec_i"] = "test", i
                if p.direct_low_vol and np.isfinite(s["pen_rv"]) and s["pen_rv"] < p.low_vol and cp[i] <= 1 - p.trig_cp:
                    emit("UPTHRUST", -1, i, h[i] + p.stop_buf_atr * a, res[i], "one-bar upthrust on low volume, direct entry")
                    del active["UPTHRUST"]
        sig_bar = np.isfinite(rv[i]) and rv[i] >= p.sos_rv and rr[i] >= p.sos_rr
        if "BUEC" not in active and sig_bar and c[i] > res[i] and cp[i] >= p.sos_cp:
            active["BUEC"] = dict(side=1, level=res[i], i0=i, pb_ext=np.inf, pulling=False, pb_rv=[])
            active.pop("UPTHRUST", None)
        if "LPSY" not in active and sig_bar and c[i] < sup[i] and cp[i] <= 1 - p.sos_cp:
            active["LPSY"] = dict(side=-1, level=sup[i], i0=i, pb_ext=-np.inf, pulling=False, pb_rv=[])
            active.pop("SPRING", None)

    armed = []
    for name, s in active.items():
        if s["side"] == -1 and p.long_only:
            continue
        armed.append(dict(setup=name, side=s["side"], level=float(s["level"]),
                          stage=s.get("stage", "pullback" if s.get("pulling") else "breakout"),
                          extreme=float(s.get("ext", s.get("pb_ext", np.nan)))))
    return signals, armed
