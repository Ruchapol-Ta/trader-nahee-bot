# PROJECT: Signal Bot 🤖

## Current Status
Signal Bot is a Python 3.10+ EOD Telegram trading signal bot. V2 plus the V3 decision layer are implemented structurally. A GitHub Actions workflow (`.github/workflows/daily-scan.yml`, cron 21:30 UTC Mon–Fri) runs `python signal_bot.py --run-now`. The Telegram target mode in CI comes from the `TELEGRAM_TARGET_MODE` repo secret (workflow defaults to `test` if the secret is unset); verify the active mode with `--telegram-rollout-check` before any rollout change.

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

V3 dry-run review (no Telegram, no journal) and Telegram rollout check:

```bash
python signal_bot.py --v3-dry-run-review
python signal_bot.py --telegram-rollout-check
```

Validation:

```bash
.\.venv-laptop\Scripts\python.exe -m pytest tests -v
.\.venv-laptop\Scripts\python.exe -m compileall .
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

Both original items are resolved:

1. **`risk_engine.py` — R:R calculation hardcoded at 2.5** — ✅ RESOLVED: `expected_rr` is resistance-aware (capped at the nearest of `high_52w`/`pivot` × 0.98, floored at entry). `scoring.py` `risk_reward` is graduated on `expected_rr`: ≥2.0→10pts, ≥1.5→6pts, ≥1.0→3pts, <1.0→0pts.
2. **`TELEGRAM_TARGET_MODE`** — ✅ RESOLVED: target-mode routing is explicit. CI mode comes from the `TELEGRAM_TARGET_MODE` repo secret (defaults to `test` when unset). Do not change the mode without explicit user confirmation.

Current remaining work:

- Keep the durable `journal-data` history path healthy and reviewable.
- Review V3 blocker patterns across multiple market days before changing any
  decision thresholds.
- Keep rollout changes limited to safe dry-run and checklist paths unless the
  user explicitly approves live sends.

## Known Issues / Quirks

- R:R (`expected_rr`) is resistance-aware in `risk_engine.py` (capped at nearest of `high_52w`/`pivot` × 0.98, floored at entry); `scoring.py` `risk_reward` is graduated on it (≥2.0→10, ≥1.5→6, ≥1.0→3, <1.0→0) — was hardcoded at 2.5
- `TELEGRAM_TARGET_MODE` is environment-controlled. `test`/`preview` route to the test chat; explicit `prod` requires the prod chat id; CI mode is controlled by the `TELEGRAM_TARGET_MODE` repo secret
- `--run-now` exits with code 1 when the scan pipeline fails, so GitHub Actions marks failed runs red; the scheduler-daemon path still swallows failures after sending a Telegram error alert
- Runs before 16:00 ET with a same-day SPY bar log `[Warning] Intraday run detected` — volume data is partial on such runs; the 21:30 UTC scheduled run is safe
- GitHub Actions persists `data/signal_journal.jsonl` to the `journal-data`
  branch after `run-now` scans, including scans that fail after producing a
  journal breadcrumb; artifacts are still uploaded for 14-day debugging

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
✅ All complete (journal, decision engine, position sizing, V3 formatter, and tests are shipped). Kept for reference:

1. Update project docs so they reflect V2/V3, not old V1 assumptions.
2. Add V3 config flags.
3. Add journal/signal storage.
4. Add tests for storage and current V2 compatibility.
5. Add decision engine skeleton.
6. Add position sizing with mock portfolio config.
7. Update Telegram formatter for V3 fields without breaking V2 formatting.
8. Run:
   ```bash
   .\.venv-laptop\Scripts\python.exe -m pytest tests -v
   .\.venv-laptop\Scripts\python.exe -m compileall .
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
- **Do NOT change `TELEGRAM_TARGET_MODE`** without explicit user confirmation; the same applies to the CI `TELEGRAM_TARGET_MODE` repo secret.
- **Always run `pytest` + `compileall` before any commit**.
- **Do NOT delete V1 modules** unless explicitly requested.
- **Do NOT push** unless explicitly requested.

## V3 Config Flags (implemented — current values in `config.py`)

```python
ENABLE_V3_DECISION_LAYER = True
ENABLE_SIGNAL_JOURNAL = True
ENABLE_POSITION_SIZING = True
ENABLE_V3_TELEGRAM_FORMAT = True

JOURNAL_PATH = "data/signal_journal.jsonl"

MOCK_PORTFOLIO_SIZE = 10000.0
DEFAULT_RISK_PER_TRADE_PCT = 0.01

RISK_MODE_CONSERVATIVE_PCT = 0.005
RISK_MODE_TINY_PCT = 0.0025
RISK_MODE_SMALL_PCT = 0.005
RISK_MODE_NORMAL_PCT = 0.01
RISK_MODE_AGGRESSIVE_PCT = 0.02
```

## Pre-V3 Modules (implemented)

```text
journal.py             # JSONL signal/run storage
decision_engine.py     # ENTER/WAIT/WATCHLIST_ONLY/AVOID decisions
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

## Pending spec amendments

- Task 6 (outcome labeler, not yet built): the fixture-ticker blacklist must
  NOT contain AAPL — AAPL is in the live scan universe, so blacklisting it
  drops real outcomes. Use run_id-provenance filtering instead, or keep the
  blacklist as NEAR/FIRST/SECOND/WATCH only.

## Commit Discipline
Before commit:

```bash
.\.venv-laptop\Scripts\python.exe -m pytest tests -v
.\.venv-laptop\Scripts\python.exe -m compileall .
git status
```

Recommended commit message:

```bash
chore: harden v3 journal pipeline docs
```

Do not push unless explicitly requested.
