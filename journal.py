# journal.py - append-only JSONL storage for V2/V3 signal outputs.
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import JOURNAL_PATH

logger = logging.getLogger(__name__)


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
        "timestamp": _timestamp(),
        "run_id": run_id,
        "delivery_type": delivery_type,
        "ticker": signal.get("ticker"),
        "setup_type": signal.get("setup_type"),
        "market_regime": signal.get("market_regime"),
        "risk_mode": position_size.get("risk_mode"),
        "decision": decision.get("decision"),
        "confidence": decision.get("confidence"),
        "grade": signal.get("grade"),
        "score": signal.get("score"),
        "entry": plan.get("entry"),
        "buy_stop": plan.get("buy_stop"),
        "stop": plan.get("stop_loss"),
        "targets": [
            target for target in [plan.get("target_1"), plan.get("target_2")]
            if target is not None
        ],
        "risk_reward": plan.get("expected_rr"),
        "main_reason": decision.get("main_reason"),
        "supporting_reasons": decision.get("supporting_reasons", []),
        "risk_warnings": decision.get("risk_warnings", []),
        "next_action": decision.get("next_action"),
        "telegram_message_text": telegram_message_text,
        "raw_signal": _json_safe(signal),
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
