# position_sizing.py - Pre-V3 mock portfolio position sizing.
import math

from config import (
    DEFAULT_RISK_PER_TRADE_PCT,
    MOCK_PORTFOLIO_SIZE,
    RISK_MODE_AGGRESSIVE_PCT,
    RISK_MODE_CONSERVATIVE_PCT,
    RISK_MODE_NORMAL_PCT,
)

RISK_MODE_PCTS = {
    "conservative": RISK_MODE_CONSERVATIVE_PCT,
    "normal": RISK_MODE_NORMAL_PCT,
    "aggressive": RISK_MODE_AGGRESSIVE_PCT,
}


def _invalid(reason: str, risk_mode: str = "normal") -> dict:
    return {
        "valid": False,
        "reason": reason,
        "risk_mode": risk_mode,
        "risk_per_share": 0.0,
        "max_capital_risk": 0.0,
        "suggested_shares": 0,
        "estimated_position_value": 0.0,
        "max_loss": 0.0,
    }


def calculate_position_size(
    entry: float | None,
    stop: float | None,
    portfolio_size: float = MOCK_PORTFOLIO_SIZE,
    risk_pct: float = DEFAULT_RISK_PER_TRADE_PCT,
    risk_mode: str = "normal",
) -> dict:
    """Calculate mock position size from entry, stop, portfolio, and risk percent."""
    try:
        entry_value = float(entry)
        stop_value = float(stop)
        portfolio_value = float(portfolio_size)
        risk_pct_value = float(risk_pct)
    except (TypeError, ValueError):
        return _invalid("entry, stop, portfolio size, and risk percent must be numeric", risk_mode)

    if entry_value <= 0:
        return _invalid("entry must be positive", risk_mode)
    if stop_value <= 0:
        return _invalid("stop must be positive", risk_mode)
    if stop_value >= entry_value:
        return _invalid("stop must be below entry", risk_mode)
    if portfolio_value <= 0:
        return _invalid("portfolio size must be positive", risk_mode)
    if risk_pct_value <= 0:
        return _invalid("risk percent must be positive", risk_mode)

    risk_per_share = round(entry_value - stop_value, 2)
    max_capital_risk = round(portfolio_value * risk_pct_value, 2)
    suggested_shares = int(math.floor(max_capital_risk / risk_per_share))
    estimated_position_value = round(suggested_shares * entry_value, 2)
    max_loss = round(suggested_shares * risk_per_share, 2)
    return {
        "valid": True,
        "reason": "ok",
        "risk_mode": risk_mode,
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
) -> dict:
    """Calculate sizing from a V2 signal's trade_plan entry and stop_loss."""
    plan = signal.get("trade_plan") or {}
    selected_risk_pct = risk_pct
    selected_mode = risk_mode
    if selected_risk_pct is None:
        selected_risk_pct = RISK_MODE_PCTS.get(risk_mode, DEFAULT_RISK_PER_TRADE_PCT)
        if risk_mode not in RISK_MODE_PCTS:
            selected_mode = "normal"
    return calculate_position_size(
        entry=plan.get("entry"),
        stop=plan.get("stop_loss"),
        portfolio_size=portfolio_size,
        risk_pct=selected_risk_pct,
        risk_mode=selected_mode,
    )
