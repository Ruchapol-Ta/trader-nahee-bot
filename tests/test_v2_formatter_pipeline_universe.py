import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import v2_engine
from message_formatter import (
    format_market_summary,
    format_trade_signal_message,
    format_watchlist_summary,
)
from universe import dedupe_tickers


def _regime(**overrides):
    data = {
        "is_valid": True,
        "summary": "Bullish market regime",
        "invalid_reasons": [],
    }
    data.update(overrides)
    return data


def _signal(**overrides):
    data = {
        "ticker": "AAPL",
        "setup_type": "VCP Breakout",
        "grade": "A+",
        "score": 91,
        "close": 100.0,
        "trade_plan": {
            "entry": 100.0,
            "buy_stop": 101.1,
            "stop_loss": 93.53,
            "target_1": 116.18,
            "target_2": 125.88,
            "expected_rr": 2.5,
            "position_size": "Portfolio size required",
            "holding_style": "Swing: 3 trading days to 8 weeks; trail with 10EMA/20EMA",
        },
        "pass_reasons": [
            "market regime bullish",
            "trend structure bullish",
            "outperformed SPY",
            "breakout above pivot",
        ],
        "invalid_condition": "None",
        "market_regime": "Bullish market regime",
    }
    data.update(overrides)
    return data


def _candidate_row(**overrides):
    data = {
        "ticker": "AAPL",
        "close": 100.0,
        "high": 101.0,
        "ema50": 92.0,
        "ema200": 80.0,
        "high_52w": 102.0,
        "range_5d_pct": 0.035,
        "range_10d_pct": 0.050,
        "range_20d_pct": 0.080,
        "atr": 2.0,
        "atr_sma20": 2.5,
        "consolidation_volume": 800_000.0,
        "avg_volume": 1_200_000.0,
        "avg_dollar_volume": 120_000_000.0,
        "volume": 1_500_000.0,
        "pivot": 99.0,
        "contraction_low": 94.0,
        "pivot_low": 95.0,
        "return_20d": 6.0,
        "market_cap": 3_000_000_000.0,
    }
    data.update(overrides)
    return data


def test_trade_signal_message_contains_required_v2_fields_without_becoming_huge():
    message = format_trade_signal_message(_signal())

    assert "📈 AAPL - VCP Breakout" in message
    assert "🏛 Market: Bullish market regime" in message
    assert "🏅 A+ | Score 91" in message
    assert "🟢 Entry: $100.00" in message
    assert "🔴 Stop: $93.53" in message
    assert "🎯 T1: $116.18 | T2: $125.88" in message
    assert "⚖️ R:R: 2.5R" in message
    assert "Position size: Portfolio size required" in message
    assert "⚠️ Invalid: None" in message
    assert "\n\n" in message
    assert len(message) < 1200


def test_market_summary_and_watchlist_are_short_and_readable():
    market_message = format_market_summary(_regime(is_valid=False, invalid_reasons=["SPY close <= 50EMA"]))
    watchlist = format_watchlist_summary([
        _signal(ticker="MSFT", grade="B", score=69, is_near_breakout=True),
        _signal(ticker="NVDA", grade="B", score=74, is_near_breakout=True),
    ], _regime())

    assert "🏛 Market regime: ⚠️ Invalid" in market_message
    assert "SPY close <= 50EMA" in market_message
    assert "📋 Signal Bot V2 - B Watchlist" in watchlist
    assert "👀 NVDA | B | 74" in watchlist
    assert "👀 MSFT | B | 69" in watchlist
    assert watchlist.index("NVDA") < watchlist.index("MSFT")


def test_invalid_market_regime_stops_before_universe_or_stock_scanning(monkeypatch):
    calls = {"universe": 0, "screen": 0, "market_summary": 0}

    def fake_market_regime():
        return {"is_valid": False, "summary": "Invalid", "invalid_reasons": ["QQQ close <= 50EMA"]}

    def fail_universe():
        calls["universe"] += 1
        raise AssertionError("universe should not load when market regime is invalid")

    def fail_screen(tickers):
        calls["screen"] += 1
        raise AssertionError("stock scan should not run when market regime is invalid")

    def fake_market_summary(regime):
        calls["market_summary"] += 1
        return 1

    monkeypatch.setattr(v2_engine, "load_market_regime", fake_market_regime)
    monkeypatch.setattr(v2_engine, "get_v2_universe", fail_universe)
    monkeypatch.setattr(v2_engine, "screen_universe", fail_screen)
    monkeypatch.setattr(v2_engine, "send_v2_market_summary", fake_market_summary)

    result = v2_engine.run_v2_scan()

    assert result["market_regime_valid"] is False
    assert calls == {"universe": 0, "screen": 0, "market_summary": 1}


