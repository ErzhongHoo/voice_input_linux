from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys
import tempfile
from typing import Mapping


TRUE_VALUES = {"1", "true", "yes", "on", "y"}
DOUBAO_ENDPOINT_REALTIME = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
DOUBAO_ENDPOINT_STREAM_INPUT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
DEFAULT_DOUBAO_ENDPOINT = DOUBAO_ENDPOINT_REALTIME
DEFAULT_DOUBAO_RESOURCE_ID = "volc.seedasr.sauc.duration"
DOUBAO_MODE_REALTIME_FINAL = "realtime_final"
DOUBAO_MODE_REALTIME = "realtime"
DOUBAO_MODE_STREAM_INPUT = "stream_input"
DOUBAO_MODE_CUSTOM = "custom"
DOUBAO_MODES = {
    DOUBAO_MODE_REALTIME_FINAL,
    DOUBAO_MODE_REALTIME,
    DOUBAO_MODE_STREAM_INPUT,
    DOUBAO_MODE_CUSTOM,
}

CONFIG_ENV_KEYS = [
    "VOICE_INPUT_ASR",
    "VOICE_INPUT_MOCK_TEXT",
    "DOUBAO_ASR_ENDPOINT",
    "DOUBAO_ASR_APP_KEY",
    "DOUBAO_ASR_ACCESS_KEY",
    "DOUBAO_ASR_ACCESS_TOKEN",
    "DOUBAO_ASR_RESOURCE_ID",
    "DOUBAO_ASR_PROTOCOL",
    "DOUBAO_ASR_MODE",
    "DOUBAO_ASR_ENABLE_PUNC",
    "DOUBAO_ASR_ENABLE_ITN",
    "DOUBAO_ASR_ENABLE_DDC",
    "DOUBAO_ASR_ENABLE_NONSTREAM",
    "VOICE_INPUT_HOTKEY_BACKEND",
    "VOICE_INPUT_HOTKEY_KEY",
    "VOICE_INPUT_EVDEV_KEY",
    "VOICE_INPUT_EVDEV_DEVICE",
    "VOICE_INPUT_INJECTOR_BACKEND",
    "VOICE_INPUT_PREFER_FCITX5",
    "VOICE_INPUT_PASTE_AT_MOUSE",
    "VOICE_INPUT_PASTE_HOTKEY",
    "VOICE_INPUT_APPEND_FINAL_PUNCTUATION",
    "VOICE_INPUT_SAMPLE_RATE",
    "VOICE_INPUT_CHANNELS",
    "VOICE_INPUT_CHUNK_MS",
    "VOICE_INPUT_DEVICE",
    "VOICE_INPUT_OVERLAY_THEME",
    "VOICE_INPUT_LOG_LEVEL",
    "VOICE_INPUT_RUNTIME_SOCKET",
    "VOICE_INPUT_CONFIG_FILE",
]


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path).expanduser()
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_quotes(value)
    return values


def resolve_config_file(env_file: str | Path | None = None) -> Path:
    if env_file is not None:
        return Path(env_file).expanduser()
    configured = os.environ.get("VOICE_INPUT_CONFIG_FILE")
    if configured:
        return Path(configured).expanduser()
    home_config = Path.home() / ".config" / "voice-input-linux.env"
    if _is_packaged_app():
        return home_config
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
    return home_config


def _is_packaged_app() -> bool:
    return bool(os.environ.get("APPIMAGE") or os.environ.get("VOICE_INPUT_APPIMAGE")) or bool(
        getattr(sys, "frozen", False)
    )


def write_env_file(path: str | Path, updates: Mapping[str, str]) -> None:
    env_path = Path(path).expanduser()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        editable = stripped and not stripped.startswith("#") and "=" in raw_line
        if not editable:
            output.append(raw_line)
            continue
        key, _ = raw_line.split("=", 1)
        key = key.strip()
        if key in updates:
            if key in seen:
                continue
            output.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        else:
            output.append(raw_line)

    missing = [key for key in CONFIG_ENV_KEYS if key in updates and key not in seen]
    if missing and output and output[-1].strip():
        output.append("")
    for key in missing:
        output.append(f"{key}={_quote_env_value(updates[key])}")

    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def ensure_config_file(path: str | Path, config: "AppConfig") -> None:
    env_path = Path(path).expanduser()
    if env_path.exists():
        return
    write_env_file(env_path, config_to_env(config))


def _quote_env_value(value: str) -> str:
    value = value.replace("\n", " ").strip()
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or "#" in value or '"' in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _get_bool(values: Mapping[str, str], key: str, default: bool) -> bool:
    value = values.get(key)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _get_int(values: Mapping[str, str], key: str, default: int) -> int:
    value = values.get(key)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _default_socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return str(Path(runtime_dir) / "voice-input-linux.sock")
    return str(Path(tempfile.gettempdir()) / f"voice-input-linux-{os.getuid()}.sock")


