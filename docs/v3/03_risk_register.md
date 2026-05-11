# V3 Risk Register

## Data Reliability Risks
- Provider data can be delayed, missing, split-adjusted unexpectedly, or temporarily unavailable.
- Market cap, volume, and dollar-volume fields may be incomplete for some tickers.
- Relative strength comparisons can be distorted by missing benchmark data.
- Stale snapshots can make an `ENTER` decision look current when it is not.

Mitigation:
- Treat missing required data as lower confidence or non-actionable.
- Journal raw inputs needed to reproduce the decision.
- Prefer safe fallback decisions over optimistic ones.

## Decision Quality Risks
- Setup score may be mistaken for trade readiness.
- Decision confidence may sound stronger than the evidence supports.
- `WAIT` can be unhelpful if next action is vague.
- `ENTER` can be unsafe if stop, entry, or R:R is invalid.

Mitigation:
- Keep decision rules explicit.
- Require valid risk fields for `ENTER`.
- Make `next_action` mandatory and specific.
- Review shadow-mode disagreements before enabling V3 output.

## Formatter Risks
- Telegram messages can become too long or hard to scan.
- V3 fields can obscure the original V2 alert.
- Formatter logic can become a second decision engine.

Mitigation:
- Keep formatter display-only.
- Add V3 fields only when enabled or present.
- Test V2 output compatibility.
- Move decision wording into `decision_engine.py`.

## V2 Regression Risks
- V3 code could accidentally change filtering, scoring, or send behavior.
- Journal write failures could interrupt scheduled runs.
- New config defaults could enable V3 prematurely.

Mitigation:
- Keep V3 behind flags.
- Run shadow mode silently first.
- Journal failures should log and continue by default.
- Add V2 backward compatibility tests.

## Overengineering Risks
- Real portfolio tracking, dashboards, backtests, or AI coaching can distract from the foundation.
- Too many abstractions can make decision rules harder to audit.
- Config sprawl can make runtime behavior unclear.

Mitigation:
- Use JSONL first.
- Use mock portfolio sizing first.
- Keep modules small and explicit.
- Defer non-foundation features until V3 decisions prove useful.
