# V3 Rollout Review Checklist

Pre-V3 foundation is structurally implemented. Use this checklist to verify
that the current rollout remains safe, durable, and additive to V2.

## Docs
- [x] AGENTS.md no longer describes only V1 EMA/RSI bot
- [x] CLAUDE.md no longer describes only V1 EMA/RSI bot
- [x] Docs clearly state V2 is current
- [x] Docs clearly state V3 goal is Trade Decision Assistant
- [x] Docs warn not to rewrite V2 scoring/filtering

## Config
- [x] V3 feature flags exist
- [x] Journal path is configurable
- [x] Mock portfolio settings exist
- [x] Risk percent settings exist
- [x] Current production behavior is explicit in docs and guarded by rollout checks

## Journal
- [x] JSONL storage implemented
- [x] Parent directory auto-created
- [x] Append-only behavior
- [x] Handles missing fields safely
- [x] Handles unserializable values safely or clearly
- [x] Does not crash bot on write failure by default
- [x] Tests exist
- [x] Invalid-market runs journal a run summary breadcrumb
- [x] GitHub Actions persists run-now journal output to `journal-data`

## Decision Engine
- [x] Supports ENTER
- [x] Supports WAIT
- [x] Supports WATCHLIST_ONLY
- [x] Supports AVOID
- [x] DecisionResult includes action_label
- [x] Returns confidence
- [x] Returns main reason
- [x] Returns supporting reasons
- [x] Returns risk warnings
- [x] Returns next action
- [x] DecisionResult includes wait_conditions
- [x] DecisionResult includes invalidation
- [x] Does not replace V2 scoring

## Decision Quality
- [x] Setup score and decision confidence are treated separately
- [x] ENTER requires valid entry and stop
- [x] ENTER requires acceptable risk/reward or a clear warning
- [x] WAIT includes a specific trigger or confirmation to wait for
- [x] WATCHLIST_ONLY explains why it is not actionable yet
- [x] AVOID includes the disqualifying reason
- [x] Missing data lowers confidence or blocks action
- [ ] Review multiple journaled market days before changing thresholds

## Position Sizing
- [x] Calculates risk per share
- [x] Calculates max capital risk
- [x] Calculates suggested shares
- [x] Calculates estimated position value
- [x] Calculates max loss
- [x] Handles invalid entry/stop
- [x] Handles stop >= entry
- [x] Handles invalid portfolio/risk pct
- [x] trade_risk_mode is separate from position sizing calculation
- [x] Tests exist

## Formatter
- [x] V2 formatting still works
- [x] V3 info shown only when present/enabled
- [x] Message is readable
- [x] Message is not too long
- [x] Tests exist

## Telegram UX
- [x] V3 fields are easy to scan
- [x] Decision and next action are visible without bloating the message
- [x] Risk warnings are concise
- [x] Formatter does not contain decision rules
- [x] V3 formatter does not generate wait/invalidation logic
- [x] V2 Telegram output is unchanged when V3 formatting is disabled
- [ ] Run `--telegram-rollout-check` before any Telegram rollout change

## Reliability
- [x] V3 errors do not block V2 sends by default
- [x] Journal failures are logged and non-fatal by default
- [x] Missing optional fields are handled safely
- [x] Required invalid risk fields prevent ENTER
- [x] No heavy dependencies added
- [x] Run-now exits red when delivery fails, so CI marks failed scans

## Shadow Validation
- [x] V3 can run silently beside V2
- [x] Shadow results are journaled
- [x] V2 A+/A vs V3 decision mismatches can be reviewed
- [x] V2 B vs V3 decision mismatches can be reviewed
- [ ] Continue reviewing V3 blocker patterns across multiple runs

## Validation
- [ ] `.\.venv-laptop\Scripts\python.exe -m pytest tests -v` passes
- [ ] `.\.venv-laptop\Scripts\python.exe -m compileall .` passes
- [ ] `.\.venv-laptop\Scripts\python.exe signal_bot.py --v3-dry-run-review` completes without sending Telegram or writing journals
- [ ] `.\.venv-laptop\Scripts\python.exe signal_bot.py --telegram-rollout-check` completes without sending Telegram
- [x] Changed files reviewed
- [x] Known limitations listed
- [ ] Commit created only after validation
