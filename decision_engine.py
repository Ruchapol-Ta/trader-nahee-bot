# decision_engine.py - Pre-V3 trade decision interpretation layer.
import math

import config as runtime_config
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
    V3_MIN_TACTICAL_STOP_DISTANCE_PCT,
    V3_WAIT_MIN_VOLUME_RATIO,
    V3_WATCHLIST_MIN_RR,
    V3_WATCHLIST_MIN_SCORE,
)

DECISION_ENTER = "ENTER"
DECISION_WAIT = "WAIT"
DECISION_WATCHLIST_ONLY = "WATCHLIST_ONLY"
DECISION_AVOID = "AVOID"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

SIZING_MODE_DISABLED = "disabled"
SIZING_MODE_MOCK_CONFIG = "mock_config"
SIZING_MODE_INVALID_INPUT = "invalid_input"

TRADE_RISK_NO_TRADE = "NO_TRADE"
TRADE_RISK_TINY = "TINY"
TRADE_RISK_SMALL = "SMALL"
TRADE_RISK_NORMAL = "NORMAL"

# Calibration bands for V3 shadow decisions. ENTER stays tied to config; the
# wider bands only decide whether a V2-selected setup is worth waiting on.
ENTER_MAX_STOP_PCT = V3_ENTER_MAX_STOP_DISTANCE_PCT
WATCHLIST_MAX_STOP_PCT = 0.16
AVOID_EXTREME_STOP_PCT = 0.20
EXTENDED_WIDE_STOP_PCT = V3_AVOID_MAX_STOP_DISTANCE_PCT


def _result(
    decision: str,
    confidence: str,
    main_reason: str,
    supporting_reasons: list[str] | None = None,
    risk_warnings: list[str] | None = None,
    risk_flags: list[str] | None = None,
    next_action: str = "",
    action_label: str | None = None,
    wait_conditions: list[str] | None = None,
    invalidation: list[str] | str | None = None,
    sizing_mode: str = SIZING_MODE_DISABLED,
    trade_risk_mode: str | None = None,
    sizing_input: dict | None = None,
    decision_entry: float | None = None,
    decision_stop: float | None = None,
    decision_stop_source: str | None = None,
    decision_stop_distance_pct: float | None = None,
    risk_profile: str | None = None,
    enter_max_stop_pct: float | None = None,
    threshold_result: dict | None = None,
) -> dict:
    if trade_risk_mode is None:
        trade_risk_mode = TRADE_RISK_NORMAL if decision == DECISION_ENTER else TRADE_RISK_NO_TRADE
    if decision == DECISION_WAIT and not wait_conditions:
        wait_conditions = [next_action] if next_action else ["Wait for the V2 setup to confirm."]
    if invalidation is None:
        invalidation = []
    elif isinstance(invalidation, str):
        invalidation = [invalidation] if invalidation else []
    if decision == DECISION_AVOID and not invalidation:
        invalidation = [main_reason]
    return {
        "decision": decision,
        "confidence": confidence,
        "action_label": action_label or _action_label(decision),
        "main_reason": main_reason,
        "supporting_reasons": supporting_reasons or [],
        "risk_warnings": risk_warnings or [],
        "risk_flags": risk_flags or [],
        "wait_conditions": wait_conditions or [],
        "invalidation": invalidation,
        "next_action": next_action,
        "sizing_mode": sizing_mode,
        "trade_risk_mode": trade_risk_mode,
        "sizing_input": sizing_input or {},
        "decision_entry": decision_entry,
        "decision_stop": decision_stop,
        "decision_stop_source": decision_stop_source,
        "decision_stop_distance_pct": decision_stop_distance_pct,
        "risk_profile": risk_profile,
        "enter_max_stop_pct": enter_max_stop_pct,
        "threshold_result": threshold_result or {},
    }


def _action_label(decision: str) -> str:
    labels = {
        DECISION_ENTER: "Enter only on planned trigger",
        DECISION_WAIT: "Wait for confirmation",
        DECISION_WATCHLIST_ONLY: "Keep on watchlist",
        DECISION_AVOID: "Avoid setup",
    }
    return labels.get(decision, str(decision))


