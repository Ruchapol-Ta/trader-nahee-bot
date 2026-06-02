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

from journal import (
    build_run_summary_record,
    build_signal_record,
    journal_run_summary,
    journal_signals,
)


def _full_v3_decision(**overrides):
    data = {
        "decision": "ENTER",
        "confidence": "HIGH",
        "action_label": "Consider entry",
        "main_reason": "High-quality breakout",
        "supporting_reasons": ["A-grade signal"],
        "risk_warnings": [],
        "risk_flags": [],
        "wait_conditions": [],
        "invalidation": ["Exit or avoid if price violates the stop."],
        "next_action": "Use buy stop",
        "sizing_mode": "mock_config",
        "trade_risk_mode": "NORMAL",
        "sizing_input": {
            "entry": 101.1,
            "stop": 96.5,
            "decision_entry": 101.1,
            "decision_stop": 96.5,
        },
        "decision_entry": 101.1,
        "decision_stop": 96.5,
        "decision_stop_source": "tactical",
        "decision_stop_distance_pct": 0.0455,
        "risk_profile": "conservative",
        "enter_max_stop_pct": 0.08,
        "threshold_result": {"within_enter_stop": True},
    }
    data.update(overrides)
    return data


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
            "structural_stop": 94.0,
            "structural_stop_source": "contraction_low",
            "structural_stop_distance_pct": 0.06,
            "tactical_stop": 96.5,
            "tactical_stop_source": "recent_5d_low",
            "tactical_stop_distance_pct": 0.035,
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
        "v3_position_size": {
            "valid": True,
            "sizing_mode": "mock_config",
            "trade_risk_mode": "NORMAL",
            "risk_pct": 0.01,
            "risk_per_share": 6.0,
            "max_capital_risk": 100.0,
            "suggested_shares": 16,
            "estimated_position_value": 1600.0,
            "max_loss": 96.0,
        },
    }
    data.update(overrides)
    return data


def test_build_signal_record_includes_delivery_type_and_v2_v3_fields():
    record = build_signal_record(
        _signal(v3_decision=_full_v3_decision(), alert_category="A_alert"),
        delivery_type="trade_alert",
        run_id="run-1",
    )

    assert record["run_id"] == "run-1"
    assert record["schema_version"] == "v3_shadow_1"
    assert record["delivery_type"] == "trade_alert"
    assert record["alert_category"] == "A_alert"
    assert record["ticker"] == "AAPL"
    assert record["decision"] == "ENTER"
    assert record["confidence"] == "HIGH"
    assert record["action_label"] == "Consider entry"
    assert record["risk_flags"] == []
    assert record["wait_conditions"] == []
    assert record["invalidation"] == ["Exit or avoid if price violates the stop."]
    assert record["sizing_mode"] == "mock_config"
    assert record["trade_risk_mode"] == "NORMAL"
    assert record["sizing_input"] == {
        "entry": 101.1,
        "stop": 96.5,
        "decision_entry": 101.1,
        "decision_stop": 96.5,
    }
    assert record["decision_entry"] == 101.1
    assert record["decision_stop"] == 96.5
    assert record["decision_stop_source"] == "tactical"
    assert record["decision_stop_distance_pct"] == 0.0455
    assert record["risk_profile"] == "conservative"
    assert record["enter_max_stop_pct"] == 0.08
    assert record["threshold_result"] == {"within_enter_stop": True}
    assert record["sizing_result"]["suggested_shares"] == 16
    assert record["sizing_result"]["max_loss"] == 96.0
    assert record["entry"] == 100.0
    assert record["stop"] == 94.0
    assert record["structural_stop"] == 94.0
    assert record["structural_stop_source"] == "contraction_low"
    assert record["structural_stop_distance_pct"] == 0.06
    assert record["tactical_stop"] == 96.5
    assert record["tactical_stop_source"] == "recent_5d_low"
    assert record["tactical_stop_distance_pct"] == 0.035
    assert record["risk_reward"] == 2.5
    assert "raw_signal" not in record


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
        signal = _signal()
        # Put an unserializable value inside a kept field (supporting_reasons).
        signal["v3_decision"]["supporting_reasons"] = [{1, 2, 3}]

        written = journal_signals([signal], [], path=journal_path, run_id="run-3")

        assert written == 1
        record = json.loads(journal_path.read_text(encoding="utf-8"))
        assert "raw_signal" not in record
        # the set was sanitized to a list without crashing the writer
        assert isinstance(record["supporting_reasons"][0], list)
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


