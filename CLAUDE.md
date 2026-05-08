# PROJECT: Signal Bot 🤖

## Overview
EOD Telegram bot that screens S&P 500, Nasdaq 100, and Russell 2000 stocks
for EMA + RSI signals and sends full-detail alerts after US market close.

## Architecture
- **Data source:** yfinance (free, no API key needed)
- **Universe:** S&P 500 + Nasdaq 100 + Russell 2000 (~1,800 tickers, deduped)
- **Signal logic:** EMA 9/21 crossover + RSI filter
- **Scheduler:** APScheduler (runs at 4:30 AM BKK time = ~30min after NYSE close)
- **Output:** Telegram Bot API → personal chat or group

## Signal Logic (Option B — Balanced)
### Bullish Signal ✅
- EMA 9 crosses ABOVE EMA 21 (today vs yesterday)
- RSI 14 is between 40–70 (momentum building, not overbought)

### Bearish Signal 🔴
- EMA 9 crosses BELOW EMA 21
- RSI 14 is between 30–60 (momentum fading, not oversold)

## Telegram Message Format
```
📊 [TICKER] — BULLISH SIGNAL

💰 Price:     $XXX.XX  (+X.XX%)
📈 EMA 9:     $XXX.XX
📉 EMA 21:    $XXX.XX
⚡ RSI 14:    XX.X
📦 Volume:    X.XXM  (vs avg X.XXM)

🎯 Entry:     $XXX.XX  (current close)
🟢 TP:        $XXX.XX  (+5%)
🔴 SL:        $XXX.XX  (-3%)

🏷️ S&P 500 | Sector: Technology
🕐 Signal at: 2025-04-23 16:30 ET
```

## Module Structure
```
signal_bot/
├── CLAUDE.md           ← this file
├── signal_bot.py       ← main entry point + scheduler
├── screener.py         ← fetch data + compute indicators
├── signals.py          ← signal logic (EMA crossover + RSI filter)
├── formatter.py        ← format Telegram message
├── telegram_sender.py  ← send via Telegram Bot API
├── universe.py         ← load ticker lists
└── config.py           ← constants (EMA periods, RSI thresholds, TP/SL %)
```

## Config Values (editable)
- EMA_SHORT = 9
- EMA_LONG = 21
- RSI_PERIOD = 14
- RSI_BULL_MIN = 40, RSI_BULL_MAX = 70
- RSI_BEAR_MIN = 30, RSI_BEAR_MAX = 60
- TP_PCT = 0.05   (5%)
- SL_PCT = 0.03   (3%)
- MAX_SIGNALS = 20  (cap per run to avoid spam)
- SCHEDULE_TIME = "04:30"  (BKK time, Asia/Bangkok)

## Environment Variables (.env)
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## Current State
- ✅ CLAUDE.md written
- ✅ signal_bot.py scaffold created
- 🔄 screener.py — fetch + EMA/RSI compute
- ❌ signals.py — crossover detection
- ❌ formatter.py — message template
- ❌ telegram_sender.py — API call
- ❌ universe.py — ticker lists
- ❌ scheduler wired up

## Coding Rules
- Python 3.10+
- Use pandas for all data manipulation
- Use yfinance for price data (period="60d", interval="1d")
- No hardcoded credentials — always use os.environ or .env
- Every function must have: docstring + try/except + meaningful error log
- Log to console with format: [TIMESTAMP] [LEVEL] message
