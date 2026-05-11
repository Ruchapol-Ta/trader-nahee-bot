# V3 Decision Framework

## Philosophy
V3 turns Signal Bot from an alert generator into a trade decision assistant.

V2 remains responsible for finding valid setups. V3 should interpret those setups into clear guidance:
- Should I enter?
- How much risk is reasonable?
- If not entering, what exactly should I wait for?

V3 must be conservative, explainable, and additive. It should never hide weak evidence behind confident language.

## Setup Score vs Decision Confidence
Setup score measures the quality of the technical setup found by V2.

Decision confidence measures whether the bot has enough complete, reliable context to recommend an action.

Examples:
- A high-scoring setup can still be `WAIT` if the breakout trigger has not happened.
- A strong breakout can still be lower confidence if risk/reward is poor, liquidity is thin, or market regime is unfavorable.
- A low-scoring setup should not become `ENTER` because of one attractive field.

## Decision Outcomes
`ENTER`
- Setup is actionable now.
- Trigger, risk, liquidity, relative strength, and market context are acceptable.
- Risk can be defined with a valid stop and acceptable R:R.

`WAIT`
- Setup is promising but lacks a required trigger or confirmation.
- The user should know the exact condition to wait for.

`WATCHLIST_ONLY`
- Setup is worth tracking but not close enough or safe enough for a trade decision.
- Often used for early bases, unfavorable regime, or incomplete risk data.

`AVOID`
- Setup has a clear disqualifier.
- Examples include poor liquidity, invalid stop, bad R:R, extended entry, weak relative strength, or unreliable data.

## Actionable Signal Requirements
An actionable signal should have:
- Clear ticker and setup type
- Current price or close
- Entry or buy stop
- Stop level
- Defined risk per share
- At least one target or acceptable R:R
- Market regime context
- Liquidity pass
- Relative strength context
- Decision reason that can be understood without reading code

## User-Facing Requirements
Every V3 decision shown to the user must include:
- Decision
- Confidence
- Main reason
- Supporting reasons
- Risk warnings
- Next action

For non-`ENTER` decisions, `next_action` is the most important field. It must say what to wait for, what would invalidate the setup, or why the signal should be ignored.