def test_failed_breakout_or_near_breakout_cannot_be_rescued_by_high_score(monkeypatch):
    monkeypatch.setattr(v2_engine, "enrich_with_market_metadata", lambda data: data)

    result = v2_engine.qualify_snapshot(
        _candidate_row(close=96.0, pivot=100.0),
        _regime(reasons=["market regime bullish"]),
        spy_return=4.0,
        qqq_return=5.0,
    )

    assert result is None


def test_near_breakout_candidate_is_b_watchlist_only(monkeypatch):
    captured = {"trade_signals": None, "watchlist": None}

    monkeypatch.setattr(
        v2_engine,
        "load_market_regime",
        lambda: _regime(market_data={"SPY": {"return_20d": 1.0}, "QQQ": {"return_20d": 2.0}}),
    )
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["NEAR"])
    monkeypatch.setattr(
        v2_engine,
        "screen_universe",
        lambda tickers: [_candidate_row(ticker="NEAR", close=98.8, high=99.0, pivot=100.0)],
    )
    monkeypatch.setattr(v2_engine, "enrich_with_market_metadata", lambda data: data)

    def fake_report(market_regime, trade_signals, watchlist, stats):
        captured["trade_signals"] = trade_signals
        captured["watchlist"] = watchlist
        return 1

    monkeypatch.setattr(v2_engine, "send_v2_report", fake_report)

    result = v2_engine.run_v2_scan()

    assert captured["trade_signals"] == []
    assert len(captured["watchlist"]) == 1
    assert captured["watchlist"][0]["ticker"] == "NEAR"
    assert captured["watchlist"][0]["grade"] == "B"
    assert result["funnel"]["near_breakout_candidates"] == 1


def test_actual_breakout_can_become_trade_alert_when_score_is_high(monkeypatch):
    captured = {"trade_signals": None, "watchlist": None}

    monkeypatch.setattr(
        v2_engine,
        "load_market_regime",
        lambda: _regime(market_data={"SPY": {"return_20d": 1.0}, "QQQ": {"return_20d": 2.0}}),
    )
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["BO"])
    monkeypatch.setattr(v2_engine, "screen_universe", lambda tickers: [_candidate_row(ticker="BO")])
    monkeypatch.setattr(v2_engine, "enrich_with_market_metadata", lambda data: data)

    def fake_report(market_regime, trade_signals, watchlist, stats):
        captured["trade_signals"] = trade_signals
        captured["watchlist"] = watchlist
        return 1

    monkeypatch.setattr(v2_engine, "send_v2_report", fake_report)

    result = v2_engine.run_v2_scan()

    assert len(captured["trade_signals"]) == 1
    assert captured["trade_signals"][0]["grade"] in {"A+", "A"}
    assert captured["watchlist"] == []
    assert result["funnel"]["actual_breakout_candidates"] == 1


def test_valid_lower_quality_setup_becomes_b_watchlist_candidate(monkeypatch):
    monkeypatch.setattr(v2_engine, "enrich_with_market_metadata", lambda data: data)

    result = v2_engine.qualify_snapshot(
        _candidate_row(
            close=100.0,
            high_52w=105.0,
            range_5d_pct=0.067,
            range_10d_pct=0.079,
            range_20d_pct=0.080,
            atr=2.24,
            atr_sma20=2.50,
            consolidation_volume=959_000.0,
            avg_volume=1_200_000.0,
            volume=1_205_000.0,
            pivot=99.90,
        ),
        _regime(reasons=["market regime bullish"]),
        spy_return=4.0,
        qqq_return=5.0,
    )

    assert result is not None
    assert result["grade"] == "B"
    assert 65 <= result["score"] <= 74


def test_c_and_reject_candidates_are_not_sent_to_telegram(monkeypatch):
    captured = {"trade_signals": None, "watchlist": None}

    monkeypatch.setattr(
        v2_engine,
        "load_market_regime",
        lambda: _regime(market_data={"SPY": {"return_20d": 1.0}, "QQQ": {"return_20d": 2.0}}),
    )
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["CANDIDATE", "REJECT"])
    monkeypatch.setattr(
        v2_engine,
        "screen_universe",
        lambda tickers: [
            _candidate_row(ticker="CANDIDATE"),
            _candidate_row(ticker="REJECT"),
        ],
    )

    def fake_qualify(snapshot, market_regime, spy_return, qqq_return, **kwargs):
        if snapshot["ticker"] == "CANDIDATE":
            return _signal(ticker="CANDIDATE", grade="C", score=58)
        return None

    def fake_report(market_regime, trade_signals, watchlist, stats):
        captured["trade_signals"] = trade_signals
        captured["watchlist"] = watchlist
        return 1

    monkeypatch.setattr(v2_engine, "qualify_snapshot", fake_qualify)
    monkeypatch.setattr(v2_engine, "send_v2_report", fake_report)

    result = v2_engine.run_v2_scan()

    assert captured["trade_signals"] == []
    assert captured["watchlist"] == []
    assert result["funnel"]["C_count"] == 1


