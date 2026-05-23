import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import liquidity_filter
import screener
import yfinance_cache


def test_yfinance_cache_uses_repo_local_cache_dir(monkeypatch, tmp_path):
    calls = []
    target = tmp_path / ".cache" / "py-yfinance"
    monkeypatch.setattr(yfinance_cache, "_DEFAULT_CACHE_DIR", target)
    monkeypatch.setattr(yfinance_cache, "_configured_cache_dir", None)
    monkeypatch.setattr(
        yfinance_cache.yf,
        "set_tz_cache_location",
        lambda path: calls.append(path),
    )

    result = yfinance_cache.configure_yfinance_cache()

    assert result == target.resolve()
    assert target.is_dir()
    assert calls == [str(target.resolve())]


def test_yfinance_cache_setup_is_idempotent(monkeypatch, tmp_path):
    calls = []
    target = tmp_path / ".cache" / "py-yfinance"
    monkeypatch.setattr(yfinance_cache, "_configured_cache_dir", None)
    monkeypatch.setattr(
        yfinance_cache.yf,
        "set_tz_cache_location",
        lambda path: calls.append(path),
    )

    first = yfinance_cache.configure_yfinance_cache(target)
    second = yfinance_cache.configure_yfinance_cache(target)

    assert first == target.resolve()
    assert second == target.resolve()
    assert calls == [str(target.resolve())]


def test_yfinance_cache_setup_failure_logs_warning(monkeypatch, tmp_path, caplog):
    target = tmp_path / ".cache" / "py-yfinance"
    monkeypatch.setattr(yfinance_cache, "_configured_cache_dir", None)

    def fail_set_location(path):
        raise RuntimeError("cache db unavailable")

    monkeypatch.setattr(yfinance_cache.yf, "set_tz_cache_location", fail_set_location)

    with caplog.at_level(logging.WARNING):
        result = yfinance_cache.configure_yfinance_cache(target)

    assert result is None
    assert "Cache setup failed: RuntimeError: cache db unavailable" in caplog.text


def test_screener_download_configures_cache_before_yfinance_download(monkeypatch):
    events = []

    def fake_cache_setup():
        events.append("cache")

    def fake_download(*args, **kwargs):
        events.append("download")
        return pd.DataFrame()

    monkeypatch.setattr(screener, "configure_yfinance_cache", fake_cache_setup)
    monkeypatch.setattr(screener.yf, "download", fake_download)

    result = screener._download_chunk(["SPY"])

    assert result == {}
    assert events == ["cache", "download"]


def test_liquidity_metadata_configures_cache_before_yfinance_ticker(monkeypatch):
    events = []

    def fake_cache_setup():
        events.append("cache")

    class FakeTicker:
        def __init__(self, ticker):
            events.append(f"ticker:{ticker}")

        @property
        def info(self):
            events.append("info")
            return {"marketCap": 123_000_000_000, "sector": "Technology"}

    monkeypatch.setattr(liquidity_filter, "configure_yfinance_cache", fake_cache_setup)
    monkeypatch.setattr(liquidity_filter.yf, "Ticker", FakeTicker)

    result = liquidity_filter.fetch_ticker_metadata("AAPL")

    assert result == {"market_cap": 123_000_000_000, "sector": "Technology"}
    assert events == ["cache", "ticker:AAPL", "info"]
