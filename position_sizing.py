# position_sizing.py - Pre-V3 mock portfolio position sizing.
import math

from config import (
    DEFAULT_RISK_PER_TRADE_PCT,
    MOCK_PORTFOLIO_SIZE,
    RISK_MODE_AGGRESSIVE_PCT,
    RISK_MODE_CONSERVATIVE_PCT,
    RISK_MODE_NORMAL_PCT,
    RISK_MODE_SMALL_PCT,
    RISK_MODE_TINY_PCT,
)

SIZING_MODE_DISABLED = "disabled"
SIZING_MODE_MOCK_CONFIG = "mock_config"
SIZING_MODE_INVALID_INPUT = "invalid_input"

TRADE_RISK_NO_TRADE = "NO_TRADE"
TRADE_RISK_TINY = "TINY"
TRADE_RISK_SMALL = "SMALL"
TRADE_RISK_NORMAL = "NORMAL"
TRADE_RISK_AGGRESSIVE = "AGGRESSIVE"

RISK_MODE_PCTS = {
    "conservative": RISK_MODE_CONSERVATIVE_PCT,
    "normal": RISK_MODE_NORMAL_PCT,
    "aggressive": RISK_MODE_AGGRESSIVE_PCT,
}

TRADE_RISK_MODE_PCTS = {
    TRADE_RISK_NO_TRADE: 0.0,
    TRADE_RISK_TINY: RISK_MODE_TINY_PCT,
    TRADE_RISK_SMALL: RISK_MODE_SMALL_PCT,
    TRADE_RISK_NORMAL: RISK_MODE_NORMAL_PCT,
    TRADE_RISK_AGGRESSIVE: RISK_MODE_AGGRESSIVE_PCT,
}


def _empty_result(
    *,
    valid: bool,
    reason: str,
    sizing_mode: str,
    trade_risk_mode: str,
    risk_pct: float = 0.0,
) -> dict:
    return {
        "valid": valid,
        "reason": reason,
        "sizing_mode": sizing_mode,
        "trade_risk_mode": trade_risk_mode,
        "risk_mode": trade_risk_mode.lower(),
        "risk_pct": risk_pct,
        "risk_per_share": 0.0,
        "max_capital_risk": 0.0,
        "suggested_shares": 0,
        "estimated_position_value": 0.0,
        "max_loss": 0.0,
    }


def _invalid(reason: str, trade_risk_mode: str = TRADE_RISK_NORMAL) -> dict:
    return _empty_result(
        valid=False,
        reason=reason,
        sizing_mode=SIZING_MODE_INVALID_INPUT,
        trade_risk_mode=trade_risk_mode,
    )


def _disabled(reason: str = "no trade recommended") -> dict:
    return _empty_result(
        valid=False,
        reason=reason,
        sizing_mode=SIZING_MODE_DISABLED,
        trade_risk_mode=TRADE_RISK_NO_TRADE,
    )


def _normalize_trade_risk_mode(value: str | None) -> str:
    mode = str(value or TRADE_RISK_NORMAL).upper()
    return mode if mode in TRADE_RISK_MODE_PCTS else TRADE_RISK_NORMAL


def _is_known_trade_risk_mode(value: str | None) -> bool:
    return str(value or "").upper() in TRADE_RISK_MODE_PCTS


