import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import signal_bot
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


def test_rollout_dry_run_checklist_does_not_call_network_or_send(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", "prod-chat")

    def fail_post(*args, **kwargs):
        raise AssertionError("dry-run checklist must not call Telegram")

    def fail_send_message(*args, **kwargs):
        raise AssertionError("dry-run checklist must not send messages")

    monkeypatch.setattr(telegram_sender.requests, "post", fail_post)
    monkeypatch.setattr(telegram_sender, "send_message", fail_send_message)

    checklist = telegram_sender.build_telegram_rollout_dry_run_checklist()

    assert checklist["ready"] is True
    assert checklist["mode"] == "prod"


def test_rollout_dry_run_unset_target_mode_reports_legacy_fallback(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.delenv("TELEGRAM_TARGET_MODE", raising=False)
    monkeypatch.delenv("TELEGRAM_TEST_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    checklist = telegram_sender.build_telegram_rollout_dry_run_checklist()

    assert checklist["ready"] is True
    assert checklist["target_mode"] == ""
    assert checklist["mode"] == "legacy"
    assert checklist["required_chat_id_name"] == "TELEGRAM_CHAT_ID"
    assert checklist["required_chat_id_present"] is True
    assert checklist["legacy_mode_active"] is True
    assert checklist["legacy_fallback_allowed"] is True
    assert checklist["legacy_fallback_active"] is True


def test_rollout_dry_run_test_mode_does_not_require_prod_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "test")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    checklist = telegram_sender.build_telegram_rollout_dry_run_checklist()

    assert checklist["ready"] is True
    assert checklist["mode"] == "test"
    assert checklist["required_chat_id_name"] == "TELEGRAM_TEST_CHAT_ID"
    assert checklist["required_chat_id_present"] is True
    assert checklist["legacy_fallback_allowed"] is False
    assert checklist["test_mode_requires_telegram_prod_chat_id"] is False


def test_rollout_dry_run_preview_mode_does_not_require_prod_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "preview")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    checklist = telegram_sender.build_telegram_rollout_dry_run_checklist()

    assert checklist["ready"] is True
    assert checklist["mode"] == "preview"
    assert checklist["required_chat_id_name"] == "TELEGRAM_TEST_CHAT_ID"
    assert checklist["required_chat_id_present"] is True
    assert checklist["legacy_fallback_allowed"] is False
    assert checklist["preview_mode_requires_telegram_prod_chat_id"] is False
    assert checklist["v3_preview_format_available_without_prod_rollout"] is True


def test_rollout_dry_run_prod_mode_blocks_legacy_chat_only(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    checklist = telegram_sender.build_telegram_rollout_dry_run_checklist()

    assert checklist["ready"] is False
    assert checklist["mode"] == "prod"
    assert checklist["required_chat_id_name"] == "TELEGRAM_PROD_CHAT_ID"
    assert checklist["required_chat_id_present"] is False
    assert checklist["legacy_fallback_allowed"] is False
    assert checklist["legacy_fallback_active"] is False
    assert checklist["explicit_prod_requires_telegram_prod_chat_id"] is True
    assert checklist["explicit_prod_blocks_legacy_fallback"] is True
    assert "TELEGRAM_PROD_CHAT_ID is required" in checklist["errors"][0]


def test_rollout_dry_run_prod_mode_ready_with_prod_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", "prod-chat")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    checklist = telegram_sender.build_telegram_rollout_dry_run_checklist()

    assert checklist["ready"] is True
    assert checklist["mode"] == "prod"
    assert checklist["required_chat_id_name"] == "TELEGRAM_PROD_CHAT_ID"
    assert checklist["required_chat_id_present"] is True
    assert checklist["legacy_fallback_allowed"] is False
    assert checklist["explicit_prod_blocks_legacy_fallback"] is True
    assert checklist["errors"] == []


def test_rollout_dry_run_checklist_does_not_expose_secret_values(monkeypatch):
    token = "123456789:secret-token-value"
    test_chat = "test-chat-secret-value"
    prod_chat = "prod-chat-secret-value"
    legacy_chat = "legacy-chat-secret-value"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", test_chat)
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", prod_chat)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", legacy_chat)

    checklist_text = repr(telegram_sender.build_telegram_rollout_dry_run_checklist())

    assert token not in checklist_text
    assert test_chat not in checklist_text
    assert prod_chat not in checklist_text
    assert legacy_chat not in checklist_text


def _run_rollout_check_cli(monkeypatch, capsys) -> str:
    monkeypatch.setattr(sys, "argv", ["signal_bot.py", "--telegram-rollout-check"])
    signal_bot.main()
    return capsys.readouterr().out


def test_rollout_check_cli_does_not_call_network_send_scan_or_scheduler(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", "prod-chat")

    def fail_post(*args, **kwargs):
        raise AssertionError("rollout check CLI must not call Telegram")

    def fail_send_message(*args, **kwargs):
        raise AssertionError("rollout check CLI must not send messages")

    def fail_run_scan(*args, **kwargs):
        raise AssertionError("rollout check CLI must not run scans")

    def fail_scheduler(*args, **kwargs):
        raise AssertionError("rollout check CLI must not start scheduler")

    monkeypatch.setattr(telegram_sender.requests, "post", fail_post)
    monkeypatch.setattr(telegram_sender, "send_message", fail_send_message)
    monkeypatch.setattr(signal_bot, "run_scan", fail_run_scan)
    monkeypatch.setattr(signal_bot, "BlockingScheduler", fail_scheduler)

    output = _run_rollout_check_cli(monkeypatch, capsys)

    assert "Telegram Rollout Dry Run" in output
    assert "Overall readiness: ready" in output


def test_rollout_check_cli_output_does_not_expose_secret_values(monkeypatch, capsys):
    token = "123456789:cli-secret-token"
    test_chat = "cli-test-chat-secret"
    prod_chat = "cli-prod-chat-secret"
    legacy_chat = "cli-legacy-chat-secret"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", test_chat)
    monkeypatch.setenv("TELEGRAM_PROD_CHAT_ID", prod_chat)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", legacy_chat)

    output = _run_rollout_check_cli(monkeypatch, capsys)

    assert token not in output
    assert test_chat not in output
    assert prod_chat not in output
    assert legacy_chat not in output
    assert "Required chat id key: TELEGRAM_PROD_CHAT_ID" in output


def test_rollout_check_cli_prod_blocks_legacy_fallback(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "prod")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    output = _run_rollout_check_cli(monkeypatch, capsys)

    assert "Current mode: prod" in output
    assert "Required chat id key: TELEGRAM_PROD_CHAT_ID" in output
    assert "Required chat id present: no" in output
    assert "Legacy fallback active: no" in output
    assert "Prod fallback blocked: yes" in output
    assert "Overall readiness: not ready" in output


def test_rollout_check_cli_test_mode_does_not_require_prod_chat_id(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "test")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)

    output = _run_rollout_check_cli(monkeypatch, capsys)

    assert "Current mode: test" in output
    assert "Required chat id key: TELEGRAM_TEST_CHAT_ID" in output
    assert "Required chat id present: yes" in output
    assert "Test mode requires prod chat id: no" in output
    assert "Overall readiness: ready" in output


def test_rollout_check_cli_preview_mode_does_not_require_prod_chat_id(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_TARGET_MODE", "preview")
    monkeypatch.setenv("TELEGRAM_TEST_CHAT_ID", "test-chat")
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)

    output = _run_rollout_check_cli(monkeypatch, capsys)

    assert "Current mode: preview" in output
    assert "Required chat id key: TELEGRAM_TEST_CHAT_ID" in output
    assert "Required chat id present: yes" in output
    assert "Preview mode requires prod chat id: no" in output
    assert "Overall readiness: ready" in output


def test_rollout_check_cli_unset_mode_reports_legacy_fallback(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.delenv("TELEGRAM_TARGET_MODE", raising=False)
    monkeypatch.delenv("TELEGRAM_TEST_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_PROD_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "legacy-chat")

    output = _run_rollout_check_cli(monkeypatch, capsys)

    assert "Current mode: legacy" in output
    assert "Required chat id key: TELEGRAM_CHAT_ID" in output
    assert "Required chat id present: yes" in output
    assert "Legacy fallback active: yes" in output
    assert "Prod fallback blocked: no" in output
    assert "Overall readiness: ready" in output