def _number(value: object) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _active_risk_policy() -> dict:
    profiles = getattr(runtime_config, "V3_RISK_PROFILES", {})
    if not isinstance(profiles, dict):
        profiles = {}
    profile = str(getattr(runtime_config, "V3_RISK_PROFILE", "conservative") or "conservative")
    if profile not in profiles:
        profile = "conservative"
    configured = profiles.get(profile) or profiles.get("conservative") or {
        "enter_max_stop_pct": V3_ENTER_MAX_STOP_DISTANCE_PCT
    }
    return {
        "risk_profile": profile,
        "enter_max_stop_pct": _number(configured.get("enter_max_stop_pct")) or V3_ENTER_MAX_STOP_DISTANCE_PCT,
    }


def _threshold_result(
    *,
    stop_distance_pct: float | None,
    enter_max_stop_pct: float,
    decision_stop_source: str | None,
    volume_ratio: float | None,
    extension: dict,
) -> dict:
    above_conservative = stop_distance_pct is not None and stop_distance_pct > V3_ENTER_MAX_STOP_DISTANCE_PCT
    tactical = decision_stop_source == "tactical"
    return {
        "within_enter_stop": (
            stop_distance_pct is not None and stop_distance_pct <= enter_max_stop_pct
        ),
        "enter_max_stop_pct": enter_max_stop_pct,
        "within_conservative_enter_limit": (
            stop_distance_pct is not None and stop_distance_pct <= V3_ENTER_MAX_STOP_DISTANCE_PCT
        ),
        "within_balanced_tactical_enter_limit": (
            tactical and stop_distance_pct is not None and V3_ENTER_MAX_STOP_DISTANCE_PCT < stop_distance_pct <= 0.10
        ),
        "within_aggressive_tactical_enter_limit": (
            tactical and stop_distance_pct is not None and 0.10 < stop_distance_pct <= 0.12
        ),
        "blocked_structural_stop_above_conservative_limit": bool(
            above_conservative and not tactical
        ),
        "blocked_no_volume_confirmation": bool(
            volume_ratio is None or volume_ratio < V3_ENTER_MIN_VOLUME_RATIO
        ),
        "blocked_extended_entry": bool(extension.get("mild") or extension.get("severe")),
    }


def _enter_trade_risk_mode(risk_profile: str, stop_distance_pct: float | None) -> str:
    if stop_distance_pct is None:
        return TRADE_RISK_NO_TRADE
    if risk_profile == "aggressive" and stop_distance_pct > 0.10:
        return TRADE_RISK_TINY
    if risk_profile in {"balanced", "aggressive"} and stop_distance_pct > 0.08:
        return TRADE_RISK_SMALL
    return TRADE_RISK_NORMAL


def _profile_enter_guard_warning(
    *,
    stop_distance_pct: float | None,
    decision_stop_source: str | None,
) -> str | None:
    if (
        stop_distance_pct is not None
        and stop_distance_pct > V3_ENTER_MAX_STOP_DISTANCE_PCT
        and decision_stop_source != "tactical"
    ):
        return "expanded risk profiles require a tactical stop above the conservative limit"
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


def _valid_trade_plan(plan: dict) -> tuple[bool, list[str], list[str], dict]:
    warnings: list[str] = []
    flags: list[str] = []
    if not isinstance(plan, dict):
        plan = {}
    entry = _number(plan.get("entry"))
    buy_stop = _number(plan.get("buy_stop"))
    stop = _number(plan.get("stop_loss"))
    structural_stop = _number(plan.get("structural_stop"))
    if structural_stop is None:
        structural_stop = stop
    tactical_stop = _number(plan.get("tactical_stop"))
    expected_rr = _number(plan.get("expected_rr"))
    decision_entry = buy_stop if buy_stop is not None and buy_stop > 0 else entry
    decision_stop = stop
    decision_stop_source = "structural" if stop is not None else None
    metrics = {
        "entry": entry,
        "stop": stop,
        "decision_entry": decision_entry,
        "decision_stop": decision_stop,
        "decision_stop_source": decision_stop_source,
        "expected_rr": expected_rr,
        "stop_distance_pct": None,
        "decision_stop_distance_pct": None,
        "structural_stop": structural_stop,
        "structural_stop_distance_pct": None,
        "tactical_stop": tactical_stop,
        "tactical_stop_distance_pct": None,
    }
    if entry is None:
        warnings.append("trade plan is missing usable entry")
        flags.append("MISSING_ENTRY")
    if stop is None:
        warnings.append("trade plan is missing usable stop")
        flags.append("MISSING_STOP")
    if expected_rr is None:
        warnings.append("trade plan is missing usable R:R")
        flags.append("MISSING_TARGETS")
    if warnings:
        return False, warnings, flags, metrics

    if stop >= entry:
        warnings.append("stop is not below entry")
        flags.append("INVALID_STOP")
    if expected_rr < V3_WATCHLIST_MIN_RR:
        warnings.append("risk/reward is below V3 watchlist minimum")
        flags.append("POOR_RISK_REWARD")
    if structural_stop is not None and decision_entry and structural_stop < decision_entry:
        metrics["structural_stop_distance_pct"] = (decision_entry - structural_stop) / decision_entry
    if (
        tactical_stop is not None
        and decision_entry is not None
        and tactical_stop < decision_entry
        and (structural_stop is None or tactical_stop > structural_stop)
    ):
        tactical_distance_pct = (decision_entry - tactical_stop) / decision_entry
        metrics["tactical_stop_distance_pct"] = tactical_distance_pct
        if tactical_distance_pct >= V3_MIN_TACTICAL_STOP_DISTANCE_PCT:
            decision_stop = tactical_stop
            decision_stop_source = "tactical"
    if decision_entry and decision_stop is not None and decision_stop < decision_entry:
        metrics["decision_stop"] = decision_stop
        metrics["decision_stop_source"] = decision_stop_source
        metrics["decision_stop_distance_pct"] = (decision_entry - decision_stop) / decision_entry
        metrics["stop_distance_pct"] = metrics["decision_stop_distance_pct"]
    return not warnings, warnings, flags, metrics


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


