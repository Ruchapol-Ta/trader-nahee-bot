import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def _signal(ticker, grade, score, actual=True, near=False):
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
            "target_1": 115.0,
            "target_2": 124.0,
            "expected_rr": 2.5,
            "position_size": "Portfolio size required",
        },
        "is_actual_breakout": actual,
        "is_near_breakout": near,
        "pass_reasons": ["breakout above pivot"],
        "invalid_condition": "None",
        "market_regime": "Bullish market regime",
    }


def test_v3_annotation_does_not_filter_reorder_or_suppress_v2_selected_signals(monkeypatch):
    captured = {"trade_signals": None, "watchlist": None}
    qualified = {
        "FIRST": _signal("FIRST", "A+", 95),
        "SECOND": _signal("SECOND", "A", 80),
        "WATCH": _signal("WATCH", "B", 70, actual=False, near=True),
        "LOW": _signal("LOW", "C", 55),
    }

    monkeypatch.setattr(v2_engine, "ENABLE_V3_DECISION_LAYER", True)
    monkeypatch.setattr(v2_engine, "ENABLE_POSITION_SIZING", True)
    monkeypatch.setattr(v2_engine, "ENABLE_SIGNAL_JOURNAL", True)
    monkeypatch.setattr(v2_engine, "load_market_regime", lambda: _regime())
    monkeypatch.setattr(v2_engine, "get_v2_universe", lambda: ["FIRST", "SECOND", "WATCH", "LOW"])
    monkeypatch.setattr(v2_engine, "screen_universe", lambda tickers: [{"ticker": ticker} for ticker in tickers])
    monkeypatch.setattr(
        v2_engine,
        "qualify_snapshot",
        lambda snapshot, market_regime, spy_return, qqq_return, **kwargs: qualified[snapshot["ticker"]],
    )

    def fake_report(market_regime, trade_signals, watchlist, stats):
        captured["trade_signals"] = trade_signals
        captured["watchlist"] = watchlist
        return 1

    journaled = []

    def fake_journal_signals(trade_signals, watchlist, run_id=None):
        journaled.extend([("trade_alert", item["ticker"]) for item in trade_signals])
        journaled.extend([("watchlist", item["ticker"]) for item in watchlist])
        return len(journaled)

    monkeypatch.setattr(v2_engine, "send_v2_report", fake_report)
    monkeypatch.setattr(v2_engine, "journal_signals", fake_journal_signals)

    v2_engine.run_v2_scan()

    assert [item["ticker"] for item in captured["trade_signals"]] == ["FIRST", "SECOND"]
    assert [item["ticker"] for item in captured["watchlist"]] == ["WATCH"]
    assert [item["ticker"] for item in captured["trade_signals"] if item.get("v3_decision")] == ["FIRST", "SECOND"]
    assert [item["ticker"] for item in captured["watchlist"] if item.get("v3_decision")] == ["WATCH"]
    assert journaled == [("trade_alert", "FIRST"), ("trade_alert", "SECOND"), ("watchlist", "WATCH")]
    assert all("v3_decision" not in signal for signal in qualified.values())
    assert all("v3_position_size" not in signal for signal in qualified.values())
