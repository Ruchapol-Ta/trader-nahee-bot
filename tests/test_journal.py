import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from journal import build_signal_record, journal_signals


def _test_path(name: str) -> Path:
    root = Path(".cache") / "pre_v3_tests" / f"{name}_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _signal(**overrides):
    data = {
        "ticker": "AAPL",
        "setup_type": "VCP Breakout",
        "market_regime": "Bullish market regime",
        "grade": "A",
        "score": 82,
        "trade_plan": {
            "entry": 100.0,
            "buy_stop": 101.1,
            "stop_loss": 94.0,
            "target_1": 115.0,
            "target_2": 124.0,
            "expected_rr": 2.5,
        },
        "v3_decision": {
            "decision": "ENTER",
            "confidence": "HIGH",
            "main_reason": "High-quality breakout",
            "supporting_reasons": ["A-grade signal"],
            "risk_warnings": [],
            "next_action": "Use buy stop",
        },
    }
    data.update(overrides)
    return data


def test_build_signal_record_includes_delivery_type_and_v2_v3_fields():
    record = build_signal_record(_signal(), delivery_type="trade_alert", run_id="run-1")

    assert record["run_id"] == "run-1"
    assert record["delivery_type"] == "trade_alert"
    assert record["ticker"] == "AAPL"
    assert record["decision"] == "ENTER"
    assert record["confidence"] == "HIGH"
    assert record["entry"] == 100.0
    assert record["stop"] == 94.0
    assert record["risk_reward"] == 2.5
    assert record["raw_signal"]["ticker"] == "AAPL"


def test_journal_signals_writes_trade_alerts_and_watchlist_jsonl():
    root = _test_path("writes")
    try:
        journal_path = root / "nested" / "signal_journal.jsonl"
        written = journal_signals(
            trade_signals=[_signal(ticker="AAPL")],
            watchlist=[_signal(ticker="MSFT", grade="B", score=69)],
            path=journal_path,
            run_id="run-2",
        )

        assert written == 2
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        assert [record["ticker"] for record in records] == ["AAPL", "MSFT"]
        assert [record["delivery_type"] for record in records] == ["trade_alert", "watchlist"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_journal_converts_unserializable_values_without_crashing():
    root = _test_path("safe")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal(raw_object={1, 2, 3})

        written = journal_signals([signal], [], path=journal_path, run_id="run-3")

        assert written == 1
        record = json.loads(journal_path.read_text(encoding="utf-8"))
        assert "raw_signal" in record
        assert "raw_object" in record["raw_signal"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_journal_write_failure_returns_zero_without_crashing():
    root = _test_path("failure")
    try:
        directory_path = root / "as_directory"
        directory_path.mkdir()

        written = journal_signals([_signal()], [], path=directory_path, run_id="run-4")

        assert written == 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_journal_malformed_v3_fields_do_not_break_scheduled_run():
    root = _test_path("malformed")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal(v3_decision=["not", "a", "dict"])

        written = journal_signals([signal], [], path=journal_path, run_id="run-5")

        assert written == 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_journal_serializes_datetime_pandas_and_nan_as_strict_json():
    root = _test_path("strict_json")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal(
            raw_datetime=datetime(2026, 5, 9, tzinfo=timezone.utc),
            raw_timestamp=pd.Timestamp("2026-05-09T20:00:00Z"),
            raw_nan=float("nan"),
        )

        written = journal_signals([signal], [], path=journal_path, run_id="run-6")

        assert written == 1
        raw_text = journal_path.read_text(encoding="utf-8")
        assert "NaN" not in raw_text
        record = json.loads(raw_text)
        assert record["raw_signal"]["raw_nan"] is None
        assert isinstance(record["raw_signal"]["raw_datetime"], str)
        assert isinstance(record["raw_signal"]["raw_timestamp"], str)
        assert not any(
            isinstance(value, float) and math.isnan(value)
            for value in record["raw_signal"].values()
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
