# decision_engine.py - Pre-V3 trade decision interpretation layer.
from config import ENABLE_V3_DECISION_LAYER

DECISION_ENTER = "ENTER"
DECISION_WAIT = "WAIT"
DECISION_WATCHLIST_ONLY = "WATCHLIST_ONLY"
DECISION_AVOID = "AVOID"


def _result(
    decision: str,
    confidence: str,
    main_reason: str,
    supporting_reasons: list[str] | None = None,
    risk_warnings: list[str] | None = None,
    next_action: str = "",
) -> dict:
    return {
        "decision": decision,
        "confidence": confidence,
        "main_reason": main_reason,
        "supporting_reasons": supporting_reasons or [],
        "risk_warnings": risk_warnings or [],
        "next_action": next_action,
    }


def _valid_trade_plan(plan: dict) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    try:
        entry = float(plan.get("entry"))
        stop = float(plan.get("stop_loss"))
        expected_rr = float(plan.get("expected_rr", 0))
    except (TypeError, ValueError):
        return False, ["trade plan is missing usable entry, stop, or R:R"]

    if stop >= entry:
        warnings.append("stop is not below entry")
    if expected_rr < 2.0:
        warnings.append("risk/reward is below Pre-V3 minimum")
    return not warnings, warnings


def _market_is_valid(signal: dict, market_regime: dict | None) -> bool:
    if market_regime is not None:
        return bool(market_regime.get("is_valid"))
    summary = str(signal.get("market_regime", "")).lower()
    return "invalid" not in summary


def evaluate_signal_decision(
    signal: dict,
    market_regime: dict | None = None,
    enabled: bool | None = None,
) -> dict | None:
    """Return an additive V3 decision for a V2-selected signal."""
    if enabled is None:
        enabled = ENABLE_V3_DECISION_LAYER
    if not enabled:
        return None

    grade = signal.get("grade")
    score = float(signal.get("score") or 0)
    plan = signal.get("trade_plan") or {}
    valid_plan, risk_warnings = _valid_trade_plan(plan)

    if grade not in {"A+", "A", "B"} or score < 65:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Signal quality is below the Pre-V3 decision threshold.",
            supporting_reasons=signal.get("pass_reasons", [])[:3],
            risk_warnings=risk_warnings or ["grade or score is too weak"],
            next_action="Avoid this setup unless a new V2 signal forms.",
        )

    if not valid_plan:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Risk plan is not usable for a trade decision.",
            supporting_reasons=signal.get("pass_reasons", [])[:3],
            risk_warnings=risk_warnings,
            next_action="Wait for a valid entry and stop before considering risk.",
        )

    if not _market_is_valid(signal, market_regime):
        return _result(
            DECISION_WATCHLIST_ONLY,
            "MEDIUM",
            "Setup is promising, but market regime is not supportive.",
            supporting_reasons=signal.get("pass_reasons", [])[:3],
            risk_warnings=["market regime is not supportive"],
            next_action="Keep on watchlist until market regime improves.",
        )

    if signal.get("is_near_breakout") and not signal.get("is_actual_breakout"):
        return _result(
            DECISION_WAIT,
            "MEDIUM",
            "Setup is near the breakout trigger but has not confirmed.",
            supporting_reasons=signal.get("pass_reasons", [])[:3],
            risk_warnings=[],
            next_action="Wait for a breakout above the pivot with acceptable volume.",
        )

    if grade in {"A+", "A"} and signal.get("is_actual_breakout", True):
        return _result(
            DECISION_ENTER,
            "HIGH",
            "High-quality V2 breakout with a usable risk plan.",
            supporting_reasons=signal.get("pass_reasons", [])[:3],
            risk_warnings=[],
            next_action="Consider entry using the V2 buy stop and defined stop loss.",
        )

    return _result(
        DECISION_WAIT,
        "MEDIUM",
        "Setup is constructive but not ready for an entry decision.",
        supporting_reasons=signal.get("pass_reasons", [])[:3],
        risk_warnings=[],
        next_action="Wait for an A-grade actual breakout signal.",
    )
