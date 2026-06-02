# journal.py - append-only JSONL storage for V2/V3 signal outputs.
import json
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from config import JOURNAL_PATH

logger = logging.getLogger(__name__)
SCHEMA_VERSION = "v3_shadow_1"


def _json_safe(value: Any) -> Any:
    """Convert nested values into JSON-serializable data."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        pass

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_field(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def build_signal_record(
    signal: dict,
    delivery_type: str,
    run_id: str | None = None,
    telegram_message_text: str | None = None,
) -> dict:
    """Build one normalized journal record from a selected V2 signal."""
    if not isinstance(signal, dict):
        raise ValueError("signal must be a dict")
    plan = signal.get("trade_plan") or {}
    decision = signal.get("v3_decision") or {}
    position_size = signal.get("v3_position_size") or {}
    if not isinstance(plan, dict):
        raise ValueError("trade_plan must be a dict when present")
    if not isinstance(decision, dict):
        raise ValueError("v3_decision must be a dict when present")
    if not isinstance(position_size, dict):
        raise ValueError("v3_position_size must be a dict when present")
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": _timestamp(),
        "run_id": run_id,
        "delivery_type": delivery_type,
        "alert_category": signal.get("alert_category"),
        "ticker": signal.get("ticker"),
        "setup_type": signal.get("setup_type"),
        "market_regime": signal.get("market_regime"),
        "risk_mode": position_size.get("risk_mode"),
        "decision": decision.get("decision"),
        "confidence": decision.get("confidence"),
        "action_label": decision.get("action_label"),
        "grade": signal.get("grade"),
        "score": signal.get("score"),
        "entry": plan.get("entry"),
        "buy_stop": plan.get("buy_stop"),
        "stop": plan.get("stop_loss"),
        "structural_stop": plan.get("structural_stop"),
        "structural_stop_source": plan.get("structural_stop_source"),
        "structural_stop_distance_pct": plan.get("structural_stop_distance_pct"),
        "tactical_stop": plan.get("tactical_stop"),
        "tactical_stop_source": plan.get("tactical_stop_source"),
        "tactical_stop_distance_pct": plan.get("tactical_stop_distance_pct"),
        "targets": [
            target for target in [plan.get("target_1"), plan.get("target_2")]
            if target is not None
        ],
        "risk_reward": plan.get("expected_rr"),
        "main_reason": decision.get("main_reason"),
        "supporting_reasons": decision.get("supporting_reasons", []),
        "risk_warnings": decision.get("risk_warnings", []),
        "risk_flags": decision.get("risk_flags", []),
        "wait_conditions": decision.get("wait_conditions", []),
        "invalidation": _list_field(decision.get("invalidation")),
        "next_action": decision.get("next_action"),
        "sizing_mode": decision.get("sizing_mode"),
        "trade_risk_mode": decision.get("trade_risk_mode"),
        "sizing_input": decision.get("sizing_input", {}),
        "decision_entry": decision.get("decision_entry"),
        "decision_stop": decision.get("decision_stop"),
        "decision_stop_source": decision.get("decision_stop_source"),
        "decision_stop_distance_pct": decision.get("decision_stop_distance_pct"),
        "risk_profile": decision.get("risk_profile"),
        "enter_max_stop_pct": decision.get("enter_max_stop_pct"),
        "threshold_result": decision.get("threshold_result"),
        "sizing_result": _json_safe(position_size) if position_size else None,
        "telegram_message_text": telegram_message_text,
    }


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _stop_distance_pct(signal: dict) -> float | None:
    plan = signal.get("trade_plan") or {}
    if not isinstance(plan, dict):
        return None
    entry = _number(plan.get("entry"))
    stop = _number(plan.get("stop_loss"))
    if entry is None or stop is None or entry <= 0 or stop >= entry:
        return None
    return round(((entry - stop) / entry) * 100, 2)


def _stored_distance_pct(plan: dict, key: str) -> float | None:
    distance = _number(plan.get(key))
    if distance is None:
        return None
    return round(distance * 100, 2)


def _plan_stop_distance_pct(
    signal: dict,
    *,
    stop_key: str,
    distance_key: str,
    fallback_stop_key: str | None = None,
) -> float | None:
    plan = signal.get("trade_plan") or {}
    if not isinstance(plan, dict):
        return None

    stored = _stored_distance_pct(plan, distance_key)
    if stored is not None:
        return stored

    entry = _number(plan.get("entry"))
    stop = _number(plan.get(stop_key))
    if stop is None and fallback_stop_key is not None:
        stop = _number(plan.get(fallback_stop_key))
    if entry is None or stop is None or entry <= 0 or stop >= entry:
        return None
    return round(((entry - stop) / entry) * 100, 2)


def _distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min_pct": None, "median_pct": None, "max_pct": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min_pct": round(ordered[0], 2),
        "median_pct": round(float(median(ordered)), 2),
        "max_pct": round(ordered[-1], 2),
    }


def _distance_distribution(signals: list[dict], distance_fn) -> dict:
    overall: list[float] = []
    by_decision: dict[str, list[float]] = defaultdict(list)
    by_grade: dict[str, list[float]] = defaultdict(list)
    for signal in signals:
        distance = distance_fn(signal)
        if distance is None:
            continue
        overall.append(distance)
        decision = (signal.get("v3_decision") or {}).get("decision")
        grade = signal.get("grade")
        if decision:
            by_decision[str(decision)].append(distance)
        if grade:
            by_grade[str(grade)].append(distance)
    return {
        "overall": _distribution(overall),
        "by_decision": {
            key: _distribution(values)
            for key, values in sorted(by_decision.items())
        },
        "by_grade": {
            key: _distribution(values)
            for key, values in sorted(by_grade.items())
        },
    }


def _stop_distance_distribution(signals: list[dict]) -> dict:
    return _distance_distribution(signals, _stop_distance_pct)


def _structural_stop_distance_distribution(signals: list[dict]) -> dict:
    return _distance_distribution(
        signals,
        lambda signal: _plan_stop_distance_pct(
            signal,
            stop_key="structural_stop",
            distance_key="structural_stop_distance_pct",
            fallback_stop_key="stop_loss",
        ),
    )


def _tactical_stop_distance_distribution(signals: list[dict]) -> dict:
    return _distance_distribution(
        signals,
        lambda signal: _plan_stop_distance_pct(
            signal,
            stop_key="tactical_stop",
            distance_key="tactical_stop_distance_pct",
        ),
    )


def _data_freshness(
    signals: list[dict],
    market_regime: dict,
    cache_note: str | None,
) -> dict:
    market_data = market_regime.get("market_data") if isinstance(market_regime, dict) else {}
    market = {}
    if isinstance(market_data, dict):
        for symbol, data in market_data.items():
            if isinstance(data, dict) and data.get("latest_bar_date") is not None:
                market[str(symbol)] = _json_safe(data.get("latest_bar_date"))
    selected = {
        str(signal.get("ticker")): _json_safe(signal.get("latest_bar_date"))
        for signal in signals
        if signal.get("ticker") and signal.get("latest_bar_date") is not None
    }
    return {
        "market": market,
        "selected_tickers": selected,
        "cache_note": cache_note or "unknown",
    }


def build_run_summary_record(
    *,
    run_id: str,
    trade_signals: list[dict],
    watchlist: list[dict],
    market_regime: dict,
    stats: dict,
    cache_note: str | None = None,
) -> dict:
    """Build one audit summary record for a V3 shadow run."""
    selected = [*(trade_signals or []), *(watchlist or [])]
    decision_counts = Counter()
    risk_flag_counts = Counter()
    error_count = 0
    for signal in selected:
        decision = signal.get("v3_decision") or {}
        if isinstance(decision, dict) and decision.get("decision"):
            decision_counts[str(decision["decision"])] += 1
            for flag in decision.get("risk_flags") or []:
                risk_flag_counts[str(flag)] += 1
        if signal.get("v3_error"):
            error_count += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "run_summary",
        "timestamp": _timestamp(),
        "run_id": run_id,
        "market_regime": market_regime.get("summary") if isinstance(market_regime, dict) else None,
        "v2_a_alert_count": len(trade_signals or []),
        "v2_b_watchlist_count": len(watchlist or []),
        "final_selected_count": len(selected),
        "v3_decision_counts": dict(decision_counts),
        "risk_flag_counts": dict(risk_flag_counts),
        "v3_error_count": error_count,
        "data_freshness": _data_freshness(selected, market_regime or {}, cache_note),
        "stop_distance_distribution": _stop_distance_distribution(selected),
        "structural_stop_distance_distribution": _structural_stop_distance_distribution(selected),
        "tactical_stop_distance_distribution": _tactical_stop_distance_distribution(selected),
        "stats": _json_safe(stats or {}),
    }


def append_jsonl_record(record: dict, path: str | Path = JOURNAL_PATH) -> bool:
    """Append one record to a JSONL file, returning False on write failure."""
    try:
        journal_path = Path(path)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with journal_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(_json_safe(record), allow_nan=False, sort_keys=True) + "\n")
        return True
    except Exception as e:
        logger.error(f"[Journal] Failed to write signal record: {e}", exc_info=True)
        return False


def _journal_one(signal: dict, delivery_type: str, path: str | Path, run_id: str | None) -> bool:
    """Build and write one journal record without raising into the scan."""
    try:
        record = build_signal_record(signal, delivery_type, run_id)
    except Exception as e:
        logger.error(f"[Journal] Failed to build signal record: {e}", exc_info=True)
        return False
    return append_jsonl_record(record, path)


def journal_run_summary(
    summary_record: dict,
    path: str | Path = JOURNAL_PATH,
) -> bool:
    """Append a run-level summary record without raising into the scan."""
    try:
        return append_jsonl_record(summary_record, path)
    except Exception as e:
        logger.error(f"[Journal] Failed to write run summary: {e}", exc_info=True)
        return False


def journal_signals(
    trade_signals: list[dict],
    watchlist: list[dict],
    path: str | Path = JOURNAL_PATH,
    run_id: str | None = None,
) -> int:
    """Journal all V2-selected trade alerts and watchlist items."""
    written = 0
    for signal in trade_signals:
        if _journal_one(signal, "trade_alert", path, run_id):
            written += 1
    for signal in watchlist:
        if _journal_one(signal, "watchlist", path, run_id):
            written += 1
    return written
