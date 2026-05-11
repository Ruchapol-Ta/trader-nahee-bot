# V3 Shadow Mode Strategy

## Goal
Run V3 silently beside V2 before changing user-facing Telegram output.

Shadow mode should answer:
- Does V3 classify signals sensibly?
- Does it preserve V2 behavior?
- Are decisions stable enough to show?
- Are logs useful for review?

## Silent Run Behavior
In shadow mode:
- V2 screening and Telegram output remain unchanged.
- V3 reads V2 signal outputs after V2 has already classified them.
- V3 writes decision results to journal/log storage.
- V3 errors are logged and do not block V2 sends.
- V3 formatter output is not sent to Telegram.

## What to Log
Log one record per relevant signal:
- timestamp
- run_id
- ticker
- V2 grade
- V2 score
- V2 setup type
- V2 alert category if available
- V3 decision
- V3 confidence
- main_reason
- supporting_reasons
- risk_warnings
- next_action
- entry, buy_stop, stop, targets, R:R
- market_regime
- liquidity result
- relative strength result
- raw signal snapshot or compact reference

Also log run-level summaries:
- total screened
- total V2 A+/A alerts
- total V2 B watchlist names
- V3 ENTER count
- V3 WAIT count
- V3 WATCHLIST_ONLY count
- V3 AVOID count
- V3 error count

## Comparing V2 vs V3
Compare decisions against existing V2 output:
- A+/A breakout alerts should usually become `ENTER` or `WAIT`.
- B watchlist summaries should usually become `WAIT` or `WATCHLIST_ONLY`.
- C/rejected signals should usually become `AVOID` or remain absent from user-facing output.

Review exceptions manually:
- V2 A+/A but V3 `AVOID`
- V2 B but V3 `ENTER`
- V3 `HIGH` confidence with missing risk fields
- V3 `ENTER` without valid entry and stop
- V3 `WAIT` without a concrete next action

## Enablement Criteria
Do not enable V3 Telegram output until:
- V2 output is unchanged in normal runs.
- Shadow mode runs without blocking the bot.
- Journal records are valid JSONL.
- Decision counts are reasonable for multiple market days.
- `ENTER` decisions always have valid risk levels.
- Non-`ENTER` decisions have specific next actions.
- Formatter output is readable and not too long.
- Tests cover V2 formatter compatibility.
- Manual review finds no repeated misleading decision reasons.
