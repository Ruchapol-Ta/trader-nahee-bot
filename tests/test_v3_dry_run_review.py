import os
import sys
import copy
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import signal_bot
import telegram_sender
import v2_engine


def _regime(**overrides):
    data = {
        "is_valid": True,
        "summary": "Bullish market regime",
        "invalid_reasons": [],
        "market_data": {"SPY": {"return_20d": 1.0}, "QQQ": {"return_20d": 2.0}},
    }
    data.update(overrides)
    return data


def _signal(ticker="AAA", grade="A", score=82, actual=True, near=False):
    return {
        "ticker": ticker,
        "setup_type": "VCP Breakout",
        "grade": grade,
        "score": score,
        "close": 100.0,
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
            "target_1": 116.0,
            "target_2": 124.0,
            "expected_rr": 2.5,
        },
        "is_actual_breakout": actual,
        "is_near_breakout": near,
        "pass_reasons": ["breakout above pivot"],
        "invalid_condition": "None",
        "market_regime": "Bullish market regime",
    }


def _shadow_cap_candidate(ticker, grade, score, shadow_score):
    signal = _signal(ticker=ticker, grade=grade, score=score)
    signal["trend_template_pass"] = True
    signal["rs_percentile"] = 90.0
    signal["new_vcp_engine"] = {
        "passed": shadow_score >= 70,
        "shadow_vcp_quality_score": shadow_score,
        "shadow_vcp_quality_grade": (
            "Elite" if shadow_score >= 90
            else "Strong" if shadow_score >= 80
            else "Good" if shadow_score >= 70
            else "Poor"
        ),
        "contraction_count": 3,
        "base_depth": 24.0,
        "final_contraction_depth": 6.0,
        "pivot_status": "near_pivot",
        "distance_to_pivot_pct": 1.0,
    }
    return signal


def _patch_scan_inputs(monkeypatch, qualified):
    monkeypatch.setattr(v2_engine, "ENABLE_SIGNAL_JOURNAL", False)
    monkeypatch.setattr(v2_engine, "ENABLE_POSITION_SIZING", False)
    monkeypatch.setattr(v2_engine, "load_market_regime", lambda: _regime())
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: list(qualified))
    monkeypatch.setattr(
        v2_engine,
        "screen_universe",
        lambda tickers: [{"ticker": ticker} for ticker in tickers],
    )
    monkeypatch.setattr(
        v2_engine,
        "evaluate_liquidity",
        lambda snapshot, check_market_cap=False, **kwargs: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(
        v2_engine,
        "qualify_snapshot",
        lambda snapshot, market_regime, spy_return, qqq_return, **kwargs: qualified[snapshot["ticker"]].copy(),
    )


def _patch_liquidity_reject_scan(monkeypatch):
    monkeypatch.setattr(v2_engine, "ENABLE_SIGNAL_JOURNAL", False)
    monkeypatch.setattr(v2_engine, "load_market_regime", lambda: _regime())
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["BAD"])
    monkeypatch.setattr(v2_engine, "screen_universe", lambda tickers: [{"ticker": "BAD"}])
    monkeypatch.setattr(
        v2_engine,
        "evaluate_liquidity",
        lambda snapshot, check_market_cap=False, **kwargs: {
            "passed": False,
            "reasons": [],
            "reject_reasons": ["price < 10.00"],
        },
    )
    monkeypatch.setattr(v2_engine, "send_v2_report", lambda *args: 0)


def test_run_v2_scan_default_behavior_still_sends_report(monkeypatch):
    captured = {"called": False}
    qualified = {"AAA": _signal("AAA", "A", 82)}
    _patch_scan_inputs(monkeypatch, qualified)
    monkeypatch.setattr(v2_engine, "ENABLE_V3_DECISION_LAYER", False)

    def fake_report(market_regime, trade_signals, watchlist, stats):
        captured["called"] = True
        assert len(trade_signals) == 1
        assert watchlist == []
        return 1

    monkeypatch.setattr(v2_engine, "send_v2_report", fake_report)

    result = v2_engine.run_v2_scan()

    assert captured["called"] is True
    assert result["messages_sent"] == 1
    assert result["telegram_skipped"] is False


def test_run_v2_scan_default_behavior_still_logs_rejects(monkeypatch):
    rejects = []
    _patch_liquidity_reject_scan(monkeypatch)
    monkeypatch.setattr(v2_engine, "_reject", lambda ticker, reasons: rejects.append((ticker, reasons)))

    result = v2_engine.run_v2_scan()

    assert rejects == [("BAD", ["price < 10.00"])]
    assert result["reject_reasons"]["rejected_by_liquidity"] == 1