def test_journal_missing_optional_v3_fields_do_not_crash_write():
    root = _test_path("partial_v3")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal(v3_decision={"decision": "WAIT"})

        written = journal_signals([signal], [], path=journal_path, run_id="run-partial")

        assert written == 1
        record = json.loads(journal_path.read_text(encoding="utf-8"))
        assert record["decision"] == "WAIT"
        assert record["action_label"] is None
        assert record["risk_flags"] == []
        assert record["wait_conditions"] == []
        assert record["invalidation"] == []
        assert record["sizing_input"] == {}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_v3_decision_can_be_journaled_without_telegram_text():
    root = _test_path("shadow")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal(v3_decision=_full_v3_decision(decision="WAIT", trade_risk_mode="NO_TRADE"))

        written = journal_signals([signal], [], path=journal_path, run_id="run-shadow")

        assert written == 1
        record = json.loads(journal_path.read_text(encoding="utf-8"))
        assert record["telegram_message_text"] is None
        assert record["decision"] == "WAIT"
        assert record["trade_risk_mode"] == "NO_TRADE"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_journal_can_persist_calibrated_watchlist_decision():
    root = _test_path("calibrated_watchlist")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal(
            grade="B",
            score=74,
            v3_decision=_full_v3_decision(
                decision="WATCHLIST_ONLY",
                confidence="MEDIUM",
                action_label="Keep on watchlist",
                main_reason="Setup is promising but not actionable yet.",
                risk_flags=["WIDE_STOP", "NO_VOLUME_CONFIRMATION"],
                wait_conditions=[],
                invalidation=["Avoid if risk remains too wide."],
                next_action="Keep on watchlist until the setup confirms a cleaner trigger.",
                trade_risk_mode="NO_TRADE",
            ),
        )

        written = journal_signals([], [signal], path=journal_path, run_id="run-calibration")

        assert written == 1
        record = json.loads(journal_path.read_text(encoding="utf-8"))
        assert record["decision"] == "WATCHLIST_ONLY"
        assert record["trade_risk_mode"] == "NO_TRADE"
        assert record["risk_flags"] == ["WIDE_STOP", "NO_VOLUME_CONFIRMATION"]
        assert record["schema_version"] == "v3_shadow_1"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_run_summary_record_writes_safely_with_freshness_and_stop_distribution():
    root = _test_path("run_summary")
    try:
        journal_path = root / "signal_journal.jsonl"
        summary = build_run_summary_record(
            run_id="run-summary",
            trade_signals=[
                _signal(
                    ticker="AAPL",
                    latest_bar_date="2026-05-08",
                    trade_plan={
                        "entry": 100.0,
                        "buy_stop": 101.0,
                        "stop_loss": 92.0,
                        "structural_stop": 92.0,
                        "structural_stop_distance_pct": 0.08,
                        "tactical_stop": 96.5,
                        "tactical_stop_distance_pct": 0.035,
                        "expected_rr": 2.5,
                    },
                    v3_decision=_full_v3_decision(
                        decision="WAIT",
                        trade_risk_mode="NO_TRADE",
                        risk_flags=["WIDE_STOP"],
                    ),
                )
            ],
            watchlist=[
                _signal(
                    ticker="MSFT",
                    grade="B",
                    score=74,
                    latest_bar_date="2026-05-08",
                    trade_plan={
                        "entry": 50.0,
                        "buy_stop": 50.5,
                        "stop_loss": 43.0,
                        "structural_stop": 43.0,
                        "structural_stop_distance_pct": 0.14,
                        "expected_rr": 2.5,
                    },
                    v3_decision=_full_v3_decision(
                        decision="WATCHLIST_ONLY",
                        confidence="MEDIUM",
                        trade_risk_mode="NO_TRADE",
                        risk_flags=["WIDE_STOP", "NO_VOLUME_CONFIRMATION"],
                    ),
                )
            ],
            market_regime={
                "summary": "Bullish market regime",
                "market_data": {
                    "SPY": {"latest_bar_date": "2026-05-08"},
                    "QQQ": {"latest_bar_date": "2026-05-08"},
                },
            },
            stats={"scanned": 2},
            cache_note="not detected",
        )

        assert summary["record_type"] == "run_summary"
        assert summary["schema_version"] == "v3_shadow_1"
        assert summary["v2_a_alert_count"] == 1
        assert summary["v2_b_watchlist_count"] == 1
        assert summary["v3_decision_counts"] == {"WAIT": 1, "WATCHLIST_ONLY": 1}
        assert summary["risk_flag_counts"] == {"WIDE_STOP": 2, "NO_VOLUME_CONFIRMATION": 1}
        assert summary["data_freshness"]["market"]["SPY"] == "2026-05-08"
        assert summary["data_freshness"]["selected_tickers"]["AAPL"] == "2026-05-08"
        assert summary["stop_distance_distribution"]["overall"]["min_pct"] == 8.0
        assert summary["stop_distance_distribution"]["overall"]["median_pct"] == 11.0
        assert summary["stop_distance_distribution"]["overall"]["max_pct"] == 14.0
        assert summary["structural_stop_distance_distribution"]["overall"]["median_pct"] == 11.0
        assert summary["tactical_stop_distance_distribution"]["overall"]["min_pct"] == 3.5
        assert summary["tactical_stop_distance_distribution"]["overall"]["median_pct"] == 3.5
        assert summary["tactical_stop_distance_distribution"]["overall"]["max_pct"] == 3.5
        assert summary["stop_distance_distribution"]["by_decision"]["WAIT"]["median_pct"] == 8.0
        assert summary["stop_distance_distribution"]["by_grade"]["B"]["median_pct"] == 14.0

        assert journal_run_summary(summary, path=journal_path) is True
        record = json.loads(journal_path.read_text(encoding="utf-8"))
        assert record["record_type"] == "run_summary"
        assert record["run_id"] == "run-summary"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_run_summary_missing_freshness_fields_do_not_crash():
    summary = build_run_summary_record(
        run_id="run-missing-freshness",
        trade_signals=[_signal()],
        watchlist=[],
        market_regime={},
        stats={},
    )

    assert summary["record_type"] == "run_summary"
    assert summary["data_freshness"]["market"] == {}
    assert summary["data_freshness"]["selected_tickers"] == {}
    assert summary["data_freshness"]["cache_note"] == "unknown"


