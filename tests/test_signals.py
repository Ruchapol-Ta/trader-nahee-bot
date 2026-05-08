# tests/test_signals.py — Unit tests for bullish pullback signal detection.
# Run with: python -m pytest tests/ -v
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals import detect_signal, filter_signals


def _row(**overrides):
    data = {
        "ticker": "AAPL",
        "open": 99.0,
        "close": 100.0,
        "low": 98.5,
        "ema20": 99.0,
        "ema50": 95.0,
        "ema200": 90.0,
        "rsi": 50.0,
        "volume": 2_000_000.0,
        "vol_sma20": 1_500_000.0,
        "swing_low_5": 94.0,
    }
    data.update(overrides)
    return data


class TestDetectSignal:
    def test_bullish_pullback_all_criteria_match(self):
        assert detect_signal(_row()) == "BULLISH"

    def test_rejects_when_trend_stack_is_not_bullish(self):
        assert detect_signal(_row(ema20=94.0, ema50=95.0, ema200=90.0)) is None
        assert detect_signal(_row(ema20=99.0, ema50=88.0, ema200=90.0)) is None

    def test_rejects_when_low_does_not_touch_ema20_or_ema50_tolerance(self):
        assert detect_signal(_row(low=101.0, ema20=99.0, ema50=95.0)) is None

    def test_accepts_pullback_touching_ema20_or_ema50_within_one_percent(self):
        assert detect_signal(_row(low=99.99, ema20=99.0, ema50=95.0)) == "BULLISH"
        assert detect_signal(_row(low=95.95, ema20=120.0, ema50=95.0)) == "BULLISH"

    def test_rejects_when_latest_candle_is_not_bullish(self):
        assert detect_signal(_row(open=101.0, close=100.0)) is None

    def test_rejects_when_rsi_outside_pullback_zone(self):
        assert detect_signal(_row(rsi=39.9)) is None
        assert detect_signal(_row(rsi=60.1)) is None

    def test_rejects_when_volume_is_below_twenty_day_average(self):
        assert detect_signal(_row(volume=999_999.0, vol_sma20=1_000_000.0)) is None

    def test_missing_keys_return_none(self):
        assert detect_signal({"ticker": "AAPL"}) is None
        assert detect_signal({}) is None


class TestFilterSignals:
    def test_adds_bullish_type_and_two_three_risk_targets(self):
        out = filter_signals([_row(close=100.0, swing_low_5=94.0)])

        assert len(out) == 1
        signal = out[0]
        assert signal["signal_type"] == "BULLISH"
        assert signal["sl"] == 93.06
        assert signal["tp2"] == 113.88
        assert signal["tp3"] == 120.82

    def test_returns_only_matching_bullish_pullbacks(self):
        out = filter_signals([
            _row(ticker="GOOD"),
            _row(ticker="BAD", close=95.0, open=100.0),
        ])

        assert [signal["ticker"] for signal in out] == ["GOOD"]
