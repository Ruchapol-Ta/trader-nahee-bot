import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telegram_sender
from message_formatter import format_market_summary


class _FakeResponse:
    status_code = 200
    text = '{"ok": true}'

    def json(self):
        return {"ok": True}


def test_test_target_mode_uses_telegram_test_chat_id(monkeypatch):
    captured = {}
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "test")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", "prod-chat")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    def fake_post(url, json, timeout):
        captured.update(json)
        return _FakeResponse()

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    assert telegram_sender.send_message("hello") is True
    assert captured["chat_id"] == "test-chat"


def test_test_target_mode_does_not_fall_back_to_production_chat(monkeypatch):
    called = False
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "test")
    monkeypatch.delenv("TELEGRAM_TEST_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", "prod-chat")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    def fake_post(url, json, timeout):
        nonlocal called
        called = True
        return _FakeResponse()

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    assert telegram_sender.send_message("hello", max_retries=1) is False
    assert called is False


def test_legacy_telegram_chat_id_still_works_when_target_mode_is_unset(monkeypatch):
    captured = {}
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.delenv("TELEGRAM_TARGET_MODE", raising=False)
    monkeypatch.delenv("TELEGRAM_TEST_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    def fake_post(url, json, timeout):
        captured.update(json)
        return _FakeResponse()

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    assert telegram_sender.send_message("hello") is True
    assert captured["chat_id"] == "legacy-chat"


def test_prod_target_mode_prefers_explicit_prod_chat_id(monkeypatch):
    captured = {}
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", "prod-chat")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    def fake_post(url, json, timeout):
        captured.update(json)
        return _FakeResponse()

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    assert telegram_sender.send_message("hello") is True
    assert captured["chat_id"] == "prod-chat"


def test_prod_target_mode_requires_explicit_prod_chat_id(monkeypatch):
    called = False
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    def fake_post(url, json, timeout):
        nonlocal called
        called = True
        return _FakeResponse()

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    readiness = telegram_sender.check_limited_live_rollout_readiness()

    assert readiness["ready"] is False
    assert readiness["is_live_rollout"] is True
    assert "TELEGRAM_PROD_CHAT_ID is required" in readiness["errors"][0]
    assert telegram_sender.send_message("hello", max_retries=1) is False
    assert called is False


def test_prod_rollout_ready_when_explicit_prod_chat_id_is_present(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", "prod-chat")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    readiness = telegram_sender.check_limited_live_rollout_readiness()

    assert readiness == {
        "ready": True,
        "target_mode": "prod",
        "is_live_rollout": True,
        "errors": [],
    }


def test_test_target_mode_rollout_readiness_does_not_require_prod_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "test")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    readiness = telegram_sender.check_limited_live_rollout_readiness()

    assert readiness == {
        "ready": True,
        "target_mode": "test",
        "is_live_rollout": False,
        "errors": [],
    }


def test_preview_target_mode_rollout_readiness_does_not_require_prod_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "preview")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    readiness = telegram_sender.check_limited_live_rollout_readiness()

    assert readiness == {
        "ready": True,
        "target_mode": "preview",
        "is_live_rollout": False,
        "errors": [],
    }


def test_v3_preview_formatting_does_not_require_prod_rollout_readiness(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "test")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")

    readiness = telegram_sender.check_limited_live_rollout_readiness()
    message = format_market_summary(
        {"is_valid": True, "summary": "Bullish market regime", "invalid_reasons": []}
    )

    assert readiness["ready"] is True
    assert message.startswith("Signal Bot V3 Preview")
