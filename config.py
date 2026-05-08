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
