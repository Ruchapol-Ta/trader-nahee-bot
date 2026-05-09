# decision_engine.py - Pre-V3 trade decision interpretation layer.
import math

from config import (
    ENABLE_V3_DECISION_LAYER,
    V3_AVOID_EXTENSION_FROM_EMA50_PCT,
    V3_AVOID_MAX_STOP_DISTANCE_PCT,
    V3_ENTER_MAX_EXTENSION_FROM_EMA20_PCT,
    V3_ENTER_MAX_EXTENSION_FROM_EMA50_PCT,
    V3_ENTER_MAX_STOP_DISTANCE_PCT,
    V3_ENTER_MIN_RR,
    V3_ENTER_MIN_SCORE,
    V3_ENTER_MIN_VOLUME_RATIO,
    V3_WAIT_MIN_VOLUME_RATIO,
    V3_WATCHLIST_MIN_RR,
    V3_WATCHLIST_MIN_SCORE,
)

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


def _number(value: object) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _ratio(numerator: object, denominator: object) -> float | None:
    top = _number(numerator)
    bottom = _number(denominator)
    if top is None or bottom in (None, 0):
        return None
    return top / bottom


def _pass_reasons(signal: dict) -> list:
    reasons = signal.get("pass_reasons", [])
    return reasons if isinstance(reasons, list) else []


def _valid_trade_plan(plan: dict) -> tuple[bool, list[str], dict]:
    warnings: list[str] = []
    if not isinstance(plan, dict):
        plan = {}
    entry = _number(plan.get("entry"))
    stop = _number(plan.get("stop_loss"))
    expected_rr = _number(plan.get("expected_rr"))
    metrics = {
        "entry": entry,
        "stop": stop,
        "expected_rr": expected_rr,
        "stop_distance_pct": None,
    }
    if entry is None or stop is None or expected_rr is None:
        return False, ["trade plan is missing usable entry, stop, or R:R"], metrics

    if stop >= entry:
        warnings.append("stop is not below entry")
    if expected_rr < V3_WATCHLIST_MIN_RR:
        warnings.append("risk/reward is below V3 watchlist minimum")
    if entry and stop < entry:
        metrics["stop_distance_pct"] = (entry - stop) / entry
    return not warnings, warnings, metrics


def _market_is_valid(signal: dict, market_regime: dict | None) -> bool:
    if market_regime is not None:
        return bool(market_regime.get("is_valid"))
    summary = str(signal.get("market_regime", "")).lower()
    return "invalid" not in summary


def _volume_ratio(signal: dict) -> float | None:
    return _ratio(signal.get("volume"), signal.get("avg_volume") or signal.get("vol_sma20"))


def _extension_metrics(signal: dict) -> dict:
    close = _number(signal.get("close"))
    ema20 = _number(signal.get("ema20"))
    ema50 = _number(signal.get("ema50"))
    from_ema20 = ((close - ema20) / ema20) if close is not None and ema20 not in (None, 0) else None
    from_ema50 = ((close - ema50) / ema50) if close is not None and ema50 not in (None, 0) else None
    return {
        "from_ema20": from_ema20,
        "from_ema50": from_ema50,
        "severe": bool(from_ema50 is not None and from_ema50 > V3_AVOID_EXTENSION_FROM_EMA50_PCT),
        "mild": bool(
            (from_ema20 is not None and from_ema20 > V3_ENTER_MAX_EXTENSION_FROM_EMA20_PCT)
            or (from_ema50 is not None and from_ema50 > V3_ENTER_MAX_EXTENSION_FROM_EMA50_PCT)
        ),
        "available": from_ema20 is not None or from_ema50 is not None,
    }


def _relative_strength_confirmed(signal: dict) -> bool:
    category_scores = signal.get("category_scores") or {}
    relative_strength_score = (
        _number(category_scores.get("relative_strength"))
        if isinstance(category_scores, dict)
        else None
    )
    if relative_strength_score is not None and relative_strength_score > 0:
        return True
    if signal.get("relative_strength_confirmed") is True:
        return True
    reasons = " ".join(str(reason).lower() for reason in _pass_reasons(signal))
    return "outperformed spy" in reasons or "outperformed qqq" in reasons or "relative strength" in reasons


def _supporting_reasons(signal: dict, extra: list[str] | None = None) -> list[str]:
    reasons = list(_pass_reasons(signal)[:3])
    for reason in extra or []:
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons[:5]


