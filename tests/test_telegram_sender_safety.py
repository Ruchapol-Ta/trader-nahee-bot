import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telegram_sender


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
