import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import universe


class _FakeResponse:
    text = "<html></html>"

    def raise_for_status(self):
        return None


def _mock_wikipedia_tables(monkeypatch, tables):
    calls = {}

    def fake_get(url, headers, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["timeout"] = timeout
        return _FakeResponse()

    def fake_read_html(source):
        calls["read_html_source"] = source
        return tables

    monkeypatch.setattr(universe.requests, "get", fake_get)
    monkeypatch.setattr(universe.pd, "read_html", fake_read_html)
    return calls


def test_nasdaq100_loader_uses_dedicated_companies_page(monkeypatch):
    expected = ["AAPL", "MSFT"] + [
        f"TEST{index:03d}" for index in range(universe.EXPECTED_MIN_NASDAQ - 2)
    ]
    calls = _mock_wikipedia_tables(
        monkeypatch,
        [pd.DataFrame({"Ticker": expected})],
    )

    result = universe.get_nasdaq100_tickers()

    assert result == expected
    assert calls["url"] == (
        "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
    )


def test_nasdaq100_loader_rejects_tables_without_ticker_column(monkeypatch):
    _mock_wikipedia_tables(
        monkeypatch,
        [pd.DataFrame({"Symbol": ["AAPL", "MSFT"]})],
    )

    with pytest.raises(
        universe.UniverseLoadError,
        match=r"Nasdaq 100: 'Ticker' column not found in any table",
    ):
        universe.get_nasdaq100_tickers()


def test_nasdaq100_loader_rejects_too_few_tickers(monkeypatch):
    tickers = [
        f"TEST{index:03d}" for index in range(universe.EXPECTED_MIN_NASDAQ - 1)
    ]
    _mock_wikipedia_tables(
        monkeypatch,
        [pd.DataFrame({"Ticker": tickers})],
    )

    with pytest.raises(
        universe.UniverseLoadError,
        match=rf"Nasdaq 100 returned only {len(tickers)} tickers",
    ):
        universe.get_nasdaq100_tickers()
