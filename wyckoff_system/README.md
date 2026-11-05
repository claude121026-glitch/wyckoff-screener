# Wyckoff Rule-Based Trading System (research prototype)

A Python system that turns the setups from *The Wyckoff Methodology in Depth* (Villahermosa) and *Trades About to Happen* (Weis) into exact rules. It then backtests them and scans for new setups after each close.

> **Status: research only. Do not trade it with real money as is.** Over 10 years the best setup has a small positive edge, but it has lost money since early 2024 (see Results). This is an educational tool, not investment advice.

---

## What it does

| Command | Purpose |
|---|---|
| `backtest` | Runs the rules bar by bar on history and reports win rate, average R, profit factor and drawdown, plus a trade log and equity curve |
| `scan` | Run after the market closes. Lists setups that **trigger at the next open** (with entry, stop and target) and setups that are **still building** |

There are two presets:
- `daily`: daily bars for swing trades (holding days to weeks)
- `5m`: 5-minute bars for intraday trading, with no entries in the first 15 minutes, none after 14:30, and a square-off at 15:10

## The rules (book → code)

All distances are measured in ATR (average true range), so the same rules work on any stock and any timeframe.

**Trading range** (both books: trades come from the edges of ranges)
- Support is the lowest low of the last 40 bars, and resistance is the highest high (36 bars on 5-minute data).
- The range must be 2–9 ATR tall, and closes must cross its midpoint at least 3 times. That second check makes sure price is swinging back and forth, not trending.