@dataclass(slots=True)
class AppConfig:
    asr_provider: str = "mock"
    mock_text: str = "这是一次语音输入测试。"

    doubao_endpoint: str = DEFAULT_DOUBAO_ENDPOINT
    doubao_app_key: str = ""
    doubao_access_key: str = ""
    doubao_resource_id: str = DEFAULT_DOUBAO_RESOURCE_ID
    doubao_protocol: str = "bigmodel_binary"
    doubao_mode: str = DOUBAO_MODE_REALTIME_FINAL
    doubao_enable_punc: bool = True
    doubao_enable_itn: bool = True
    doubao_enable_ddc: bool = False
    doubao_enable_nonstream: bool = True

    hotkey_backend: str = "auto"
    hotkey_key: str = "right_alt"
    evdev_device: str = ""
    evdev_key: str = "KEY_RIGHTALT"

    injector_backend: str = "auto"
    prefer_fcitx5: bool = True
    paste_at_mouse: bool = True
    paste_hotkey: str = "ctrl+v"
    append_final_punctuation: bool = True

    sample_rate: int = 16000
    channels: int = 1
    chunk_ms: int = 200
    input_device: str = ""

    overlay_theme: str = "auto"
    log_level: str = "INFO"
    socket_path: str = ""
    config_file: str = ""

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "AppConfig":
        return cls(
            asr_provider=values.get("VOICE_INPUT_ASR", values.get("ASR_PROVIDER", "mock")).lower(),
            mock_text=values.get("VOICE_INPUT_MOCK_TEXT", "这是一次语音输入测试。"),
            doubao_endpoint=values.get(
                "DOUBAO_ASR_ENDPOINT",
                DEFAULT_DOUBAO_ENDPOINT,
            ),
            doubao_app_key=values.get("DOUBAO_ASR_APP_KEY", ""),
            doubao_access_key=values.get(
                "DOUBAO_ASR_ACCESS_KEY",
                values.get("DOUBAO_ASR_ACCESS_TOKEN", ""),
            ),
            doubao_resource_id=values.get("DOUBAO_ASR_RESOURCE_ID", DEFAULT_DOUBAO_RESOURCE_ID),
            doubao_protocol=values.get("DOUBAO_ASR_PROTOCOL", "bigmodel_binary"),
            doubao_mode=_get_doubao_mode(values),
            doubao_enable_punc=_get_bool(values, "DOUBAO_ASR_ENABLE_PUNC", True),
            doubao_enable_itn=_get_bool(values, "DOUBAO_ASR_ENABLE_ITN", True),
            doubao_enable_ddc=_get_bool(values, "DOUBAO_ASR_ENABLE_DDC", False),
            doubao_enable_nonstream=_get_bool(values, "DOUBAO_ASR_ENABLE_NONSTREAM", True),
            hotkey_backend=values.get("VOICE_INPUT_HOTKEY_BACKEND", "auto").lower(),
            hotkey_key=values.get("VOICE_INPUT_HOTKEY_KEY", "right_alt"),
            evdev_device=values.get("VOICE_INPUT_EVDEV_DEVICE", ""),
            evdev_key=values.get("VOICE_INPUT_EVDEV_KEY", "KEY_RIGHTALT"),
            injector_backend=values.get("VOICE_INPUT_INJECTOR_BACKEND", "auto").lower(),
            prefer_fcitx5=_get_bool(values, "VOICE_INPUT_PREFER_FCITX5", True),
            paste_at_mouse=_get_bool(values, "VOICE_INPUT_PASTE_AT_MOUSE", True),
            paste_hotkey=values.get("VOICE_INPUT_PASTE_HOTKEY", "ctrl+v").strip().lower() or "ctrl+v",
            append_final_punctuation=_get_bool(values, "VOICE_INPUT_APPEND_FINAL_PUNCTUATION", True),
            sample_rate=_get_int(values, "VOICE_INPUT_SAMPLE_RATE", 16000),
            channels=_get_int(values, "VOICE_INPUT_CHANNELS", 1),
            chunk_ms=_get_int(values, "VOICE_INPUT_CHUNK_MS", 200),
            input_device=values.get("VOICE_INPUT_DEVICE", ""),
            overlay_theme=values.get("VOICE_INPUT_OVERLAY_THEME", "auto").lower(),
            log_level=values.get("VOICE_INPUT_LOG_LEVEL", "INFO").upper(),
            socket_path=values.get("VOICE_INPUT_RUNTIME_SOCKET", "") or _default_socket_path(),
        )

    def masked(self) -> dict[str, str | int | bool]:
        secret_fields = {
            "doubao_app_key",
            "doubao_access_key",
        }
        result: dict[str, str | int | bool] = {}
        for field in self.__dataclass_fields__:
            value = getattr(self, field)
            if field in secret_fields and value:
                result[field] = "***"
            else:
                result[field] = value
        return result

    def effective_doubao_endpoint(self) -> str:
        return doubao_endpoint_for_mode(self.doubao_mode) or self.doubao_endpoint

    def effective_doubao_enable_nonstream(self) -> bool:
        if self.doubao_mode == DOUBAO_MODE_REALTIME_FINAL:
            return True
        if self.doubao_mode in {DOUBAO_MODE_REALTIME, DOUBAO_MODE_STREAM_INPUT}:
            return False
        return self.doubao_enable_nonstream


