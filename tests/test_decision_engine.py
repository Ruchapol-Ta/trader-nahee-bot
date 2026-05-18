import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

from decision_engine import evaluate_signal_decision


def _signal(**overrides):
    data = {
        "ticker": "AAPL",
        "grade": "A",
        "score": 82,
        "close": 100.0,
        "ema20": 96.0,
        "ema50": 90.0,
        "volume": 1_250_000.0,
        "avg_volume": 1_000_000.0,
        "is_actual_breakout": True,
        "is_near_breakout": False,
        "market_regime": "Bullish market regime",
        "trade_plan": {
            "entry": 100.0,
            "stop_loss": 94.0,
            "expected_rr": 2.5,
        },
        "category_scores": {"relative_strength": 15},
        "pass_reasons": ["trend structure bullish", "breakout above pivot"],
    }
    data.update(overrides)
    return data


def _assert_decision_shape(result):
    assert set(result) == {
        "decision",
        "confidence",
        "action_label",
        "main_reason",
        "supporting_reasons",
        "risk_warnings",
        "risk_flags",
        "wait_conditions",
        "invalidation",
        "next_action",
        "sizing_mode",
        "trade_risk_mode",
        "sizing_input",
        "decision_entry",
        "decision_stop",
        "decision_stop_source",
        "decision_stop_distance_pct",
        "risk_profile",
        "enter_max_stop_pct",
        "threshold_result",
    }
    assert isinstance(result["supporting_reasons"], list)
    assert isinstance(result["risk_warnings"], list)
    assert isinstance(result["risk_flags"], list)
    assert isinstance(result["wait_conditions"], list)
    assert isinstance(result["invalidation"], list)
    assert isinstance(result["sizing_input"], dict)


def _trade_plan_with_tactical(
    *,
    entry=100.0,
    buy_stop=101.0,
    stop_loss=84.0,
    structural_stop=84.0,
    tactical_stop=94.0,
    expected_rr=2.5,
):
    return {
        "entry": entry,
        "buy_stop": buy_stop,
        "stop_loss": stop_loss,
        "structural_stop": structural_stop,
        "structural_stop_distance_pct": (entry - structural_stop) / entry,
        "tactical_stop": tactical_stop,
        "tactical_stop_distance_pct": ((buy_stop or entry) - tactical_stop) / (buy_stop or entry),
        "expected_rr": expected_rr,
    }


def _structural_trade_plan(*, decision_distance_pct, entry=100.0, buy_stop=100.0, expected_rr=2.5):
    stop = round(buy_stop * (1 - decision_distance_pct), 4)
    return {
        "entry": entry,
        "buy_stop": buy_stop,
        "stop_loss": stop,
        "structural_stop": stop,
        "structural_stop_distance_pct": decision_distance_pct,
        "expected_rr": expected_rr,
    }


def _tactical_trade_plan(*, decision_distance_pct, entry=100.0, buy_stop=100.0, expected_rr=2.5):
    tactical_stop = round(buy_stop * (1 - decision_distance_pct), 4)
    return {
        "entry": entry,
        "buy_stop": buy_stop,
        "stop_loss": 80.0,
        "structural_stop": 80.0,
        "structural_stop_distance_pct": 0.20,
        "tactical_stop": tactical_stop,
        "tactical_stop_distance_pct": decision_distance_pct,
        "expected_rr": expected_rr,
    }


def test_decision_layer_returns_none_when_disabled():
    assert evaluate_signal_decision(_signal(), enabled=False) is None


def test_actual_a_breakout_with_valid_risk_returns_enter():
    result = evaluate_signal_decision(_signal(), enabled=True)

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["action_label"] == "Enter only on planned trigger"
    assert result["action_label"] != "Consider entry"
    assert result["confidence"] == "HIGH"
    assert result["trade_risk_mode"] != "NO_TRADE"
    assert result["next_action"] == "Enter only if the planned buy stop triggers and the trading stop remains valid."
    assert "Consider entry" not in result["next_action"]
    assert result["decision_stop_source"] == "structural"


