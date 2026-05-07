from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .base import InjectionError, TextInjectorBackend

PASTE_SHORTCUTS = {
    "ctrl+v": {
        "xdotool": "ctrl+v",
        "wtype_modifiers": ["ctrl"],
        "wtype_key": "v",
        "ydotool": ["29:1", "47:1", "47:0", "29:0"],
    },
    "ctrl+shift+v": {
        "xdotool": "ctrl+shift+v",
        "wtype_modifiers": ["ctrl", "shift"],
        "wtype_key": "v",
        "ydotool": ["29:1", "42:1", "47:1", "47:0", "42:0", "29:0"],
    },
    "shift+insert": {
        "xdotool": "shift+Insert",
        "wtype_modifiers": ["shift"],
        "wtype_key": "Insert",
        "ydotool": ["42:1", "110:1", "110:0", "42:0"],
    },
}


class ClipboardInjector(TextInjectorBackend):
    _selection_owner: subprocess.Popen[str] | None = None

    def __init__(self, paste_hotkey: str = "ctrl+v") -> None:
        self.paste_hotkey = normalize_paste_hotkey(paste_hotkey)
        self.name = f"clipboard-paste({self.paste_hotkey})"

    def is_available(self) -> bool:
        return _clipboard_copy_available()

    def inject_text(self, text: str) -> None:
        copy_to_clipboard(text)
        time.sleep(0.05)
        try:
            self._paste()
        except InjectionError as exc:
            raise InjectionError(f"{exc}；文本已复制到剪贴板，请手动按 {self.paste_hotkey}。") from exc

    def _copy_with_x_selection(self, command: list[str], text: str) -> None:
        _copy_with_x_selection(command, text)

    def _paste(self) -> None:
        if _is_wayland():
            proc = _paste_wayland(self.paste_hotkey)
        else:
            proc = _paste_x11(self.paste_hotkey)
        if proc is None:
            raise InjectionError("没有可用的自动粘贴工具")
        if proc.returncode != 0:
            raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or "粘贴快捷键发送失败")


def copy_to_clipboard(text: str) -> None:
    errors: list[str] = []
    for name, copy in _clipboard_copy_strategies():
        try:
            copy(text)
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    detail = "；".join(errors) if errors else "没有检测到可用剪贴板工具"
    raise InjectionError(f"无法写入系统剪贴板: {detail}")


def _clipboard_copy_available() -> bool:
    if _is_wayland():
        return shutil.which("wl-copy") is not None or _kde_klipper_available() or _qt_clipboard_available()
    return any(shutil.which(command) for command in ("xclip", "xsel")) or _qt_clipboard_available()


def _clipboard_copy_strategies() -> list[tuple[str, Callable[[str], None]]]:
    strategies: list[tuple[str, Callable[[str], None]]] = []
    if _is_wayland():
        if shutil.which("wl-copy"):
            strategies.append(("wl-copy", _copy_with_wl_copy))
        if _kde_klipper_available():
            strategies.append(("KDE Klipper", _copy_with_kde_klipper))
        if _qt_clipboard_available():
            strategies.append(("Qt", _copy_with_qt))
    else:
        if shutil.which("xclip"):
            strategies.append(
                ("xclip", lambda text: _copy_with_x_selection(["xclip", "-selection", "clipboard"], text))
            )
        if shutil.which("xsel"):
            strategies.append(
                ("xsel", lambda text: _copy_with_x_selection(["xsel", "--clipboard", "--input"], text))
            )
        if _qt_clipboard_available():
            strategies.append(("Qt", _copy_with_qt))
    strategies.append(("pyperclip", _copy_with_pyperclip))
    return strategies


def _copy_with_wl_copy(text: str) -> None:
    _run_clipboard_command(["wl-copy"], text, "复制到 Wayland 剪贴板失败")


def _copy_with_kde_klipper(text: str) -> None:
    _run_clipboard_command(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.kde.klipper",
            "--object-path",
            "/klipper",
            "--method",
            "org.kde.klipper.klipper.setClipboardContents",
            text,
        ],
        None,
        "KDE Klipper 复制失败",
    )


def _run_clipboard_command(command: list[str], text: str | None, failure_message: str) -> None:
    try:
        proc = subprocess.run(
            command,
            env=_desktop_subprocess_env(),
            input=text,
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise InjectionError(f"{command[0]} 写入剪贴板超时") from exc
    except OSError as exc:
        raise InjectionError(str(exc)) from exc
    if proc.returncode != 0:
        raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or failure_message)


