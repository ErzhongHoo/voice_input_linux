from __future__ import annotations

import json
import urllib.request

import pytest

from voice_input.config import ORGANIZER_PROVIDER_DEEPSEEK, ORGANIZER_PROVIDER_OPENAI_COMPATIBLE
from voice_input.postprocess.organizer import ChatCompletionTextOrganizer, TextOrganizerError


class FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_deepseek_provider_posts_chat_completion_payload_with_thinking() -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(bytes(request.data or b"").decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "整理后的文本。"}}]})

    organizer = ChatCompletionTextOrganizer(
        endpoint="https://api.deepseek.com/chat/completions",
        api_key="sk-test",
        model="deepseek-v4-flash",
        provider=ORGANIZER_PROVIDER_DEEPSEEK,
        timeout=30,
        urlopen=fake_urlopen,
    )

    assert organizer.organize("嗯，今天这个事情吧需要处理") == "整理后的文本。"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["timeout"] == 30
    assert captured["authorization"] == "Bearer sk-test"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"
    assert payload["stream"] is False
    assert payload["messages"][-1]["content"] == "嗯，今天这个事情吧需要处理"


def test_openai_compatible_provider_omits_deepseek_thinking_fields() -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["payload"] = json.loads(bytes(request.data or b"").decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "整理后的文本。"}}]})

    organizer = ChatCompletionTextOrganizer(
        endpoint="https://example.test/v1/chat/completions",
        api_key="sk-test",
        model="gpt-test",
        provider=ORGANIZER_PROVIDER_OPENAI_COMPATIBLE,
        urlopen=fake_urlopen,
    )

    assert organizer.organize("hello") == "整理后的文本。"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-test"
    assert "thinking" not in payload
    assert "reasoning_effort" not in payload


def test_organizer_requires_api_key() -> None:
    organizer = ChatCompletionTextOrganizer(
        endpoint="https://api.deepseek.com/chat/completions",
        api_key="",
    )

    with pytest.raises(TextOrganizerError, match="API Key"):
        organizer.organize("hello")
