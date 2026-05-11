from __future__ import annotations

import asyncio
import json

from voice_input.asr.qwen_realtime_asr import QwenRealtimeASRClient, qwen_realtime_url


def test_qwen_realtime_url_adds_model_query() -> None:
    assert (
        qwen_realtime_url("wss://dashscope.aliyuncs.com/api-ws/v1/realtime", "qwen3-asr-flash-realtime")
        == "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3-asr-flash-realtime"
    )


def test_qwen_realtime_url_keeps_existing_model_query() -> None:
    assert qwen_realtime_url("wss://example.test/realtime?model=custom&foo=bar", "qwen3-asr-flash-realtime") == (
        "wss://example.test/realtime?model=custom&foo=bar"
    )


def test_qwen_session_update_uses_pcm_and_vad() -> None:
    client = QwenRealtimeASRClient(
        endpoint="wss://example.test/realtime",
        api_key="sk-test",
        model="qwen3-asr-flash-realtime",
        language="zh",
        sample_rate=16000,
        enable_server_vad=True,
        vad_threshold=0.0,
        vad_silence_ms=400,
    )

    event = client._build_session_update()

    assert event["type"] == "session.update"
    assert event["session"]["modalities"] == ["text"]
    assert event["session"]["input_audio_format"] == "pcm"
    assert event["session"]["sample_rate"] == 16000
    assert event["session"]["input_audio_transcription"] == {"language": "zh"}
    assert event["session"]["turn_detection"] == {
        "type": "server_vad",
        "threshold": 0.0,
        "silence_duration_ms": 400,
    }


def test_qwen_consumes_partial_and_completed_events() -> None:
    client = QwenRealtimeASRClient(
        endpoint="wss://example.test/realtime",
        api_key="sk-test",
        model="qwen3-asr-flash-realtime",
    )

    client._consume_event(
        {
            "type": "conversation.item.input_audio_transcription.text",
            "item_id": "item-1",
            "text": "你好",
            "stash": "世界",
        }
    )
    assert asyncio.run(client.get_partial_text()) == "你好世界"

    client._consume_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "item-1",
            "transcript": "你好世界。",
        }
    )
    client._consume_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "item-2",
            "transcript": "第二句。",
        }
    )

    assert asyncio.run(client.get_final_text()) == "你好世界。第二句。"


def test_qwen_send_audio_chunk_uses_base64_event() -> None:
    sent: list[str] = []

    class FakeWebSocket:
        async def send(self, message: str) -> None:
            sent.append(message)

    client = QwenRealtimeASRClient(
        endpoint="wss://example.test/realtime",
        api_key="sk-test",
        model="qwen3-asr-flash-realtime",
    )
    client._ws = FakeWebSocket()

    asyncio.run(client.send_audio_chunk(b"\x01\x02"))

    payload = json.loads(sent[0])
    assert payload["type"] == "input_audio_buffer.append"
    assert payload["audio"] == "AQI="
