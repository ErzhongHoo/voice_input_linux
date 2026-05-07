from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

from .base import InjectionError, TextInjectorBackend


class YdotoolInjector(TextInjectorBackend):
    name = "ydotool"

    def is_available(self) -> bool:
        return shutil.which("ydotool") is not None and _ydotool_socket().exists()

    def inject_text(self, text: str) -> None:
        if not self.is_available():
            raise InjectionError(
                "ydotool 不可用。请先启动 ydotoold，并确保当前用户可访问 /dev/uinput。"
            )
        proc = subprocess.run(
            ["ydotool", "type", "--", text],
            text=True,
            capture_output=True,
            timeout=10.0,
            check=False,
        )
        if proc.returncode != 0:
            raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or "ydotool type failed")


def _ydotool_socket() -> Path:
    configured = os.environ.get("YDOTOOL_SOCKET")
    if configured:
        return Path(configured)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / ".ydotool_socket"