def test_run_v2_scan_default_behavior_still_logs_relative_strength(monkeypatch):
    captured = []
    qualified = {"AAA": _signal("AAA", "A", 82)}
    _patch_scan_inputs(monkeypatch, qualified)
    monkeypatch.setattr(v2_engine, "send_v2_report", lambda *args: 1)

    def fake_qualify(snapshot, market_regime, spy_return, qqq_return, **kwargs):
        captured.append((
            kwargs.get("log_relative_strength"),
            kwargs.get("fetch_liquidity_metadata"),
            kwargs.get("log_liquidity_metadata_warnings"),
        ))
        return qualified[snapshot["ticker"]].copy()

    monkeypatch.setattr(v2_engine, "qualify_snapshot", fake_qualify)

    result = v2_engine.run_v2_scan()

    assert captured == [(True, True, True)]
    assert result["messages_sent"] == 1


def test_run_v2_scan_default_behavior_still_writes_journal_when_enabled(monkeypatch):
    journal_calls = {"signals": 0, "summary": 0}
    qualified = {"AAA": _signal("AAA", "A", 82)}
    _patch_scan_inputs(monkeypatch, qualified)
    monkeypatch.setattr(v2_engine, "ENABLE_SIGNAL_JOURNAL", True)
    monkeypatch.setattr(v2_engine, "ENABLE_V3_DECISION_LAYER", True)
    monkeypatch.setattr(v2_engine, "send_v2_report", lambda *args: 1)

    def fake_journal_signals(trade_signals, watchlist, run_id=None):
        journal_calls["signals"] += 1
        assert len(trade_signals) == 1
        assert watchlist == []
        assert run_id
        return len(trade_signals) + len(watchlist)

    def fake_journal_run_summary(summary):
        journal_calls["summary"] += 1
        assert summary["final_selected_count"] == 1
        return True

    monkeypatch.setattr(v2_engine, "journal_signals", fake_journal_signals)
    monkeypatch.setattr(v2_engine, "journal_run_summary", fake_journal_run_summary)

    result = v2_engine.run_v2_scan()

    assert result["messages_sent"] == 1
    assert journal_calls == {"signals": 1, "summary": 1}


def test_run_v2_scan_dry_run_skips_v2_report_and_generates_v3_decisions(monkeypatch):
    qualified = {
        "AAA": _signal("AAA", "A", 82),
        "WATCH": _signal("WATCH", "B", 70, actual=False, near=True),
    }
    _patch_scan_inputs(monkeypatch, qualified)
    monkeypatch.setattr(v2_engine, "ENABLE_SIGNAL_JOURNAL", True)
    monkeypatch.setattr(v2_engine, "ENABLE_V3_DECISION_LAYER", True)

    def fail_report(*args, **kwargs):
        raise AssertionError("dry-run review must not call send_v2_report")

    def fail_journal_signals(*args, **kwargs):
        raise AssertionError("dry-run review must not call journal_signals")

    def fail_journal_run_summary(*args, **kwargs):
        raise AssertionError("dry-run review must not call journal_run_summary")

    monkeypatch.setattr(v2_engine, "send_v2_report", fail_report)
    monkeypatch.setattr(v2_engine, "journal_signals", fail_journal_signals)
    monkeypatch.setattr(v2_engine, "journal_run_summary", fail_journal_run_summary)

    result = v2_engine.run_v2_scan(send_telegram=False, write_journal=False)

    assert result["messages_sent"] == 0
    assert result["telegram_skipped"] is True
    assert result["trade_signals"] == 1
    assert result["watchlist"] == 1
    assert sum(result["v3_decision_counts"].values()) == 2
    assert {sample["ticker"] for sample in result["v3_sample_decisions"]} == {"AAA", "WATCH"}
    assert all(sample["decision"] for sample in result["v3_sample_decisions"])


