from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

from .base import InjectionError, TextInjectorBackend
from .clipboard_injector import PASTE_SHORTCUTS, _desktop_subprocess_env, copy_to_clipboard, normalize_paste_hotkey


class YdotoolInjector(TextInjectorBackend):
    def __init__(self, paste_hotkey: str = "ctrl+v") -> None:
        self.paste_hotkey = normalize_paste_hotkey(paste_hotkey)
        self.name = "ydotool"

    def is_available(self) -> bool:
        return shutil.which("ydotool") is not None and _ydotool_socket().exists()

    def inject_text(self, text: str) -> None:
        if not self.is_available():
            raise InjectionError(
                "ydotool 不可用。请先启动 ydotoold，并确保当前用户可访问 /dev/uinput。"
            )
        if _needs_clipboard_paste(text):
            self._paste_with_clipboard(text)
            return
        proc = subprocess.run(
            ["ydotool", "type", "--", text],
            env=_desktop_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=10.0,
            check=False,
        )
        if proc.returncode != 0:
            raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or "ydotool type failed")

    def _paste_with_clipboard(self, text: str) -> None:
        copy_to_clipboard(text)
        time.sleep(0.05)
        proc = subprocess.run(
            ["ydotool", "key", *PASTE_SHORTCUTS[self.paste_hotkey]["ydotool"]],
            env=_desktop_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
        if proc.returncode != 0:
            raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or "ydotool paste hotkey failed")


def _needs_clipboard_paste(text: str) -> bool:
    return any(ord(character) > 127 for character in text)


def _ydotool_socket() -> Path:
    configured = os.environ.get("YDOTOOL_SOCKET")
    if configured:
        return Path(configured)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / ".ydotool_socket"
