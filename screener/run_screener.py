"""Run the Wyckoff screener on all NSE stocks and build an HTML report.

  python -I fetch_data.py          # once per evening, after 15:45 IST
  python -I run_screener.py        # analyse + report
  python -I run_screener.py --min-turnover 10 --charts 60

Output: reports/<date>/screener.csv and reports/<date>/report.html (+ charts/).
Screening labels are for manual chart review. Not investment advice.
"""
import argparse
import html
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fetch_data import latest_prices, load_listing   # noqa: E402
from wyckoff_screen import analyze, RANGE_BARS        # noqa: E402

ACTION_ORDER = ["Review now", "Watchlist", "Avoid longs", "Ignore"]


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-turnover", type=float, default=5.0, help="median daily traded value, Rs crore")
    ap.add_argument("--min-price", type=float, default=10.0)
    ap.add_argument("--charts", type=int, default=40, help="max watchlist charts (all 'Review now' are charted)")
    return ap.parse_args()


def chart(sym, name, df, row, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = df.iloc[-160:]
    c = df["Close"]
    ma50, ma200 = c.rolling(50).mean().iloc[-160:], c.rolling(200).mean().iloc[-160:]
    fig, (ax, av) = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    for i, (_, r) in enumerate(x.iterrows()):
        col = "#2e7d32" if r.Close >= r.Open else "#c62828"
        ax.vlines(i, r.Low, r.High, color=col, lw=0.8)
        ax.add_patch(plt.Rectangle((i - 0.35, min(r.Open, r.Close)), 0.7, max(abs(r.Close - r.Open), 1e-9), color=col))
        av.bar(i, r.Volume, color=col, width=0.8)
    ax.plot(range(len(x)), ma50.to_numpy(), color="#1565c0", lw=1, label="50-day MA")
    ax.plot(range(len(x)), ma200.to_numpy(), color="#6a1b9a", lw=1, label="200-day MA")
    s0 = len(x) - RANGE_BARS
    ax.hlines([row["range_low"], row["range_high"]], s0, len(x) - 1, colors="#ef6c00", linestyles="--", lw=0.8,
              alpha=0.7, label=f"{RANGE_BARS}-day high/low")
    if np.isfinite(row.get("setup_level", np.nan)):
        ax.axhline(row["setup_level"], color="#2e7d32", lw=1.1, ls="-.",
                   label=f"setup level {row['setup_level']} ({row['triggered'] or row['building']})")
    if np.isfinite(row.get("setup_stop", np.nan)):
        ax.axhline(row["setup_stop"], color="#c62828", lw=1, ls=":", label=f"setup stop {row['setup_stop']}")
    av.plot(range(len(x)), x["Volume"].rolling(20).mean().to_numpy(), color="#333", lw=0.8)
    av.set_ylim(0, float(np.nanmedian(x["Volume"])) * 5)   # keep normal bars visible; spikes are clipped
    ticks = list(range(0, len(x), 20))
    av.set_xticks(ticks); av.set_xticklabels([x.index[i].strftime("%d %b %y") for i in ticks], fontsize=7)
    ax.set_title(f"{sym}  {name[:40]}  |  {row['category']}  |  acc {row['acc_score']} / dist {row['dist_score']}",
                 fontsize=9.5)
    ax.legend(fontsize=7, loc="upper left"); ax.grid(alpha=0.25); av.grid(alpha=0.25)
    av.ticklabel_format(axis="y", style="plain"); av.set_yticklabels([])
    fig.tight_layout(); fig.savefig(path, dpi=95); plt.close(fig)


def main():
    a = parse()
    px, src = latest_prices()
    # align everyone to the most common last date; drop stale (suspended) symbols
    last = px.groupby("symbol")["date"].max()
    common = last.mode().iloc[0]
    px = px[px["date"] <= common]
    stale = last[last < common - pd.Timedelta(days=7)].index
    px = px[~px["symbol"].isin(stale)]
    names = load_listing().set_index("symbol")
    rows, data = [], {}
    for sym, g in px.groupby("symbol"):
        g = g.set_index("date").sort_index()[["Open", "High", "Low", "Close", "Volume"]]
        if len(g) < 260 or g["Close"].iloc[-1] < a.min_price:
            continue
        turnover = np.nanmedian((g["Close"] * g["Volume"]).iloc[-50:]) / 1e7
        if turnover < a.min_turnover:
            continue
        try:
            r = analyze(g)
        except Exception as e:
            print(f"  {sym}: skipped ({e})"); continue
        r = {"symbol": sym, "name": names["name"].get(sym, ""), "series": names["series"].get(sym, ""), **r}
        rows.append(r); data[sym] = g
    res = pd.DataFrame(rows)
    res["action"] = pd.Categorical(res["action"], ACTION_ORDER, ordered=True)
    res = res.sort_values(["action", "net_score"], ascending=[True, False])
    asof = str(res["date"].max())
    out_dir = os.path.join(HERE, "reports", asof); os.makedirs(os.path.join(out_dir, "charts"), exist_ok=True)
    res.to_csv(os.path.join(out_dir, "screener.csv"), index=False)

    # charts: every "Review now", then the best watchlist names by net score
    to_chart = pd.concat([res[res.action == "Review now"],
                          res[res.action == "Watchlist"].head(a.charts)])
    for _, r in to_chart.iterrows():
        chart(r.symbol, r["name"], data[r.symbol], r, os.path.join(out_dir, "charts", f"{r.symbol}.png"))

    n_total = px["symbol"].nunique()
    write_html(res, to_chart, out_dir, asof, n_total, len(res), a, src)
    print(f"\nuniverse with data: {n_total} | liquid & analysed: {len(res)} | as of {asof}")
    print(res.groupby(["action", "category"], observed=True).size().to_string())
    print(f"\nreport: {os.path.join(out_dir, 'report.html')}")


def write_html(res, charted, out_dir, asof, n_total, n_liquid, a, src):
    esc = html.escape
    cols = ["symbol", "name", "close", "category", "action", "acc_score", "dist_score", "net_score", "stage",
            "turnover_cr", "pos_in_range", "range_low", "range_high", "prior_move_pct", "vol_dryup", "updown_vol",
            "wave_vol_ratio", "triggered", "building", "setup_level", "setup_stop", "risk_pct", "risk_atr", "sos_bar", "sow_bar", "selling_climax", "buying_climax"]
    def table(df, tid):
        head = "".join(f"<th onclick=\"sortT('{tid}',{k})\">{esc(c)}</th>" for k, c in enumerate(cols))
        body = []
        for _, r in df.iterrows():
            cells = []
            for c in cols:
                v = r[c]
                v = "" if (isinstance(v, float) and not np.isfinite(v)) else v
                cells.append(f"<td>{esc(str(v))}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        return f"<table id='{tid}'><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
    counts = res.groupby(["action", "category"], observed=True).size().reset_index(name="stocks")
    count_rows = "".join(f"<tr><td>{esc(str(r.action))}</td><td>{esc(r.category)}</td><td>{r.stocks}</td></tr>"
                         for r in counts.itertuples())
    cards = []
    for _, r in charted.iterrows():
        cards.append(f"<div class='card'><img src='charts/{esc(r.symbol)}.png' loading='lazy'>"
                     f"<p><b>{esc(r.symbol)}</b>: {esc(str(r.action))}. Range {r.range_low}–{r.range_high}, "
                     f"up/down volume {r.updown_vol}, volume dry-up {r.vol_dryup}. "
                     f"{'Triggered: ' + esc(r.triggered) + '. ' if r.triggered else ''}"
                     f"{'Building: ' + esc(r.building) + '. ' if r.building else ''}"
                     f"{'Setup stop ' + str(r.setup_stop) + '.' if np.isfinite(r.setup_stop) else ''}</p></div>")
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Wyckoff screener {asof}</title>
<meta name="color-scheme" content="light">
<style>:root{{color-scheme:light}} html,body{{background:#fff;color:#222}}
body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;max-width:1500px}} td{{background:#fff}}
h1{{margin-bottom:4px}} .warn{{background:#fff3e0;border:1px solid #ffb74d;padding:12px 16px;border-radius:6px}}
table{{border-collapse:collapse;font-size:12px;margin:8px 0}} th,td{{border:1px solid #ddd;padding:3px 6px;white-space:nowrap}}
th{{background:#f5f5f5;cursor:pointer;position:sticky;top:0}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:14px}}
.card{{border:1px solid #ddd;border-radius:6px;padding:6px}} .card img{{width:100%}} .card p{{font-size:12px;margin:4px}}
#q{{padding:6px;width:320px}} .scroll{{max-height:640px;overflow:auto}}</style></head><body>
<h1>Wyckoff screener: NSE, as of {asof}</h1>
<p>{n_total} NSE securities with Yahoo data · {n_liquid} passed the filters (median turnover ≥ ₹{a.min_turnover:g} cr/day, price ≥ ₹{a.min_price:g}, 260+ days of history) · price file {esc(src)}</p>
<div class="warn"><b>Read this first.</b> These labels sort charts for <b>manual Wyckoff review</b>. They are not buy or sell recommendations.
In 10-year backtests on 60 NSE stocks, the coded setups showed no reliable edge: springs did best (+0.21R per trade from 2016–2026) but lost money from Mar 2024 onward,
and none of 12,096 rule combinations was profitable in every period and stock group. Check every chart yourself, define your own stop, and size your positions for your own risk.</div>
<h2>Summary</h2><table><tr><th>Action</th><th>Category</th><th>Stocks</th></tr>{count_rows}</table>
<h2>Charts: every “Review now” stock, plus the top watchlist names by net score</h2><div class="grid">{''.join(cards)}</div>
<h2>All analysed stocks</h2><input id="q" placeholder="filter: symbol, category, action…" oninput="filt()">
<div class="scroll">{table(res, "all")}</div>
<p style="font-size:11px;color:#666">Scores: acc = accumulation evidence (range after a decline, volume drying up, up-volume above down-volume, larger up-waves, shortening selling thrusts, higher lows, sign-of-strength bars, spring/breakout-test rules).
dist = the mirror image. Net = acc − dist. Data: NSE equity list and Yahoo Finance daily bars.</p>
<script>
function filt(){{const q=document.getElementById('q').value.toLowerCase();
 document.querySelectorAll('#all tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(q)?'':'none');}}
function sortT(id,k){{const t=document.getElementById(id),b=t.tBodies[0],rs=[...b.rows];
 const dir=t.dataset.k==k&&t.dataset.d=='a'?'d':'a';t.dataset.k=k;t.dataset.d=dir;
 rs.sort((x,y)=>{{let a=x.cells[k].innerText,c=y.cells[k].innerText,na=parseFloat(a),nc=parseFloat(c);
  let r=(!isNaN(na)&&!isNaN(nc))?na-nc:a.localeCompare(c);return dir=='a'?r:-r;}});rs.forEach(r=>b.appendChild(r));}}
</script></body></html>"""
    with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