def calculate_position_size(
    entry: float | None,
    stop: float | None,
    portfolio_size: float = MOCK_PORTFOLIO_SIZE,
    risk_pct: float | None = None,
    risk_mode: str = "normal",
    trade_risk_mode: str | None = None,
) -> dict:
    """Calculate mock position size from entry, stop, portfolio, and risk percent."""
    if trade_risk_mode is not None and not _is_known_trade_risk_mode(trade_risk_mode):
        return _invalid("unknown trade risk mode", str(trade_risk_mode).upper())

    selected_trade_risk_mode = _normalize_trade_risk_mode(trade_risk_mode)
    if trade_risk_mode is None and risk_mode in RISK_MODE_PCTS:
        selected_risk_pct = risk_pct if risk_pct is not None else RISK_MODE_PCTS[risk_mode]
        selected_trade_risk_mode = risk_mode.upper() if risk_mode != "conservative" else TRADE_RISK_SMALL
    else:
        selected_risk_pct = (
            risk_pct
            if risk_pct is not None
            else TRADE_RISK_MODE_PCTS[selected_trade_risk_mode]
        )

    if selected_trade_risk_mode == TRADE_RISK_NO_TRADE:
        return _disabled()

    try:
        entry_value = float(entry)
        stop_value = float(stop)
        portfolio_value = float(portfolio_size)
        risk_pct_value = float(selected_risk_pct)
    except (TypeError, ValueError):
        return _invalid(
            "entry, stop, portfolio size, and risk percent must be numeric",
            selected_trade_risk_mode,
        )

    if entry_value <= 0:
        return _invalid("entry must be positive", selected_trade_risk_mode)
    if stop_value <= 0:
        return _invalid("stop must be positive", selected_trade_risk_mode)
    if stop_value >= entry_value:
        return _invalid("stop must be below entry", selected_trade_risk_mode)
    if portfolio_value <= 0:
        return _invalid("portfolio size must be positive", selected_trade_risk_mode)
    if risk_pct_value <= 0:
        return _invalid("risk percent must be positive", selected_trade_risk_mode)

    risk_per_share = round(entry_value - stop_value, 2)
    max_capital_risk = round(portfolio_value * risk_pct_value, 2)
    suggested_shares = int(math.floor(max_capital_risk / risk_per_share))
    estimated_position_value = round(suggested_shares * entry_value, 2)
    max_loss = round(suggested_shares * risk_per_share, 2)
    return {
        "valid": True,
        "reason": "ok",
        "sizing_mode": SIZING_MODE_MOCK_CONFIG,
        "trade_risk_mode": selected_trade_risk_mode,
        "risk_mode": selected_trade_risk_mode.lower(),
        "risk_pct": risk_pct_value,
        "risk_per_share": risk_per_share,
        "max_capital_risk": max_capital_risk,
        "suggested_shares": suggested_shares,
        "estimated_position_value": estimated_position_value,
        "max_loss": max_loss,
    }


def calculate_signal_position_size(
    signal: dict,
    portfolio_size: float = MOCK_PORTFOLIO_SIZE,
    risk_pct: float | None = None,
    risk_mode: str = "normal",
    trade_risk_mode: str | None = None,
) -> dict:
    """Calculate sizing from V3 sizing_input when present, otherwise V2 levels."""
    plan = signal.get("trade_plan") or {}
    decision = signal.get("v3_decision") or {}
    selected_trade_risk_mode = trade_risk_mode
    if selected_trade_risk_mode is None and isinstance(decision, dict):
        selected_trade_risk_mode = decision.get("trade_risk_mode")
    sizing_input = decision.get("sizing_input") if isinstance(decision, dict) else {}
    if not isinstance(sizing_input, dict):
        sizing_input = {}

    selected_risk_pct = risk_pct
    selected_mode = risk_mode
    if selected_trade_risk_mode is None and selected_risk_pct is None:
        selected_risk_pct = RISK_MODE_PCTS.get(risk_mode, DEFAULT_RISK_PER_TRADE_PCT)
        if risk_mode not in RISK_MODE_PCTS:
            selected_mode = "normal"
    return calculate_position_size(
        entry=sizing_input.get("decision_entry", sizing_input.get("entry", plan.get("entry"))),
        stop=sizing_input.get("decision_stop", sizing_input.get("stop", plan.get("stop_loss"))),
        portfolio_size=portfolio_size,
        risk_pct=selected_risk_pct,
        risk_mode=selected_mode,
        trade_risk_mode=selected_trade_risk_mode,
    )
