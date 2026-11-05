"""Streamlit front-end for the NSE Wyckoff screener.

  streamlit run screener/app.py

Screening labels are for manual chart review. Not investment advice.
"""
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(HERE, "reports")
PRICES = os.path.join(HERE, "data", "prices")
ACTIONS = ["Review now", "Watchlist", "Avoid longs", "Ignore"]
ACTION_COLOR = {"Review now": "#2e7d32", "Watchlist": "#1565c0", "Avoid longs": "#c62828", "Ignore": "#757575"}

st.set_page_config(page_title="NSE Wyckoff Screener", page_icon="📈", layout="wide")


# ---------------- data ----------------
def report_dates():
    if not os.path.isdir(REPORTS):
        return []
    return sorted((d for d in os.listdir(REPORTS) if os.path.exists(os.path.join(REPORTS, d, "screener.csv"))),
                  reverse=True)


@st.cache_data(show_spinner=False)
def load_screen(date):
    df = pd.read_csv(os.path.join(REPORTS, date, "screener.csv"))
    df["action"] = pd.Categorical(df["action"], ACTIONS, ordered=True)
    return df


@st.cache_data(show_spinner="Loading price history…")
def load_prices():
    files = sorted(f for f in os.listdir(PRICES) if f.startswith("prices_")) if os.path.isdir(PRICES) else []
    if not files:
        return pd.DataFrame(), ""
    return pd.read_csv(os.path.join(PRICES, files[-1]), parse_dates=["date"]), files[-1]


# Streamlit Community Cloud runs the app as "appuser"; there the nightly GitHub Action refreshes the data instead.
IS_CLOUD = os.environ.get("HOME", "").startswith("/home/appuser")


@st.cache_data(ttl=6 * 3600, show_spinner="Downloading price history…")
def prices_for(symbol):
    """Fallback when no local price file exists (e.g. on Streamlit Cloud): fetch one stock from Yahoo."""
    import yfinance as yf
    g = yf.Ticker(symbol + ".NS").history(period="2y", interval="1d", auto_adjust=True)
    if g.empty:
        return pd.DataFrame()
    g = g[["Open", "High", "Low", "Close", "Volume"]].reset_index().rename(columns={"Date": "date"})
    g["date"] = pd.to_datetime(g["date"]).dt.tz_localize(None).dt.normalize()
    g["symbol"] = symbol
    return g


def refresh_data(log):
    for script in ("fetch_data.py", "run_screener.py"):
        log.write(f"Running {script} …")
        p = subprocess.run([sys.executable, "-I", os.path.join(HERE, script)], capture_output=True, text=True, cwd=HERE)
        tail = (p.stdout + p.stderr).strip().splitlines()[-12:]
        log.code("\n".join(tail) or "(no output)")
        if p.returncode != 0:
            log.error(f"{script} failed (exit code {p.returncode})")
            return False
    return True