def test_v3_decision_blockers_are_derived_from_existing_decision_fields():
    selected = [
        {
            "ticker": "ENTER",
            "grade": "A",
            "v3_decision": {
                "decision": "ENTER",
                "risk_flags": ["WIDE_STOP"],
                "risk_warnings": ["stop distance is wide (9.0%)"],
            },
        },
        {
            "ticker": "WAIT",
            "grade": "A",
            "v3_decision": {
                "decision": "WAIT",
                "main_reason": "Setup quality is strong, but current stop distance is too wide for entry.",
                "risk_flags": ["WIDE_STOP"],
                "risk_warnings": [
                    "stop distance is wide (12.0%)",
                ],
                "threshold_result": {"blocked_no_volume_confirmation": True},
            },
        },
        {
            "ticker": "BONLY",
            "grade": "B",
            "v3_decision": {
                "decision": "WATCHLIST_ONLY",
                "main_reason": "Setup is promising but not actionable yet.",
                "risk_flags": [],
                "risk_warnings": [],
            },
        },
        {
            "ticker": "EXCESS",
            "grade": "A",
            "v3_decision": {
                "decision": "AVOID",
                "main_reason": "Stop distance is too wide for the V3 risk rules.",
                "risk_flags": ["WIDE_STOP"],
                "risk_warnings": ["stop distance is excessive (22.0%)"],
            },
        },
        {
            "ticker": "SETUP",
            "grade": "A",
            "v3_decision": {
                "decision": "AVOID",
                "main_reason": "Signal does not show an actual or near breakout state.",
                "risk_flags": ["GENERIC_SETUP_EVIDENCE"],
                "risk_warnings": ["breakout state is not confirmed"],
            },
        },
        {
            "ticker": "OTHER",
            "grade": "A",
            "v3_decision": {
                "decision": "WAIT",
                "main_reason": "Operator review needed.",
                "risk_flags": [],
                "risk_warnings": [],
            },
        },
    ]
    before = copy.deepcopy(selected)

    blockers = v2_engine._v3_decision_blockers(selected[:1], selected[1:])

    assert selected == before
    assert blockers == {
        "stop_distance_wide": 1,
        "stop_distance_excessive": 1,
        "volume_confirmation_light": 1,
        "b_grade_not_actionable": 1,
        "missing_setup_confirmation": 1,
        "other": 1,
    }


def test_v3_selected_review_includes_all_selected_rows_and_compact_fields():
    def selected_signal(ticker, grade, score, decision, confidence, stop_pct, volume_ratio, **decision_overrides):
        v3_decision = {
            "decision": decision,
            "decision_subtype": decision_overrides.pop("decision_subtype", None),
            "confidence": confidence,
            "decision_stop_distance_pct": stop_pct,
            "risk_flags": decision_overrides.pop("risk_flags", []),
            "risk_warnings": decision_overrides.pop("risk_warnings", []),
        }
        v3_decision.update(decision_overrides)
        return {
            "ticker": ticker,
            "grade": grade,
            "score": score,
            "volume": volume_ratio * 100.0,
            "avg_volume": 100.0,
            "v3_decision": v3_decision,
        }

    trade_signals = [
        selected_signal(
            "ONE",
            "A",
            85,
            "WAIT",
            "MEDIUM",
            0.101,
            0.81,
            decision_subtype="WAIT_TIGHTER_STOP_AND_VOLUME",
            risk_flags=["WIDE_STOP"],
        ),
        selected_signal("TWO", "A", 82, "WAIT", "MEDIUM", 0.092, 0.60, risk_flags=["NO_VOLUME_CONFIRMATION"]),
    ]
    watchlist = [
        selected_signal("THREE", "B", 74, "WATCHLIST_ONLY", "MEDIUM", 0.091, 0.48),
        selected_signal("FOUR", "A", 80, "AVOID", "LOW", 0.22, 1.10, risk_warnings=["stop distance is excessive (22.0%)"]),
        selected_signal("FIVE", "A", 78, "AVOID", "LOW", 0.05, 1.20, risk_flags=["GENERIC_SETUP_EVIDENCE"]),
        selected_signal("SIX", "A", 77, "WAIT", "MEDIUM", 0.06, 1.30),
    ]
    counts_before = v2_engine._v3_decision_counts(trade_signals, watchlist)
    before = copy.deepcopy((trade_signals, watchlist))

    review = v2_engine._v3_selected_review(trade_signals, watchlist)
    detailed_examples = v2_engine._v3_sample_decisions(trade_signals, watchlist)

    assert (trade_signals, watchlist) == before
    assert v2_engine._v3_decision_counts(trade_signals, watchlist) == counts_before
    assert [row["ticker"] for row in review] == ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX"]
    assert [sample["ticker"] for sample in detailed_examples] == ["ONE", "TWO", "THREE"]
    assert [row["delivery_type"] for row in review] == [
        "trade_alert",
        "trade_alert",
        "watchlist",
        "watchlist",
        "watchlist",
        "watchlist",
    ]
    assert review[0] == {
        "ticker": "ONE",
        "delivery_type": "trade_alert",
        "grade": "A",
        "score": 85,
        "decision": "WAIT",
        "decision_subtype": "WAIT_TIGHTER_STOP_AND_VOLUME",
        "confidence": "MEDIUM",
        "stop_distance_pct": 0.101,
        "volume_ratio": 0.81,
        "blockers": ["wide_stop"],
        "v3_error": None,
    }
    assert review[1]["blockers"] == ["light_volume"]
    assert review[2]["blockers"] == ["b_grade"]
    assert review[3]["blockers"] == ["excessive_stop"]
    assert review[4]["blockers"] == ["missing_setup"]
    assert review[5]["blockers"] == ["other"]


