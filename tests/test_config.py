from pathlib import Path

from voice_input.config import (
    DOUBAO_ENDPOINT_STREAM_INPUT,
    DOUBAO_MODE_REALTIME,
    DOUBAO_MODE_REALTIME_FINAL,
    DOUBAO_MODE_STREAM_INPUT,
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


def test_load_config_paste_hotkey(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOICE_INPUT_PASTE_HOTKEY=ctrl+shift+v\n", encoding="utf-8")
    config = load_config(env, {})
    assert config.paste_hotkey == "ctrl+shift+v"


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
