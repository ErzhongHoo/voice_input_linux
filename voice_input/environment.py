from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from voice_input.audio.devices import list_input_devices
from voice_input.config import ASR_PROVIDER_QWEN, DOUBAO_ASR_PROVIDERS, AppConfig
from voice_input.hotkey.evdev_backend import EvdevHotkeyBackend
from voice_input.hotkey.pynput_backend import PynputHotkeyBackend
from voice_input.inject.clipboard_injector import ClipboardInjector
from voice_input.inject.fcitx5_injector import Fcitx5Injector
from voice_input.inject.wtype_injector import WtypeInjector
from voice_input.inject.xdotool_injector import XdotoolInjector
from voice_input.inject.ydotool_injector import YdotoolInjector


STATUS_ORDER = {"fail": 0, "warn": 1, "ok": 2, "info": 3}


@dataclass(frozen=True, slots=True)
class EnvironmentCheck:
    category: str
    name: str
    status: str
    summary: str
    detail: str = ""


def run_environment_checks(config: AppConfig) -> list[EnvironmentCheck]:
    checks: list[EnvironmentCheck] = []
    checks.extend(_platform_checks())
    checks.extend(_audio_checks(config))
    checks.extend(_asr_checks(config))
    checks.extend(_organizer_checks(config))
    checks.extend(_hotkey_checks(config))
    checks.extend(_injection_checks(config))
    checks.extend(_system_checks())
    return checks


def summarize_checks(checks: list[EnvironmentCheck]) -> str:
    failed = sum(1 for check in checks if check.status == "fail")
    warned = sum(1 for check in checks if check.status == "warn")
    ok = sum(1 for check in checks if check.status == "ok")
    if failed:
        return f"{failed} 项失败，{warned} 项需要注意，{ok} 项正常"
    if warned:
        return f"{warned} 项需要注意，{ok} 项正常"
    return f"{ok} 项正常"


def format_check_report(checks: list[EnvironmentCheck]) -> str:
    lines = [summarize_checks(checks), ""]
    for check in checks:
        lines.append(f"[{_status_text(check.status)}] {check.category} / {check.name}: {check.summary}")
        if check.detail:
            lines.append(f"  {check.detail}")
    return "\n".join(lines)


def _platform_checks() -> list[EnvironmentCheck]:
    checks = [
        EnvironmentCheck(
            "系统",
            "架构",
            "ok" if platform.machine().lower() in {"x86_64", "amd64", "aarch64", "arm64"} else "warn",
            f"{platform.system()} {platform.machine()}",
            f"Python {sys.version.split()[0]}",
        )
    ]

    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    display = os.environ.get("DISPLAY", "")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    if wayland_display or session_type == "wayland":
        checks.append(
            EnvironmentCheck(
                "系统",
                "桌面会话",
                "warn",
                "Wayland 会话",
                "Wayland 限制全局按键监听和模拟输入；推荐 compositor 快捷键 + ydotool。",
            )
        )
    elif display:
        checks.append(EnvironmentCheck("系统", "桌面会话", "ok", f"X11 DISPLAY={display}"))
    else:
        checks.append(EnvironmentCheck("系统", "桌面会话", "fail", "没有检测到 DISPLAY 或 WAYLAND_DISPLAY"))

    libc = _glibc_version()
    bundled = bool(os.environ.get("VOICE_INPUT_BUNDLED_GLIBC"))
    if bundled:
        checks.append(
            EnvironmentCheck(
                "系统",
                "glibc",
                "warn",
                f"{libc}，正在使用 AppImage 内置 glibc",
                "内置 glibc 是实验模式；正式分发仍建议在较老发行版构建。",
            )
        )
    elif os.environ.get("APPIMAGE") or os.environ.get("VOICE_INPUT_APPIMAGE"):
        checks.append(
            EnvironmentCheck(
                "系统",
                "glibc",
                "warn",
                f"{libc}，依赖宿主系统 glibc",
                "如果目标系统 glibc 比构建机旧，AppImage 可能无法启动。",
            )
        )
    else:
        checks.append(EnvironmentCheck("系统", "glibc", "info", libc))
    return checks


