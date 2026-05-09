# Codex Prompt Pack — Pre-V3 Foundation

## Prompt 1 — Plan Only

```text
You are preparing the Signal Bot repo for V3.

Important:
V2 is already implemented, committed, and pushed. Do not assume the old EMA/RSI-only V1 bot is the current system.

Goal:
Prepare a safe Pre-V3 foundation before full V3 implementation.

Pre-V3 order:
1. Update AGENTS.md / CLAUDE.md if needed
2. Add V3 config flags
3. Add journal/signal storage
4. Add tests for storage + current V2 compatibility
5. Add decision engine skeleton
6. Add position sizing with mock portfolio config
7. Update Telegram formatter
8. Run:
   python -m pytest tests -v
   python -m compileall .

Before changing code, inspect the repo and return:
- Existing architecture
- Files that must change
- New files to create
- Exact test files to add/update
- Any risk to V2 behavior
- Implementation order
- Whether JSONL or SQLite is safer for this repo

Do not change code yet.
Wait for approval.
```

## Prompt 2 — Implement Pre-V3 Foundation

```text
Proceed with Pre-V3 foundation implementation based on the approved plan.

Rules:
- Do not break V2 behavior.
- Do not rewrite V2 scoring/filtering.
- Add V3 as an additive layer.
- Keep risky behavior behind config flags.
- Prefer JSONL journal unless there is a strong reason to use SQLite.
- Add tests for each new module.
- Use existing project style.
- Do not add heavy dependencies.
- Do not implement dashboard, backtest, AI coach, real portfolio tracking, or strategy optimization.

Implement:

1. Update AGENTS.md and CLAUDE.md
- Reflect current V2 architecture.
- Remove stale V1-only assumptions.
- Add V3 direction and rules.

2. Add config flags
Suggested:
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

3. Add journal storage
Create journal.py or signal_logger.py.
Use append-only JSONL.
Make it safe:
- Create parent directory if missing
- Convert unserializable objects safely if needed
- Log write failures
- Do not crash the full bot by default

4. Add decision engine skeleton
Create decision_engine.py.
Support:
- ENTER
- WAIT
- WATCHLIST_ONLY
- AVOID
Return:
- decision
- confidence
- main_reason
- supporting_reasons
- risk_warnings
- next_action

5. Add position sizing
Create position_sizing.py.
Calculate:
- risk_per_share
- max_capital_risk
- suggested_shares
- estimated_position_value
- max_loss
Handle invalid input safely.

6. Update Telegram formatter
If V3 decision data exists or V3 formatter flag is enabled, show:
- Decision
- Confidence
- Risk Mode
- Position Size
- Why this decision
- Watch out
- Next action

Preserve V2 message behavior when V3 data is absent/disabled.

7. Add tests
Add meaningful tests for:
- JSONL journal write
- journal invalid/missing fields
- decision outcomes or skeleton behavior
- position sizing normal case
- position sizing invalid cases
- formatter backward compatibility
- V2 compatibility where practical

After implementation:
- Run python -m pytest tests -v
- Run python -m compileall .
- Show changed files
- Show test results
- Show sample V3 Telegram output
- List known limitations
```

## Prompt 3 — Strict Review

```text
Review the Pre-V3 foundation implementation as a strict senior engineer and trading-system reviewer.

Check:
1. Did it preserve V2 behavior?
2. Are AGENTS.md / CLAUDE.md now accurate?
3. Are V3 config flags safe?
4. Is journal storage reliable and simple?
5. Is decision_engine.py additive, not disruptive?
6. Is position_sizing.py mathematically correct?
7. Does formatter preserve V2 output when V3 is absent/disabled?
8. Are tests meaningful?
9. Are logs useful but not noisy?
10. Did implementation avoid unnecessary dependencies and over-engineering?

Return:
- Pass/fail by section
- Critical issues
- Recommended fixes
- Nice-to-have improvements
- Readiness score from 1-10

Do not change code yet.
```

## Prompt 4 — Fix Review Issues

```text
Fix only the issues identified in the Pre-V3 review.

Rules:
- Do not add new features.
- Do not rewrite unrelated code.
- Preserve V2 behavior.
- Add or update tests for each fix.
- Run:
  python -m pytest tests -v
  python -m compileall .

Return:
- Fixed issues
- Changed files
- Test results
- Remaining limitations
```

## Prompt 5 — Commit

```text
Prepare Pre-V3 foundation for commit.

Before committing:
1. Run python -m pytest tests -v
2. Run python -m compileall .
3. Show git status
4. Summarize changed files
5. Summarize implemented foundation
6. List known limitations

If everything is clean and safe, create commit:

feat: add pre-v3 trade decision foundation

Do not push until I explicitly approve.
```

## Prompt 6 — Push

```text
Push the Pre-V3 foundation commit.

Before pushing:
- Confirm current branch
- Confirm latest commit
- Confirm working tree is clean

Then push to the current remote branch.
```
