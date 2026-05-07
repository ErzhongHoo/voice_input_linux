from __future__ import annotations

import asyncio
import gzip
import json
import logging
from typing import Any
import uuid

from .base import AsrClient, AsrError


LOGGER = logging.getLogger(__name__)

PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_REQUEST = 0b0010
FULL_SERVER_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111

NO_SEQUENCE = 0b0000
POS_SEQUENCE = 0b0001
NEG_SEQUENCE = 0b0010
NEG_WITH_SEQUENCE = 0b0011

NO_SERIALIZATION = 0b0000
JSON_SERIALIZATION = 0b0001

NO_COMPRESSION = 0b0000
GZIP_COMPRESSION = 0b0001


class DoubaoBigASRClient(AsrClient):
    """Volcengine/Doubao bigmodel streaming ASR client.

    This implements the documented v3 OpenSpeech binary WebSocket framing:
    gzip-compressed JSON full request followed by gzip-compressed PCM audio
    frames. Request payload fields are intentionally isolated in
    `_build_start_payload()` because Volcengine keeps adding model options.
    """

    def __init__(
        self,
        endpoint: str,
        app_key: str,
        access_key: str,
        resource_id: str,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        self.endpoint = endpoint
        self.app_key = app_key
        self.access_key = access_key
        self.resource_id = resource_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.request_id = str(uuid.uuid4())
        self._ws: Any | None = None
        self._sequence = 1
        self._receiver_task: asyncio.Task[None] | None = None
        self._partial_text = ""
        self._final_text = ""
        self._done = asyncio.Event()
        self._audio_chunks = 0
        self._audio_bytes = 0

    async def start_session(self) -> None:
        if not self.endpoint:
            raise AsrError("DOUBAO_ASR_ENDPOINT 未配置")
        if not self.app_key or not self.access_key:
            raise AsrError("DOUBAO_ASR_APP_KEY / DOUBAO_ASR_ACCESS_KEY 未配置，请使用 mock 或补齐鉴权")

        try:
            import websockets
        except Exception as exc:  # noqa: BLE001
            raise AsrError(f"websockets 依赖不可用: {exc}") from exc

        headers = {
            "X-Api-App-Key": self.app_key,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": self.request_id,
            "X-Api-Request-Id": self.request_id,
        }
        LOGGER.info("Connecting Doubao ASR endpoint=%s request_id=%s", self.endpoint, self.request_id)
        try:
            try:
                self._ws = await websockets.connect(
                    self.endpoint,
                    additional_headers=headers,
                    max_size=100 * 1024 * 1024,
                )
            except TypeError:
                self._ws = await websockets.connect(
                    self.endpoint,
                    extra_headers=headers,
                    max_size=100 * 1024 * 1024,
                )
        except Exception as exc:  # noqa: BLE001
            raise AsrError(f"连接豆包 ASR 失败: {exc}") from exc

        self._log_response_headers()

        payload = self._build_start_payload()
        await self._ws.send(
            _build_frame(
                message_type=FULL_CLIENT_REQUEST,
                flags=POS_SEQUENCE,
                serialization=JSON_SERIALIZATION,
                compression=GZIP_COMPRESSION,
                payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                sequence=self._sequence,
            )
        )
        LOGGER.info("Doubao ASR start request sent request_id=%s", self.request_id)
        self._sequence += 1
        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def send_audio_chunk(self, chunk: bytes) -> None:
        if self._ws is None:
            raise AsrError("ASR session 尚未启动")
        await self._ws.send(
            _build_frame(
                message_type=AUDIO_ONLY_REQUEST,
                flags=POS_SEQUENCE,
                serialization=NO_SERIALIZATION,
                compression=GZIP_COMPRESSION,
                payload=chunk,
                sequence=self._sequence,
            )
        )
        self._audio_chunks += 1
        self._audio_bytes += len(chunk)
        LOGGER.debug("Doubao ASR audio chunk sent seq=%s bytes=%s", self._sequence, len(chunk))
        self._sequence += 1

    async def finish_session(self) -> None:
        if self._ws is None:
            return
        await self._ws.send(
            _build_frame(
                message_type=AUDIO_ONLY_REQUEST,
                flags=NEG_WITH_SEQUENCE,
                serialization=NO_SERIALIZATION,
                compression=GZIP_COMPRESSION,
                payload=b"",
                sequence=-self._sequence,
            )
        )
        LOGGER.info("Doubao ASR finish request sent seq=%s", -self._sequence)
        LOGGER.info(
            "Doubao ASR audio sent request_id=%s chunks=%s bytes=%s",
            self.request_id,
            self._audio_chunks,
            self._audio_bytes,
        )
        try:
            await asyncio.wait_for(self._done.wait(), timeout=20.0)
        except TimeoutError:
            LOGGER.warning("Doubao ASR final response timed out")
        finally:
            if self._receiver_task:
                self._receiver_task.cancel()
                try:
                    await self._receiver_task
                except asyncio.CancelledError:
                    pass
            await self._ws.close()
            self._ws = None

    async def get_partial_text(self) -> str:
        return self._partial_text

    async def get_final_text(self) -> str:
        return self._final_text or self._partial_text

    def _build_start_payload(self) -> dict[str, Any]:
        # Official bigmodel streaming ASR docs keep `model_name` as bigmodel
        # for both 1.0 and 2.0. The model generation is selected by the
        # X-Api-Resource-Id header, e.g. volc.seedasr.sauc.duration for
        # Doubao streaming speech recognition model 2.0 hourly billing.
        return {
            "user": {"uid": "voice-input-linux"},
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": self.sample_rate,
                "bits": 16,
                "channel": self.channels,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_ddc": False,
                "result_type": "full",
                "show_utterances": True,
                "enable_punc": True,
                "end_window_size": 800,
                "platform": "Linux",
            },
        }

    def _log_response_headers(self) -> None:
        if self._ws is None:
            return
        headers = getattr(self._ws, "response_headers", None)
        response = getattr(self._ws, "response", None)
        if headers is None and response is not None:
            headers = getattr(response, "headers", None)
        if headers is None:
            return
        logid = None
        try:
            logid = headers.get("X-Tt-Logid") or headers.get("x-tt-logid")
        except AttributeError:
            return
        if logid:
            LOGGER.info("Doubao ASR connected request_id=%s logid=%s", self.request_id, logid)

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, str):
                    payload = json.loads(message)
                    LOGGER.info("Doubao ASR text frame received keys=%s text_len=%s", list(payload), len(_extract_text(payload)))
                    self._consume_payload(payload)
                    continue
                frame = _parse_frame(message)
                if frame["message_type"] == SERVER_ERROR_RESPONSE:
                    raise AsrError(
                        f"豆包 ASR 服务端错误 code={frame.get('error_code')}: {frame.get('payload')}"
                    )
                payload = frame.get("payload")
                LOGGER.info(
                    "Doubao ASR frame type=%s flags=%s seq=%s last=%s payload=%s text_len=%s",
                    frame.get("message_type"),
                    frame.get("flags"),
                    frame.get("sequence"),
                    frame.get("is_last"),
                    _payload_summary(payload),
                    len(_extract_text(payload)),
                )
                if payload is not None and len(_extract_text(payload)) == 0:
                    LOGGER.info("Doubao ASR empty-text payload preview=%s", _json_preview(payload))
                if isinstance(payload, dict):
                    self._consume_payload(payload)
                if (
                    frame.get("message_type") == FULL_SERVER_RESPONSE
                    and frame.get("is_last")
                    and payload is not None
                ):
                    self._done.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Doubao ASR receive loop failed")
            self._done.set()
            raise AsrError(str(exc)) from exc

    def _consume_payload(self, payload: dict[str, Any]) -> None:
        text = _extract_text(payload)
        if text:
            self._partial_text = text

        if _looks_final(payload):
            self._final_text = text or self._partial_text
            self._done.set()