def test_near_breakout_returns_wait():
    result = evaluate_signal_decision(
        _signal(grade="B", score=70, is_actual_breakout=False, is_near_breakout=True),
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert "breakout" in result["next_action"].lower()
    assert result["wait_conditions"]
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_b_actual_breakout_with_valid_market_decent_risk_and_volume_returns_wait():
    result = evaluate_signal_decision(
        _signal(grade="B", score=70, is_actual_breakout=True, is_near_breakout=False),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert "B-grade" in result["main_reason"]


def test_b_actual_breakout_with_bad_volume_returns_watchlist_only():
    result = evaluate_signal_decision(
        _signal(
            grade="B",
            score=70,
            is_actual_breakout=True,
            is_near_breakout=False,
            volume=800_000.0,
            avg_volume=1_000_000.0,
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WATCHLIST_ONLY"
    assert any("volume" in warning.lower() for warning in result["risk_warnings"])
    assert "NO_VOLUME_CONFIRMATION" in result["risk_flags"]
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_promising_signal_in_unsupportive_market_returns_watchlist_only():
    result = evaluate_signal_decision(
        _signal(grade="B", score=70, market_regime="Invalid market regime"),
        market_regime={"is_valid": False, "summary": "Invalid market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WATCHLIST_ONLY"
    assert result["next_action"] == "Keep on watchlist until the setup confirms a cleaner trigger."
    assert "market regime improves" not in result["next_action"]


def test_relative_strength_can_be_confirmed_from_category_scores_without_benchmark_data():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": 15}, pass_reasons=[]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"


def test_realistic_a_plus_v2_trade_alert_remains_enter():
    result = evaluate_signal_decision(
        _signal(
            grade="A+",
            score=91,
            close=100.0,
            ema20=97.0,
            ema50=92.0,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            category_scores={
                "market_regime": 10,
                "liquidity": 10,
                "trend_structure": 15,
                "relative_strength": 15,
                "high_52w_proximity": 10,
                "consolidation_tightness": 10,
                "atr_contraction": 10,
                "volume_quality": 10,
                "risk_reward": 10,
            },
            pass_reasons=[
                "SPY bullish EMA stack",
                "trend structure bullish",
                "outperformed SPY",
                "breakout above pivot",
            ],
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"


def test_a_grade_wide_structural_but_tactical_stop_under_enter_max_can_enter():
    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_trade_plan_with_tactical(
                entry=100.0,
                buy_stop=101.0,
                stop_loss=82.0,
                structural_stop=82.0,
                tactical_stop=94.0,
            ),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["decision_entry"] == 101.0
    assert result["decision_stop"] == 94.0
    assert result["decision_stop_source"] == "tactical"
    assert round(result["decision_stop_distance_pct"], 4) == 0.0693
    assert "WIDE_STOP" not in result["risk_flags"]
    assert "STRUCTURAL_STOP_WIDE" in result["risk_flags"]
    assert result["sizing_input"]["decision_entry"] == 101.0
    assert result["sizing_input"]["decision_stop"] == 94.0


def test_a_grade_tactical_stop_between_enter_and_watchlist_band_remains_wait():
    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_trade_plan_with_tactical(
                entry=100.0,
                buy_stop=101.0,
                stop_loss=82.0,
                structural_stop=82.0,
                tactical_stop=92.0,
            ),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert result["decision_stop_source"] == "tactical"
    assert round(result["decision_stop_distance_pct"], 4) == 0.0891
    assert "WIDE_STOP" in result["risk_flags"]
    assert "STRUCTURAL_STOP_WIDE" in result["risk_flags"]


def test_conservative_profile_keeps_adi_like_tactical_risk_as_wait(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "conservative")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_trade_plan_with_tactical(
                entry=100.0,
                buy_stop=101.0,
                stop_loss=82.0,
                structural_stop=82.0,
                tactical_stop=91.78,
            ),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert result["risk_profile"] == "conservative"
    assert result["enter_max_stop_pct"] == 0.08
    assert result["trade_risk_mode"] == "NO_TRADE"
    assert result["threshold_result"]["within_enter_stop"] is False


def test_balanced_profile_turns_clean_adi_like_tactical_risk_into_small_enter(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "balanced")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_trade_plan_with_tactical(
                entry=100.0,
                buy_stop=101.0,
                stop_loss=82.0,
                structural_stop=82.0,
                tactical_stop=91.78,
            ),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["risk_profile"] == "balanced"
    assert result["enter_max_stop_pct"] == 0.10
    assert result["trade_risk_mode"] == "SMALL"
    assert result["threshold_result"]["within_enter_stop"] is True


def test_aggressive_profile_allows_10_to_12_pct_risk_with_tiny_mode(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "aggressive")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_trade_plan_with_tactical(
                entry=100.0,
                buy_stop=101.0,
                stop_loss=82.0,
                structural_stop=82.0,
                tactical_stop=89.5,
            ),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["risk_profile"] == "aggressive"
    assert result["enter_max_stop_pct"] == 0.12
    assert result["trade_risk_mode"] == "TINY"


def test_balanced_profile_does_not_enter_structural_stop_above_conservative_limit(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "balanced")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_structural_trade_plan(decision_distance_pct=0.0913),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert result["decision_stop_source"] == "structural"
    assert result["trade_risk_mode"] == "NO_TRADE"
    assert result["threshold_result"]["blocked_structural_stop_above_conservative_limit"] is True


def test_aggressive_profile_does_not_enter_structural_stop_above_conservative_limit(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "aggressive")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_structural_trade_plan(decision_distance_pct=0.11),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert result["decision_stop_source"] == "structural"
    assert result["trade_risk_mode"] == "NO_TRADE"
    assert result["threshold_result"]["blocked_structural_stop_above_conservative_limit"] is True


def test_exact_eight_percent_boundary_can_enter_with_structural_stop(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "conservative")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_structural_trade_plan(decision_distance_pct=0.08),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["decision_stop_source"] == "structural"
    assert result["trade_risk_mode"] == "NORMAL"
    assert result["threshold_result"]["within_conservative_enter_limit"] is True


def test_exact_ten_percent_boundary_enters_balanced_with_tactical_stop(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "balanced")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_tactical_trade_plan(decision_distance_pct=0.10),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["decision_stop_source"] == "tactical"
    assert result["trade_risk_mode"] == "SMALL"
    assert result["threshold_result"]["within_balanced_tactical_enter_limit"] is True


def test_exact_twelve_percent_boundary_enters_aggressive_with_tactical_stop(monkeypatch):
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "aggressive")

    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_tactical_trade_plan(decision_distance_pct=0.12),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["decision_stop_source"] == "tactical"
    assert result["trade_risk_mode"] == "TINY"
    assert result["threshold_result"]["within_aggressive_tactical_enter_limit"] is True


def test_runtime_profile_resolution_reads_config_module(monkeypatch):
    signal = _signal(
        grade="A",
        score=82,
        volume=1_400_000.0,
        avg_volume=1_000_000.0,
        trade_plan=_tactical_trade_plan(decision_distance_pct=0.0913),
    )

    monkeypatch.setattr(config, "V3_RISK_PROFILE", "conservative")
    conservative = evaluate_signal_decision(
        signal,
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )
    monkeypatch.setattr(config, "V3_RISK_PROFILE", "balanced")
    balanced = evaluate_signal_decision(
        signal,
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    assert conservative["decision"] == "WAIT"
    assert balanced["decision"] == "ENTER"
    assert balanced["risk_profile"] == "balanced"


def test_no_volume_confirmation_blocks_enter_under_balanced_and_aggressive(monkeypatch):
    for profile in ["balanced", "aggressive"]:
        monkeypatch.setattr(config, "V3_RISK_PROFILE", profile)

        result = evaluate_signal_decision(
            _signal(
                grade="A",
                score=82,
                volume=1_000_000.0,
                avg_volume=1_000_000.0,
                trade_plan=_trade_plan_with_tactical(
                    entry=100.0,
                    buy_stop=101.0,
                    stop_loss=82.0,
                    structural_stop=82.0,
                    tactical_stop=91.78,
                ),
            ),
            market_regime={"is_valid": True, "summary": "Bullish market regime"},
            enabled=True,
        )

        _assert_decision_shape(result)
        assert result["decision"] == "WAIT"
        assert result["trade_risk_mode"] == "NO_TRADE"
        assert "NO_VOLUME_CONFIRMATION" in result["risk_flags"]


def test_extension_blocks_enter_under_all_profiles(monkeypatch):
    for profile in ["conservative", "balanced", "aggressive"]:
        monkeypatch.setattr(config, "V3_RISK_PROFILE", profile)

        result = evaluate_signal_decision(
            _signal(
                grade="A",
                score=82,
                close=100.0,
                ema20=90.0,
                ema50=85.0,
                volume=1_400_000.0,
                avg_volume=1_000_000.0,
                trade_plan=_trade_plan_with_tactical(
                    entry=100.0,
                    buy_stop=101.0,
                    stop_loss=82.0,
                    structural_stop=82.0,
                    tactical_stop=94.0,
                ),
            ),
            market_regime={"is_valid": True, "summary": "Bullish market regime"},
            enabled=True,
        )

        _assert_decision_shape(result)
        assert result["decision"] != "ENTER"
        assert result["trade_risk_mode"] == "NO_TRADE"
        assert "EXTENDED_ENTRY" in result["risk_flags"]


def test_b_grade_tactical_stop_under_enter_max_remains_watchlist_only():
    result = evaluate_signal_decision(
        _signal(
            grade="B",
            score=74,
            is_actual_breakout=False,
            is_near_breakout=True,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            trade_plan=_trade_plan_with_tactical(
                entry=100.0,
                buy_stop=101.0,
                stop_loss=82.0,
                structural_stop=82.0,
                tactical_stop=94.0,
            ),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WATCHLIST_ONLY"
    assert result["trade_risk_mode"] == "NO_TRADE"
    assert result["decision_stop_source"] == "tactical"


def test_b_grade_remains_watchlist_only_under_all_risk_profiles(monkeypatch):
    for profile in ["conservative", "balanced", "aggressive"]:
        monkeypatch.setattr(config, "V3_RISK_PROFILE", profile)

        result = evaluate_signal_decision(
            _signal(
                grade="B",
                score=74,
                is_actual_breakout=False,
                is_near_breakout=True,
                volume=1_400_000.0,
                avg_volume=1_000_000.0,
                trade_plan=_tactical_trade_plan(decision_distance_pct=0.06),
            ),
            market_regime={"is_valid": True, "summary": "Bullish market regime"},
            enabled=True,
        )

        _assert_decision_shape(result)
        assert result["decision"] == "WATCHLIST_ONLY"
        assert result["trade_risk_mode"] == "NO_TRADE"


def test_extended_entry_plus_wide_tactical_stop_remains_avoid():
    result = evaluate_signal_decision(
        _signal(
            grade="B",
            score=74,
            close=100.0,
            ema20=84.0,
            ema50=82.0,
            is_actual_breakout=False,
            is_near_breakout=True,
            trade_plan=_trade_plan_with_tactical(
                entry=100.0,
                buy_stop=101.0,
                stop_loss=78.0,
                structural_stop=78.0,
                tactical_stop=88.0,
            ),
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert "EXTENDED_ENTRY" in result["risk_flags"]
    assert "WIDE_STOP" in result["risk_flags"]


def test_actual_breakout_without_relative_strength_confirmation_returns_wait():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": 0}, pass_reasons=[]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("relative strength" in warning.lower() for warning in result["risk_warnings"])


def test_negative_relative_strength_category_score_does_not_confirm_rs():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": -1}, pass_reasons=[]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("relative strength" in warning.lower() for warning in result["risk_warnings"])


def test_pass_reasons_relative_strength_evidence_still_confirms_rs():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": 0}, pass_reasons=["outperformed QQQ"]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"


def test_malformed_inputs_do_not_crash_and_degrade_to_avoid_or_wait():
    result = evaluate_signal_decision(
        _signal(
            score="not-a-number",
            trade_plan=["not", "a", "dict"],
            pass_reasons="outperformed SPY",
            category_scores=["not", "a", "dict"],
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] in {"AVOID", "WAIT"}


def test_missing_ema_and_volume_fields_do_not_crash_and_degrade_safely():
    signal = _signal()
    for key in ["ema20", "ema50", "volume", "avg_volume"]:
        signal.pop(key)

    result = evaluate_signal_decision(
        signal,
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("unavailable" in warning.lower() for warning in result["risk_warnings"])
    assert "NO_VOLUME_CONFIRMATION" in result["risk_flags"]


def test_risk_reward_between_watchlist_and_entry_threshold_returns_wait():
    result = evaluate_signal_decision(
        _signal(trade_plan={"entry": 100.0, "stop_loss": 94.0, "expected_rr": 2.2}),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("risk/reward" in warning.lower() for warning in result["risk_warnings"])


def test_excessive_stop_distance_returns_avoid():
    result = evaluate_signal_decision(
        _signal(trade_plan={"entry": 100.0, "stop_loss": 78.0, "expected_rr": 2.5}),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert any("stop distance" in warning.lower() for warning in result["risk_warnings"])


def test_a_grade_wide_stop_calibrates_to_wait_not_avoid():
    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=81,
            volume=1_000_000.0,
            avg_volume=1_000_000.0,
            trade_plan={"entry": 100.0, "stop_loss": 87.0, "expected_rr": 2.5},
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert result["main_reason"] == "Setup quality is strong, but current stop distance is too wide for entry."
    assert "WIDE_STOP" in result["risk_flags"]
    assert "NO_VOLUME_CONFIRMATION" in result["risk_flags"]
    assert "Wait for a tighter stop below the V3 ENTER risk limit." in result["wait_conditions"]
    assert "Wait for acceptable volume confirmation." in result["wait_conditions"]
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_b_grade_wide_stop_calibrates_to_watchlist_only_not_avoid():
    result = evaluate_signal_decision(
        _signal(
            grade="B",
            score=74,
            is_actual_breakout=False,
            is_near_breakout=True,
            trade_plan={"entry": 100.0, "stop_loss": 85.5, "expected_rr": 2.5},
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WATCHLIST_ONLY"
    assert result["main_reason"] == "Setup is promising but not actionable yet."
    assert result["next_action"] == "Keep on watchlist until the setup confirms a cleaner trigger."
    assert "WIDE_STOP" in result["risk_flags"]
    assert result["wait_conditions"] == []
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_extended_entry_plus_very_wide_stop_remains_avoid():
    result = evaluate_signal_decision(
        _signal(
            grade="B",
            score=74,
            close=100.0,
            ema20=84.0,
            ema50=82.0,
            is_actual_breakout=False,
            is_near_breakout=True,
            trade_plan={"entry": 100.0, "stop_loss": 84.0, "expected_rr": 2.5},
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert "EXTENDED_ENTRY" in result["risk_flags"]
    assert "WIDE_STOP" in result["risk_flags"]


def test_no_volume_confirmation_alone_does_not_force_avoid():
    result = evaluate_signal_decision(
        _signal(volume=1_000_000.0, avg_volume=1_000_000.0),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert "NO_VOLUME_CONFIRMATION" in result["risk_flags"]
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_enter_remains_strict_for_stop_distance():
    result = evaluate_signal_decision(
        _signal(
            grade="A",
            score=82,
            volume=1_500_000.0,
            avg_volume=1_000_000.0,
            trade_plan={"entry": 100.0, "stop_loss": 91.5, "expected_rr": 2.5},
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] != "ENTER"
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_severe_extension_returns_avoid():
    result = evaluate_signal_decision(
        _signal(close=100.0, ema20=72.0, ema50=70.0),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert any("extended" in warning.lower() for warning in result["risk_warnings"])


def test_invalid_risk_or_weak_grade_returns_avoid():
    result = evaluate_signal_decision(
        _signal(grade="C", score=55, trade_plan={"entry": 100.0, "stop_loss": 101.0, "expected_rr": 0.5}),
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert result["risk_warnings"]
    assert result["trade_risk_mode"] == "NO_TRADE"
    assert result["invalidation"]


def test_missing_entry_blocks_enter():
    result = evaluate_signal_decision(
        _signal(trade_plan={"stop_loss": 94.0, "expected_rr": 2.5}),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] != "ENTER"
    assert "MISSING_ENTRY" in result["risk_flags"]
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_missing_stop_blocks_enter():
    result = evaluate_signal_decision(
        _signal(trade_plan={"entry": 100.0, "expected_rr": 2.5}),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] != "ENTER"
    assert "MISSING_STOP" in result["risk_flags"]
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_stop_at_or_above_entry_blocks_enter():
    result = evaluate_signal_decision(
        _signal(trade_plan={"entry": 100.0, "stop_loss": 100.0, "expected_rr": 2.5}),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] != "ENTER"
    assert "INVALID_STOP" in result["risk_flags"]
    assert result["trade_risk_mode"] == "NO_TRADE"


def test_generic_setup_evidence_flag_when_pass_reasons_are_missing():
    result = evaluate_signal_decision(
        _signal(pass_reasons=[]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert "GENERIC_SETUP_EVIDENCE" in result["risk_flags"]
