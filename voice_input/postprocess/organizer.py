from __future__ import annotations

from collections.abc import Callable
import json
import urllib.error
import urllib.request
from typing import Any

from voice_input.config import (
    DEFAULT_ORGANIZER_MODEL,
    ORGANIZER_PROVIDER_DEEPSEEK,
)


class TextOrganizerError(RuntimeError):
    pass


class ChatCompletionTextOrganizer:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str = DEFAULT_ORGANIZER_MODEL,
        provider: str = ORGANIZER_PROVIDER_DEEPSEEK,
        timeout: int = 45,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = endpoint.strip().rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_ORGANIZER_MODEL
        self.provider = provider.strip().lower() or ORGANIZER_PROVIDER_DEEPSEEK
        self.timeout = max(5, timeout)
        self._urlopen = urlopen or urllib.request.urlopen

    def organize(self, text: str) -> str:
        value = text.strip()
        if not value:
            return ""
        if not self.api_key:
            raise TextOrganizerError("缺少整理模型 API Key，请配置 VOICE_INPUT_ORGANIZER_API_KEY。")
        if not self.endpoint:
            raise TextOrganizerError("缺少整理模型 Endpoint，请配置 VOICE_INPUT_ORGANIZER_ENDPOINT。")

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(self._payload(value), ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self._urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise TextOrganizerError(f"整理模型请求失败: HTTP {exc.code} {body[:300]}") from exc
        except urllib.error.URLError as exc:
            raise TextOrganizerError(f"整理模型请求失败: {exc.reason}") from exc
        except OSError as exc:
            raise TextOrganizerError(f"整理模型请求失败: {exc}") from exc

        try:
            body = json.loads(raw_body)
            content = str(body["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TextOrganizerError("整理模型返回格式无法解析。") from exc

        content = _strip_code_fence(content)
        if not content:
            raise TextOrganizerError("整理模型返回空文本。")
        return content

    def _payload(self, text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是中文语音输入整理器。把 ASR 转写整理成可直接输入的文本。"
                        "保留原意和信息，不扩写事实；删除口水话、重复、停顿词和自我修正；"
                        "按自然书面语重组句子，必要时分段。不要解释，不要加标题，不要输出 Markdown。"
                        "如果原文是英文或中英混合，保留原语言风格。"
                    ),
                },
                {"role": "user", "content": text},
            ],
            "stream": False,
        }
        if self.provider == ORGANIZER_PROVIDER_DEEPSEEK:
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = "high"
        return payload


def _strip_code_fence(text: str) -> str:
    value = text.strip()
    if not value.startswith("```"):
        return value
    lines = value.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return value