def _build_header(
    message_type: int,
    flags: int,
    serialization: int,
    compression: int,
) -> bytes:
    return bytes(
        [
            (PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0x00,
        ]
    )


def _build_frame(
    message_type: int,
    flags: int,
    serialization: int,
    compression: int,
    payload: bytes,
    sequence: int | None = None,
) -> bytes:
    body = gzip.compress(payload) if compression == GZIP_COMPRESSION else payload
    frame = bytearray(_build_header(message_type, flags, serialization, compression))
    if flags & 0b0001:
        if sequence is None:
            raise ValueError("sequence is required when frame flags include sequence")
        frame.extend(int(sequence).to_bytes(4, "big", signed=True))
    frame.extend(len(body).to_bytes(4, "big", signed=False))
    frame.extend(body)
    return bytes(frame)


def _parse_frame(data: bytes) -> dict[str, Any]:
    if len(data) < 4:
        raise AsrError("无效 ASR 响应: header 不足 4 字节")

    header_size = data[0] & 0x0F
    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    offset = header_size * 4

    sequence: int | None = None
    if flags & 0b0001:
        sequence = int.from_bytes(data[offset : offset + 4], "big", signed=True)
        offset += 4

    if message_type == SERVER_ERROR_RESPONSE:
        if len(data) < offset + 8:
            raise AsrError("无效 ASR 错误响应: payload 不足")
        error_code = int.from_bytes(data[offset : offset + 4], "big", signed=False)
        offset += 4
        payload_size = int.from_bytes(data[offset : offset + 4], "big", signed=False)
        offset += 4
        payload = data[offset : offset + payload_size]
        try:
            decoded_error: Any = payload.decode("utf-8")
            if serialization == JSON_SERIALIZATION:
                decoded_error = json.loads(decoded_error)
        except Exception:  # noqa: BLE001
            decoded_error = repr(payload)
        return {
            "message_type": message_type,
            "flags": flags,
            "serialization": serialization,
            "compression": compression,
            "sequence": sequence,
            "error_code": error_code,
            "payload": decoded_error,
            "is_last": False,
        }

    if len(data) < offset + 4:
        return {
            "message_type": message_type,
            "flags": flags,
            "sequence": sequence,
            "payload": None,
            "is_last": bool(flags & 0b0010),
        }

    payload_size = int.from_bytes(data[offset : offset + 4], "big", signed=False)
    offset += 4
    payload = data[offset : offset + payload_size]

    if compression == GZIP_COMPRESSION and payload:
        payload = gzip.decompress(payload)

    decoded: Any = payload
    if serialization == JSON_SERIALIZATION and payload:
        decoded = json.loads(payload.decode("utf-8"))
    elif message_type == SERVER_ERROR_RESPONSE and payload:
        try:
            decoded = payload.decode("utf-8")
        except UnicodeDecodeError:
            decoded = repr(payload)

    return {
        "message_type": message_type,
        "flags": flags,
        "serialization": serialization,
        "compression": compression,
        "sequence": sequence,
        "payload": decoded,
        "is_last": bool(flags & 0b0010) or (sequence is not None and sequence < 0),
    }


def _extract_text(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("text", "transcript", "result_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        result = payload.get("result")
        if result is not None:
            text = _extract_text(result)
            if text:
                return text
        utterances = payload.get("utterances")
        if isinstance(utterances, list):
            parts = [_extract_text(item) for item in utterances]
            return "".join(part for part in parts if part)
        for value in payload.values():
            text = _extract_text(value)
            if text:
                return text
    if isinstance(payload, list):
        parts = [_extract_text(item) for item in payload]
        return "".join(part for part in parts if part)
    return ""


def _payload_summary(payload: Any) -> str:
    if payload is None:
        return "none"
    if isinstance(payload, dict):
        return "dict:" + ",".join(str(key) for key in payload.keys())
    if isinstance(payload, list):
        return f"list:{len(payload)}"
    if isinstance(payload, bytes):
        return f"bytes:{len(payload)}"
    return type(payload).__name__


def _json_preview(payload: Any, limit: int = 1200) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        text = repr(payload)
    if len(text) > limit:
        return text[:limit] + "...<truncated>"
    return text


def _looks_final(payload: dict[str, Any]) -> bool:
    final_keys = ("is_final", "final", "completed", "end", "is_last")
    for key in final_keys:
        if payload.get(key) is True:
            return True
    if payload.get("event") in {
        "conversation.item.input_audio_transcription.completed",
        "asr.completed",
    }:
        return True
    return False