def test_format_v3_dry_run_review_prints_full_selected_review_beyond_samples():
    selected_review = [
        {
            "ticker": f"SEL{i}",
            "grade": "A" if i < 3 else "B",
            "score": 85 - i,
            "decision": "WAIT" if i < 5 else "WATCHLIST_ONLY",
            "decision_subtype": "WAIT_TIGHTER_STOP_AND_VOLUME" if i == 0 else None,
            "confidence": "MEDIUM",
            "stop_distance_pct": 0.10 + (i / 1000),
            "volume_ratio": 0.80 + (i / 100),
            "blockers": ["wide_stop", "light_volume"] if i == 0 else ["b_grade"],
        }
        for i in range(6)
    ]
    output = signal_bot.format_v3_dry_run_review({
        "market_regime": "Bullish market regime",
        "market_regime_valid": True,
        "scanned": 6,
        "trade_signals": 2,
        "watchlist": 4,
        "funnel": {"scanned": 6, "final_setup_passed": 6},
        "reject_reasons": {},
        "v3_decision_counts": {
            "ENTER": 0,
            "WAIT": 5,
            "WATCHLIST_ONLY": 1,
            "AVOID": 0,
            "none": 0,
        },
        "telegram_skipped": True,
        "journal_skipped": True,
        "v3_blockers": {
            "stop_distance_wide": 1,
            "stop_distance_excessive": 0,
            "volume_confirmation_light": 1,
            "b_grade_not_actionable": 5,
            "missing_setup_confirmation": 0,
            "other": 0,
        },
        "v3_selected_review": selected_review,
        "v3_sample_decisions": [
            {
                "ticker": "SEL0",
                "grade": "A",
                "decision": "WAIT",
                "confidence": "MEDIUM",
                "main_reason": "Sample only.",
            }
        ],
    })

    assert "V3 decisions: ENTER: 0 | WAIT: 5 | WATCHLIST_ONLY: 1 | AVOID: 0 | none: 0" in output
    assert "Selected V3 review:" in output
    for i in range(6):
        assert f"- SEL{i} |" in output
    assert (
        "- SEL0 | A | WAIT | MEDIUM | score 85 | stop 10.0% | vol 0.80x | "
        "wide_stop, light_volume | subtype wait_stop+volume"
    ) in output
    assert "- SEL5 | B | WATCHLIST_ONLY | MEDIUM | score 80 | stop 10.5% | vol 0.85x | b_grade" in output
    assert "Detailed examples:" in output
    assert "Sample decisions:" not in output


def test_format_v3_dry_run_review_maps_wait_volume_subtype_label():
    output = signal_bot.format_v3_dry_run_review({
        "market_regime": "Bullish market regime",
        "market_regime_valid": True,
        "scanned": 1,
        "trade_signals": 1,
        "watchlist": 0,
        "funnel": {"scanned": 1, "final_setup_passed": 1},
        "reject_reasons": {},
        "v3_decision_counts": {
            "ENTER": 0,
            "WAIT": 1,
            "WATCHLIST_ONLY": 0,
            "AVOID": 0,
            "none": 0,
        },
        "telegram_skipped": True,
        "journal_skipped": True,
        "v3_blockers": {
            "stop_distance_wide": 0,
            "stop_distance_excessive": 0,
            "volume_confirmation_light": 1,
            "b_grade_not_actionable": 0,
            "missing_setup_confirmation": 0,
            "other": 0,
        },
        "v3_selected_review": [
            {
                "ticker": "AAPL",
                "delivery_type": "trade_alert",
                "grade": "A",
                "score": 82,
                "decision": "WAIT",
                "decision_subtype": "WAIT_VOLUME_CONFIRMATION",
                "confidence": "MEDIUM",
                "stop_distance_pct": 0.074,
                "volume_ratio": 0.90,
                "blockers": ["light_volume"],
            }
        ],
        "v3_sample_decisions": [],
    })

    assert "V3 decisions: ENTER: 0 | WAIT: 1 | WATCHLIST_ONLY: 0 | AVOID: 0 | none: 0" in output
    assert "- AAPL | A | WAIT | MEDIUM | score 82 | stop 7.4% | vol 0.90x | light_volume | subtype wait_volume" in output
    assert "WAIT_VOLUME_CONFIRMATION" not in output