# ---------------- plain-language evidence ----------------
def evidence(r):
    def line(ok, bad, text):
        icon = "🟢" if ok else ("🔴" if bad else "⚪")
        return f"{icon} {text}"
    rows = [
        line(r.stage == "markup", r.stage == "markdown",
             f"**Cycle stage: {r.stage}.** Price is {r.vs_ma200_pct:+.1f}% from its 200-day average, which is moving {r.ma200_slope_pct:+.2f}% per month."),
        line(bool(r.in_range), False,
             f"**Trading range (60 days):** {'yes' if r.in_range else 'no'}, {r.range_low} to {r.range_high} "
             f"({r.range_height_atr} ATR tall). Price sits at {r.pos_in_range:.0%} of the range."),
        line(r.prior_move_pct <= -15, r.prior_move_pct >= 15,
             f"**Trend before the range:** {r.prior_move_pct:+.1f}% "
             f"({'a decline, which fits accumulation' if r.prior_move_pct <= -15 else 'an advance, which fits distribution or re-accumulation' if r.prior_move_pct >= 15 else 'no strong trend'})."),
        line(r.vol_dryup < 0.8, r.vol_dryup > 1.3 and r.in_range,
             f"**Volume, last 20 days vs. the 40 before:** {r.vol_dryup:.2f}× "
             f"({'drying up' if r.vol_dryup < 0.8 else 'expanding' if r.vol_dryup > 1.3 else 'normal'})."),
        line(r.updown_vol > 1.2, r.updown_vol < 0.83,
             f"**Up-day vs. down-day volume (40 days):** {r.updown_vol:.2f} "
             f"({'buyers heavier' if r.updown_vol > 1 else 'sellers heavier'})."),
        line(r.wave_vol_ratio > 1.15 if pd.notna(r.wave_vol_ratio) else False,
             r.wave_vol_ratio < 0.87 if pd.notna(r.wave_vol_ratio) else False,
             f"**Weis waves, up-wave vs. down-wave volume:** {r.wave_vol_ratio if pd.notna(r.wave_vol_ratio) else 'n/a'}."),
        line(bool(r.higher_lows), bool(r.lower_highs),
             f"**Swings:** {'higher lows' if r.higher_lows else ''}{' / ' if r.higher_lows and r.lower_highs else ''}"
             f"{'lower highs' if r.lower_highs else ''}{'no clear sequence' if not (r.higher_lows or r.lower_highs) else ''}. "
             f"Selling thrust shortening: {'yes' if r.sot_down else 'no'}. Buying thrust shortening: {'yes' if r.sot_up else 'no'}."),
    ]
    ev = [f"sign-of-strength bar {r.sos_bar}" if isinstance(r.sos_bar, str) and r.sos_bar else "",
          f"sign-of-weakness bar {r.sow_bar}" if isinstance(r.sow_bar, str) and r.sow_bar else "",
          f"selling climax {r.selling_climax}" if isinstance(r.selling_climax, str) and r.selling_climax else "",
          f"buying climax {r.buying_climax}" if isinstance(r.buying_climax, str) and r.buying_climax else ""]
    ev = [e for e in ev if e]
    rows.append(f"⚪ **Recent events:** {', '.join(ev) if ev else 'none'}.")
    trig = r.triggered if isinstance(r.triggered, str) and r.triggered else "none"
    bld = r.building if isinstance(r.building, str) and r.building else "none"
    rows.append(f"⚪ **Setup rules:** triggered: {trig}; building: {bld}.")
    return rows


def chart(px, r, bars, asof):
    g = px[px["symbol"] == r.symbol].sort_values("date") if not px.empty else pd.DataFrame()
    if g.empty:
        g = prices_for(r.symbol)
        if g.empty:
            return None
        g = g[g["date"] <= pd.Timestamp(asof)]          # keep the chart consistent with the report date
    g = g.assign(ma50=g["Close"].rolling(50).mean(), ma200=g["Close"].rolling(200).mean(),
                 vma=g["Volume"].rolling(20).mean()).iloc[-bars:]
    x = g["date"].dt.strftime("%Y-%m-%d")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=x, open=g.Open, high=g.High, low=g.Low, close=g.Close, name="price",
                                 increasing_line_color="#2e7d32", decreasing_line_color="#c62828"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=g.ma50, name="50-day MA", line=dict(color="#1565c0", width=1)), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=g.ma200, name="200-day MA", line=dict(color="#6a1b9a", width=1)), 1, 1)
    colors = np.where(g["Close"] >= g["Open"], "#2e7d32", "#c62828")
    fig.add_trace(go.Bar(x=x, y=g.Volume, marker_color=colors, name="volume", showlegend=False), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=g.vma, name="20-day avg volume", line=dict(color="#333", width=1)), 2, 1)
    def hline(y, text, color, dash):
        if pd.notna(y):
            fig.add_hline(y=y, line=dict(color=color, dash=dash, width=1), row=1, col=1,
                          annotation_text=f"{text} {y:,.2f}", annotation_position="top left",
                          annotation_font=dict(size=10, color=color))
    hline(r.range_high, "60d high", "#ef6c00", "dash")
    hline(r.range_low, "60d low", "#ef6c00", "dash")
    hline(r.setup_level, "setup level", "#2e7d32", "dashdot")
    hline(r.setup_stop, "stop", "#c62828", "dot")
    fig.update_xaxes(type="category", nticks=10, rangeslider_visible=False)
    vmax = float(np.nanmedian(g["Volume"])) * 5
    fig.update_yaxes(range=[0, vmax], row=2, col=1)
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.04),
                      title=dict(text=f"{r.symbol}: {r.category}", font=dict(size=14)))
    return fig