def _audio_checks(config: AppConfig) -> list[EnvironmentCheck]:
    try:
        devices = list_input_devices()
    except Exception as exc:  # noqa: BLE001
        return [EnvironmentCheck("音频", "sounddevice", "fail", "无法枚举输入设备", str(exc))]

    checks = [
        EnvironmentCheck(
            "音频",
            "输入设备",
            "ok" if devices else "fail",
            f"检测到 {len(devices)} 个输入设备" if devices else "没有检测到麦克风",
            "\n".join(device.label for device in devices[:12]),
        )
    ]

    configured = config.input_device.strip()
    if not configured:
        checks.append(EnvironmentCheck("音频", "当前麦克风", "ok", "使用系统默认麦克风"))
        return checks

    matched = any(configured == device.name or configured == str(device.index) for device in devices)
    checks.append(
        EnvironmentCheck(
            "音频",
            "当前麦克风",
            "ok" if matched else "fail",
            configured if matched else f"当前配置不可见: {configured}",
            "在 设置 -> 高级 -> 麦克风 中刷新并选择当前设备。" if not matched else "",
        )
    )
    return checks


def _asr_checks(config: AppConfig) -> list[EnvironmentCheck]:
    if config.asr_provider == "mock":
        return [EnvironmentCheck("ASR", "模式", "ok", "mock，本地闭环测试")]
    if config.asr_provider == ASR_PROVIDER_QWEN:
        missing = []
        if not config.qwen_endpoint:
            missing.append("Endpoint")
        if not config.qwen_api_key:
            missing.append("API Key")
        if not config.qwen_model:
            missing.append("Model")
        if missing:
            return [
                EnvironmentCheck(
                    "ASR",
                    "千问配置",
                    "fail",
                    "缺少 " + "、".join(missing),
                    "在 设置 -> ASR 中补齐。Key 不会写入日志。",
                )
            ]
        return [
            EnvironmentCheck(
                "ASR",
                "千问配置",
                "ok",
                config.qwen_model,
                f"Endpoint: {config.qwen_endpoint}；Language: {config.qwen_language}",
            )
        ]

    if config.asr_provider not in DOUBAO_ASR_PROVIDERS:
        return [EnvironmentCheck("ASR", "模式", "fail", f"未知 ASR provider: {config.asr_provider}")]

    missing = []
    if not config.doubao_endpoint:
        missing.append("Endpoint")
    if not config.doubao_app_key:
        missing.append("App Key")
    if not config.doubao_access_key:
        missing.append("Access Key")
    if not config.doubao_resource_id:
        missing.append("Resource ID")

    if missing:
        return [
            EnvironmentCheck(
                "ASR",
                "豆包配置",
                "fail",
                "缺少 " + "、".join(missing),
                "在 设置 -> ASR 中补齐。Key 不会写入日志。",
            )
        ]
    return [
        EnvironmentCheck(
            "ASR",
            "豆包配置",
            "ok",
            "bigmodel_async 配置完整",
            f"Resource ID: {config.doubao_resource_id}",
        )
    ]


def _organizer_checks(config: AppConfig) -> list[EnvironmentCheck]:
    provider = _organizer_provider_label(config.organizer_provider)
    if not config.organizer_api_key:
        return [
            EnvironmentCheck(
                "整理模型",
                provider,
                "warn",
                "未配置 API Key",
                "轻点右 Alt 的整理模式会回退输入原始识别文本。",
            )
        ]
    if not config.organizer_endpoint:
        return [EnvironmentCheck("整理模型", provider, "fail", "未配置 Endpoint")]
    return [
        EnvironmentCheck(
            "整理模型",
            provider,
            "ok",
            f"{config.organizer_model} 配置完整",
            config.organizer_endpoint,
        )
    ]


def _organizer_provider_label(provider: str) -> str:
    if provider == "deepseek":
        return "DeepSeek"
    if provider == "openai_compatible":
        return "OpenAI 兼容接口"
    return provider or "未配置"


