from __future__ import annotations

import os
import shutil
import subprocess

from .base import InjectionError, TextInjectorBackend


class XdotoolInjector(TextInjectorBackend):
    name = "xdotool"

    def is_available(self) -> bool:
        return bool(os.environ.get("DISPLAY")) and shutil.which("xdotool") is not None

    def inject_text(self, text: str) -> None:
        if not self.is_available():
            raise InjectionError("xdotool 不可用或当前不是 X11/XWayland DISPLAY")
        proc = subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "0", text],
            text=True,
            capture_output=True,
            timeout=10.0,
            check=False,
        )
        if proc.returncode != 0:
            raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or "xdotool type failed")