def test_journal_persists_sizing_result_safely():
    root = _test_path("sizing_result")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal(
            v3_decision=_full_v3_decision(trade_risk_mode="SMALL"),
            v3_position_size={
                "valid": True,
                "sizing_mode": "mock_config",
                "trade_risk_mode": "SMALL",
                "risk_pct": 0.005,
                "risk_per_share": 6.0,
                "max_capital_risk": 50.0,
                "suggested_shares": 8,
                "estimated_position_value": 800.0,
                "max_loss": 48.0,
            },
        )

        written = journal_signals([signal], [], path=journal_path, run_id="run-sizing")

        assert written == 1
        record = json.loads(journal_path.read_text(encoding="utf-8"))
        assert record["sizing_result"]["trade_risk_mode"] == "SMALL"
        assert record["sizing_result"]["suggested_shares"] == 8
        assert record["sizing_result"]["max_capital_risk"] == 50.0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_journal_serializes_datetime_pandas_and_nan_as_strict_json():
    root = _test_path("strict_json")
    try:
        journal_path = root / "signal_journal.jsonl"
        signal = _signal()
        # Embed datetime / pandas / NaN inside a kept nested field.
        signal["v3_decision"]["threshold_result"] = {
            "as_of_datetime": datetime(2026, 5, 9, tzinfo=timezone.utc),
            "as_of_timestamp": pd.Timestamp("2026-05-09T20:00:00Z"),
            "raw_nan": float("nan"),
        }

        written = journal_signals([signal], [], path=journal_path, run_id="run-6")

        assert written == 1
        raw_text = journal_path.read_text(encoding="utf-8")
        assert "NaN" not in raw_text
        record = json.loads(raw_text)
        threshold = record["threshold_result"]
        assert threshold["raw_nan"] is None
        assert isinstance(threshold["as_of_datetime"], str)
        assert isinstance(threshold["as_of_timestamp"], str)
        assert not any(
            isinstance(value, float) and math.isnan(value)
            for value in threshold.values()
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
