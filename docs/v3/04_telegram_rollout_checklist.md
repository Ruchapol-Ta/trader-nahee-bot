# Telegram Rollout Checklist

## 1. Purpose

Use this checklist before any Telegram preview, test, or prod rollout. The rollout check is dry-run/check-only: it inspects the local Telegram rollout environment and V3 preview readiness without sending Telegram messages.

The check must not expose Telegram bot token values or chat ID values. It should only print safe labels, environment key names, yes/no fields, and ready/not ready status.

## 2. Exact Safe Command

Run from the repo root:

```powershell
.\.venv-laptop\Scripts\python.exe signal_bot.py --telegram-rollout-check
```

This command should return immediately after printing the checklist. It must not run a normal scan, start scheduler behavior, or send Telegram messages.

## 3. Expected Output Fields

Expected fields include:

- Current mode
- Token present
- Required chat id key
- Required chat id present
- Legacy fallback active
- Prod fallback blocked
- Test mode requires prod chat id
- Preview mode requires prod chat id
- V3 preview formatting available
- Overall readiness

Safe output can include environment key names such as `TELEGRAM_PROD_CHAT_ID`. It must not include the actual bot token or any chat ID value.

## 4. Mode Meanings

### legacy

Legacy mode is active only when `TELEGRAM_TARGET_MODE` is unset. In this mode, the historical `TELEGRAM_CHAT_ID` fallback may be used.

### test

Test mode is active when `TELEGRAM_TARGET_MODE=test`. It requires `TELEGRAM_TEST_CHAT_ID` and does not require `TELEGRAM_PROD_CHAT_ID`.

### preview

Preview mode is active when `TELEGRAM_TARGET_MODE=preview`. It is a safe non-prod mode for rollout readiness checks and does not require `TELEGRAM_PROD_CHAT_ID`.

### prod

Prod mode is active when `TELEGRAM_TARGET_MODE=prod`. It requires `TELEGRAM_PROD_CHAT_ID`.

Explicit prod mode must not fall back to `TELEGRAM_CHAT_ID`.

## 5. Required Env Vars By Mode

| Mode | Required token | Required chat ID |
| --- | --- | --- |
| legacy | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_CHAT_ID` |
| test | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_TEST_CHAT_ID` |
| preview | `TELEGRAM_BOT_TOKEN` | none |
| prod | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_PROD_CHAT_ID` |

`TELEGRAM_CHAT_ID` fallback only applies when `TELEGRAM_TARGET_MODE` is unset.

## 6. Prod Safety Rules

Explicit prod mode requires `TELEGRAM_PROD_CHAT_ID` so production routing is intentional and reviewable.

When `TELEGRAM_TARGET_MODE=prod`, the bot must not use legacy `TELEGRAM_CHAT_ID` as a fallback. This prevents accidental production delivery through an older or ambiguous chat ID setting.

Do not use prod mode unless `TELEGRAM_PROD_CHAT_ID` is present and intentionally configured.

## 7. How To Read ready / not ready

`Overall readiness: ready` means the current mode has the required non-secret environment state for the dry-run checklist.

`Overall readiness: not ready` means one or more required values or safety rules are missing for the current mode. Read the printed safe fields and any listed errors, then update local environment values as needed.

Do not change config defaults just to pass the check. Fix the environment for the intended rollout mode instead.

## 8. What Not To Do

- Do not paste Telegram tokens or chat IDs into logs, screenshots, commits, tickets, or chat messages.
- Do not use prod mode without `TELEGRAM_PROD_CHAT_ID`.
- Do not rely on `TELEGRAM_CHAT_ID` fallback when `TELEGRAM_TARGET_MODE` is explicitly set.
- Do not change config defaults just to pass the check.
- Do not run live Telegram send commands unless intentionally testing a rollout.
- Do not treat this dry-run checklist as proof that a message was delivered; it does not send Telegram messages.
