# config.py — Signal Bot Configuration
# All tunable constants live here. Edit and restart the bot to take effect.

# === EMA Settings ===
EMA_FAST = 20
EMA_MID = 50
EMA_LONG = 200

# === RSI Settings ===
RSI_PERIOD = 14
RSI_PULLBACK_MIN = 40
RSI_PULLBACK_MAX = 60
RSI_PULLBACK_MID = (RSI_PULLBACK_MIN + RSI_PULLBACK_MAX) / 2

# === Pullback / Risk Management ===
PULLBACK_TOLERANCE = 0.01
SL_SWING_LOOKBACK = 5
SL_BUFFER_PCT = 0.01
TP2_RISK_MULTIPLE = 2
TP3_RISK_MULTIPLE = 3

# === Volume Display ===
VOLUME_WINDOW = 20          # trading days for the average-volume baseline
VOLUME_HIGH_RATIO = 1.5     # 🔥 flag when today's volume ≥ this × avg

# === Screening ===
MAX_SIGNALS = 20            # EOD cap, balanced across bullish/bearish
DATA_PERIOD = "18mo"        # yfinance lookback; enough history for stable EMA200
DATA_INTERVAL = "1d"
MIN_DATA_ROWS = 250

# === V2 Trade Qualification Engine ===
V2_MARKET_SYMBOLS = ("SPY", "QQQ")
V2_SETUP_TYPE = "VCP Breakout"

# Liquidity
V2_MIN_PRICE = 10.0
V2_MIN_AVG_VOLUME = 1_000_000
V2_MIN_AVG_DOLLAR_VOLUME = 20_000_000
V2_MIN_MARKET_CAP = 2_000_000_000

# Indicator windows
ATR_PERIOD = 14
ATR_SMA_WINDOW = 20
RELATIVE_STRENGTH_LOOKBACK = 20
HIGH_52W_LOOKBACK = 252
VCP_PIVOT_LOOKBACK = 20
VCP_CONTRACTION_LOOKBACK_SHORT = 5
VCP_CONTRACTION_LOOKBACK_MID = 10
VCP_CONTRACTION_LOOKBACK_LONG = 20

# Setup thresholds
VCP_MAX_52W_HIGH_DISTANCE = 0.05
VCP_RANGE_TIGHTENING_RATIO = 0.85
VCP_ATR_CONTRACTION_RATIO = 0.90
VCP_VOLUME_DRY_UP_RATIO = 0.80
VCP_BREAKOUT_VOLUME_RATIO = 1.00
VCP_NEAR_BREAKOUT_THRESHOLD = 0.015

# Scoring / grading
V2_SCORE_A_PLUS_MIN = 85
V2_SCORE_A_MIN = 75
V2_SCORE_B_MIN = 65
V2_SCORE_C_MIN = 50
V2_SCORE_WEIGHTS = {
    "market_regime": 10,
    "liquidity": 10,
    "trend_structure": 15,
    "relative_strength": 15,
    "high_52w_proximity": 10,
    "consolidation_tightness": 10,
    "atr_contraction": 10,
    "volume_quality": 10,
    "risk_reward": 10,
}
V2_MAX_TRADE_SIGNALS = 20
V2_MAX_WATCHLIST = 10

# Risk framework
V2_RISK_PER_TRADE = 0.01
V2_MAX_OPEN_POSITIONS = 5
V2_MAX_TOTAL_PORTFOLIO_RISK = 0.05
V2_MAX_NEW_POSITIONS_PER_DAY = 2
V2_MAX_SAME_SECTOR_POSITIONS = 2
V2_PYRAMID_MIN_R = 1.5
V2_ADD_ON_MAX_SIZE_PCT = 0.50
V2_TARGET_1_R = 2.5
V2_TARGET_2_R = 4.0
V2_STOP_BUFFER_PCT = 0.005
V2_BUY_STOP_BUFFER_PCT = 0.001
V2_HOLDING_STYLE = "Swing: 3 trading days to 8 weeks; trail with 10EMA/20EMA"

# === Pre-V3 Foundation ===
ENABLE_V3_DECISION_LAYER = False
ENABLE_SIGNAL_JOURNAL = True
ENABLE_POSITION_SIZING = False
ENABLE_V3_TELEGRAM_FORMAT = False

