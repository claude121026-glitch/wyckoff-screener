"""Bar-by-bar backtest of the signals.

Conservative assumptions:
  * entry at the next bar's open; skipped if that open is already beyond the stop
  * if a bar touches both stop and target, the stop is assumed to fill first
  * gaps through the stop/target fill at the open, not at the level
  * costs charged on both sides
"""
import numpy as np
import pandas as pd


def _hhmm(ts):
    return ts.strftime("%H:%M")


def backtest(df, signals, p, symbol=""):
    o, h, l, c, atr = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close", "atr"))
    idx, dates, n = df.index, df.index.date, len(df)
    by_bar = {}
    for s in signals:
        by_bar.setdefault(s["i"], []).append(s)
    cost = p.cost_bps / 1e4
    trades, pos = [], None
    session_bar = 0

    for i in range(n):
        session_bar = 0 if i == 0 or dates[i] != dates[i - 1] else session_bar + 1

        # ----- entry from a signal on the previous bar -----
        if pos is None and (i - 1) in by_bar:
            s = by_bar[i - 1][0]
            side, stop, entry = s["side"], s["stop"], o[i]
            risk = (entry - stop) * side
            a = atr[i - 1]
            ok = risk > 0 and np.isfinite(a) and p.min_risk_atr * a <= risk <= p.max_risk_atr * a
            ok = ok and 2 * cost * entry <= p.max_cost_frac * risk      # costs must be small vs. risk
            if p.intraday:
                ok = ok and session_bar >= p.skip_open_bars and _hhmm(idx[i]) <= p.last_entry \
                     and dates[i] == dates[i - 1]           # never carry a signal across sessions
            if ok:
                pos = dict(symbol=symbol, setup=s["setup"], side=side, entry_time=idx[i], entry=entry,
                           stop=stop, target=entry + side * p.rmult * risk, risk=risk, i0=i, note=s["note"])

        # ----- manage the open position -----
        if pos is not None:
            side, stop, tgt = pos["side"], pos["stop"], pos["target"]
            px = reason = None
            if side == 1:
                if o[i] <= stop: px, reason = o[i], "stop (gap)"
                elif l[i] <= stop: px, reason = stop, "stop"
                elif o[i] >= tgt: px, reason = o[i], "target (gap)"
                elif h[i] >= tgt: px, reason = tgt, "target"
            else:
                if o[i] >= stop: px, reason = o[i], "stop (gap)"
                elif h[i] >= stop: px, reason = stop, "stop"
                elif o[i] <= tgt: px, reason = o[i], "target (gap)"
                elif l[i] <= tgt: px, reason = tgt, "target"
            if px is None:
                last_of_session = i == n - 1 or dates[i + 1] != dates[i]
                if p.intraday and (_hhmm(idx[i]) >= p.exit_time or last_of_session):
                    px, reason = c[i], "session exit"
                elif not p.intraday and i - pos["i0"] + 1 >= p.max_hold:
                    px, reason = c[i], "time stop"
                elif i == n - 1:
                    px, reason = c[i], "end of data"
            if px is not None:
                e_eff = pos["entry"] * (1 + side * cost)
                x_eff = px * (1 - side * cost)
                pos.update(exit_time=idx[i], exit=px, reason=reason, bars=i - pos["i0"] + 1,
                           R=side * (x_eff - e_eff) / pos["risk"],
                           ret_pct=side * (x_eff / e_eff - 1) * 100)
                trades.append(pos)
                pos = None
    return trades


def summarize(trades, p, label="ALL"):
    if not trades:
        return {"label": label, "trades": 0}
    t = pd.DataFrame(trades).sort_values("exit_time")
    R = t["R"].to_numpy()
    wins, losses = R[R > 0], R[R <= 0]
    cum = np.cumsum(R)
    dd_R = float(np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]))
    eq = np.cumprod(1 + p.risk_pct / 100 * R)
    peak = np.maximum.accumulate(np.r_[1, eq])
    dd_eq = float(np.max(1 - np.r_[1, eq] / peak)) * 100
    return {
        "label": label,
        "trades": len(R),
        "win%": round(100 * len(wins) / len(R), 1),
        "avg_R": round(float(R.mean()), 3),
        "total_R": round(float(R.sum()), 1),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else float("inf"),
        "max_dd_R": round(dd_R, 1),
        f"equity_x@{p.risk_pct:g}%risk": round(float(eq[-1]), 3),
        "max_dd_%": round(dd_eq, 1),
        "avg_bars": round(float(t["bars"].mean()), 1),
    }