# ---------------- page ----------------
st.title("📈 NSE Wyckoff Screener")
st.warning("**For manual chart review only. These are not buy or sell recommendations.** In 10-year backtests the coded "
           "Wyckoff rules showed no reliable edge: springs did best (+0.21R per trade from 2016–2026) but lost money from "
           "Mar 2024 onward. Check every chart yourself, set your own stop, and size each trade for your own risk.")

dates = report_dates()
with st.sidebar:
    st.header("Data")
    if dates:
        date = st.selectbox("Report date", dates)
    else:
        date = None
        st.info("No report yet. Click **Update data**.")
    if IS_CLOUD:
        st.caption("Data is refreshed automatically every weekday evening by a scheduled GitHub Action.")
    else:
        with st.expander("Update data (takes about 7 minutes)"):
            st.caption("Downloads the NSE list and 2 years of prices for ~2,630 stocks, then re-runs the screener. "
                       "Run it after 15:45 IST.")
            if st.button("Run crawler + screener", type="primary"):
                box = st.container()
                with st.spinner("Working…"):
                    ok = refresh_data(box)
                if ok:
                    st.cache_data.clear()
                    st.success("Done. Reloading…")
                    st.rerun()

if not date:
    st.stop()

df = load_screen(date)
px, price_file = load_prices()

with st.sidebar:
    st.header("Filters")
    acts = st.multiselect("Action", ACTIONS, default=["Review now", "Watchlist"])
    cats = st.multiselect("Category", sorted(df["category"].unique()))
    min_to = st.slider("Min. turnover (₹ crore/day)", 0.0, 100.0, 5.0, 1.0)
    min_net = st.slider("Min. net score (accumulation − distribution)", -100, 100, -100, 5)
    q = st.text_input("Search symbol or name")

f = df[df["action"].isin(acts)] if acts else df
if cats:
    f = f[f["category"].isin(cats)]
f = f[(f["turnover_cr"] >= min_to) & (f["net_score"] >= min_net)]
if q:
    f = f[f["symbol"].str.contains(q, case=False) | f["name"].fillna("").str.contains(q, case=False)]
f = f.sort_values(["action", "net_score"], ascending=[True, False])

# summary
st.caption(f"As of **{date}** · {len(df)} liquid NSE stocks analysed · price file `{price_file}`")
cols = st.columns(4)
for c, a in zip(cols, ACTIONS):
    c.metric(a, int((df["action"] == a).sum()))

tab1, tab2, tab3 = st.tabs(["📋 Screener", "🔍 Stock detail", "📊 Categories"])

with tab1:
    show = ["symbol", "name", "close", "action", "category", "net_score", "acc_score", "dist_score", "stage",
            "turnover_cr", "setup_level", "setup_stop", "risk_pct", "risk_atr", "pos_in_range", "updown_vol",
            "vol_dryup", "triggered", "building"]
    st.dataframe(f[show], hide_index=True, use_container_width=True, height=520,
                 column_config={"net_score": st.column_config.ProgressColumn("net score", min_value=-100, max_value=100,
                                                                             format="%d"),
                                "turnover_cr": st.column_config.NumberColumn("turnover ₹cr", format="%.1f"),
                                "risk_pct": st.column_config.NumberColumn("risk %", format="%.1f"),
                                "pos_in_range": st.column_config.NumberColumn("pos in range", format="%.2f")})
    st.download_button("Download filtered list (CSV)", f.to_csv(index=False).encode(), f"wyckoff_{date}.csv", "text/csv")

