from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

from .base import InjectionError, TextInjectorBackend


class MousePositionInjector(TextInjectorBackend):
    def __init__(self, delegate: TextInjectorBackend) -> None:
        self.delegate = delegate
        self.name = f"mouse-click -> {delegate.name}"

    def is_available(self) -> bool:
        return self.delegate.is_available() and _mouse_click_available()

    def inject_text(self, text: str) -> None:
        _click_current_mouse_position()
        time.sleep(0.12)
        self.delegate.inject_text(text)


def _mouse_click_available() -> bool:
    if shutil.which("ydotool") and _ydotool_socket().exists():
        return True
    return bool(os.environ.get("DISPLAY")) and shutil.which("xdotool") is not None


def _click_current_mouse_position() -> None:
    if shutil.which("ydotool") and _ydotool_socket().exists():
        proc = subprocess.run(
            ["ydotool", "click", "0xC0"],
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
    elif os.environ.get("DISPLAY") and shutil.which("xdotool"):
        proc = subprocess.run(
            ["xdotool", "click", "1"],
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
    else:
        raise InjectionError("没有可用的鼠标点击工具，无法粘贴到鼠标位置")

    if proc.returncode != 0:
        raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or "鼠标点击失败")


def _ydotool_socket() -> Path:
    configured = os.environ.get("YDOTOOL_SOCKET")
    if configured:
        return Path(configured)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / ".ydotool_socket"
