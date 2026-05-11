from pathlib import Path

from voice_input.config import (
    DOUBAO_ENDPOINT_STREAM_INPUT,
    DOUBAO_MODE_REALTIME,
    DOUBAO_MODE_REALTIME_FINAL,
    DOUBAO_MODE_STREAM_INPUT,
    DEFAULT_ORGANIZER_ENDPOINT,
    DEFAULT_ORGANIZER_MODEL,
    DEFAULT_QWEN_ASR_ENDPOINT,
    DEFAULT_QWEN_ASR_MODEL,
    ORGANIZER_PROVIDER_DEEPSEEK,
    ORGANIZER_PROVIDER_OPENAI_COMPATIBLE,
    ensure_config_file,
    load_config,
    read_env_file,
    write_env_file,
)


def test_read_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        """
        # comment
        VOICE_INPUT_ASR=doubao
        DOUBAO_ASR_APP_KEY="app"
        """,
        encoding="utf-8",
    )
    values = read_env_file(env)
    assert values["VOICE_INPUT_ASR"] == "doubao"
    assert values["DOUBAO_ASR_APP_KEY"] == "app"


def test_load_config_env_override(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOICE_INPUT_ASR=mock\nVOICE_INPUT_CHUNK_MS=100\n", encoding="utf-8")
    config = load_config(env, {"VOICE_INPUT_ASR": "doubao"})
    assert config.asr_provider == "doubao"
    assert config.chunk_ms == 100


def test_load_config_file_from_environment(tmp_path: Path) -> None:
    env = tmp_path / "voice-input-linux.env"
    env.write_text("VOICE_INPUT_ASR=mock\nVOICE_INPUT_MOCK_TEXT=hello\n", encoding="utf-8")
    config = load_config(None, {"VOICE_INPUT_CONFIG_FILE": str(env)})
    assert config.config_file == str(env)
    assert config.mock_text == "hello"


def test_default_doubao_config_uses_streaming_asr_2(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config = load_config(env, {})
    assert config.doubao_endpoint == "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    assert config.effective_doubao_endpoint() == "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    assert config.doubao_resource_id == "volc.seedasr.sauc.duration"
    assert config.doubao_mode == DOUBAO_MODE_REALTIME_FINAL
    assert config.paste_at_mouse is True
    assert config.paste_hotkey == "ctrl+v"
    assert config.append_final_punctuation is True
    assert config.doubao_enable_punc is True
    assert config.doubao_enable_itn is True
    assert config.doubao_enable_ddc is False
    assert config.doubao_enable_nonstream is True
    assert config.effective_doubao_enable_nonstream() is True
    assert config.organizer_provider == ORGANIZER_PROVIDER_DEEPSEEK
    assert config.organizer_endpoint == DEFAULT_ORGANIZER_ENDPOINT
    assert config.organizer_model == DEFAULT_ORGANIZER_MODEL
    assert config.organizer_timeout == 45
    assert config.qwen_endpoint == DEFAULT_QWEN_ASR_ENDPOINT
    assert config.qwen_model == DEFAULT_QWEN_ASR_MODEL
    assert config.qwen_language == "zh"
    assert config.qwen_enable_server_vad is True
    assert config.qwen_vad_threshold == 0.0
    assert config.qwen_vad_silence_ms == 400


def test_load_config_paste_hotkey(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOICE_INPUT_PASTE_HOTKEY=ctrl+shift+v\n", encoding="utf-8")
    config = load_config(env, {})
    assert config.paste_hotkey == "ctrl+shift+v"


def test_load_config_organizer_options(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "VOICE_INPUT_ORGANIZER_PROVIDER=openai_compatible",
                "VOICE_INPUT_ORGANIZER_ENDPOINT=https://example.test/v1/chat/completions",
                "VOICE_INPUT_ORGANIZER_API_KEY=secret",
                "VOICE_INPUT_ORGANIZER_MODEL=gpt-test",
                "VOICE_INPUT_ORGANIZER_TIMEOUT=60",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(env, {})
    assert config.organizer_provider == ORGANIZER_PROVIDER_OPENAI_COMPATIBLE
    assert config.organizer_endpoint == "https://example.test/v1/chat/completions"
    assert config.organizer_api_key == "secret"
    assert config.organizer_model == "gpt-test"
    assert config.organizer_timeout == 60
    assert config.masked()["organizer_api_key"] == "***"


def test_load_config_legacy_deepseek_options(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "VOICE_INPUT_DEEPSEEK_ENDPOINT=https://example.test/v1/chat/completions",
                "VOICE_INPUT_DEEPSEEK_API_KEY=secret",
                "VOICE_INPUT_DEEPSEEK_MODEL=deepseek-reasoner",
                "VOICE_INPUT_DEEPSEEK_TIMEOUT=60",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(env, {})
    assert config.organizer_provider == ORGANIZER_PROVIDER_DEEPSEEK
    assert config.organizer_endpoint == "https://example.test/v1/chat/completions"
    assert config.organizer_api_key == "secret"
    assert config.organizer_model == "deepseek-reasoner"
    assert config.organizer_timeout == 60


def test_load_config_organizer_base_url_fallback(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config = load_config(env, {"VOICE_INPUT_ORGANIZER_BASE_URL": "https://example.test/v1"})
    assert config.organizer_endpoint == "https://example.test/v1/chat/completions"


def test_load_config_qwen_asr_options(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "VOICE_INPUT_ASR=aliyun_qwen",
                "QWEN_ASR_ENDPOINT=wss://example.test/realtime",
                "QWEN_ASR_API_KEY=sk-test",
                "QWEN_ASR_MODEL=qwen3-asr-flash-realtime",
                "QWEN_ASR_LANGUAGE=en",
                "QWEN_ASR_ENABLE_SERVER_VAD=false",
                "QWEN_ASR_VAD_THRESHOLD=0.2",
                "QWEN_ASR_VAD_SILENCE_MS=800",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(env, {})
    assert config.asr_provider == "qwen"
    assert config.qwen_endpoint == "wss://example.test/realtime"
    assert config.qwen_api_key == "sk-test"
    assert config.qwen_model == "qwen3-asr-flash-realtime"
    assert config.qwen_language == "en"
    assert config.qwen_enable_server_vad is False
    assert config.qwen_vad_threshold == 0.2
    assert config.qwen_vad_silence_ms == 800
    assert config.masked()["qwen_api_key"] == "***"


def test_load_config_append_final_punctuation(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOICE_INPUT_APPEND_FINAL_PUNCTUATION=false\n", encoding="utf-8")
    config = load_config(env, {})
    assert config.append_final_punctuation is False


def test_load_config_doubao_request_options(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "DOUBAO_ASR_ENABLE_PUNC=false",
                "DOUBAO_ASR_ENABLE_ITN=false",
                "DOUBAO_ASR_ENABLE_DDC=true",
                "DOUBAO_ASR_ENABLE_NONSTREAM=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(env, {})
    assert config.doubao_enable_punc is False
    assert config.doubao_enable_itn is False
    assert config.doubao_enable_ddc is True
    assert config.doubao_enable_nonstream is False
    assert config.doubao_mode == DOUBAO_MODE_REALTIME
    assert config.effective_doubao_enable_nonstream() is False


def test_load_config_doubao_stream_input_mode(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DOUBAO_ASR_MODE=stream_input\n", encoding="utf-8")
    config = load_config(env, {})
    assert config.doubao_mode == DOUBAO_MODE_STREAM_INPUT
    assert config.effective_doubao_endpoint() == DOUBAO_ENDPOINT_STREAM_INPUT
    assert config.effective_doubao_enable_nonstream() is False


def test_write_env_file_preserves_comments(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# hello\nVOICE_INPUT_ASR=mock\n", encoding="utf-8")
    write_env_file(env, {"VOICE_INPUT_ASR": "doubao", "DOUBAO_ASR_APP_KEY": "app key"})
    text = env.read_text(encoding="utf-8")
    assert "# hello" in text
    assert "VOICE_INPUT_ASR=doubao" in text
    assert 'DOUBAO_ASR_APP_KEY="app key"' in text


def test_write_env_file_removes_duplicate_updated_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOICE_INPUT_DEVICE=\nVOICE_INPUT_DEVICE=10\n", encoding="utf-8")
    write_env_file(env, {"VOICE_INPUT_DEVICE": "8"})
    text = env.read_text(encoding="utf-8")
    assert text.count("VOICE_INPUT_DEVICE=") == 1
    assert "VOICE_INPUT_DEVICE=8" in text


def test_ensure_config_file_creates_default(tmp_path: Path) -> None:
    env = tmp_path / "voice-input-linux.env"
    config = load_config(env, {})
    ensure_config_file(env, config)
    text = env.read_text(encoding="utf-8")
    assert "VOICE_INPUT_ASR=mock" in text
    assert "VOICE_INPUT_PASTE_HOTKEY=ctrl+v" in text
    assert "VOICE_INPUT_APPEND_FINAL_PUNCTUATION=true" in text
    assert "DOUBAO_ASR_MODE=realtime_final" in text
    assert "DOUBAO_ASR_ENABLE_PUNC=true" in text
    assert "DOUBAO_ASR_ENABLE_NONSTREAM=true" in text
    assert "QWEN_ASR_ENDPOINT=wss://dashscope.aliyuncs.com/api-ws/v1/realtime" in text
    assert "QWEN_ASR_MODEL=qwen3-asr-flash-realtime" in text
    assert "QWEN_ASR_LANGUAGE=zh" in text
    assert "VOICE_INPUT_ORGANIZER_PROVIDER=deepseek" in text
    assert "VOICE_INPUT_ORGANIZER_ENDPOINT=https://api.deepseek.com/chat/completions" in text