def _risk_warning_summary(
    *,
    rr: float | None,
    stop_distance_pct: float | None,
    volume_ratio: float | None,
    extension: dict,
    relative_strength: bool,
) -> list[str]:
    warnings: list[str] = []
    if rr is not None and rr < V3_ENTER_MIN_RR:
        warnings.append(f"risk/reward is below entry threshold ({rr:.1f}R)")
    if stop_distance_pct is not None and stop_distance_pct > V3_ENTER_MAX_STOP_DISTANCE_PCT:
        warnings.append(f"stop distance is wide ({stop_distance_pct:.1%})")
    if volume_ratio is None:
        warnings.append("volume confirmation data unavailable")
    elif volume_ratio < V3_ENTER_MIN_VOLUME_RATIO:
        warnings.append(f"volume confirmation is light ({volume_ratio:.2f}x average)")
    if not extension["available"]:
        warnings.append("extension data unavailable")
    elif extension["mild"]:
        warnings.append("price is extended from key moving averages")
    if not relative_strength:
        warnings.append("relative strength is not confirmed by existing V2 fields")
    return warnings


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
    score = _number(signal.get("score")) or 0
    plan = signal.get("trade_plan") or {}
    valid_plan, risk_warnings, plan_metrics = _valid_trade_plan(plan)
    expected_rr = plan_metrics["expected_rr"]
    stop_distance_pct = plan_metrics["stop_distance_pct"]
    volume_ratio = _volume_ratio(signal)
    extension = _extension_metrics(signal)
    relative_strength = _relative_strength_confirmed(signal)
    actual_breakout = bool(signal.get("is_actual_breakout"))
    near_breakout = bool(signal.get("is_near_breakout"))
    market_valid = _market_is_valid(signal, market_regime)

    if grade not in {"A+", "A", "B"} or score < V3_WATCHLIST_MIN_SCORE:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Signal quality is below the V3 decision threshold.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=risk_warnings or ["grade or score is too weak"],
            next_action="Avoid this setup unless a new V2 signal forms.",
        )

    if not valid_plan:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Risk plan is not usable for a trade decision.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=risk_warnings,
            next_action="Wait for a valid entry and stop before considering risk.",
        )

    if expected_rr is not None and expected_rr < V3_WATCHLIST_MIN_RR:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Risk/reward is too weak for a production trade decision.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[f"risk/reward is below watchlist threshold ({expected_rr:.1f}R)"],
            next_action="Avoid this setup unless a new V2 signal forms with better reward versus risk.",
        )

    if stop_distance_pct is not None and stop_distance_pct > V3_AVOID_MAX_STOP_DISTANCE_PCT:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Stop distance is too wide for the V3 risk rules.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[f"stop distance is excessive ({stop_distance_pct:.1%})"],
            next_action="Avoid unless price tightens or a closer valid stop forms.",
        )

    if extension["severe"]:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Price is too extended for a fresh trade decision.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=["price is severely extended from the 50EMA"],
            next_action="Avoid chasing; wait for consolidation or a new V2 setup.",
        )

    if not actual_breakout and not near_breakout:
        return _result(
            DECISION_AVOID,
            "LOW",
            "Signal does not show an actual or near breakout state.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=["breakout state is not confirmed"],
            next_action="Avoid until V2 identifies a valid breakout or near-breakout setup.",
        )

    if grade == "B" and actual_breakout and (
        volume_ratio is None or volume_ratio < V3_WAIT_MIN_VOLUME_RATIO
    ):
        warning = "volume confirmation data unavailable" if volume_ratio is None else f"volume confirmation is weak ({volume_ratio:.2f}x average)"
        return _result(
            DECISION_AVOID,
            "LOW",
            "B-grade breakout is too weak for a V3 wait decision.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[warning],
            next_action="Avoid unless volume improves and a new V2-selected setup forms.",
        )

    if not market_valid:
        return _result(
            DECISION_WATCHLIST_ONLY,
            "MEDIUM",
            "Setup is promising, but market regime is not supportive.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=["market regime is not supportive"],
            next_action="Keep on watchlist until market regime improves.",
        )

    if near_breakout and not actual_breakout:
        return _result(
            DECISION_WAIT,
            "MEDIUM",
            "Setup is near the breakout trigger but has not confirmed.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[],
            next_action="Wait for a breakout above the pivot with acceptable volume.",
        )

    if grade == "B" and actual_breakout:
        return _result(
            DECISION_WAIT,
            "MEDIUM",
            "B-grade actual breakout is constructive but not strong enough to enter.",
            supporting_reasons=_supporting_reasons(signal, ["actual breakout confirmed"]),
            risk_warnings=_risk_warning_summary(
                rr=expected_rr,
                stop_distance_pct=stop_distance_pct,
                volume_ratio=volume_ratio,
                extension=extension,
                relative_strength=relative_strength,
            )[:3],
            next_action="Wait for an A-grade signal or stronger confirmation before considering entry.",
        )

    entry_warnings = _risk_warning_summary(
        rr=expected_rr,
        stop_distance_pct=stop_distance_pct,
        volume_ratio=volume_ratio,
        extension=extension,
        relative_strength=relative_strength,
    )
    if grade in {"A+", "A"} and actual_breakout and score >= V3_ENTER_MIN_SCORE and not entry_warnings:
        return _result(
            DECISION_ENTER,
            "HIGH",
            "High-quality V2 breakout with a usable risk plan.",
            supporting_reasons=_supporting_reasons(signal, ["volume and relative strength confirmed"]),
            risk_warnings=[],
            next_action="Consider entry using the V2 buy stop and defined stop loss.",
        )

    return _result(
        DECISION_WAIT,
        "MEDIUM",
        "Setup is constructive but not ready for an entry decision.",
        supporting_reasons=_supporting_reasons(signal),
        risk_warnings=entry_warnings[:3],
        next_action="Wait for stronger confirmation while keeping the V2 trade plan intact.",
    )