with tab2:
    if f.empty:
        st.info("No stocks match the filters.")
    else:
        sym = st.selectbox("Stock", f["symbol"] + " — " + f["name"].fillna("").str[:40], index=0)
        r = f[f["symbol"] == sym.split(" — ")[0]].iloc[0]
        left, right = st.columns([2.2, 1])
        with left:
            bars = st.slider("Bars shown", 60, 500, 180, 20)
            fig = chart(px, r, bars, date)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No price history available for this stock.")
        with right:
            st.markdown(f"### {r.symbol}")
            st.markdown(f"<span style='background:{ACTION_COLOR[r.action]};color:#fff;padding:3px 8px;border-radius:4px'>"
                        f"{r.action}</span> &nbsp; {r.category}", unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Close", f"₹{r.close:,.2f}")
            m2.metric("Accumulation", int(r.acc_score))
            m3.metric("Distribution", int(r.dist_score))
            st.markdown("**Evidence**")
            for line in evidence(r):
                st.markdown(line)

        st.markdown("---")
        st.subheader("Position-size calculator (risk-based)")
        c1, c2, c3, c4, c5 = st.columns(5)
        capital = c1.number_input("Capital (₹)", 10000.0, 1e9, 500000.0, 10000.0)
        risk_pct = c2.number_input("Risk per trade (%)", 0.1, 5.0, 1.0, 0.1)
        entry = c3.number_input("Entry (₹)", 0.01, 1e7, float(r.close), 0.05)
        default_stop = float(r.setup_stop) if pd.notna(r.setup_stop) else float(r.range_low)
        stop = c4.number_input("Stop (₹)", 0.01, 1e7, min(default_stop, entry * 0.999), 0.05)
        rmult = c5.number_input("Target (R multiple)", 0.5, 10.0, 2.0, 0.5)
        risk_ps = entry - stop
        if risk_ps <= 0:
            st.error("The stop must be below the entry for a long trade.")
        else:
            qty = int((capital * risk_pct / 100) // risk_ps)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Quantity", f"{qty:,}")
            k2.metric("Money at risk", f"₹{qty * risk_ps:,.0f}")
            k3.metric("Position value", f"₹{qty * entry:,.0f}", f"{100 * qty * entry / capital:.0f}% of capital")
            k4.metric(f"Target ({rmult:g}R)", f"₹{entry + rmult * risk_ps:,.2f}")
            atr = r.close * r.atr_pct / 100
            if risk_ps > 4 * atr:
                st.warning(f"The stop is {risk_ps / atr:.1f} ATR away (more than 4 ATR). The entry may be extended.")
            if pd.notna(r.range_high) and entry + rmult * risk_ps > r.range_high and entry < r.range_high:
                st.info(f"The target is above the 60-day high ({r.range_high:,.2f}), so price must break resistance to reach it.")
        st.caption("Checklist: context on your side? · can you see the range, shakeout and test yourself? · quiet test, "
                   "volume rising on the move up? · room to the next resistance ≥ 2R? · stop below the spring or pullback low? "
                   "· risk ≤ 1% of capital? · place entry, stop and target together.")

with tab3:
    cnt = df.groupby(["action", "category"], observed=True).size().reset_index(name="stocks")
    st.dataframe(cnt, hide_index=True, use_container_width=True)
    st.bar_chart(df["stage"].value_counts())
    st.caption("Cycle stage of all analysed stocks (markup = above a rising 200-day average; markdown = the mirror image).")
