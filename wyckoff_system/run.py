"""Command-line entry point.

  python run.py backtest --preset daily --universe nifty30
  python run.py backtest --preset 5m --symbols NIFTYBEES.NS
  python run.py backtest --preset 5m --symbols ^NSEI --volume-from NIFTYBEES.NS
  python run.py scan     --preset daily --universe nifty30

Educational tool. Not investment advice; backtests are not a promise of future results.
"""
import argparse
import os
import sys
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)          # allow running with `python -I`

import pandas as pd                # noqa: E402
from config import PRESETS         # noqa: E402
from data import fetch             # noqa: E402
from signals import add_indicators, generate_signals  # noqa: E402
from backtest import backtest, summarize               # noqa: E402

UNIVERSES = {
    "nifty30": [
        "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS", "ITC.NS", "LT.NS",
        "SBIN.NS", "BHARTIARTL.NS", "AXISBANK.NS", "KOTAKBANK.NS", "HINDUNILVR.NS", "BAJFINANCE.NS",
        "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "NTPC.NS", "POWERGRID.NS",
        "ASIANPAINT.NS", "M&M.NS", "WIPRO.NS", "HCLTECH.NS", "ONGC.NS", "TATASTEEL.NS",
        "JSWSTEEL.NS", "NESTLEIND.NS", "COALINDIA.NS", "BAJAJ-AUTO.NS", "DRREDDY.NS",
    ],
    "nifty": ["NIFTYBEES.NS"],
}
INTERVAL = {"daily": ("1d", "10y"), "5m": ("5m", "60d")}


def parse():
    ap = argparse.ArgumentParser(description="Wyckoff rule-based system")
    ap.add_argument("command", choices=["backtest", "scan"])
    ap.add_argument("--preset", choices=list(PRESETS), default="daily")
    ap.add_argument("--symbols", help="comma-separated Yahoo tickers")
    ap.add_argument("--universe", choices=list(UNIVERSES))
    ap.add_argument("--volume-from", help="take volume from this ticker (e.g. NIFTYBEES.NS for ^NSEI)")
    ap.add_argument("--period", help="Yahoo period, e.g. 10y, 60d")
    ap.add_argument("--long-only", action="store_true", help="no short setups (cash-market delivery)")
    ap.add_argument("--no-context", action="store_true", help="disable the moving-average context filter")
    ap.add_argument("--rmult", type=float, help="profit target in R (default 2)")
    ap.add_argument("--cost-bps", type=float, help="cost per side in basis points (default: preset)")
    ap.add_argument("--market-filter", action="store_true", help="trade only with the Nifty 200-day trend")
    ap.add_argument("--setups", help="comma-separated subset of SPRING,UPTHRUST,BUEC,LPSY (default: all)")
    ap.add_argument("--split", default="2022-01-01", help="date that separates the two test periods")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--cache", default=os.path.join(HERE, "data_cache"))
    ap.add_argument("--refresh", action="store_true", help="re-download data")
    return ap.parse_args()


def build_params(a):
    p = PRESETS[a.preset]
    if a.long_only: p = replace(p, long_only=True)
    if a.no_context: p = replace(p, ctx_len=0)
    if a.rmult: p = replace(p, rmult=a.rmult)
    if a.cost_bps is not None: p = replace(p, cost_bps=a.cost_bps)
    if a.market_filter: p = replace(p, market_filter=True)
    return p


def symbols_of(a):
    if a.symbols: return [s.strip() for s in a.symbols.split(",") if s.strip()]
    if a.universe: return UNIVERSES[a.universe]
    sys.exit("give --symbols or --universe")


def load(sym, a):
    interval, period = INTERVAL[a.preset]
    return fetch(sym, interval, a.period or period, a.cache, volume_from=a.volume_from, refresh=a.refresh)


_MKT = {}


def attach_market(df, a, p):
    """Add df['mkt']: 1 if Nifty closed above its moving average, else 0 (NaN while the MA warms up).
    Daily bars use the same day's Nifty close (known at the signal bar's close).
    Intraday bars use the PREVIOUS day's value, to avoid look-ahead."""
    if not p.market_filter:
        return df
    if "up" not in _MKT:
        m = fetch("^NSEI", "1d", "10y", a.cache, refresh=a.refresh)
        sma = m["Close"].rolling(p.market_ma).mean()
        up = (m["Close"] > sma).astype(float).where(sma.notna())
        up.index = up.index.date
        _MKT["up"] = up.shift(1) if p.intraday else up
    df["mkt"] = pd.Series(df.index.date, index=df.index).map(_MKT["up"]).to_numpy(dtype=float)
    return df


def keep(items, a):
    if not a.setups:
        return items
    allowed = {s.strip().upper() for s in a.setups.split(",")}
    return [x for x in items if x["setup"] in allowed]


