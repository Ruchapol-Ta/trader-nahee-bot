import os
import sys

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
        lambda snapshot, check_market_cap=False: {"passed": True, "reasons": []},
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
        lambda snapshot, check_market_cap=False: {
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

    monkeypatch.setattr(v2_engine, "send_v2_market_summary", fail_market_summary)
    monkeypatch.setattr(v2_engine, "get_v2_universe", fail_universe)

    result = v2_engine.run_v2_scan(send_telegram=False)

    assert result["market_regime_valid"] is False
    assert result["market_regime"] == "Invalid market"
    assert result["messages_sent"] == 0
    assert result["telegram_skipped"] is True
    assert result["v3_decision_counts"] == {
        "ENTER": 0,
        "WAIT": 0,
        "WATCHLIST_ONLY": 0,
        "AVOID": 0,
        "none": 0,
    }


def test_v3_dry_run_cli_returns_early_without_scheduler_or_telegram(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["signal_bot.py", "--v3-dry-run-review"])
    monkeypatch.setattr(v2_engine, "ENABLE_V3_DECISION_LAYER", False)

    def fake_run_v2_scan(
        *,
        debug=False,
        send_telegram=True,
        write_journal=True,
        log_rejects=True,
    ):
        assert debug is False
        assert send_telegram is False
        assert write_journal is False
        assert log_rejects is False
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
    assert "AAA | A | ENTER | HIGH" in output
    assert v2_engine.ENABLE_V3_DECISION_LAYER is False
