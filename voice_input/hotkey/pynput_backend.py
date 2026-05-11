from __future__ import annotations

from collections.abc import Callable
import logging
import os
from typing import Any

from .base import HotkeyBackend, HotkeyError


LOGGER = logging.getLogger(__name__)


class PynputHotkeyBackend(HotkeyBackend):
    name = "pynput"

    def __init__(self, key_name: str = "right_alt") -> None:
        self.key_name = key_name
        self._listener: Any | None = None
        self._pressed = False

    def is_available(self) -> bool:
        try:
            import pynput.keyboard  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("pynput unavailable: %s", exc)
            return False
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def start(
        self,
        callback: Callable[[], None],
        release_callback: Callable[[], None] | None = None,
    ) -> None:
        try:
            from pynput import keyboard
        except Exception as exc:  # noqa: BLE001
            raise HotkeyError(f"pynput 不可用: {exc}") from exc

        target_keys = self._target_keys(keyboard)
        self._pressed = False

        def on_press(key: object) -> None:
            if key in target_keys and not self._pressed:
                self._pressed = True
                callback()

        def on_release(key: object) -> None:
            if key in target_keys and self._pressed:
                self._pressed = False
                if release_callback is not None:
                    release_callback()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._pressed = False

    def _target_keys(self, keyboard: Any) -> set[object]:
        normalized = self.key_name.strip().lower().replace("-", "_")
        names = {normalized}
        if normalized in {"right_alt", "alt_r", "key.alt_r"}:
            names.update({"alt_r", "key.alt_r", "right_alt"})
        if normalized in {"altgr", "alt_gr", "key.alt_gr"}:
            names.update({"alt_gr", "key.alt_gr", "altgr"})

        targets: set[object] = set()
        if names & {"right_alt", "alt_r", "key.alt_r"} and hasattr(keyboard.Key, "alt_r"):
            targets.add(keyboard.Key.alt_r)
        if names & {"altgr", "alt_gr", "key.alt_gr"} and hasattr(keyboard.Key, "alt_gr"):
            targets.add(keyboard.Key.alt_gr)

        # Some layouts expose Right Alt as AltGr, so listen to both by default.
        if normalized == "right_alt" and hasattr(keyboard.Key, "alt_gr"):
            targets.add(keyboard.Key.alt_gr)

        if not targets:
            raise HotkeyError(f"不支持的 pynput 快捷键: {self.key_name}")
        return targets
