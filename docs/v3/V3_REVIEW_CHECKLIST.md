# Pre-V3 Review Checklist

## Docs
- [ ] AGENTS.md no longer describes only V1 EMA/RSI bot
- [ ] CLAUDE.md no longer describes only V1 EMA/RSI bot
- [ ] Docs clearly state V2 is current
- [ ] Docs clearly state V3 goal is Trade Decision Assistant
- [ ] Docs warn not to rewrite V2 scoring/filtering

## Config
- [ ] V3 feature flags exist
- [ ] Defaults are safe
- [ ] Journal path is configurable
- [ ] Mock portfolio settings exist
- [ ] Risk percent settings exist

## Journal
- [ ] JSONL or SQLite storage implemented
- [ ] Parent directory auto-created
- [ ] Append-only behavior
- [ ] Handles missing fields safely
- [ ] Handles unserializable values safely or clearly
- [ ] Does not crash bot on write failure by default
- [ ] Tests exist

## Decision Engine
- [ ] Supports ENTER
- [ ] Supports WAIT
- [ ] Supports WATCHLIST_ONLY
- [ ] Supports AVOID
- [ ] DecisionResult includes action_label
- [ ] Returns confidence
- [ ] Returns main reason
- [ ] Returns supporting reasons
- [ ] Returns risk warnings
- [ ] Returns next action
- [ ] DecisionResult includes wait_conditions
- [ ] DecisionResult includes invalidation
- [ ] Does not replace V2 scoring

## Decision Quality
- [ ] Setup score and decision confidence are treated separately
- [ ] ENTER requires valid entry and stop
- [ ] ENTER requires acceptable risk/reward or a clear warning
- [ ] WAIT includes a specific trigger or confirmation to wait for
- [ ] WATCHLIST_ONLY explains why it is not actionable yet
- [ ] AVOID includes the disqualifying reason
- [ ] Missing data lowers confidence or blocks action

## Position Sizing
- [ ] Calculates risk per share
- [ ] Calculates max capital risk
- [ ] Calculates suggested shares
- [ ] Calculates estimated position value
- [ ] Calculates max loss
- [ ] Handles invalid entry/stop
- [ ] Handles stop >= entry
- [ ] Handles invalid portfolio/risk pct
- [ ] trade_risk_mode is separate from position sizing calculation
- [ ] Tests exist

## Formatter
- [ ] V2 formatting still works
- [ ] V3 info shown only when present/enabled
- [ ] Message is readable
- [ ] Message is not too long
- [ ] Tests exist

## Telegram UX
- [ ] V3 fields are easy to scan
- [ ] Decision and next action are visible without bloating the message
- [ ] Risk warnings are concise
- [ ] Formatter does not contain decision rules
- [ ] V3 formatter does not generate wait/invalidation logic
- [ ] V2 Telegram output is unchanged when V3 formatting is disabled

## Reliability
- [ ] V3 errors do not block V2 sends by default
- [ ] Journal failures are logged and non-fatal by default
- [ ] Missing optional fields are handled safely
- [ ] Required invalid risk fields prevent ENTER
- [ ] No heavy dependencies added

## Shadow Validation
- [ ] V3 can run silently beside V2
- [ ] Shadow results are journaled
- [ ] V2 A+/A vs V3 decision mismatches can be reviewed
- [ ] V2 B vs V3 decision mismatches can be reviewed
- [ ] V3 Telegram output remains disabled until reviewed across multiple runs

## Validation
- [ ] `python -m pytest tests -v` passes
- [ ] `python -m compileall .` passes
- [ ] Changed files reviewed
- [ ] Known limitations listed
- [ ] Commit created only after validation