def _sizing_mode(plan_metrics: dict) -> str:
    entry = plan_metrics.get("decision_entry")
    stop = plan_metrics.get("decision_stop")
    if entry is None or stop is None:
        return SIZING_MODE_INVALID_INPUT
    if stop >= entry:
        return SIZING_MODE_INVALID_INPUT
    return SIZING_MODE_MOCK_CONFIG


def _sizing_input(plan_metrics: dict) -> dict:
    data = {
        "entry": plan_metrics.get("decision_entry"),
        "stop": plan_metrics.get("decision_stop"),
        "decision_entry": plan_metrics.get("decision_entry"),
        "decision_stop": plan_metrics.get("decision_stop"),
    }
    return {key: value for key, value in data.items() if value is not None}


def _context_risk_flags(
    *,
    signal: dict,
    rr: float | None,
    stop_distance_pct: float | None,
    volume_ratio: float | None,
    extension: dict,
    relative_strength: bool,
    market_valid: bool,
    structural_stop_distance_pct: float | None,
    decision_stop_source: str | None,
    enter_max_stop_pct: float,
) -> list[str]:
    flags: list[str] = []
    if rr is None:
        flags.append("MISSING_TARGETS")
    elif rr < V3_ENTER_MIN_RR:
        flags.append("POOR_RISK_REWARD")
    if stop_distance_pct is not None and stop_distance_pct > enter_max_stop_pct:
        flags.append("WIDE_STOP")
    if (
        decision_stop_source == "tactical"
        and structural_stop_distance_pct is not None
        and structural_stop_distance_pct > enter_max_stop_pct
    ):
        flags.append("STRUCTURAL_STOP_WIDE")
    if volume_ratio is None or volume_ratio < V3_ENTER_MIN_VOLUME_RATIO:
        flags.append("NO_VOLUME_CONFIRMATION")
    if extension.get("mild") or extension.get("severe"):
        flags.append("EXTENDED_ENTRY")
    if not relative_strength:
        flags.append("WEAK_RELATIVE_STRENGTH")
    if not market_valid:
        flags.append("UNFAVORABLE_MARKET_REGIME")
    if not _pass_reasons(signal):
        flags.append("GENERIC_SETUP_EVIDENCE")
    return list(dict.fromkeys(flags))