def test_format_v3_dry_run_review_includes_vcp_shadow_comparison():
    output = signal_bot.format_v3_dry_run_review({
        "market_regime": "Bullish market regime",
        "market_regime_valid": True,
        "scanned": 10,
        "trade_signals": 1,
        "watchlist": 1,
        "funnel": {"scanned": 10, "final_setup_passed": 2},
        "reject_reasons": {},
        "vcp_shadow": {
            "agreement_counts": {"both_passed": 2, "current_only": 3, "both_failed": 5},
            "current_logic_passed": 5,
            "new_engine_passed": 2,
            "new_engine_contractions_2plus": 4,
            "new_engine_contractions_3plus": 2,
            "new_engine_pivot_identified": 6,
            "new_engine_extended": 1,
            "shadow_quality_grades": {
                "Elite": 1,
                "Strong": 1,
                "Poor": 3,
            },
            "shadow_quality_score_buckets": {
                "90-100": 1,
                "80-89": 1,
                "0-59": 3,
            },
            "shadow_quality_average": 54.6,
            "new_engine_reject_reasons": {
                "prior uptrend not confirmed": 3,
                "final contraction depth 18.0% > 12%": 2,
            },
            "new_engine_warning_flags": {
                "preferred_contractions_missing": 2,
                "final_contraction_volume_not_dry": 1,
            },
        },
        "v3_decision_counts": {
            "ENTER": 0,
            "WAIT": 2,
            "WATCHLIST_ONLY": 0,
            "AVOID": 0,
            "none": 0,
        },
        "telegram_skipped": True,
        "journal_skipped": True,
        "v3_blockers": {},
        "v3_selected_review": [],
        "v3_sample_decisions": [],
    })

    assert "VCP shadow comparison:" in output
    assert "- agreement: both_failed: 5 | current_only: 3 | both_passed: 2" in output
    assert "- pass counts: current 5 | new 2 | 2+ contractions 4 | 3+ contractions 2 | pivots 6 | extended 1" in output
    assert "- quality grades: Poor: 3 | Elite: 1 | Strong: 1" in output
    assert "- quality scores: 0-59: 3 | 80-89: 1 | 90-100: 1 | avg 54.6" in output
    assert "prior uptrend not confirmed: 3" in output
    assert "preferred_contractions_missing: 2" in output


def test_shadow_grade_cap_simulation_demotes_without_promoting():
    simulation = v2_engine._shadow_grade_cap_simulation([
        _shadow_cap_candidate("ELITE", "A+", 91, 95),
        _shadow_cap_candidate("WEAK", "A", 81, 37),
        _shadow_cap_candidate("BSTRONG", "B", 74, 95),
        _shadow_cap_candidate("STRONG", "A", 80, 85),
        _shadow_cap_candidate("CAPA", "A+", 90, 85),
        _shadow_cap_candidate("GOOD", "B", 70, 75),
    ])

    by_ticker = {
        row["ticker"]: row
        for row in simulation["rows"]
    }

    assert simulation["current_distribution"] == {"A+": 2, "A": 2, "B": 2}
    assert simulation["simulated_distribution"] == {"A+": 1, "C": 1, "B": 2, "A": 2}
    assert simulation["promotions"] == []
    assert by_ticker["WEAK"]["simulated_grade"] == "C"
    assert "capped to C" in by_ticker["WEAK"]["simulated_grade_reason"]
    assert by_ticker["BSTRONG"]["simulated_grade"] == "B"
    assert simulation["biggest_a_to_c_changes"][0]["ticker"] == "WEAK"
    assert simulation["biggest_b_to_a_or_a_plus_changes"] == []
    assert simulation["top_simulated_a_plus_candidates"][0]["ticker"] == "ELITE"


