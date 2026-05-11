from __future__ import annotations

import asyncio
import json
import uuid

from voice_input.asr.qwen_realtime_asr import qwen_realtime_url
from voice_input.config import ASR_PROVIDER_QWEN, DOUBAO_ASR_PROVIDERS, AppConfig
from voice_input.postprocess.organizer import ChatCompletionTextOrganizer


class ModelConnectionError(RuntimeError):
    pass


def check_asr_connection(config: AppConfig, timeout: int = 10) -> str:
    if config.asr_provider == "mock":
        return "mock ASR 可用"

    if config.asr_provider == ASR_PROVIDER_QWEN:
        missing = []
        if not config.qwen_endpoint:
            missing.append("Endpoint")
        if not config.qwen_api_key:
            missing.append("API Key")
        if not config.qwen_model:
            missing.append("Model")
        if missing:
            raise ModelConnectionError("缺少 " + "、".join(missing))
        try:
            asyncio.run(_check_qwen_connection(config, timeout))
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ModelConnectionError):
                raise
            raise ModelConnectionError(f"连接千问 ASR 失败: {exc}") from exc
        return "千问 ASR 连接正常"

    if config.asr_provider not in DOUBAO_ASR_PROVIDERS:
        raise ModelConnectionError(f"未知 ASR provider: {config.asr_provider}")

    missing = []
    if not config.effective_doubao_endpoint():
        missing.append("Endpoint")
    if not config.doubao_app_key:
        missing.append("App Key")
    if not config.doubao_access_key:
        missing.append("Access Key")
    if not config.doubao_resource_id:
        missing.append("Resource ID")
    if missing:
        raise ModelConnectionError("缺少 " + "、".join(missing))

    try:
        asyncio.run(_check_doubao_connection(config, timeout))
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ModelConnectionError):
            raise
        raise ModelConnectionError(f"连接豆包 ASR 失败: {exc}") from exc
    return "豆包 ASR 连接正常"


def check_organizer_connection(config: AppConfig) -> str:
    organizer = ChatCompletionTextOrganizer(
        endpoint=config.organizer_endpoint,
        api_key=config.organizer_api_key,
        model=config.organizer_model,
        provider=config.organizer_provider,
        timeout=config.organizer_timeout,
    )
    try:
        organizer.organize("连通性测试。请只回复 OK。")
    except Exception as exc:  # noqa: BLE001
        raise ModelConnectionError(str(exc)) from exc
    return "整理模型连接正常"


async def _check_doubao_connection(config: AppConfig, timeout: int) -> None:
    try:
        import websockets
    except Exception as exc:  # noqa: BLE001
        raise ModelConnectionError(f"websockets 依赖不可用: {exc}") from exc

    request_id = str(uuid.uuid4())
    headers = {
        "X-Api-App-Key": config.doubao_app_key,
        "X-Api-Access-Key": config.doubao_access_key,
        "X-Api-Resource-Id": config.doubao_resource_id,
        "X-Api-Connect-Id": request_id,
        "X-Api-Request-Id": request_id,
    }
    ws = None
    try:
        try:
            ws = await asyncio.wait_for(
                websockets.connect(
                    config.effective_doubao_endpoint(),
                    additional_headers=headers,
                    max_size=100 * 1024 * 1024,
                ),
                timeout=timeout,
            )
        except TypeError:
            ws = await asyncio.wait_for(
                websockets.connect(
                    config.effective_doubao_endpoint(),
                    extra_headers=headers,
                    max_size=100 * 1024 * 1024,
                ),
                timeout=timeout,
            )
    finally:
        if ws is not None:
            await ws.close()


async def _check_qwen_connection(config: AppConfig, timeout: int) -> None:
    try:
        import websockets
    except Exception as exc:  # noqa: BLE001
        raise ModelConnectionError(f"websockets 依赖不可用: {exc}") from exc

    headers = {
        "Authorization": f"Bearer {config.qwen_api_key}",
        "OpenAI-Beta": "realtime=v1",
    }
    url = qwen_realtime_url(config.qwen_endpoint, config.qwen_model)
    ws = None
    try:
        try:
            ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    additional_headers=headers,
                    max_size=100 * 1024 * 1024,
                ),
                timeout=timeout,
            )
        except TypeError:
            ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    extra_headers=headers,
                    max_size=100 * 1024 * 1024,
                ),
                timeout=timeout,
            )
        await ws.send(
            json.dumps(
                {
                    "event_id": "event_" + uuid.uuid4().hex,
                    "type": "session.update",
                    "session": {
                        "input_audio_format": "pcm",
                        "sample_rate": config.sample_rate,
                        "input_audio_transcription": {"language": config.qwen_language},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": config.qwen_vad_threshold,
                            "silence_duration_ms": config.qwen_vad_silence_ms,
                        }
                        if config.qwen_enable_server_vad
                        else None,
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            payload = json.loads(message)
            event_type = payload.get("type")
            if event_type == "session.updated":
                await ws.send(json.dumps({"event_id": "event_" + uuid.uuid4().hex, "type": "session.finish"}))
                return
            if event_type == "error":
                error = payload.get("error")
                raise ModelConnectionError(str(error or payload))
    finally:
        if ws is not None:
            await ws.close()