def _risk_warning_summary(
    *,
    rr: float | None,
    stop_distance_pct: float | None,
    volume_ratio: float | None,
    extension: dict,
    relative_strength: bool,
    enter_max_stop_pct: float,
) -> list[str]:
    warnings: list[str] = []
    if rr is not None and rr < V3_ENTER_MIN_RR:
        warnings.append(f"risk/reward is below entry threshold ({rr:.1f}R)")
    if stop_distance_pct is not None and stop_distance_pct > enter_max_stop_pct:
        warnings.append(f"stop distance is wide ({stop_distance_pct:.1%})")
    if volume_ratio is None:
        warnings.append("volume confirmation data unavailable")
    elif volume_ratio < V3_ENTER_MIN_VOLUME_RATIO:
        warnings.append(f"volume confirmation below threshold ({volume_ratio:.2f}x average)")
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
    valid_plan, risk_warnings, plan_flags, plan_metrics = _valid_trade_plan(plan)
    expected_rr = plan_metrics["expected_rr"]
    stop_distance_pct = plan_metrics["stop_distance_pct"]
    structural_stop_distance_pct = plan_metrics["structural_stop_distance_pct"]
    decision_stop_source = plan_metrics["decision_stop_source"]
    decision_entry = plan_metrics["decision_entry"]
    decision_stop = plan_metrics["decision_stop"]
    decision_stop_distance_pct = plan_metrics["decision_stop_distance_pct"]
    volume_ratio = _volume_ratio(signal)
    extension = _extension_metrics(signal)
    relative_strength = _relative_strength_confirmed(signal)
    actual_breakout = bool(signal.get("is_actual_breakout"))
    near_breakout = bool(signal.get("is_near_breakout"))
    market_valid = _market_is_valid(signal, market_regime)
    sizing_mode = _sizing_mode(plan_metrics)
    sizing_input = _sizing_input(plan_metrics)
    risk_policy = _active_risk_policy()
    risk_profile = risk_policy["risk_profile"]
    enter_max_stop_pct = risk_policy["enter_max_stop_pct"]
    threshold_result = _threshold_result(
        stop_distance_pct=stop_distance_pct,
        enter_max_stop_pct=enter_max_stop_pct,
        decision_stop_source=decision_stop_source,
        volume_ratio=volume_ratio,
        extension=extension,
    )
    context_flags = _context_risk_flags(
        signal=signal,
        rr=expected_rr,
        stop_distance_pct=stop_distance_pct,
        volume_ratio=volume_ratio,
        extension=extension,
        relative_strength=relative_strength,
        market_valid=market_valid,
        structural_stop_distance_pct=structural_stop_distance_pct,
        decision_stop_source=decision_stop_source,
        enter_max_stop_pct=enter_max_stop_pct,
    )
    base_flags = list(dict.fromkeys([*plan_flags, *context_flags]))
    result_plan_fields = {
        "decision_entry": decision_entry,
        "decision_stop": decision_stop,
        "decision_stop_source": decision_stop_source,
        "decision_stop_distance_pct": decision_stop_distance_pct,
        "risk_profile": risk_profile,
        "enter_max_stop_pct": enter_max_stop_pct,
        "threshold_result": threshold_result,
    }

    if grade not in {"A+", "A", "B"} or score < V3_WATCHLIST_MIN_SCORE:
        return _result(
            DECISION_AVOID,
            CONFIDENCE_LOW,
            "Signal quality is below the V3 decision threshold.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=risk_warnings or ["grade or score is too weak"],
            risk_flags=base_flags or ["GENERIC_SETUP_EVIDENCE"],
            next_action="Avoid this setup unless a new V2 signal forms.",
            invalidation=["Current V2 grade or score is below the V3 threshold."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if not valid_plan:
        return _result(
            DECISION_AVOID,
            CONFIDENCE_LOW,
            "Risk plan is not usable for a trade decision.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=risk_warnings,
            risk_flags=base_flags,
            next_action="Wait for a valid entry and stop before considering risk.",
            invalidation=["Do not enter without a valid entry, stop, and reward/risk plan."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if expected_rr is not None and expected_rr < V3_WATCHLIST_MIN_RR:
        return _result(
            DECISION_AVOID,
            CONFIDENCE_LOW,
            "Risk/reward is too weak for a production trade decision.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[f"risk/reward is below watchlist threshold ({expected_rr:.1f}R)"],
            risk_flags=base_flags,
            next_action="Avoid this setup unless a new V2 signal forms with better reward versus risk.",
            invalidation=["Reward/risk is below the V3 watchlist threshold."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if extension["severe"]:
        return _result(
            DECISION_AVOID,
            CONFIDENCE_LOW,
            "Price is too extended for a fresh trade decision.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=["price is severely extended from the 50EMA"],
            risk_flags=base_flags,
            next_action="Avoid chasing; wait for consolidation or a new V2 setup.",
            invalidation=["Price is severely extended from the 50EMA."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if stop_distance_pct is not None and stop_distance_pct > AVOID_EXTREME_STOP_PCT:
        return _result(
            DECISION_AVOID,
            CONFIDENCE_LOW,
            "Stop distance is too wide for the V3 risk rules.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[f"stop distance is excessive ({stop_distance_pct:.1%})"],
            risk_flags=base_flags,
            next_action="Avoid unless price tightens or a closer valid stop forms.",
            invalidation=["The current stop distance exceeds V3 avoid limits."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if (
        stop_distance_pct is not None
        and stop_distance_pct > EXTENDED_WIDE_STOP_PCT
        and extension["mild"]
    ):
        return _result(
            DECISION_AVOID,
            CONFIDENCE_LOW,
            "Setup is too extended while the stop distance is still wide.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[
                f"stop distance is wide ({stop_distance_pct:.1%})",
                "price is extended from key moving averages",
            ],
            risk_flags=base_flags,
            next_action="Avoid unless price consolidates and a tighter stop forms.",
            invalidation=["Extension and stop distance are both outside V3 tracking limits."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if not actual_breakout and not near_breakout:
        return _result(
            DECISION_AVOID,
            CONFIDENCE_LOW,
            "Signal does not show an actual or near breakout state.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=["breakout state is not confirmed"],
            risk_flags=base_flags or ["GENERIC_SETUP_EVIDENCE"],
            next_action="Avoid until V2 identifies a valid breakout or near-breakout setup.",
            invalidation=["No actual or near-breakout trigger is present."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if (
        grade in {"A+", "A"}
        and actual_breakout
        and score >= V3_ENTER_MIN_SCORE
        and expected_rr is not None
        and expected_rr >= V3_ENTER_MIN_RR
        and stop_distance_pct is not None
        and enter_max_stop_pct < stop_distance_pct <= WATCHLIST_MAX_STOP_PCT
    ):
        wait_conditions = ["Wait for a tighter stop below the V3 ENTER risk limit."]
        if volume_ratio is None or volume_ratio < V3_ENTER_MIN_VOLUME_RATIO:
            wait_conditions.append("Wait for acceptable volume confirmation.")
        return _result(
            DECISION_WAIT,
            CONFIDENCE_MEDIUM,
            "Setup quality is strong, but current stop distance is too wide for entry.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=_risk_warning_summary(
                rr=expected_rr,
                stop_distance_pct=stop_distance_pct,
                volume_ratio=volume_ratio,
                extension=extension,
                relative_strength=relative_strength,
                enter_max_stop_pct=enter_max_stop_pct,
            )[:3],
            risk_flags=base_flags,
            next_action="Wait for price to tighten or a closer valid stop to form.",
            wait_conditions=wait_conditions,
            invalidation=["Avoid if stop distance remains above V3 tracking limits."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if (
        grade == "B"
        and decision_stop_source == "tactical"
        and score >= V3_WATCHLIST_MIN_SCORE
        and expected_rr is not None
        and expected_rr >= V3_WATCHLIST_MIN_RR
        and stop_distance_pct is not None
        and stop_distance_pct <= enter_max_stop_pct
    ):
        return _result(
            DECISION_WATCHLIST_ONLY,
            CONFIDENCE_MEDIUM,
            "Setup is promising but not actionable yet.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=_risk_warning_summary(
                rr=expected_rr,
                stop_distance_pct=stop_distance_pct,
                volume_ratio=volume_ratio,
                extension=extension,
                relative_strength=relative_strength,
                enter_max_stop_pct=enter_max_stop_pct,
            )[:3],
            risk_flags=base_flags,
            next_action="Keep on watchlist until the setup confirms a cleaner trigger.",
            invalidation=["Avoid entry until the setup offers a cleaner trigger and tighter risk plan."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if (
        grade == "B"
        and score >= V3_WATCHLIST_MIN_SCORE
        and expected_rr is not None
        and expected_rr >= V3_WATCHLIST_MIN_RR
        and stop_distance_pct is not None
        and enter_max_stop_pct < stop_distance_pct <= WATCHLIST_MAX_STOP_PCT
    ):
        return _result(
            DECISION_WATCHLIST_ONLY,
            CONFIDENCE_MEDIUM,
            "Setup is promising but not actionable yet.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=_risk_warning_summary(
                rr=expected_rr,
                stop_distance_pct=stop_distance_pct,
                volume_ratio=volume_ratio,
                extension=extension,
                relative_strength=relative_strength,
                enter_max_stop_pct=enter_max_stop_pct,
            )[:3],
            risk_flags=base_flags,
            next_action="Keep on watchlist until the setup confirms a cleaner trigger.",
            invalidation=["Avoid entry until the setup offers a cleaner trigger and tighter risk plan."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if grade == "B" and actual_breakout and (
        volume_ratio is None or volume_ratio < V3_WAIT_MIN_VOLUME_RATIO
    ):
        warning = "volume confirmation data unavailable" if volume_ratio is None else f"volume confirmation below threshold ({volume_ratio:.2f}x average)"
        return _result(
            DECISION_WATCHLIST_ONLY,
            CONFIDENCE_MEDIUM,
            "Setup is promising but not actionable yet.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[warning],
            risk_flags=base_flags,
            next_action="Keep on watchlist until the setup confirms a cleaner trigger.",
            invalidation=["Avoid entry until volume confirms the breakout."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if not market_valid:
        return _result(
            DECISION_WATCHLIST_ONLY,
            CONFIDENCE_MEDIUM,
            "Setup is promising, but market regime is not supportive.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=["market regime is not supportive"],
            risk_flags=base_flags,
            next_action="Keep on watchlist until the setup confirms a cleaner trigger.",
            invalidation=["Avoid entries while the market regime remains unsupportive."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if near_breakout and not actual_breakout:
        return _result(
            DECISION_WAIT,
            CONFIDENCE_MEDIUM,
            "Setup is near the breakout trigger but has not confirmed.",
            supporting_reasons=_supporting_reasons(signal),
            risk_warnings=[],
            risk_flags=base_flags,
            next_action="Wait for a breakout above the pivot with acceptable volume.",
            wait_conditions=["Breakout above the pivot.", "Acceptable volume confirmation."],
            invalidation=["Avoid if the setup loses the V2 base or stop structure."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    if grade == "B" and actual_breakout:
        return _result(
            DECISION_WAIT,
            CONFIDENCE_MEDIUM,
            "B-grade actual breakout is constructive but not strong enough to enter.",
            supporting_reasons=_supporting_reasons(signal, ["actual breakout confirmed"]),
            risk_warnings=_risk_warning_summary(
                rr=expected_rr,
                stop_distance_pct=stop_distance_pct,
            volume_ratio=volume_ratio,
            extension=extension,
            relative_strength=relative_strength,
            enter_max_stop_pct=enter_max_stop_pct,
        )[:3],
            risk_flags=base_flags,
            next_action="Wait for an A-grade signal or stronger confirmation before considering entry.",
            wait_conditions=["A-grade V2 signal.", "Stronger confirmation before entry."],
            invalidation=["Avoid if the breakout fails or risk/reward deteriorates."],
            sizing_mode=sizing_mode,
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    entry_warnings = _risk_warning_summary(
        rr=expected_rr,
        stop_distance_pct=stop_distance_pct,
        volume_ratio=volume_ratio,
        extension=extension,
        relative_strength=relative_strength,
        enter_max_stop_pct=enter_max_stop_pct,
    )
    profile_guard_warning = _profile_enter_guard_warning(
        stop_distance_pct=stop_distance_pct,
        decision_stop_source=decision_stop_source,
    )
    if profile_guard_warning:
        entry_warnings.append(profile_guard_warning)
    if grade in {"A+", "A"} and actual_breakout and score >= V3_ENTER_MIN_SCORE and not entry_warnings:
        return _result(
            DECISION_ENTER,
            CONFIDENCE_HIGH,
            "High-quality V2 breakout with a usable risk plan.",
            supporting_reasons=_supporting_reasons(signal, ["volume and relative strength confirmed"]),
            risk_warnings=[],
            risk_flags=base_flags,
            next_action="Enter only if the planned buy stop triggers and the trading stop remains valid.",
            invalidation=["Exit or avoid if price violates the trading stop."],
            sizing_mode=sizing_mode,
            trade_risk_mode=_enter_trade_risk_mode(risk_profile, stop_distance_pct),
            sizing_input=sizing_input,
            **result_plan_fields,
        )

    return _result(
        DECISION_WAIT,
        CONFIDENCE_MEDIUM,
        "Setup is constructive but not ready for an entry decision.",
        supporting_reasons=_supporting_reasons(signal),
        risk_warnings=entry_warnings[:3],
        risk_flags=base_flags,
        next_action="Wait for stronger confirmation while keeping the V2 trade plan intact.",
        wait_conditions=["Stronger confirmation from V2 setup evidence.", "Risk warnings resolved."],
        invalidation=["Avoid if V2 setup quality weakens or risk levels deteriorate."],
        sizing_mode=sizing_mode,
        sizing_input=sizing_input,
        **result_plan_fields,
    )