def test_format_v3_dry_run_review_includes_shadow_grade_cap_simulation():
    simulation = v2_engine._shadow_grade_cap_simulation([
        _shadow_cap_candidate("ELITE", "A+", 91, 95),
        _shadow_cap_candidate("WEAK", "A", 81, 37),
        _shadow_cap_candidate("BSTRONG", "B", 74, 95),
    ])

    output = signal_bot.format_v3_dry_run_review({
        "market_regime": "Bullish market regime",
        "market_regime_valid": True,
        "scanned": 3,
        "trade_signals": 1,
        "watchlist": 1,
        "funnel": {"scanned": 3},
        "reject_reasons": {},
        "vcp_shadow": {},
        "shadow_grade_cap_simulation": simulation,
        "shadow_grade_cap_report_files": {
            "csv": "reports/daily_review/shadow_grade_cap.csv",
            "json": "reports/daily_review/shadow_grade_cap.json",
        },
        "v3_decision_counts": {},
        "telegram_skipped": True,
        "journal_skipped": True,
        "v3_blockers": {},
        "v3_selected_review": [],
        "v3_sample_decisions": [],
    })

    assert "Shadow grade-cap simulation:" in output
    assert "- current grades: A+: 1 | A: 1 | B: 1" in output
    assert "- simulated grades: A+: 1 | B: 1 | C: 1" in output
    assert "- promotions: 0" in output
    assert "- demotions: 1" in output
    assert "WEAK | A->C | shadow 37" in output
    assert "none; cap-only simulation cannot promote B candidates" in output
    assert "Top simulated A+ candidates:" in output
    assert "CSV export: reports/daily_review/shadow_grade_cap.csv" in output
    assert "JSON export: reports/daily_review/shadow_grade_cap.json" in output


def test_shadow_grade_cap_report_export_writes_csv_and_json(tmp_path):
    simulation = v2_engine._shadow_grade_cap_simulation([
        _shadow_cap_candidate("ELITE", "A+", 91, 95),
        _shadow_cap_candidate("WEAK", "A", 81, 37),
    ])
    files = signal_bot.export_shadow_grade_cap_reports(
        {"shadow_grade_cap_simulation": simulation},
        report_dir=tmp_path,
    )

    csv_path = tmp_path / os.path.basename(files["csv"])
    json_path = tmp_path / os.path.basename(files["json"])

    assert files["row_count"] == 2
    assert csv_path.exists()
    assert json_path.exists()
    assert "ticker,current_grade,simulated_grade" in csv_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["report_type"] == "shadow_grade_cap_simulation"
    assert payload["simulation"]["rows"][0]["ticker"] == "ELITE"


def test_run_v3_dry_run_review_exports_shadow_grade_cap_reports(monkeypatch, tmp_path):
    simulation = v2_engine._shadow_grade_cap_simulation([
        _shadow_cap_candidate("ELITE", "A+", 91, 95),
    ])

    def fake_run_v2_scan(**kwargs):
        assert kwargs["send_telegram"] is False
        assert kwargs["write_journal"] is False
        return {
            "market_regime": "Bullish market regime",
            "market_regime_valid": True,
            "scanned": 1,
            "trade_signals": 1,
            "watchlist": 0,
            "funnel": {"scanned": 1},
            "reject_reasons": {},
            "vcp_shadow": {},
            "shadow_grade_cap_simulation": simulation,
            "v3_decision_counts": {},
            "telegram_skipped": True,
            "journal_skipped": True,
            "v3_blockers": {},
            "v3_selected_review": [],
            "v3_sample_decisions": [],
        }

    monkeypatch.setattr(signal_bot, "DAILY_REVIEW_REPORT_DIR", tmp_path)
    monkeypatch.setattr(signal_bot, "run_v2_scan", fake_run_v2_scan)

    result = signal_bot.run_v3_dry_run_review()

    files = result["shadow_grade_cap_report_files"]
    assert files["row_count"] == 1
    assert os.path.exists(files["csv"])
    assert os.path.exists(files["json"])


def test_run_v2_scan_quiet_mode_suppresses_reject_logs_but_keeps_aggregation(monkeypatch):
    _patch_liquidity_reject_scan(monkeypatch)

    def fail_reject(*args, **kwargs):
        raise AssertionError("quiet dry-run must not log per-ticker rejects")

    def fail_report(*args, **kwargs):
        raise AssertionError("dry-run review must not call send_v2_report")

    monkeypatch.setattr(v2_engine, "_reject", fail_reject)
    monkeypatch.setattr(v2_engine, "send_v2_report", fail_report)

    result = v2_engine.run_v2_scan(
        send_telegram=False,
        write_journal=False,
        log_rejects=False,
    )

    assert result["messages_sent"] == 0
    assert result["telegram_skipped"] is True
    assert result["journal_skipped"] is True
    assert result["reject_reasons"]["rejected_by_liquidity"] == 1
    assert result["funnel"]["rejected_count"] == 1