def test_trade_alerts_are_capped_by_max_new_positions_per_day(monkeypatch):
    captured = {"trade_count": None}

    monkeypatch.setattr(
        v2_engine,
        "load_market_regime",
        lambda: _regime(market_data={"SPY": {"return_20d": 1.0}, "QQQ": {"return_20d": 2.0}}),
    )
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["A", "B", "C"])
    monkeypatch.setattr(
        v2_engine,
        "screen_universe",
        lambda tickers: [_candidate_row(ticker=ticker) for ticker in tickers],
    )
    monkeypatch.setattr(
        v2_engine,
        "qualify_snapshot",
        lambda snapshot, market_regime, spy_return, qqq_return, **kwargs: _signal(
            ticker=snapshot["ticker"],
            grade="A+",
            score=90,
        ),
    )

    def fake_report(market_regime, trade_signals, watchlist, stats):
        captured["trade_count"] = len(trade_signals)
        return 1

    monkeypatch.setattr(v2_engine, "send_v2_report", fake_report)

    result = v2_engine.run_v2_scan()

    assert result["market_regime_valid"] is True
    assert captured["trade_count"] == 2


def test_v2_scan_reports_filter_funnel_and_reject_aggregation(monkeypatch):
    captured = {"stats": None}

    monkeypatch.setattr(
        v2_engine,
        "load_market_regime",
        lambda: _regime(market_data={"SPY": {"return_20d": 1.0}, "QQQ": {"return_20d": 2.0}}),
    )
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["PASS", "TREND", "RS", "HIGH"])
    monkeypatch.setattr(
        v2_engine,
        "screen_universe",
        lambda tickers: [
            _candidate_row(ticker="PASS"),
            _candidate_row(ticker="TREND", ema50=110.0),
            _candidate_row(ticker="RS", return_20d=0.5),
            _candidate_row(ticker="HIGH", high_52w=120.0),
        ],
    )
    monkeypatch.setattr(v2_engine, "enrich_with_market_metadata", lambda data: data)

    def fake_report(market_regime, trade_signals, watchlist, stats):
        captured["stats"] = stats
        return 1

    monkeypatch.setattr(v2_engine, "send_v2_report", fake_report)

    result = v2_engine.run_v2_scan()

    assert result["funnel"]["scanned"] == 4
    assert result["funnel"]["liquidity_passed"] == 4
    assert result["funnel"]["trend_passed"] == 3
    assert result["funnel"]["relative_strength_passed"] == 3
    assert result["funnel"]["high_52w_passed"] == 3
    assert result["funnel"]["breakout_passed"] == 4
    assert result["reject_reasons"]["rejected_by_trend"] == 1
    assert result["reject_reasons"]["rejected_by_relative_strength"] == 1
    assert result["funnel"]["hard_gate_passed"] == 2
    assert result["funnel"]["actual_breakout_candidates"] == 2
    assert result["funnel"]["A_plus_count"] == 2
    assert result["funnel"]["B_watchlist_count"] == 0
    assert result["funnel"]["C_count"] == 0
    assert captured["stats"]["funnel"]["final_setup_passed"] == 2


def test_debug_mode_collects_top_near_miss_candidates(monkeypatch):
    monkeypatch.setattr(
        v2_engine,
        "load_market_regime",
        lambda: _regime(market_data={"SPY": {"return_20d": 1.0}, "QQQ": {"return_20d": 2.0}}),
    )
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["MISS"])
    monkeypatch.setattr(
        v2_engine,
        "screen_universe",
        lambda tickers: [_candidate_row(
            ticker="MISS",
            close=96.0,
            pivot=99.0,
            high_52w=105.0,
            return_20d=3.0,
        )],
    )
    monkeypatch.setattr(v2_engine, "enrich_with_market_metadata", lambda data: data)
    monkeypatch.setattr(v2_engine, "send_v2_report", lambda *args: 1)

    result = v2_engine.run_v2_scan(debug=True)

    assert result["near_misses"]
    near_miss = result["near_misses"][0]
    assert near_miss["ticker"] == "MISS"
    assert "close is not above or within near-breakout range of pivot/resistance" in near_miss["failed_conditions"]
    assert near_miss["distance_from_52w_high_pct"] == 8.57
    assert near_miss["relative_strength_20d"] == 3.0
    assert near_miss["breakout_status"] is False


def test_duplicate_tickers_are_deduped_and_sorted_for_v2_universe():
    assert dedupe_tickers(["MSFT", "AAPL", "BRK.B"], ["AAPL", "GOOG", "BRK-B"]) == [
        "AAPL",
        "BRK-B",
        "GOOG",
        "MSFT",
    ]