def _copy_with_pyperclip(text: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
    except Exception as exc:  # noqa: BLE001
        raise InjectionError(str(exc)) from exc


def _copy_with_x_selection(command: list[str], text: str) -> None:
    if ClipboardInjector._selection_owner and ClipboardInjector._selection_owner.poll() is None:
        ClipboardInjector._selection_owner.terminate()
    proc = subprocess.Popen(
        command,
        env=_desktop_subprocess_env(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    proc.stdin.write(text)
    proc.stdin.close()
    time.sleep(0.1)
    if proc.poll() not in (None, 0):
        stderr = proc.stderr.read() if proc.stderr else ""
        raise InjectionError(stderr.strip() or "复制到 X11 剪贴板失败")
    ClipboardInjector._selection_owner = proc


def normalize_paste_hotkey(value: str) -> str:
    raw = value.strip().lower().replace(" ", "").replace("_", "+").replace("-", "+")
    aliases = {"control": "ctrl", "ctl": "ctrl", "ins": "insert"}
    parts = [aliases.get(part, part) for part in raw.split("+") if part]
    if set(parts) == {"ctrl", "shift", "v"}:
        return "ctrl+shift+v"
    normalized = "+".join(parts)
    if normalized in PASTE_SHORTCUTS:
        return normalized
    return "ctrl+v"


def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _kde_klipper_available() -> bool:
    if shutil.which("gdbus") is None:
        return False
    try:
        proc = subprocess.run(
            [
                "gdbus",
                "introspect",
                "--session",
                "--dest",
                "org.kde.klipper",
                "--object-path",
                "/klipper",
            ],
            env=_desktop_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and "setClipboardContents" in proc.stdout


def _qt_clipboard_available() -> bool:
    try:
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() is not None
    except Exception:  # noqa: BLE001
        return False


def _copy_with_qt(text: str) -> None:
    from PySide6.QtGui import QClipboard, QGuiApplication

    clipboard = QGuiApplication.clipboard()
    if clipboard is None:
        raise InjectionError("Qt 剪贴板不可用")
    clipboard.setText(text, QClipboard.Mode.Clipboard)
    if clipboard.supportsSelection():
        clipboard.setText(text, QClipboard.Mode.Selection)
    QGuiApplication.processEvents()
    if clipboard.text(QClipboard.Mode.Clipboard) != text:
        raise InjectionError("Qt 剪贴板写入后读取不一致")


def _paste_wayland(shortcut: str) -> subprocess.CompletedProcess[str] | None:
    spec = PASTE_SHORTCUTS[normalize_paste_hotkey(shortcut)]
    if shutil.which("wtype"):
        command = ["wtype"]
        for modifier in spec["wtype_modifiers"]:
            command.extend(["-M", modifier])
        command.extend(["-P", spec["wtype_key"], "-p", spec["wtype_key"]])
        for modifier in reversed(spec["wtype_modifiers"]):
            command.extend(["-m", modifier])
        return subprocess.run(
            command,
            env=_desktop_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
    if shutil.which("ydotool") and _ydotool_socket().exists():
        return subprocess.run(
            ["ydotool", "key", *spec["ydotool"]],
            env=_desktop_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
    return None


def _paste_x11(shortcut: str) -> subprocess.CompletedProcess[str] | None:
    spec = PASTE_SHORTCUTS[normalize_paste_hotkey(shortcut)]
    if shutil.which("xdotool"):
        return subprocess.run(
            ["xdotool", "key", "--clearmodifiers", spec["xdotool"]],
            env=_desktop_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
    if shutil.which("ydotool") and _ydotool_socket().exists():
        return subprocess.run(
            ["ydotool", "key", *spec["ydotool"]],
            env=_desktop_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
    return None


def _ydotool_socket() -> Path:
    configured = os.environ.get("YDOTOOL_SOCKET")
    if configured:
        return Path(configured)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / ".ydotool_socket"


def _desktop_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    original_library_path = env.get("LD_LIBRARY_PATH_ORIG")
    if original_library_path is not None:
        env["LD_LIBRARY_PATH"] = original_library_path
    elif getattr(sys, "frozen", False) or env.get("APPIMAGE") or env.get("VOICE_INPUT_APPIMAGE"):
        env.pop("LD_LIBRARY_PATH", None)
    return env