**1. SPRING (long)**: Phase C shakeout (Villahermosa Ch. 18, Weis Ch. 5)
1. A bar dips below support by no more than 1.5 ATR. A deeper break is treated as a real breakdown (Weis's QQQ example).
2. Price closes back above support within 3 bars. This is the "no follow-through" test.
3. If the penetration happened on low volume (under 0.8× average), enter straight away. This is Spring #3: supply is exhausted.
4. Otherwise, wait for a **test**: a bar that holds above the spring low, comes back near the broken level, and has below-average volume and a below-average range.
5. **Trigger**: a close above the test bar's high, closing in the upper half of the bar. Enter at the next open.
6. **Stop** goes just below the spring low. **Target** is 2R. A time stop exits after 25 bars.

**2. UPTHRUST (short)**: the mirror image above resistance.

**3. BUEC / LPS (long)**: Phase D breakout test (Villahermosa Ch. 19–20)
1. **Sign of strength**: a close above resistance on a wide bar with high volume (1.3× average volume, 1.1× average range), closing in the top 40% of the bar.
2. A pullback follows on **below-average volume** that does **not close back inside the range** (no more than 0.25 ATR below the old resistance).
3. **Trigger**: a close above the previous bar's high, with a strong close. Stop goes below the pullback low and the old resistance.

**4. LPSY (short)**: the mirror image below support.

**Context** (both books: trade with the larger structure)
- Longs only when price is above its 100-bar moving average. Shorts only when it's below. Use `--no-context` to turn this off.

**Risk** (Villahermosa Ch. 27)
- Size each trade to risk 1% of equity.
- Skip a trade if its stop is under 0.5 ATR or over 4 ATR away.
- Skip a trade if round-trip costs would be more than 25% of the risk.

**Backtest honesty**
- Entry is at the next bar's open, so there's no look-ahead.
- If one bar touches both the stop and the target, the stop is assumed to fill first.
- Gaps fill at the open price, not at the stop or target level.
- Costs are charged on both sides: 10 bps per side for daily delivery trades, 5 bps per side for intraday.
- A daily bar from the current session is dropped before 15:45 IST, so a half-finished day is never treated as complete.

The parameters were set from the books **before** any testing. They were not optimized.

## Results (data to 5 Nov 2026, from Yahoo Finance)

### Daily, 30 large NSE stocks, 10 years, costs 10 bps per side

| Setup | Trades | Win % | Avg R | Profit factor |
|---|---|---|---|---|
| **SPRING (long)** | 138 | 50.0 | **+0.22** | 1.48 |
| BUEC (long) | 234 | 43.6 | +0.03 | 1.05 |
| UPTHRUST (short) | 80 | 31.2 | −0.20 | 0.72 |
| LPSY (short) | 74 | 31.1 | −0.22 | 0.68 |
| All four | 526 | 41.6 | +0.01 | 1.02 |

How robust the springs-only, long-only setup is:

| Variation | Trades | Avg R |
|---|---|---|
| Base | 140 | +0.21 |
| Costs 15 bps per side | 139 | +0.20 |
| 3R target instead of 2R | 140 | +0.29 |
| No context filter | 518 | +0.14 |
| 2016–2021 | 66 | +0.33 |
| 2022–2026 | 74 | +0.11 |
| **Since Mar 2024** | **37** | **−0.19** |

Other checks:
- Springs made money on 18 of the 30 stocks.
- The 90% bootstrap confidence interval for springs' average R is +0.05 to +0.40.
- Year by year, the gains came from 2017 and 2021–2023. 2018–2020 were flat, and **2024–2026 were negative**.

### Market filter test (`--market-filter`): did not help

Wyckoff's own first step was to trade with the overall market. I tested that as a single rule, with no tuning: longs only while the Nifty closes above its 200-day average, shorts only while it's below. Daily bars use the same day's Nifty close. Intraday bars use the previous day's, to avoid look-ahead. The 200-day average needs time to warm up, so the comparison only covers Aug 2017 onward.

| System | Avg R, no filter | Avg R, with filter | Since Mar 2024, no filter | Since Mar 2024, with filter |
|---|---|---|---|---|
| Springs (long) | +0.20 (136 trades) | +0.20 (114) | −0.19 (37) | −0.24 (29) |
| Springs + BUEC (long) | +0.09 (≈370) | +0.09 (311) | −0.24 (91) | −0.22 (74) |
| All four setups | +0.01 (≈520) | +0.03 (364) | −0.26 (140) | −0.25 (100) |

- The spring trades the filter removed averaged +0.22R, just as good as the ones it kept. So the filter only cuts the number of trades.
- It helps the all-setups version only because it blocks most short trades in bull markets. The shorts that remain still lose (−0.32R).
- **It does not fix the losses since 2024**, which happened mostly while the Nifty was above its 200-day average.
- The option stays in the code but is **off by default**.

### Investigation: why the spring edge faded after Mar 2024

**Short answer: most of the spring "edge" was the general tendency of uptrending large caps to bounce after dips. That tendency disappeared after early 2024. The Wyckoff-specific timing added a little at best.**

1. **The entries didn't change; the follow-through did.**
   - Stop size (about 2.1 ATR), signal-bar volume, range height and the share of direct entries are all about the same before and after.
   - After Mar 2024 the median best move after entry fell from **1.14R to 0.55R**.
   - Only **30%** of trades reached +1R, down from 55%. Stop-outs rose from 35% to **56%**.
2. **Dip-buying in these 30 stocks stopped working in general.**
   - The average 15-day forward return across all stock-days fell from +1.32% to +0.32%.
   - A simple dip-buy (stock above its 100-day average, in the bottom third of its 40-day range) went from **+1.63% to −0.34%**.
   - The springs' best years (2017, 2021, 2023) were also the years the 30-stock basket rose most (+34% to +38%).
3. **A control test confirms it.** Plain dip-buys run through the *same* engine (same stop size, 2R target, 25-bar time stop and costs):

   | Period | Plain dip-buy | Springs | Springs minus dip-buy (90% CI) |
   |---|---|---|---|
   | 2016 – Feb 2024 | +0.21R (489 trades) | +0.36R (103) | +0.14R (−0.08 to +0.37) |
   | Mar 2024 – now | −0.19R (158) | −0.19R (37) | 0.00R (−0.36 to +0.36) |

   About 60% of the spring result before 2024 is explained by plain dip-buying. The extra from springs is small and not statistically reliable. After 2024 springs did exactly as badly as random dips.
4. **It isn't bad luck.** If recent spring trades came from the pre-2024 distribution, a 37-trade average this low would happen with probability **0.004**. Before 2024, no 37-trade stretch averaged below +0.04R. A permutation test of before vs. after gives p = 0.011.
5. **The regime is quieter.** Median Nifty volatility at entry dropped from 12.4% to 10.5% a year, and stocks sat closer to their 100-day averages. Spring trades taken in the lowest-volatility third averaged only +0.06R, versus +0.38R in the highest third. That pattern is suggestive, but it's based on about 47 trades per group, so it's a lead to investigate, not a proven filter.

**What it means:** as coded, this is mainly a "buy dips in uptrending large caps" system with Wyckoff entry timing on top. It works when the market has steady upward drift and fails when it doesn't. The parts Weis treats as decisive (absorption, the story of the lines, reading the context bar by bar) aren't well captured by fixed rules. They may be where any real edge lies, and they're the hardest to code.

The analysis scripts are `investigate.py`, `regime.py`, `luck.py` and `control.py` in the session scratchpad.

### Grid search: 12,096 combinations, no robust winner

**What was varied:**
- Setup group: Spring, BUEC, Spring+BUEC, Upthrust, LPSY, UT+LPSY, or all four
- Range length: 20, 40 or 60 days
- How quiet the test must be: 0.8× or 1.0× average volume
- Breakout bar volume: 1.2× or 1.5× average
- Spring #3 direct entry: on or off
- Stock trend filter: none, or the 50-, 100- or 200-day average
- Nifty market filter: on or off
- Profit target: 1.5R, 2R or 3R
- Time stop: 10, 25 or 40 days

**How it was tested:** every combination ran on two separate sets of 30 stocks (U1 = the original large caps; U2 = 30 other liquid NSE stocks). Results were split into three periods: train (2016–2021), validation (2022 – Feb 2024) and test (Mar 2024 – now). The selection rule was fixed in advance: pick the top 20 by U1 training results only.

| Top 20 by training results (avg R) | Train | Validation | Test |
|---|---|---|---|
| U1 (the stocks they were tuned on) | +0.56 | +0.37 | **−0.16** |
| U2 (stocks never seen during tuning) | +0.24 | −0.24 | −0.06 |

- **Out of 6,471 combinations with enough trades, none had avg R above +0.05 in all six slices** (3 periods × 2 stock groups). Exactly one was above zero in all six: Spring, 20-day range, quiet test < 0.8×, no direct entry, 100-day trend filter, market filter on, 3R target, 40-day time stop. On U1 it earned +0.44 / +0.43 / +0.29R, but on U2 only +0.03 / +0.03 / +0.01R, which is roughly zero. It was found by searching the whole grid, so it's a data-mined candidate, not a proven edge.
- **Training results barely predict the recent period.** The rank correlation between training and test results is +0.15. Between U1 training and U2 test it's −0.15.
- **Only 16% (U1) and 26% (U2) of combinations made money** in the recent test period.
- **Short setups flipped.** Upthrust/LPSY combinations had the best recent results (up to +0.45R), but they lost money in both earlier periods. That's a regime change, not a stable edge.
- **Patterns that hold up:** springs are the only family that's positive on U1 in training. Larger targets (3R) and longer holds (40 days) do better, which suggests what pays is catching a trend after the spring, not a quick bounce.

The grid runner, analysis script and full results (`grid.py`, `analyze_grid.py`, `grid_results.csv`) are in the session scratchpad.

### Intraday, 5-minute NIFTYBEES, 60 days (the only 5-minute history Yahoo provides)

- 24 trades, −0.08R per trade **before** costs. That's far too small a sample to judge, and it shows no edge.
- After costs it's much worse. The median stop is only 0.14% of price, so a 0.10% round-trip cost uses up most of the risk on every trade.
- With the cost filter switched on, hardly any trades qualify.
- **Conclusion: as built, the 5-minute version is not viable.** It would need much cheaper execution (Nifty futures), wider structures (15-minute bars), or more history to test properly.

### What the results agree with in the books
- **Springs worked best.** Weis says springs are easier to trade than upthrusts and that springs in uptrends succeed more often.
- **Short setups lost money** in what was mostly a decade-long Indian bull market. Weis says upthrusts work in downtrends but often fail in uptrends.
- Context matters. The edge appears in strong trending years and fades in choppy ones.

## Usage

Requires Python 3 with `yfinance`, `pandas`, `numpy` and `matplotlib`. Data is cached in `data_cache/`, and outputs go to `results/`.

```bash
# daily backtests
python -I run.py backtest --preset daily --universe nifty30
python -I run.py backtest --preset daily --universe nifty30 --setups SPRING --long-only
python -I run.py backtest --preset daily --symbols RELIANCE.NS,TCS.NS --cost-bps 15

# intraday backtests
python -I run.py backtest --preset 5m --symbols NIFTYBEES.NS
python -I run.py backtest --preset 5m --symbols ^NSEI --volume-from NIFTYBEES.NS

# evening routine: what triggers tomorrow, what is building
python -I run.py scan --preset daily --universe nifty30 --setups SPRING,BUEC --long-only
```

Options:
- `--setups`: choose from SPRING, UPTHRUST, BUEC, LPSY
- `--long-only`: no shorts. Cash-market delivery in India can't be shorted overnight.
- `--no-context`: turn off the moving-average filter
- `--market-filter`: trade only with the Nifty's 200-day trend (tested; it didn't help)
- `--rmult`: profit target in R
- `--cost-bps`: cost per side
- `--split`: date that separates the two test periods
- `--refresh`: re-download data