def test_run_v2_scan_dry_run_skips_market_summary_when_market_invalid(monkeypatch):
    monkeypatch.setattr(
        v2_engine,
        "load_market_regime",
        lambda: _regime(is_valid=False, summary="Invalid market", invalid_reasons=["SPY below 50EMA"]),
    )

    def fail_market_summary(*args, **kwargs):
        raise AssertionError("dry-run review must not call send_v2_market_summary")

    def fail_universe(*args, **kwargs):
        raise AssertionError("invalid market should not scan the universe")

    def fail_journal_run_summary(*args, **kwargs):
        raise AssertionError("dry-run review must not call journal_run_summary")

    monkeypatch.setattr(v2_engine, "send_v2_market_summary", fail_market_summary)
    monkeypatch.setattr(v2_engine, "get_v2_universe", fail_universe)
    monkeypatch.setattr(v2_engine, "journal_run_summary", fail_journal_run_summary)

    result = v2_engine.run_v2_scan(send_telegram=False, write_journal=False)

    assert result["market_regime_valid"] is False
    assert result["market_regime"] == "Invalid market"
    assert result["messages_sent"] == 0
    assert result["telegram_skipped"] is True
    assert result["journal_skipped"] is True
    assert result["v3_decision_counts"] == {
        "ENTER": 0,
        "WAIT": 0,
        "WATCHLIST_ONLY": 0,
        "AVOID": 0,
        "none": 0,
    }


def test_run_v2_scan_journals_invalid_market_summary_before_return(monkeypatch):
    journaled = []
    market_regime = _regime(
        is_valid=False,
        summary="Invalid market regime",
        invalid_reasons=["SPY market data unavailable", "QQQ market data unavailable"],
        market_data={},
    )
    monkeypatch.setattr(v2_engine, "ENABLE_SIGNAL_JOURNAL", True)
    monkeypatch.setattr(v2_engine, "load_market_regime", lambda: market_regime)
    monkeypatch.setattr(v2_engine, "send_v2_market_summary", lambda market_regime: 1)

    def fail_universe(*args, **kwargs):
        raise AssertionError("invalid market should not scan the universe")

    def fail_journal_signals(*args, **kwargs):
        raise AssertionError("invalid market has no selected signals to journal")

    def fake_journal_run_summary(summary):
        journaled.append(summary)
        return True

    monkeypatch.setattr(v2_engine, "get_v2_universe", fail_universe)
    monkeypatch.setattr(v2_engine, "journal_signals", fail_journal_signals)
    monkeypatch.setattr(v2_engine, "journal_run_summary", fake_journal_run_summary)

    result = v2_engine.run_v2_scan()

    assert result["market_regime_valid"] is False
    assert result["messages_sent"] == 1
    assert result["journal_skipped"] is False
    assert result["scanned"] == 0
    assert result["trade_signals"] == 0
    assert result["watchlist"] == 0
    assert result["market_invalid_reasons"] == [
        "SPY market data unavailable",
        "QQQ market data unavailable",
    ]
    assert len(journaled) == 1
    summary = journaled[0]
    assert summary["record_type"] == "run_summary"
    assert summary["market_regime"] == "Invalid market regime"
    assert summary["final_selected_count"] == 0
    assert summary["stats"]["scanned"] == 0
    assert summary["stats"]["market_regime_valid"] is False
    assert summary["stats"]["market_invalid_reasons"] == [
        "SPY market data unavailable",
        "QQQ market data unavailable",
    ]
    assert summary["data_freshness"]["market"] == {}