def doubao_endpoint_for_mode(mode: str) -> str:
    if mode in {DOUBAO_MODE_REALTIME_FINAL, DOUBAO_MODE_REALTIME}:
        return DOUBAO_ENDPOINT_REALTIME
    if mode == DOUBAO_MODE_STREAM_INPUT:
        return DOUBAO_ENDPOINT_STREAM_INPUT
    return ""


def _get_doubao_mode(values: Mapping[str, str]) -> str:
    configured = values.get("DOUBAO_ASR_MODE", "").strip().lower()
    if configured in DOUBAO_MODES:
        return configured

    endpoint = values.get("DOUBAO_ASR_ENDPOINT", DEFAULT_DOUBAO_ENDPOINT).strip()
    enable_nonstream = _get_bool(values, "DOUBAO_ASR_ENABLE_NONSTREAM", True)
    if endpoint == DOUBAO_ENDPOINT_STREAM_INPUT:
        return DOUBAO_MODE_STREAM_INPUT
    if endpoint == DOUBAO_ENDPOINT_REALTIME:
        return DOUBAO_MODE_REALTIME_FINAL if enable_nonstream else DOUBAO_MODE_REALTIME
    return DOUBAO_MODE_CUSTOM


def load_config(
    env_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    values: dict[str, str] = {}
    runtime_env = os.environ if environ is None else environ
    config_file = resolve_config_file(env_file or runtime_env.get("VOICE_INPUT_CONFIG_FILE"))
    values.update(read_env_file(config_file))

    values.update(dict(runtime_env))
    config = AppConfig.from_mapping(values)
    config.config_file = str(config_file)
    return config


def config_to_env(config: AppConfig) -> dict[str, str]:
    return {
        "VOICE_INPUT_ASR": config.asr_provider,
        "VOICE_INPUT_MOCK_TEXT": config.mock_text,
        "DOUBAO_ASR_ENDPOINT": config.effective_doubao_endpoint(),
        "DOUBAO_ASR_APP_KEY": config.doubao_app_key,
        "DOUBAO_ASR_ACCESS_KEY": config.doubao_access_key,
        "DOUBAO_ASR_ACCESS_TOKEN": config.doubao_access_key,
        "DOUBAO_ASR_RESOURCE_ID": config.doubao_resource_id,
        "DOUBAO_ASR_PROTOCOL": config.doubao_protocol,
        "DOUBAO_ASR_MODE": config.doubao_mode,
        "DOUBAO_ASR_ENABLE_PUNC": "true" if config.doubao_enable_punc else "false",
        "DOUBAO_ASR_ENABLE_ITN": "true" if config.doubao_enable_itn else "false",
        "DOUBAO_ASR_ENABLE_DDC": "true" if config.doubao_enable_ddc else "false",
        "DOUBAO_ASR_ENABLE_NONSTREAM": "true" if config.effective_doubao_enable_nonstream() else "false",
        "VOICE_INPUT_HOTKEY_BACKEND": config.hotkey_backend,
        "VOICE_INPUT_HOTKEY_KEY": config.hotkey_key,
        "VOICE_INPUT_EVDEV_KEY": config.evdev_key,
        "VOICE_INPUT_EVDEV_DEVICE": config.evdev_device,
        "VOICE_INPUT_INJECTOR_BACKEND": config.injector_backend,
        "VOICE_INPUT_PREFER_FCITX5": "true" if config.prefer_fcitx5 else "false",
        "VOICE_INPUT_PASTE_AT_MOUSE": "true" if config.paste_at_mouse else "false",
        "VOICE_INPUT_PASTE_HOTKEY": config.paste_hotkey,
        "VOICE_INPUT_APPEND_FINAL_PUNCTUATION": "true" if config.append_final_punctuation else "false",
        "VOICE_INPUT_SAMPLE_RATE": str(config.sample_rate),
        "VOICE_INPUT_CHANNELS": str(config.channels),
        "VOICE_INPUT_CHUNK_MS": str(config.chunk_ms),
        "VOICE_INPUT_DEVICE": config.input_device,
        "VOICE_INPUT_OVERLAY_THEME": config.overlay_theme,
        "VOICE_INPUT_LOG_LEVEL": config.log_level,
        "VOICE_INPUT_RUNTIME_SOCKET": config.socket_path,
    }
