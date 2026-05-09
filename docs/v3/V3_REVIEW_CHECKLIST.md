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
- [ ] Returns confidence
- [ ] Returns main reason
- [ ] Returns supporting reasons
- [ ] Returns risk warnings
- [ ] Returns next action
- [ ] Does not replace V2 scoring

## Position Sizing
- [ ] Calculates risk per share
- [ ] Calculates max capital risk
- [ ] Calculates suggested shares
- [ ] Calculates estimated position value
- [ ] Calculates max loss
- [ ] Handles invalid entry/stop
- [ ] Handles stop >= entry
- [ ] Handles invalid portfolio/risk pct
- [ ] Tests exist

## Formatter
- [ ] V2 formatting still works
- [ ] V3 info shown only when present/enabled
- [ ] Message is readable
- [ ] Message is not too long
- [ ] Tests exist

## Validation
- [ ] `python -m pytest tests -v` passes
- [ ] `python -m compileall .` passes
- [ ] Changed files reviewed
- [ ] Known limitations listed
- [ ] Commit created only after validation
