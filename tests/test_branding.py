import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from formatter import format_signal_message, format_summary_message
import telegram_sender

FORBIDDEN_BRAND = "Trader" + "KP"
FORBIDDEN_HASHTAG = "#" + FORBIDDEN_BRAND


def _sample_signal() -> dict:
    return {
        "ticker": "AAPL",
        "signal_type": "BULLISH",
        "open": 99.0,
        "low": 98.5,
        "close": 100.0,
        "pct_change": 1.25,
        "ema20": 99.0,
        "ema50": 95.0,
        "ema200": 90.0,
        "rsi": 55.0,
        "volume": 2_000_000,
        "avg_volume": 1_000_000,
        "vol_sma20": 1_000_000,
        "sl": 93.06,
        "tp2": 113.88,
        "tp3": 120.82,
    }


def test_formatted_signal_messages_do_not_include_traderkp_brand():
    signal = _sample_signal()

    assert FORBIDDEN_BRAND not in format_signal_message(signal)
    assert FORBIDDEN_HASHTAG not in format_signal_message(signal)
    assert FORBIDDEN_BRAND not in format_summary_message([signal])


def test_telegram_status_messages_do_not_include_traderkp_brand(monkeypatch):
    sent: list[str] = []

    def fake_send_message(text: str, *args, **kwargs) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr(telegram_sender, "send_message", fake_send_message)

    telegram_sender.send_error_alert("boom")
    telegram_sender.send_signals([])

    assert sent
    assert all(FORBIDDEN_BRAND not in message for message in sent)
    assert all(FORBIDDEN_HASHTAG not in message for message in sent)


def test_python_sources_do_not_emit_traderkp_brand():
    root = Path(__file__).resolve().parents[1]
    ignored = {"AGENTS.md", "CLAUDE.md"}
    sources = [
        path
        for path in root.glob("*.py")
        if path.name not in ignored and not path.name.startswith("test_")
    ]

    offenders = [
        path.name
        for path in sources
        if FORBIDDEN_BRAND in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
