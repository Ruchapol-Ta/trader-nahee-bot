# V3 Pre-Implementation Master Plan

## Purpose
Prepare Signal Bot for V3 without breaking the existing V2 bot.

V3 direction:
- V2 finds and formats trading signals.
- V3 interprets those signals into decision guidance.
- V3 starts collecting structured data for future performance improvement.

## Core Principle
Do not rewrite V2.

V3 should sit on top of V2:
```text
V2 signal pipeline
→ V3 decision layer
→ V3 position sizing
→ V3 journal
→ V3 Telegram formatting
```

## Step-by-Step Order

### Step 1 — Update Docs
Update:
- `AGENTS.md`
- `CLAUDE.md`

Goal:
- Remove stale V1-only assumptions.
- Document current V2 modules and V3 direction.
- Add implementation rules for Codex/Claude.

### Step 2 — Add V3 Config Flags
Add safe feature flags.

Recommended defaults:
```python
ENABLE_V3_DECISION_LAYER = False
ENABLE_SIGNAL_JOURNAL = True
ENABLE_POSITION_SIZING = False
ENABLE_V3_TELEGRAM_FORMAT = False
```

Reason:
- Journal can safely run early.
- Decision/position/formatter changes can be enabled later.

### Step 3 — Add Journal / Signal Storage
Add `journal.py` or `signal_logger.py`.

Recommended format:
- JSONL first
- One record per signal or generated output
- Append-only
- Safe failure behavior: log error, do not crash whole bot unless strict mode is enabled

Suggested fields:
```text
timestamp
run_id
ticker
setup_type
market_regime
risk_mode
decision
confidence
grade
score
entry
buy_stop
stop
targets
risk_reward
main_reason
supporting_reasons
risk_warnings
next_action
telegram_message_text
raw_signal
```

### Step 4 — Add Storage + V2 Compatibility Tests
Before changing behavior:
- Test journal writes valid JSONL.
- Test malformed/missing fields do not crash.
- Test V2 formatter output still works.
- Test V2 pipeline behavior remains compatible.

### Step 5 — Add Decision Engine Skeleton
Add `decision_engine.py`.

Initial logic can be conservative:
- If V3 disabled: return no decision or pass-through.
- If signal is actual breakout, good grade, good R:R, supportive market: `ENTER`
- If near breakout or incomplete trigger: `WAIT`
- If promising but market not supportive: `WATCHLIST_ONLY`
- If bad R:R, wide stop, low score, or extended: `AVOID`

Decision result structure:
```python
{
    "decision": "ENTER",
    "confidence": "HIGH",
    "main_reason": "...",
    "supporting_reasons": [...],
    "risk_warnings": [...],
    "next_action": "..."
}
```

### Step 6 — Add Position Sizing
Add `position_sizing.py`.

Use mock/config portfolio first:
```python
portfolio_size = MOCK_PORTFOLIO_SIZE
risk_pct = DEFAULT_RISK_PER_TRADE_PCT
```

Calculate:
```text
risk_per_share = entry - stop
max_capital_risk = portfolio_size * risk_pct
suggested_shares = floor(max_capital_risk / risk_per_share)
estimated_position_value = suggested_shares * entry
max_loss = suggested_shares * risk_per_share
```

Handle:
- missing entry
- missing stop
- stop >= entry
- zero/negative portfolio
- zero/negative risk percent

### Step 7 — Update Telegram Formatter
Add V3 fields only if enabled or decision data exists.

V3 format should show:
```text
Decision
Confidence
Risk Mode
Position Size
Why this decision
Watch out
Next action
```

Do not make messages too long.

### Step 8 — Validate
Run:
```bash
python -m pytest tests -v
python -m compileall .
```

### Step 9 — Review Before Full V3
Before implementing deeper V3:
- Confirm V2 still works.
- Confirm journal records are written.
- Confirm decision skeleton outputs are clear.
- Confirm position sizing math is correct.
- Confirm Telegram output is readable.

## Not Included Yet
Do not implement these in Pre-V3:
- real broker/account integration
- real open-position tracking
- sector exposure enforcement using actual holdings
- backtest engine
- historical replay
- dashboard
- AI coach
- strategy optimization
- CI/lint/type tooling mixed with trading logic

## Final Pre-V3 Acceptance Criteria
Pre-V3 is ready when:
- Docs are updated.
- Config flags exist.
- Journal storage works.
- Decision engine skeleton exists.
- Position sizing module works.
- Formatter can display V3 info without breaking V2.
- Tests pass.
- Compileall passes.