def cmd_backtest(a, p):
    os.makedirs(a.out, exist_ok=True)
    all_trades = []
    for sym in symbols_of(a):
        try:
            df = attach_market(add_indicators(load(sym, a), p), a, p)
        except Exception as e:
            print(f"  skip {sym}: {e}")
            continue
        sigs, _ = generate_signals(df, p)
        sigs = keep(sigs, a)
        tr = backtest(df, sigs, p, sym)
        all_trades += tr
        print(f"  {sym:16s} bars {len(df):5d}  signals {len(sigs):4d}  trades {len(tr):4d}")
    if not all_trades:
        print("no trades"); return
    t = pd.DataFrame(all_trades).sort_values("exit_time")
    tag = f"{a.preset}_{'long' if p.long_only else 'both'}{'_noctx' if not p.ctx_len else ''}_{p.cost_bps:g}bps"
    if a.setups: tag += "_" + a.setups.replace(",", "-").lower()
    if p.market_filter: tag += "_mkt"
    t.to_csv(os.path.join(a.out, f"trades_{tag}.csv"), index=False)

    rows = [summarize(all_trades, p, "ALL")]
    for name, g in t.groupby("setup"):
        rows.append(summarize(g.to_dict("records"), p, name))
    for side, g in t.groupby("side"):
        rows.append(summarize(g.to_dict("records"), p, "longs" if side == 1 else "shorts"))
    split = pd.Timestamp(a.split, tz=t["entry_time"].iloc[0].tz)
    early, late = t[t["entry_time"] < split], t[t["entry_time"] >= split]
    if len(early) and len(late):
        rows.append(summarize(early.to_dict("records"), p, f"before {a.split}"))
        rows.append(summarize(late.to_dict("records"), p, f"from {a.split}"))
    s = pd.DataFrame(rows).set_index("label")
    print("\n" + s.to_string())
    s.to_csv(os.path.join(a.out, f"summary_{tag}.csv"))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.plot(t["exit_time"].to_numpy(), t["R"].cumsum().to_numpy(), lw=1.4, label="all setups")
        for name, g in t.groupby("setup"):
            ax.plot(g["exit_time"].to_numpy(), g["R"].cumsum().to_numpy(), lw=0.9, alpha=0.8, label=name)
        ax.axhline(0, color="#999", lw=0.8)
        ax.set_title(f"Cumulative R (after costs), preset={a.preset}, {len(t)} trades")
        ax.set_ylabel("R"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
        fig.tight_layout(); fig.savefig(os.path.join(a.out, f"equity_{tag}.png"), dpi=120)
    except Exception as e:
        print("chart skipped:", e)
    print(f"\nsaved trades/summary/equity to {a.out}")


def cmd_scan(a, p):
    """Run after the close: list setups that trigger at the next open, and setups still building."""
    rows = []
    for sym in symbols_of(a):
        try:
            df = attach_market(add_indicators(load(sym, a), p), a, p)
        except Exception as e:
            print(f"  skip {sym}: {e}"); continue
        sigs, armed = generate_signals(df, p)
        sigs, armed = keep(sigs, a), keep(armed, a)
        last = len(df) - 1
        px, atr = df["Close"].iloc[-1], df["atr"].iloc[-1]
        bar = f"{df.index[-1]:%Y-%m-%d %H:%M}" if p.intraday else f"{df.index[-1]:%Y-%m-%d}"
        for s in sigs:
            if s["i"] == last:
                risk = abs(px - s["stop"])
                rows.append(dict(symbol=sym, bar=bar, status="ENTRY next open", setup=s["setup"],
                                 side="long" if s["side"] == 1 else "short", close=round(px, 2),
                                 stop=round(s["stop"], 2),
                                 target=round(px + s["side"] * p.rmult * risk, 2),
                                 level=round(s["level"], 2), note=s["note"]))
        for s in armed:
            rows.append(dict(symbol=sym, bar=bar, status=f"building ({s['stage']})", setup=s["setup"],
                             side="long" if s["side"] == 1 else "short", close=round(px, 2),
                             stop="", target="", level=round(s["level"], 2),
                             note=f"extreme {s['extreme']:.2f}, ATR {atr:.2f}"))
    print(f"\nScan (preset={a.preset}, setups={a.setups or 'all'}, long_only={p.long_only})")
    if not rows:
        print("No setups triggered or building."); return
    out = pd.DataFrame(rows).sort_values(["status", "symbol"])
    print(out.to_string(index=False))
    os.makedirs(a.out, exist_ok=True)
    out.to_csv(os.path.join(a.out, f"scan_{a.preset}.csv"), index=False)


if __name__ == "__main__":
    args = parse()
    params = build_params(args)
    (cmd_backtest if args.command == "backtest" else cmd_scan)(args, params)
