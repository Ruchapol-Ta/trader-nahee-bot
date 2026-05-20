# V3 Dry-Run Review Guide

## 1. Purpose

Use the V3 dry-run review before changing V3 thresholds or rollout behavior. It runs the current scan and V3 decision review path in a safe operator-review mode so you can inspect what V3 would decide without sending Telegram messages or writing journal records.

This command is for diagnostics only. Dry-run output is not a trade instruction.

## 2. Exact Safe Command

Run from the repo root:

```powershell
.\.venv-laptop\Scripts\python.exe signal_bot.py --v3-dry-run-review
```

## 3. What The Command Does

- Runs the V2 scan path and selected-signal review.
- Enables V3 decision review in memory for the dry-run.
- Keeps dry-run output quiet by suppressing per-ticker reject noise.
- Prints market context, V2 funnel counts, reject aggregation, V3 decision counts, V3 blockers, selected V3 review rows, and detailed examples.
- Skips Telegram delivery.
- Skips journal writes.

## 4. What The Command Does Not Do

- It does not send Telegram messages.
- It does not write journal files.
- It does not change config defaults.
- It does not edit `.env`.
- It does not change V2 scoring or filtering.
- It does not change V3 decision logic or thresholds.
- It does not enable live trading or production delivery.

## 5. How To Read The Output

### Market regime

Shows the broad market context used by the scan, such as bullish, neutral, or defensive market conditions. Use this as context for the selected signals, not as a standalone trade signal.

### V2 funnel

Shows how many tickers moved through the scan stages. This helps identify whether the result set is small because the market had few setups or because a specific filter rejected many names.

### Reject aggregation

Shows the most common V2 reject reasons in aggregate. This should remain available even when per-ticker reject logs are suppressed.

### V3 decisions

Shows the count of selected names by V3 decision outcome:

- `ENTER`
- `WAIT`
- `WATCHLIST_ONLY`
- `AVOID`
- `none`

Review these counts before changing thresholds. For example, a bullish market with many `WAIT` decisions may point to risk or confirmation issues rather than a broken scan.

### Telegram delivery

Should show that Telegram delivery was skipped. If this command sends Telegram, treat that as a safety regression.

### Journal writes

Should show that journal writes were skipped. The dry-run review is print-only by default.

### V3 blockers

Shows aggregate blocker counts derived from existing V3 decision reasons, warnings, flags, and selected-signal metadata. Use this section to understand why selected names are not becoming `ENTER`.

### Selected V3 review

Shows every selected trade alert and watchlist name in a compact row. Each row includes the ticker, grade, decision, confidence, score when available, stop distance, volume ratio, and compact blocker labels.

### Detailed examples

Shows a small capped set of detailed examples with the main reason, supporting reasons, and warnings. Use this section to understand representative decisions without duplicating the full selected list.

## 6. Common V3 Blockers

### stop_distance_wide

The stop distance is wider than preferred for clean actionability. This often keeps an otherwise promising setup in `WAIT` or `WATCHLIST_ONLY`.

### stop_distance_excessive

The stop distance is too wide for the current risk rules. This is stronger than `stop_distance_wide` and usually blocks `ENTER`.

### volume_confirmation_light

The volume confirmation is below the V3 confirmation threshold. The displayed ratio may still be above average, such as `1.05x average`, but below the configured confirmation requirement.

### b_grade_not_actionable

The setup is B-grade and not considered actionable by the current V3 decision rules. These are usually watchlist candidates unless other evidence improves.

### missing_setup_confirmation

The selected name is missing required setup or breakout confirmation evidence. Review this before loosening thresholds.

### other

The decision did not map cleanly to the known blocker categories. Inspect the detailed examples or the selected review row for context.

## 7. Recommended Operating Flow

1. Run the dry-run review command.
2. Confirm Telegram delivery and journal writes are both skipped.
3. Review the market regime and V2 funnel.
4. Review `ENTER`, `WAIT`, `WATCHLIST_ONLY`, and `AVOID` counts.
5. Review V3 blockers before changing thresholds.
6. Read selected V3 review rows to see all selected names.
7. Use detailed examples to understand representative decisions.
8. Make only small, testable changes after the blocker pattern is clear.

Do not treat dry-run output as trade instruction. It is a diagnostic review of current decision behavior.

## 8. Troubleshooting

### yfinance/network delay

The dry-run still needs market data. If Yahoo or yfinance is slow, the command may take longer or fail before the decision review. Retry after network access is stable.

### no selected signals

If no trade alerts or watchlist names are selected, inspect the V2 funnel and reject aggregation first. The dry-run can only review V3 decisions for names selected by the scan.

### bullish market but zero ENTER

A bullish regime does not guarantee `ENTER` decisions. Review V3 blockers, especially stop distance, volume confirmation, setup confirmation, and B-grade actionability.

### volume confirmation below threshold wording

The phrase `volume confirmation below threshold` means the volume ratio is below the V3 confirmation requirement. It does not necessarily mean volume is below average.

## 9. Safety Notes

- Do not paste Telegram tokens or chat IDs into logs, screenshots, commits, tickets, or chat messages.
- Do not change config defaults just to make dry-run output look better.
- Do not change thresholds until the blocker pattern is understood.
- Do not use dry-run output as a trade instruction.
- Do not run Telegram delivery unless intentionally testing rollout behavior.
