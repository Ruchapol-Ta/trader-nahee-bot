# V3 Implementation Log

Use this file if you want Codex to track implementation progress.

## Phase: Pre-V3 Foundation

### Status
Structurally complete and enabled. V2 remains the base scanner; V3 adds
decision annotation, mock position sizing, JSONL journaling, and Telegram
formatting on top of V2-selected signals.

### Completed
- [x] Docs updated for V2/V3 architecture
- [x] Config flags added
- [x] Journal storage added
- [x] Storage tests added
- [x] V2 compatibility tests added
- [x] Decision engine added
- [x] Position sizing added
- [x] Telegram formatter updated
- [x] Tests run in the project virtualenv
- [x] Compileall run in the project virtualenv
- [x] Review completed
- [ ] Current ops/journal durability patch committed

### Notes
- V3 is an additive decision layer. Do not loosen V3 decision thresholds or
  rewrite V2 scoring/filtering as part of ops polish.
- Latest local journal review showed a bullish market with 514 scanned, 5 A
  alerts, 10 B watchlist, ENTER 0, WAIT 5, WATCHLIST_ONLY 9, AVOID 1, and no
  V3 errors. The main blockers were weak volume confirmation and wide stops.
- Remaining work is rollout validation, durable journal history, and decision
  calibration over multiple market days.

### Architecture Decisions
Record decisions that affect module boundaries, data flow, config flags, formatter behavior, or storage format.

- Patch Slice 2 adds V3 shadow journal integration. V3 decisions can be collected for review while Telegram output remains V2-compatible unless `ENABLE_V3_TELEGRAM_FORMAT=True`.
- Run-level summaries are journaled even when the market regime is invalid, so
  skipped scans still leave an audit breadcrumb.
- GitHub Actions persists `data/signal_journal.jsonl` to the `journal-data`
  branch after `run-now` scans, including scans that fail after producing a
  journal file.

### Failure Log
Record implementation failures, broken assumptions, test failures, data issues, and how they were resolved.

- System Python is missing project dependencies. Validation should use
  `.\.venv-laptop\Scripts\python.exe`.
- Market-data failures can make `--v3-dry-run-review` report `Market valid: no`
  or `Scanned: 0`; diagnose data/cache readiness before attempting live sends.

### Technical Debt
Record known shortcuts that are acceptable for Pre-V3 but should be revisited before full V3.

- Durable journal history exists as an append-only branch, but there is not yet
  a reporting tool over that branch history.
- Decision calibration should be based on multiple journaled market days before
  any threshold changes.

### Known Limitations
- No real portfolio tracking yet.
- No trade lifecycle tracking yet.
- No backtest or historical replay yet.
- No dashboard yet.
- No AI coach yet.
