"""Parameters for the Wyckoff rule-based system.

Every threshold below maps to a rule from the two books (see README.md).
Defaults were set from the books *before* backtesting, not optimised.
"""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Params:
    # --- measurement ---
    atr_len: int = 14          # average true range, used to scale every distance
    vol_len: int = 20          # look-back for "average" volume and bar range

    # --- trading range (Ch. 5 Villahermosa, Ch. 1-3 Weis) ---
    range_len: int = 40        # bars that define the range (support = lowest low, resistance = highest high)
    min_h_atr: float = 2.0     # range must be at least this many ATRs tall ...
    max_h_atr: float = 9.0     # ... and at most this many (taller = a trend, not a range)
    min_cross: int = 3         # closes must cross the range midpoint this often (price swings back and forth)

    # --- spring / upthrust (shake, Phase C) ---
    max_pen_atr: float = 1.5   # deeper penetration = real breakdown, not a spring (Weis, QQQ Apr 2000)
    rec_bars: int = 3          # must close back inside the range within this many bars
    direct_low_vol: bool = True  # Spring #3: low-volume penetration may be bought directly
    low_vol: float = 0.8       # "low volume" = below this multiple of average
    test_bars: int = 15        # the test must arrive within this many bars of the recovery
    test_zone_atr: float = 1.0 # the test must come back to within this distance of the broken level
    test_rv: float = 1.0       # test volume below average ("no supply")
    test_rr: float = 1.0       # test bar range below average (narrow)
    trig_cp: float = 0.5       # trigger bar closes in the upper half (long) / lower half (short)

    # --- breakout test (SOS -> BUEC/LPS, SOW -> LPSY) ---
    sos_rv: float = 1.3        # breakout bar volume vs average
    sos_rr: float = 1.1        # breakout bar range vs average
    sos_cp: float = 0.6        # breakout bar closes in its top 40% (long)
    reentry_atr: float = 0.25  # a close this far back inside the range cancels the breakout
    pb_max: int = 12           # pullback + trigger must happen within this many bars
    pb_rv: float = 1.0         # average pullback volume must be below average ("lack of interest")

    # --- context (trade with the larger structure) ---
    ctx_len: int = 100         # longs only above this moving average, shorts only below; 0 = off
    market_filter: bool = False  # Wyckoff step 1: trade with the market. Longs only if Nifty > its MA, shorts only if below
    market_ma: int = 200       # length of the Nifty moving average for the market filter

    # --- risk and exits ---
    stop_buf_atr: float = 0.1  # stop goes this far beyond the invalidation point
    rmult: float = 2.0         # profit target = rmult x initial risk
    max_hold: int = 25         # time stop in bars (daily mode)
    max_risk_atr: float = 4.0  # skip trades whose stop is unreasonably wide
    min_risk_atr: float = 0.5  # skip trades whose stop is unrealistically tight
    cost_bps: float = 10.0     # cost per side (brokerage + taxes + slippage), basis points
    max_cost_frac: float = 0.25  # skip trades where round-trip cost > 25% of the risk (stop too tight to pay for itself)
    risk_pct: float = 1.0      # % of equity risked per trade (Villahermosa: max 1%)

    # --- intraday session handling ---
    intraday: bool = False
    reset_daily: bool = False  # cancel half-built setups at each new session
    skip_open_bars: int = 0    # no entries during the first N bars of the session
    last_entry: str = "23:59"  # no new entries after this time
    exit_time: str = "23:59"   # flatten all positions at/after this time

    long_only: bool = False


DAILY = Params()

INTRADAY_5M = replace(
    Params(),
    range_len=36,      # 3 hours of 5-minute bars
    min_h_atr=1.5,
    max_h_atr=8.0,
    test_bars=18,
    pb_max=12,
    ctx_len=150,       # about two sessions
    cost_bps=5.0,      # index ETF intraday: low brokerage/STT, plus slippage
    intraday=True,
    reset_daily=True,
    skip_open_bars=3,  # skip the first 15 minutes (gap noise)
    last_entry="14:30",
    exit_time="15:10", # square off before the close
)

PRESETS = {"daily": DAILY, "5m": INTRADAY_5M}