JOURNAL_PATH = "data/signal_journal.jsonl"

MOCK_PORTFOLIO_SIZE = 10000.0
DEFAULT_RISK_PER_TRADE_PCT = 0.01

RISK_MODE_CONSERVATIVE_PCT = 0.005
RISK_MODE_NORMAL_PCT = 0.01
RISK_MODE_AGGRESSIVE_PCT = 0.02

# V3 decision thresholds. These annotate V2-selected signals only.
V3_ENTER_MIN_SCORE = V2_SCORE_A_MIN
V3_WATCHLIST_MIN_SCORE = V2_SCORE_B_MIN
V3_ENTER_MIN_RR = V2_TARGET_1_R
V3_WATCHLIST_MIN_RR = 2.0

V3_ENTER_MAX_STOP_DISTANCE_PCT = 0.08
V3_AVOID_MAX_STOP_DISTANCE_PCT = 0.12

V3_ENTER_MAX_EXTENSION_FROM_EMA20_PCT = 0.08
V3_ENTER_MAX_EXTENSION_FROM_EMA50_PCT = 0.20
V3_AVOID_EXTENSION_FROM_EMA50_PCT = 0.30

V3_ENTER_MIN_VOLUME_RATIO = 1.10
V3_WAIT_MIN_VOLUME_RATIO = VCP_BREAKOUT_VOLUME_RATIO

# === Universe Sanity Thresholds ===
# Fix #2 — refuse to proceed when a core source returns a crippled list.
EXPECTED_MIN_SP500 = 450
EXPECTED_MIN_NASDAQ = 90

# === Recent-Cross Scanner (one-off) ===
RECENT_CROSS_LOOKBACK_DAYS = 10
RECENT_CROSS_MAX_SIGNALS = 25

# === Scheduler ===
SCHEDULE_HOUR = 4           # BKK local
SCHEDULE_MINUTE = 30
TIMEZONE = "Asia/Bangkok"
# Fix #20 — externalize the market timezone.
MARKET_TIMEZONE = "America/New_York"
# Fix #19 — 1 h grace tolerates machine-sleep / brief downtime.
MISFIRE_GRACE_SEC = 3600

# === Validation (Fix #17) ===
assert EMA_FAST < EMA_MID < EMA_LONG, "EMA periods must be EMA_FAST < EMA_MID < EMA_LONG"
assert 0 < PULLBACK_TOLERANCE < 1, "PULLBACK_TOLERANCE must be in (0, 1)"
assert 0 < SL_BUFFER_PCT < 1, "SL_BUFFER_PCT must be in (0, 1)"
assert SL_SWING_LOOKBACK > 0, "SL_SWING_LOOKBACK must be positive"
assert TP2_RISK_MULTIPLE > 0 and TP3_RISK_MULTIPLE > TP2_RISK_MULTIPLE, "invalid TP risk multiples"
assert MAX_SIGNALS > 0, "MAX_SIGNALS must be positive"
assert MIN_DATA_ROWS >= EMA_LONG, "MIN_DATA_ROWS must cover EMA_LONG"
assert RSI_PULLBACK_MIN < RSI_PULLBACK_MAX, "invalid RSI pullback band"
assert 0 <= SCHEDULE_HOUR < 24 and 0 <= SCHEDULE_MINUTE < 60, "invalid schedule time"
assert V2_MIN_PRICE > 0, "V2_MIN_PRICE must be positive"
assert V2_MIN_AVG_VOLUME > 0, "V2_MIN_AVG_VOLUME must be positive"
assert V2_MIN_AVG_DOLLAR_VOLUME > 0, "V2_MIN_AVG_DOLLAR_VOLUME must be positive"
assert V2_MIN_MARKET_CAP > 0, "V2_MIN_MARKET_CAP must be positive"
assert sum(V2_SCORE_WEIGHTS.values()) == 100, "V2 score weights must total 100"
assert V2_SCORE_A_PLUS_MIN > V2_SCORE_A_MIN > V2_SCORE_B_MIN > V2_SCORE_C_MIN
assert 0 < V2_STOP_BUFFER_PCT < 1, "V2_STOP_BUFFER_PCT must be in (0, 1)"
assert V2_TARGET_2_R > V2_TARGET_1_R > 0, "invalid V2 target multiples"