## Files

| File | Contents |
|---|---|
| `config.py` | Every parameter, with the book rule it comes from, plus the `daily` and `5m` presets |
| `data.py` | Download and cache from Yahoo, fill missing opening-bar volume, drop unfinished daily bars |
| `signals.py` | Indicators, range detection, and the four setup state machines |
| `backtest.py` | The bar-by-bar backtest engine and summary statistics |
| `run.py` | The command-line interface (backtest and scan) |

## Known limitations

- **Yahoo data is free but imperfect.** Some opening 5-minute bars have zero volume (filled from the daily total). The latest daily bar is sometimes missing prices until Yahoo finalizes it. The Nifty index has no volume at all (use `--volume-from NIFTYBEES.NS`).
- **Survivorship bias.** The universe is *today's* large caps, which favors stocks that did well.
- **The multi-stock equity figure is approximate.** It compounds trades in order of exit time and ignores capital tied up in overlapping positions. Average R and profit factor are the reliable numbers.
- **One position per stock at a time.** There's no portfolio limit on how many stocks are held at once.
- **Code can't fully reproduce discretionary reading.** Phases A–B, absorption and the "story of the lines" are only roughly captured by the range filter. Both authors warn that the method is an art, not a mechanical pattern.

## Suggested next steps (research, before any live use)

1. ~~Add a market context filter~~ Done: it didn't help (see Results). Changing the filter's settings now would be curve-fitting to the backtest.
2. ~~Find out why the edge faded after 2024~~ Done: the market's upward drift disappeared, and springs were mostly riding it (see the Investigation section). Any new filter, such as volatility, must be decided *before* testing it on data the system hasn't seen.
3. **Forward-test the scanner** on paper for several months and compare the results with the backtest.
3. **Use better intraday data** (Nifty futures with real volume and longer history) before drawing any conclusion about the 5-minute version.
