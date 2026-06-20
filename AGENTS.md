# AGENTS.md

`AGENTS.md` is the source of truth for this repository. If any other local
instruction file conflicts with this file, follow `AGENTS.md`.

## Project Mission

Signal Bot is a Python 3.10+ end-of-day US equity screening bot. Its job is to
identify a small number of high-quality market leaders and prepare actionable
trade-decision context for the user.

The goal is not to maximize signal count. The goal is to find authentic
Mark Minervini-style Volatility Contraction Pattern (VCP) candidates with strong
trend, leadership, constructive contraction, clean pivot behavior, and real
demand confirmation.

False positives are more harmful than missed opportunities.

## Current Phase

Current phase: **VCP Core Refactor**.

The active work is to convert the current bullish breakout scanner into a
stricter Minervini-style VCP screener while preserving the existing bot
operations, V3 decision layer, Telegram safety boundaries, journal behavior, and
position sizing behavior.

## Current Architecture

The active project lives in this repository root. Do not use archive directories
as implementation targets.

Core runtime flow:

```text
signal_bot.py
  -> v2_engine.py
    -> universe.py
    -> market_regime.py
    -> screener.py
    -> liquidity_filter.py
    -> relative_strength.py
    -> setup_vcp.py
    -> scoring.py
    -> risk_engine.py
    -> decision_engine.py
    -> position_sizing.py
    -> message_formatter.py
    -> telegram_sender.py
    -> journal.py
```

Current module roles:

```text
signal_bot.py          # scheduler and CLI orchestration
v2_engine.py           # main V2 pipeline orchestration
universe.py            # S&P 500, Nasdaq 100, Russell sample, dedupe
screener.py            # yfinance batch download, indicators, snapshots
market_regime.py       # SPY/QQQ market regime hard gate
liquidity_filter.py    # price, volume, dollar volume, optional market cap
relative_strength.py   # current relative-strength filtering
setup_vcp.py           # current VCP / breakout / near-breakout checks
scoring.py             # score and grade
risk_engine.py         # entry, buy stop, stop, targets, and R:R
decision_engine.py     # V3 ENTER / WAIT / WATCHLIST_ONLY / AVOID decision layer
position_sizing.py     # mock/config portfolio sizing calculation
message_formatter.py   # V2/V3 Telegram formatting
telegram_sender.py     # Telegram Bot API send path
journal.py             # JSONL signal/run storage
config.py              # thresholds, flags, and constants
logging_config.py      # console and rotating log configuration
yfinance_cache.py      # repo-local yfinance cache setup
```

Legacy V1 modules may still exist and must not be deleted without explicit
approval:

```text
signals.py
formatter.py
recent_cross_scan.py
smoke_test.py
```

GitHub Actions workflows exist under `.github/workflows/`, including scheduled
scan and test workflows. Do not change workflows during the VCP Core Refactor
unless explicitly requested.

## Trading Philosophy

Use authentic Minervini-style screening principles:

- First require a strong trend and market leadership.
- Prefer stocks near highs and far above major lows.
- Require constructive VCP base structure, not random volatility compression.
- Prefer multiple contractions with tightening depth and improving volume.
- Use the final contraction / handle area to define the pivot.
- Treat price extension above pivot as risk, not strength.
- Treat volume dry-up near the pivot as structure quality.
- Treat breakout volume as demand confirmation.
- Keep risk/reward separate from setup quality.

A weak VCP must not receive an A or A+ grade just because risk/reward or short
term momentum looks attractive.

## In-Scope Work

For the VCP Core Refactor, keep implementation focused on:

- `setup_vcp.py`
- `relative_strength.py`
- `screener.py`
- `scoring.py`
- `config.py` only when new thresholds are needed
- focused tests under `tests/`

Required refactor priorities:

1. Add a full Minervini trend template as hard filters.
2. Replace benchmark-only 20-day RS with universe-based RS percentile.
3. Replace simple range compression with real contraction-sequence detection.
4. Define pivots from the final contraction / handle area.
5. Include volume dry-up as VCP structure quality.
6. Require stronger breakout volume for breakout candidates.
7. Split VCP quality, trade readiness, and risk/reward scoring.
8. Add clear diagnostics for pass/fail reasons, warnings, and scoring.
9. Add focused tests for trend template, RS percentile, contractions, pivot,
   extension rejection, volume dry-up, and grade gating.

## Out-of-Scope Work

Do not do these during the VCP Core Refactor unless explicitly approved:

- Read or modify `.env`.
- Trigger Telegram sends.
- Run a live scan.
- Push to remote.
- Delete V1 legacy modules.
- Broad folder restructuring.
- Change Telegram formatting unless required for diagnostics.
- Change journal format unless required for diagnostics.
- Change GitHub Actions workflows.
- Change V3 wording.
- Change position sizing behavior.
- Add backtesting, dashboards, AI coaching, strategy optimization, or new heavy
  dependencies.

## Safety Rules

- Do not read `.env`.
- Do not print or expose secret values.
- Do not trigger Telegram sends.
- Do not run `python signal_bot.py --run-now` unless the user explicitly asks
  for a live scan.
