from __future__ import annotations

import shutil
import subprocess

from .base import InjectionError, TextInjectorBackend


class Fcitx5Injector(TextInjectorBackend):
    name = "fcitx5-dbus"

    def is_available(self) -> bool:
        if shutil.which("fcitx5-remote") is None or shutil.which("gdbus") is None:
            return False
        return any(_method_exists(command) for command in _commit_candidates(""))

    def inject_text(self, text: str) -> None:
        if not self.is_available():
            raise InjectionError("fcitx5-remote 或 gdbus 不可用")

        errors: list[str] = []
        for command in _commit_candidates(text):
            proc = subprocess.run(command, text=True, capture_output=True, timeout=2.0, check=False)
            if proc.returncode == 0:
                return
            errors.append(proc.stderr.strip() or proc.stdout.strip() or str(proc.returncode))
        raise InjectionError("fcitx5 DBus commit 失败: " + " | ".join(errors))


def _commit_candidates(text: str) -> list[list[str]]:
    return [
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.fcitx.Fcitx5",
            "--object-path",
            "/controller",
            "--method",
            "org.fcitx.Fcitx.Controller1.CommitString",
            text,
        ],
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.fcitx.Fcitx",
            "--object-path",
            "/inputmethod",
            "--method",
            "org.fcitx.Fcitx.InputMethod.CommitString",
            text,
        ],
    ]


def _method_exists(command: list[str]) -> bool:
    proc = subprocess.run(command, text=True, capture_output=True, timeout=1.0, check=False)
    return proc.returncode == 0