def _hotkey_checks(config: AppConfig) -> list[EnvironmentCheck]:
    backend = config.hotkey_backend
    if backend in {"none", "disabled", "off"}:
        return [EnvironmentCheck("快捷键", "全局监听", "warn", "已关闭内置全局快捷键")]

    pynput_ok = PynputHotkeyBackend(config.hotkey_key).is_available()
    evdev_ok = EvdevHotkeyBackend(config.evdev_key, config.evdev_device or None).is_available()
    checks = [
        EnvironmentCheck("快捷键", "pynput", "ok" if pynput_ok else "warn", "可用" if pynput_ok else "不可用"),
        EnvironmentCheck("快捷键", "evdev", "ok" if evdev_ok else "warn", "可用" if evdev_ok else "不可用或权限不足"),
    ]

    if backend == "auto":
        checks.append(
            EnvironmentCheck(
                "快捷键",
                "当前策略",
                "ok" if (pynput_ok or evdev_ok) else "fail",
                "auto 可选择可用 backend" if (pynput_ok or evdev_ok) else "没有可用快捷键 backend",
            )
        )
    elif backend == "pynput":
        checks.append(EnvironmentCheck("快捷键", "当前策略", "ok" if pynput_ok else "fail", "pynput"))
    elif backend == "evdev":
        checks.append(EnvironmentCheck("快捷键", "当前策略", "ok" if evdev_ok else "fail", "evdev"))
    else:
        checks.append(EnvironmentCheck("快捷键", "当前策略", "fail", f"未知 backend: {backend}"))

    if _is_wayland():
        checks.append(
            EnvironmentCheck(
                "快捷键",
                "Wayland",
                "warn",
                "全局监听可能被桌面环境拦截",
                "推荐把系统全局快捷键绑定到 AppImage toggle。",
            )
        )
    return checks


def _injection_checks(config: AppConfig) -> list[EnvironmentCheck]:
    fcitx5_ok = _safe_available(Fcitx5Injector())
    wtype_ok = _safe_available(WtypeInjector())
    xdotool_ok = _safe_available(XdotoolInjector())
    ydotool_ok = _safe_available(YdotoolInjector())
    clipboard_ok = _safe_available(ClipboardInjector(config.paste_hotkey))
    click_ok = _mouse_click_available()

    checks = [
        EnvironmentCheck("输入", "fcitx5", "ok" if fcitx5_ok else "warn", "可用" if fcitx5_ok else "不可用"),
        EnvironmentCheck("输入", "wtype", "ok" if wtype_ok else "warn", "可用" if wtype_ok else "不可用"),
        EnvironmentCheck("输入", "xdotool", "ok" if xdotool_ok else "warn", "可用" if xdotool_ok else "不可用"),
        EnvironmentCheck("输入", "ydotool", "ok" if ydotool_ok else "warn", "可用" if ydotool_ok else "不可用或 ydotoold 未启动"),
        EnvironmentCheck(
            "输入",
            "剪贴板粘贴",
            "ok" if clipboard_ok else "fail",
            f"可用，快捷键 {config.paste_hotkey}" if clipboard_ok else "没有可用剪贴板 fallback",
        ),
    ]
    if config.paste_at_mouse:
        checks.append(
            EnvironmentCheck(
                "输入",
                "鼠标位置点击",
                "ok" if click_ok else "fail",
                "可用" if click_ok else "没有可用鼠标点击工具",
                "Wayland 推荐 ydotoold；X11 可使用 xdotool。" if not click_ok else "",
            )
        )
    if not any((fcitx5_ok, wtype_ok, xdotool_ok, ydotool_ok, clipboard_ok)):
        checks.append(EnvironmentCheck("输入", "当前策略", "fail", "没有可用文本输入 backend"))
    return checks


def _system_checks() -> list[EnvironmentCheck]:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return [EnvironmentCheck("系统", "systemd user", "warn", "没有 systemctl，自启动不可用")]
    proc = subprocess.run(
        [systemctl, "--user", "show-environment"],
        text=True,
        capture_output=True,
        timeout=2.0,
        check=False,
    )
    return [
        EnvironmentCheck(
            "系统",
            "systemd user",
            "ok" if proc.returncode == 0 else "warn",
            "可用" if proc.returncode == 0 else "systemctl --user 不可用",
            proc.stderr.strip() if proc.returncode != 0 else "",
        )
    ]


def _glibc_version() -> str:
    try:
        return os.confstr("CS_GNU_LIBC_VERSION")
    except Exception:  # noqa: BLE001
        libc_name, libc_version = platform.libc_ver()
        return " ".join(part for part in (libc_name, libc_version) if part) or "未知"


def _safe_available(injector: object) -> bool:
    try:
        return bool(injector.is_available())
    except Exception:  # noqa: BLE001
        return False


def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _mouse_click_available() -> bool:
    if shutil.which("ydotool") and _ydotool_socket().exists():
        return True
    return bool(os.environ.get("DISPLAY")) and shutil.which("xdotool") is not None


def _ydotool_socket() -> Path:
    configured = os.environ.get("YDOTOOL_SOCKET")
    if configured:
        return Path(configured)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / ".ydotool_socket"


def _status_text(status: str) -> str:
    return {
        "ok": "正常",
        "warn": "注意",
        "fail": "失败",
        "info": "信息",
    }.get(status, status)
