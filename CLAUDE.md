# PROJECT: Signal Bot 🤖

## Current Status
Signal Bot is now a Python 3.10+ EOD Telegram trading signal bot with V2 already implemented, committed, and pushed.

V2 is no longer the original EMA 9/21 + RSI-only bot. Do not use the old V1 assumptions as the source of truth.

## Current V2 Overview
The bot screens US equities and sends Telegram alerts after US market close.

Current V2 focus:
- Market-regime-aware signal pipeline
- VCP / breakout / near-breakout setup detection
- Liquidity filtering
- Relative strength filtering
- Scoring and grading
- Risk engine for entry, stop, buy stop, targets, and R:R
- A+/A breakout alerts
- B watchlist summaries
- C/rejected signals excluded from Telegram
- Diagnostic funnel and reject aggregation

## Runtime
Main scheduled bot:

```bash
python signal_bot.py
```

One-off run:

```bash
python signal_bot.py --run-now
```

One-off V2 debug run:

```bash
python signal_bot.py --run-now --debug-v2
```

Validation:

```bash
python -m pytest tests -v
python -m compileall .
```

## Current Known Stack
- Python 3.10+
- yfinance
- pandas
- requests
- APScheduler
- pytz
- python-dotenv
- lxml
- pytest

No pyproject.toml, Poetry, Pipenv, Docker, CI, lint, type checker, or pre-commit tooling is currently assumed.

## Core Modules
Current core modules may include:

```text
signal_bot.py          # scheduler and --run-now orchestration
v2_engine.py           # V2 pipeline orchestration
universe.py            # S&P 500, Nasdaq 100, Russell sample, dedupe
screener.py            # yfinance batch download, indicators, snapshots
market_regime.py       # SPY/QQQ market regime hard gate
liquidity_filter.py    # price, volume, dollar volume, optional market cap
relative_strength.py   # 20-day outperformance vs SPY/QQQ
setup_vcp.py           # VCP / breakout / near-breakout checks
scoring.py             # score and grade
risk_engine.py         # entry, buy stop, stop, R targets
message_formatter.py   # V2 Telegram formatting
telegram_sender.py     # Telegram Bot API send path
config.py              # thresholds and constants
logging_config.py      # console + rotating log configuration
```

V1 modules may still exist and should not be deleted unless explicitly requested:
```text
signals.py
formatter.py
recent_cross_scan.py
smoke_test.py
```

## Open Items (V3 Rollout Remaining)

Item 1 is resolved. Item 2 remains confirmed incomplete — do not assume it is done:

1. **`risk_engine.py` — R:R calculation hardcoded at 2.5** — ✅ RESOLVED: `expected_rr` is resistance-aware (capped at the nearest of `high_52w`/`pivot` × 0.98, floored at entry). `scoring.py` `risk_reward` is graduated on `expected_rr`: ≥2.0→10pts, ≥1.5→6pts, ≥1.0→3pts, <1.0→0pts.
2. **`TELEGRAM_TARGET_MODE` still in test mode**: Must be flipped to `prod` before live scheduling is enabled. Confirm with user before switching.

## Known Issues / Quirks

- R:R (`expected_rr`) is resistance-aware in `risk_engine.py` (capped at nearest of `high_52w`/`pivot` × 0.98, floored at entry); `scoring.py` `risk_reward` is graduated on it (≥2.0→10, ≥1.5→6, ≥1.0→3, <1.0→0) — was hardcoded at 2.5
- `TELEGRAM_TARGET_MODE` in test mode means alerts go to test chat, not prod chat — do not assume prod is live

## V3 Goal
V3 should upgrade the bot from a Signal Alert Bot into a Trade Decision Assistant.

V3 must answer three questions for each relevant signal:

1. Should I enter?
2. If yes, how much should I risk?
3. If no, what exactly should I wait for?

## Required V3 Decision Outcomes
V3 decision layer must classify signals into:

- `ENTER`
- `WAIT`
- `WATCHLIST_ONLY`
- `AVOID`

Decision output should include:
- decision
- confidence
- main_reason
- supporting_reasons
- risk_warnings
- next_action

## Pre-V3 Foundation Requirements
Before implementing full V3, complete these foundation steps:

1. Update project docs so they reflect V2/V3, not old V1 assumptions.
2. Add V3 config flags.
3. Add journal/signal storage.
4. Add tests for storage and current V2 compatibility.
5. Add decision engine skeleton.
6. Add position sizing with mock portfolio config.
7. Update Telegram formatter for V3 fields without breaking V2 formatting.
8. Run:
   ```bash
   python -m pytest tests -v
   python -m compileall .
   ```

## Implementation Rules
- Do not break V2 behavior.
- Do not rewrite V2 scoring/filtering unless explicitly required.
- V3 should read V2 signal outputs and add decision interpretation on top.
- Keep V3 behind config flags where possible.
- Prefer simple modules and explicit tests.
- Start with JSONL journaling unless SQLite is clearly already supported or trivial.
- Use mock/config portfolio sizing first; do not implement real account/position tracking yet.
- Do not add backtest, dashboard, AI coach, or strategy optimization in Pre-V3.
- Do not introduce heavy dependencies.
- Preserve Telegram sending behavior.
- Keep live Telegram sends limited during testing.
- Use pytest and compileall before commit.

## Hard Rules
- **Do NOT fix `risk_engine.py` R:R and change `TELEGRAM_TARGET_MODE` in the same commit** — keep them separate and confirm each with user first.
- **Do NOT flip `TELEGRAM_TARGET_MODE` to prod** without explicit user confirmation — this triggers live alerts.
- **Always run `pytest` + `compileall` before any commit**.
- **Do NOT delete V1 modules** unless explicitly requested.
- **Do NOT push** unless explicitly requested.

## Suggested V3 Config Flags
Add to `config.py` or the existing config location:

```python
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
```

## Suggested Pre-V3 Modules
Add only if they do not already exist:

```text
journal.py             # JSONL signal/run storage
decision_engine.py     # ENTER/WAIT/WATCHLIST_ONLY/AVOID skeleton
position_sizing.py     # mock portfolio sizing calculation
```

## Testing Expectations
Add or update tests for:

```text
tests/test_journal.py
tests/test_decision_engine.py
tests/test_position_sizing.py
tests/test_v3_formatter_compatibility.py
tests/test_v2_backward_compatibility.py
```

## Commit Discipline
Before commit:

```bash
python -m pytest tests -v
python -m compileall .
git status
```

Recommended commit message:

```bash
feat: add pre-v3 trade decision foundation
```

Do not push unless explicitly requested.
