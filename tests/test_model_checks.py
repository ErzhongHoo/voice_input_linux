from __future__ import annotations

from voice_input.config import AppConfig, ORGANIZER_PROVIDER_OPENAI_COMPATIBLE
from voice_input.model_checks import ModelConnectionError, check_asr_connection, check_organizer_connection


def test_check_asr_connection_accepts_mock() -> None:
    assert check_asr_connection(AppConfig(asr_provider="mock")) == "mock ASR 可用"


def test_check_asr_connection_reports_missing_doubao_fields() -> None:
    try:
        check_asr_connection(AppConfig(asr_provider="doubao"))
    except ModelConnectionError as exc:
        assert "App Key" in str(exc)
        assert "Access Key" in str(exc)
    else:
        raise AssertionError("expected ModelConnectionError")


def test_check_asr_connection_reports_missing_qwen_fields() -> None:
    try:
        check_asr_connection(AppConfig(asr_provider="qwen", qwen_api_key=""))
    except ModelConnectionError as exc:
        assert "API Key" in str(exc)
    else:
        raise AssertionError("expected ModelConnectionError")


def test_check_asr_connection_accepts_qwen(monkeypatch) -> None:
    called: dict[str, object] = {}

    async def fake_check(config: AppConfig, timeout: int) -> None:
        called["model"] = config.qwen_model
        called["timeout"] = timeout

    monkeypatch.setattr("voice_input.model_checks._check_qwen_connection", fake_check)

    config = AppConfig(asr_provider="qwen", qwen_api_key="sk-test")
    assert check_asr_connection(config, timeout=3) == "千问 ASR 连接正常"
    assert called == {"model": "qwen3-asr-flash-realtime", "timeout": 3}


def test_check_organizer_connection_uses_current_config(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOrganizer:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def organize(self, text: str) -> str:
            captured["text"] = text
            return "OK"

    monkeypatch.setattr("voice_input.model_checks.ChatCompletionTextOrganizer", FakeOrganizer)

    config = AppConfig(
        organizer_provider=ORGANIZER_PROVIDER_OPENAI_COMPATIBLE,
        organizer_endpoint="https://example.test/v1/chat/completions",
        organizer_api_key="secret",
        organizer_model="gpt-test",
        organizer_timeout=12,
    )

    assert check_organizer_connection(config) == "整理模型连接正常"
    assert captured["provider"] == ORGANIZER_PROVIDER_OPENAI_COMPATIBLE
    assert captured["endpoint"] == "https://example.test/v1/chat/completions"
    assert captured["api_key"] == "secret"
    assert captured["model"] == "gpt-test"
    assert captured["timeout"] == 12
    assert "连通性测试" in str(captured["text"])
