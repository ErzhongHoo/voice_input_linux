from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

from .base import AsrClient, AsrError


LOGGER = logging.getLogger(__name__)


class QwenRealtimeASRClient(AsrClient):
    """Alibaba Cloud Bailian Qwen ASR realtime WebSocket client."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        language: str = "zh",
        sample_rate: int = 16000,
        enable_server_vad: bool = True,
        vad_threshold: float = 0.0,
        vad_silence_ms: int = 400,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.enable_server_vad = enable_server_vad
        self.vad_threshold = vad_threshold
        self.vad_silence_ms = vad_silence_ms
        self.request_id = str(uuid.uuid4())
        self._ws: Any | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._session_ready = asyncio.Event()
        self._done = asyncio.Event()
        self._error: AsrError | None = None
        self._completed_order: list[str] = []
        self._completed_by_item: dict[str, str] = {}
        self._current_item_id = ""
        self._current_partial = ""
        self._partial_text = ""
        self._final_text = ""
        self._audio_chunks = 0
        self._audio_bytes = 0

    async def start_session(self) -> None:
        if not self.endpoint:
            raise AsrError("QWEN_ASR_ENDPOINT 未配置")
        if not self.api_key:
            raise AsrError("QWEN_ASR_API_KEY 未配置")
        if not self.model:
            raise AsrError("QWEN_ASR_MODEL 未配置")

        try:
            import websockets
        except Exception as exc:  # noqa: BLE001
            raise AsrError(f"websockets 依赖不可用: {exc}") from exc

        url = qwen_realtime_url(self.endpoint, self.model)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        LOGGER.info("Connecting Qwen ASR endpoint=%s model=%s request_id=%s", self.endpoint, self.model, self.request_id)
        try:
            try:
                self._ws = await websockets.connect(
                    url,
                    additional_headers=headers,
                    max_size=100 * 1024 * 1024,
                )
            except TypeError:
                self._ws = await websockets.connect(
                    url,
                    extra_headers=headers,
                    max_size=100 * 1024 * 1024,
                )
        except Exception as exc:  # noqa: BLE001
            raise AsrError(f"连接千问 ASR 失败: {exc}") from exc

        self._receiver_task = asyncio.create_task(self._receive_loop())
        await self._send_event(self._build_session_update())
        try:
            await asyncio.wait_for(self._session_ready.wait(), timeout=10.0)
        except TimeoutError as exc:
            await self._close()
            raise AsrError("等待千问 ASR session.updated 超时") from exc
        if self._error is not None:
            await self._close()
            raise self._error

    async def send_audio_chunk(self, chunk: bytes) -> None:
        if self._ws is None:
            raise AsrError("ASR session 尚未启动")
        await self._send_event(
            {
                "event_id": _event_id(),
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("ascii"),
            }
        )
        self._audio_chunks += 1
        self._audio_bytes += len(chunk)
        LOGGER.debug("Qwen ASR audio chunk sent bytes=%s", len(chunk))

    async def finish_session(self) -> None:
        if self._ws is None:
            return
        if not self.enable_server_vad and self._audio_chunks:
            await self._send_event({"event_id": _event_id(), "type": "input_audio_buffer.commit"})
        await self._send_event({"event_id": _event_id(), "type": "session.finish"})
        LOGGER.info(
            "Qwen ASR finish request sent request_id=%s chunks=%s bytes=%s",
            self.request_id,
            self._audio_chunks,
            self._audio_bytes,
        )
        try:
            await asyncio.wait_for(self._done.wait(), timeout=30.0)
        except TimeoutError:
            LOGGER.warning("Qwen ASR final response timed out")
        if self._error is not None:
            await self._close()
            raise self._error
        await self._close()

    async def get_partial_text(self) -> str:
        return self._partial_text

    async def get_final_text(self) -> str:
        return self._final_text or self._partial_text

    def _build_session_update(self) -> dict[str, Any]:
        turn_detection: dict[str, Any] | None = None
        if self.enable_server_vad:
            turn_detection = {
                "type": "server_vad",
                "threshold": self.vad_threshold,
                "silence_duration_ms": self.vad_silence_ms,
            }
        return {
            "event_id": _event_id(),
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm",
                "sample_rate": self.sample_rate,
                "input_audio_transcription": {
                    "language": self.language,
                },
                "turn_detection": turn_detection,
            },
        }

    async def _send_event(self, event: dict[str, Any]) -> None:
        if self._ws is None:
            raise AsrError("ASR session 尚未启动")
        await self._ws.send(json.dumps(event, ensure_ascii=False, separators=(",", ":")))

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    message = message.decode("utf-8", errors="replace")
                payload = json.loads(message)
                LOGGER.debug("Qwen ASR event received type=%s", payload.get("type"))
                self._consume_event(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Qwen ASR receive loop failed")
            self._error = exc if isinstance(exc, AsrError) else AsrError(str(exc))
            self._session_ready.set()
            self._done.set()

    def _consume_event(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("type") or "")
        if event_type == "session.updated":
            self._session_ready.set()
            return
        if event_type == "session.finished":
            self._done.set()
            return
        if event_type == "error":
            error = payload.get("error")
            if isinstance(error, dict):
                code = str(error.get("code") or "")
                message = str(error.get("message") or error)
                raise AsrError(f"千问 ASR 服务端错误 code={code}: {message}")
            raise AsrError(f"千问 ASR 服务端错误: {payload}")
        if event_type == "conversation.item.input_audio_transcription.failed":
            error = payload.get("error")
            if isinstance(error, dict):
                code = str(error.get("code") or "")
                message = str(error.get("message") or error)
                raise AsrError(f"千问 ASR 识别失败 code={code}: {message}")
            raise AsrError(f"千问 ASR 识别失败: {payload}")
        if event_type == "conversation.item.input_audio_transcription.text":
            self._current_item_id = str(payload.get("item_id") or self._current_item_id)
            self._current_partial = (str(payload.get("text") or "") + str(payload.get("stash") or "")).strip()
            self._partial_text = self._joined_text(include_current=True)
            return
        if event_type == "conversation.item.input_audio_transcription.completed":
            item_id = str(payload.get("item_id") or payload.get("event_id") or len(self._completed_order))
            transcript = str(payload.get("transcript") or "").strip()
            if transcript:
                if item_id not in self._completed_by_item:
                    self._completed_order.append(item_id)
                self._completed_by_item[item_id] = transcript
                if item_id == self._current_item_id:
                    self._current_partial = ""
                self._final_text = self._joined_text()
                self._partial_text = self._final_text

    def _joined_text(self, include_current: bool = False) -> str:
        parts = [self._completed_by_item[item_id] for item_id in self._completed_order if self._completed_by_item[item_id]]
        if include_current and self._current_partial:
            parts.append(self._current_partial)
        return "".join(parts)

    async def _close(self) -> None:
        if self._receiver_task is not None:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass
            self._receiver_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None


def qwen_realtime_url(endpoint: str, model: str) -> str:
    parts = urlsplit(endpoint.strip())
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if model and "model" not in query:
        query["model"] = model
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _event_id() -> str:
    return "event_" + uuid.uuid4().hex