def test_v3_dry_run_cli_returns_early_without_scheduler_or_telegram(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["signal_bot.py", "--v3-dry-run-review"])
    monkeypatch.setattr(v2_engine, "ENABLE_V3_DECISION_LAYER", False)

    def fake_run_v2_scan(
        *,
        debug=False,
        send_telegram=True,
        write_journal=True,
        log_rejects=True,
        log_relative_strength=True,
        fetch_liquidity_metadata=True,
        log_liquidity_metadata_warnings=True,
    ):
        assert debug is False
        assert send_telegram is False
        assert write_journal is False
        assert log_rejects is False
        assert log_relative_strength is False
        assert fetch_liquidity_metadata is False
        assert log_liquidity_metadata_warnings is False
        assert v2_engine.ENABLE_V3_DECISION_LAYER is True
        return {
            "market_regime": "Bullish market regime",
            "market_regime_valid": True,
            "scanned": 2,
            "trade_signals": 1,
            "watchlist": 1,
            "funnel": {
                "scanned": 2,
                "liquidity_passed": 2,
                "final_setup_passed": 2,
                "rejected_count": 3,
            },
            "reject_reasons": {
                "rejected_by_breakout_or_near_breakout": 2,
                "rejected_by_liquidity": 1,
            },
            "telegram_skipped": True,
            "journal_skipped": True,
            "v3_decision_counts": {
                "ENTER": 1,
                "WAIT": 0,
                "WATCHLIST_ONLY": 1,
                "AVOID": 0,
                "none": 0,
            },
            "v3_blockers": {
                "stop_distance_wide": 1,
                "stop_distance_excessive": 0,
                "volume_confirmation_light": 0,
                "b_grade_not_actionable": 1,
                "missing_setup_confirmation": 0,
                "other": 0,
            },
            "v3_selected_review": [
                {
                    "ticker": "AAA",
                    "delivery_type": "trade_alert",
                    "grade": "A",
                    "score": 82,
                    "decision": "ENTER",
                    "confidence": "HIGH",
                    "stop_distance_pct": 0.045,
                    "volume_ratio": 1.25,
                    "blockers": [],
                },
                {
                    "ticker": "WATCH",
                    "delivery_type": "watchlist",
                    "grade": "B",
                    "score": 70,
                    "decision": "WATCHLIST_ONLY",
                    "confidence": "MEDIUM",
                    "stop_distance_pct": 0.091,
                    "volume_ratio": 0.48,
                    "blockers": ["wide_stop", "light_volume"],
                },
            ],
            "v3_sample_decisions": [
                {
                    "ticker": "AAA",
                    "grade": "A",
                    "decision": "ENTER",
                    "confidence": "HIGH",
                    "main_reason": "High-quality breakout with a usable risk plan.",
                    "supporting_reasons": ["A-grade signal"],
                    "risk_warnings": [],
                }
            ],
        }

    def fail_scheduler(*args, **kwargs):
        raise AssertionError("dry-run CLI must not start scheduler")

    def fail_run_scan(*args, **kwargs):
        raise AssertionError("dry-run CLI must not call run_scan")

    def fail_send_message(*args, **kwargs):
        raise AssertionError("dry-run CLI must not send Telegram messages")

    def fail_journal_signals(*args, **kwargs):
        raise AssertionError("dry-run CLI must not call journal_signals")

    def fail_journal_run_summary(*args, **kwargs):
        raise AssertionError("dry-run CLI must not call journal_run_summary")

    monkeypatch.setattr(signal_bot, "run_v2_scan", fake_run_v2_scan)
    monkeypatch.setattr(signal_bot, "BlockingScheduler", fail_scheduler)
    monkeypatch.setattr(signal_bot, "run_scan", fail_run_scan)
    monkeypatch.setattr(telegram_sender, "send_message", fail_send_message)
    monkeypatch.setattr(signal_bot, "send_error_alert", fail_send_message)
    monkeypatch.setattr(v2_engine, "journal_signals", fail_journal_signals)
    monkeypatch.setattr(v2_engine, "journal_run_summary", fail_journal_run_summary)

    signal_bot.main()

    output = capsys.readouterr().out
    assert "V3 Dry Run Review" in output
    assert "Telegram delivery: skipped" in output
    assert "Journal writes: skipped" in output
    assert "V2 funnel:" in output
    assert "scanned: 2" in output
    assert "Reject aggregation:" in output
    assert "rejected_by_breakout_or_near_breakout: 2" in output
    assert "V3 decisions: ENTER: 1 | WAIT: 0 | WATCHLIST_ONLY: 1 | AVOID: 0 | none: 0" in output
    assert "V3 blockers:" in output
    assert "- stop_distance_wide: 1" in output
    assert "- b_grade_not_actionable: 1" in output
    assert "Selected V3 review:" in output
    assert "- AAA | A | ENTER | HIGH | score 82 | stop 4.5% | vol 1.25x | none" in output
    assert "- WATCH | B | WATCHLIST_ONLY | MEDIUM | score 70 | stop 9.1% | vol 0.48x | wide_stop, light_volume" in output
    assert "Detailed examples:" in output
    assert "Sample decisions:" not in output
    assert "AAA | A | ENTER | HIGH" in output
    assert v2_engine.ENABLE_V3_DECISION_LAYER is False