- Do not push unless the user explicitly asks.
- Do not delete legacy V1 modules unless the user explicitly asks.
- Do not restructure folders without explicit approval.
- Keep changes focused and reviewable.
- Treat `TELEGRAM_TARGET_MODE` and Telegram routing as safety-sensitive.
- Prefer dry-run/review commands for validation.
- Before any send-capable test, verify Telegram routing safety and get explicit
  user approval.

## Runtime Commands

Scheduler daemon:

```bash
python signal_bot.py
```

Live one-off scan. This can trigger production behavior and must not be run
without explicit user approval:

```bash
python signal_bot.py --run-now
```

V2 debug live scan. This is still a live scan and requires explicit user
approval:

```bash
python signal_bot.py --run-now --debug-v2
```

Safe V3 dry-run review, preferred for non-Telegram review:

```bash
.\.venv-laptop\Scripts\python.exe signal_bot.py --v3-dry-run-review
```

Telegram rollout safety check. Use only when Telegram rollout safety is in
scope:

```bash
.\.venv-laptop\Scripts\python.exe signal_bot.py --telegram-rollout-check
```

## Validation Commands

Primary validation before code commits:

```bash
.\.venv-laptop\Scripts\python.exe -m pytest tests -v
.\.venv-laptop\Scripts\python.exe -m compileall .
```

Documentation-only validation:

```bash
git diff -- AGENTS.md CLAUDE.md
git status --short
```

## Current Known Issues

- The current scanner is still closer to a bullish breakout / near-breakout
  scanner than an authentic Minervini VCP screener.
- `relative_strength.py` currently reflects benchmark-comparison logic rather
  than a true universe-based RS percentile.
- `setup_vcp.py` currently needs stricter contraction, base, pivot, and volume
  dry-up logic.
- Scoring needs separation between VCP quality, trade readiness, and
  risk/reward so non-setup factors cannot inflate weak patterns.
- Breakout volume must not treat roughly average volume as strong confirmation.
- Runs before 16:00 ET may use partial same-day volume data.
- `--run-now` is a live scan path and can interact with Telegram behavior.
- `data/signal_journal.jsonl` may contain local fixture or historical run data;
  use provenance carefully when comparing outcomes.
- Pending spec note: an outcome-labeler fixture-ticker blacklist must not
  contain `AAPL`; AAPL is in the live scan universe.

## VCP Refactor Priorities

Trend template hard filters:

- close > SMA50
- close > SMA150
- close > SMA200
- SMA50 > SMA150 > SMA200
- SMA200 rising versus 20 trading days ago
- close >= 30% above 52-week low
- close within 25% of 52-week high
- return clear pass/fail reasons

Relative strength:

- Calculate composite RS from 3-month, 6-month, and 12-month returns when data
  exists.
- Use universe-based percentile.
- Require RS percentile >= 80 as a hard filter.
- Give score boost for RS percentile >= 90.
- Keep SPY/QQQ comparison only as optional context.

VCP structure:

- Detect at least 2 valid contractions; prefer 3.
- Include swing high, swing low, pullback percent, duration, and volume behavior.
- Prefer contractions that decrease from left to right.
- Require the final contraction to be tighter than earlier contractions.
- Reject loose, wide, random bases.
- Reject stocks without a prior uptrend.
- Starting thresholds: maximum base depth 35%, preferred base depth <= 25%,
  final contraction max depth 10-12%, base duration 3 weeks to 6 months.

Pivot and breakout behavior:

- Stop using a simple previous 20-day high as the primary pivot.
- Define pivot from the high of the final contraction / handle area.
- Return pivot price, distance from close to pivot, pivot status, and extension
  status.
- Reject price more than 5% above pivot.
- Reject candidates with no identifiable pivot.

Volume:

- Compare final contraction average volume against 50-day average volume.
- Check down-volume shrinking during later contractions.
- Check recent volume dry-up near the pivot.
- Suggested starting dry-up threshold: final contraction volume <= 80% of
  50-day average.
- For breakout candidates, require breakout volume >= 1.3x 50-day average;
  >= 1.5x should score better.

Diagnostics:

Each candidate should expose:

- `trend_template_pass`
- `rs_percentile`
- `contraction_count`
- `contraction_depths`
- `base_depth`
- `base_duration_days`
- `final_contraction_depth`
- `volume_dry_up_ratio`
- `pivot_price`
- `distance_to_pivot_pct`
- `breakout_volume_ratio`
- `vcp_quality_score`
- `reject_reasons`
- `warning_flags`

## Commit Discipline

- Keep commits small and reviewable.
- Commit Phase 1 docs separately from Phase 2 code.
- Do not mix folder cleanup with VCP logic changes.
- Do not push unless explicitly requested.
- Before code commits, run pytest and compileall.
- For docs-only commits, show `git diff -- AGENTS.md CLAUDE.md` and get user
  approval before committing.
- Suggested Phase 1 commit message:

```bash
docs: make AGENTS master project brain
```

- Suggested Phase 2 commit message:

```bash
feat: implement minervini vcp core
```
