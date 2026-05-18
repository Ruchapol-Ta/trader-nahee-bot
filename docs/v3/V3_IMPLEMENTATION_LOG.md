# V3 Implementation Log

Use this file if you want Codex to track implementation progress.

## Phase: Pre-V3 Foundation

### Status
Not started.

### Completed
- [ ] Docs updated
- [ ] Config flags added
- [ ] Journal storage added
- [ ] Storage tests added
- [ ] V2 compatibility tests added
- [ ] Decision engine skeleton added
- [ ] Position sizing added
- [ ] Telegram formatter updated
- [ ] Tests run
- [ ] Compileall run
- [ ] Review completed
- [ ] Commit created

### Notes
Add notes here after each Codex step.

### Architecture Decisions
Record decisions that affect module boundaries, data flow, config flags, formatter behavior, or storage format.

- Patch Slice 2 adds V3 shadow journal integration. V3 decisions can be collected for review while Telegram output remains V2-compatible unless `ENABLE_V3_TELEGRAM_FORMAT=True`.

### Failure Log
Record implementation failures, broken assumptions, test failures, data issues, and how they were resolved.

- Pending.

### Technical Debt
Record known shortcuts that are acceptable for Pre-V3 but should be revisited before full V3.

- Pending.

### Known Limitations
- No real portfolio tracking yet.
- No trade lifecycle tracking yet.
- No backtest or historical replay yet.
- No dashboard yet.
- No AI coach yet.
