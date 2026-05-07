from __future__ import annotations

import os
import shutil
import subprocess

from .base import InjectionError, TextInjectorBackend


class WtypeInjector(TextInjectorBackend):
    name = "wtype"

    def is_available(self) -> bool:
        return bool(os.environ.get("WAYLAND_DISPLAY")) and shutil.which("wtype") is not None

    def inject_text(self, text: str) -> None:
        if not self.is_available():
            raise InjectionError("wtype 不可用或当前不是 Wayland session")
        proc = subprocess.run(
            ["wtype", "--", text],
            text=True,
            capture_output=True,
            timeout=10.0,
            check=False,
        )
        if proc.returncode != 0:
            raise InjectionError(proc.stderr.strip() or proc.stdout.strip() or "wtype failed")

