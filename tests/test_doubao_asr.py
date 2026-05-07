import json

from voice_input.asr.doubao_big_asr import DoubaoBigASRClient, _extract_text, _parse_frame


def test_extract_text_from_official_result_shape() -> None:
    payload = {
        "audio_info": {"duration": 3696},
        "result": {
            "text": "这是字节跳动，今日头条母公司。",
            "utterances": [
                {"definite": True, "text": "这是字节跳动，"},
                {"definite": True, "text": "今日头条母公司。"},
            ],
        },
    }
    assert _extract_text(payload) == "这是字节跳动，今日头条母公司。"


def test_parse_error_response_frame() -> None:
    error = {"error": "bad request"}
    payload = json.dumps(error).encode("utf-8")
    frame = bytes([0x11, 0xF0, 0x10, 0x00])
    frame += (45000001).to_bytes(4, "big")
    frame += len(payload).to_bytes(4, "big")
    frame += payload
    parsed = _parse_frame(frame)
    assert parsed["message_type"] == 15
    assert parsed["error_code"] == 45000001
    assert parsed["payload"] == error


def test_start_payload_uses_full_result_type() -> None:
    client = DoubaoBigASRClient(
        endpoint="wss://example.test",
        app_key="app",
        access_key="access",
        resource_id="volc.seedasr.sauc.duration",
    )
    payload = client._build_start_payload()
    assert payload["audio"]["format"] == "pcm"
    assert payload["request"]["model_name"] == "bigmodel"
    assert payload["request"]["result_type"] == "full"
    assert payload["request"]["show_utterances"] is True
