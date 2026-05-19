import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import liquidity_filter
from liquidity_filter import evaluate_liquidity
from relative_strength import evaluate_relative_strength


def _liquidity_row(**overrides):
    data = {
        "ticker": "AAPL",
        "close": 100.0,
        "avg_volume": 2_000_000.0,
        "avg_dollar_volume": 200_000_000.0,
        "market_cap": 2_500_000_000.0,
    }
    data.update(overrides)
    return data


def test_liquidity_passes_when_price_volume_dollar_volume_and_market_cap_pass():
    result = evaluate_liquidity(_liquidity_row())

    assert result["passed"] is True
    assert result["score"] == 10
    assert result["reject_reasons"] == []


def test_liquidity_rejects_low_quality_names_with_clear_reasons():
    result = evaluate_liquidity(_liquidity_row(
        close=9.99,
        avg_volume=999_999.0,
        avg_dollar_volume=19_999_999.0,
        market_cap=1_999_999_999.0,
    ))

    assert result["passed"] is False
    assert "price < 10.00" in result["reject_reasons"]
    assert "20d avg volume < 1000000" in result["reject_reasons"]
    assert "20d avg dollar volume < 20000000" in result["reject_reasons"]
    assert "market cap < 2000000000" in result["reject_reasons"]


def test_liquidity_missing_market_cap_logs_reason_but_does_not_reject(caplog):
    caplog.set_level(logging.WARNING, logger="liquidity_filter")

    result = evaluate_liquidity(_liquidity_row(market_cap=None))

    assert result["passed"] is True
    assert "market cap unavailable" in result["reasons"]
    assert "market cap unavailable" in caplog.text.lower()


def test_liquidity_missing_market_cap_can_suppress_warning_without_rejecting(caplog):
    caplog.set_level(logging.WARNING, logger="liquidity_filter")

    result = evaluate_liquidity(
        _liquidity_row(market_cap=None),
        log_market_cap_warning=False,
    )

    assert result["passed"] is True
    assert "market cap unavailable" in result["reasons"]
    assert "market cap unavailable" not in caplog.text.lower()


def test_metadata_fetch_default_logs_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="liquidity_filter")

    def fail_ticker(ticker):
        raise RuntimeError("metadata service down")

    monkeypatch.setattr(liquidity_filter.yf, "Ticker", fail_ticker)

    result = liquidity_filter.fetch_ticker_metadata("AAPL")

    assert result == {"market_cap": None, "sector": None}
    assert "metadata fetch failed" in caplog.text
    assert "RuntimeError" in caplog.text


def test_metadata_fetch_warning_can_be_suppressed(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="liquidity_filter")

    def fail_ticker(ticker):
        raise RuntimeError("metadata service down")

    monkeypatch.setattr(liquidity_filter.yf, "Ticker", fail_ticker)

    result = liquidity_filter.fetch_ticker_metadata("AAPL", log_warnings=False)

    assert result == {"market_cap": None, "sector": None}
    assert "metadata fetch failed" not in caplog.text


def test_metadata_enrichment_can_skip_yfinance_fetch(monkeypatch):
    def fail_ticker(ticker):
        raise AssertionError("dry-run metadata skip must not call yfinance")

    monkeypatch.setattr(liquidity_filter.yf, "Ticker", fail_ticker)

    result = liquidity_filter.enrich_with_market_metadata(
        _liquidity_row(ticker="AAPL", market_cap=None),
        fetch_metadata=False,
        log_warnings=False,
    )

    assert result["ticker"] == "AAPL"
    assert result["market_cap"] is None
    assert result["sector"] is None


def test_relative_strength_passes_when_stock_beats_spy_or_qqq():
    result = evaluate_relative_strength(
        {"ticker": "AAPL", "return_20d": 6.0},
        spy_return_20d=4.0,
        qqq_return_20d=7.0,
    )

    assert result["passed"] is True
    assert result["score"] == 15
    assert "outperformed SPY" in result["reasons"]


def test_relative_strength_rejects_when_stock_lags_both_benchmarks():
    result = evaluate_relative_strength(
        {"ticker": "AAPL", "return_20d": 3.0},
        spy_return_20d=4.0,
        qqq_return_20d=5.0,
    )

    assert result["passed"] is False
    assert result["score"] == 0
    assert "did not outperform SPY or QQQ" in result["reject_reasons"]


def test_relative_strength_default_logs_lagging_ticker(caplog):
    caplog.set_level(logging.INFO, logger="relative_strength")

    result = evaluate_relative_strength(
        {"ticker": "AAPL", "return_20d": 3.0},
        spy_return_20d=4.0,
        qqq_return_20d=5.0,
    )

    assert result["passed"] is False
    assert "[RelativeStrength] AAPL: lagged SPY/QQQ" in caplog.text


def test_relative_strength_can_suppress_lagging_ticker_log(caplog):
    caplog.set_level(logging.INFO, logger="relative_strength")

    result = evaluate_relative_strength(
        {"ticker": "AAPL", "return_20d": 3.0},
        spy_return_20d=4.0,
        qqq_return_20d=5.0,
        log_lagging=False,
    )

    assert result["passed"] is False
    assert result["score"] == 0
    assert "did not outperform SPY or QQQ" in result["reject_reasons"]
    assert "lagged SPY/QQQ" not in caplog.text
