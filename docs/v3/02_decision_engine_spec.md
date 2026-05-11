# V3 Decision Engine Spec

## Purpose
`decision_engine.py` should read V2 signal outputs and return a structured decision without changing V2 scoring, filtering, or Telegram behavior.

## Inputs
Expected input fields may come from V2 signal dictionaries or lightweight adapters:
- `ticker`
- `setup_type`
- `grade`
- `score`
- `market_regime`
- `liquidity_pass`
- `relative_strength`
- `is_breakout`
- `is_near_breakout`
- `entry`
- `buy_stop`
- `stop`
- `targets`
- `risk_reward`
- `current_price`
- `risk_warnings`
- `raw_signal`

The engine must tolerate missing optional fields and downgrade confidence instead of crashing.

## Output Fields
Decision output must include:
- `decision`
- `action_label`
- `confidence`
- `main_reason`
- `supporting_reasons`
- `risk_warnings`
- `next_action`
- `wait_conditions`
- `invalidation`
- `sizing_mode`
- `trade_risk_mode`
- `sizing_input`

## DecisionResult Structure
Use a simple structure first. A dataclass is preferred if it fits the repo style.

```python
{
    "decision": "WAIT",
    "action_label": "Wait for breakout confirmation",
    "confidence": "MEDIUM",
    "main_reason": "Setup is close, but breakout trigger has not confirmed.",
    "supporting_reasons": [
        "Relative strength is acceptable.",
        "Liquidity filter passed."
    ],
    "risk_warnings": [
        "Entry/stop distance is wider than preferred."
    ],
    "next_action": "Wait for price to clear the buy stop on strong volume.",
    "wait_conditions": [
        "Price closes above the buy stop.",
        "Breakout volume confirms demand."
    ],
    "invalidation": "Avoid if price breaks below the proposed stop or relative strength weakens.",
    "sizing_mode": "mock_config",
    "trade_risk_mode": "NO_TRADE",
    "sizing_input": {
        "entry": 100.0,
        "stop": 95.0,
        "risk_pct": 0.01
    }
}
```

## Risk Flags
Risk flags should be explicit and formatter-friendly:
- `MISSING_ENTRY`
- `MISSING_STOP`
- `INVALID_STOP`
- `POOR_RISK_REWARD`
- `WIDE_STOP`
- `EXTENDED_ENTRY`
- `LOW_LIQUIDITY`
- `WEAK_RELATIVE_STRENGTH`
- `UNFAVORABLE_MARKET_REGIME`
- `NO_VOLUME_CONFIRMATION`
- `GENERIC_SETUP_EVIDENCE`
- `MISSING_TARGETS`
- `STALE_OR_INCOMPLETE_DATA`

## Confidence Principles
Confidence is not the same as bullishness.

Increase confidence when:
- Required fields are present.
- V2 grade and setup evidence agree.
- Risk levels are valid.
- Market regime and relative strength support the setup.
- Decision outcome follows clear rules.

Decrease confidence when:
- Data is missing or stale.
- Setup evidence conflicts.
- Risk/reward is borderline.
- The decision depends on one field.
- Market regime is weak or unclear.

Allowed initial values:
- `HIGH`
- `MEDIUM`
- `LOW`

## Sizing Mode Interface
The decision engine should not own sizing math or calculate share quantity. It recommends `trade_risk_mode` and passes clean sizing inputs to `position_sizing.py`.

Suggested interface:
```python
calculate_position_size(
    entry: float,
    stop: float,
    portfolio_size: float,
    risk_pct: float,
)
```

Suggested sizing modes:
- `disabled`
- `mock_config`
- `invalid_input`

`sizing_mode` describes whether the sizing system should run:
- `disabled`
- `mock_config`
- `invalid_input`

`trade_risk_mode` describes the recommended trade risk posture:
- `NO_TRADE`
- `TINY`
- `SMALL`
- `NORMAL`
- `AGGRESSIVE`

Examples:
- `WAIT` should usually use `trade_risk_mode="NO_TRADE"`.
- Borderline `ENTER` decisions may use `TINY` or `SMALL`.
- Strong `ENTER` decisions may use `NORMAL`.
- `AGGRESSIVE` should be rare and require unusually complete evidence.

## Edge Cases
Handle safely:
- Missing ticker
- Missing grade or score
- Missing entry, buy stop, or stop
- Stop greater than or equal to entry
- Negative or zero prices
- Missing market regime
- Missing relative strength fields
- Signal rejected by V2 but still present in debug data
- Conflicting breakout and near-breakout flags
- Missing targets or R:R
- Non-numeric strings from data providers
