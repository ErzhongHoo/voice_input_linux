from __future__ import annotations

import logging
import os

from voice_input.config import AppConfig

from .base import CompositeInjector, InjectionError, TextInjectorBackend
from .clipboard_injector import ClipboardInjector
from .fcitx5_injector import Fcitx5Injector
from .mouse_injector import MousePositionInjector
from .wtype_injector import WtypeInjector
from .xdotool_injector import XdotoolInjector
from .ydotool_injector import YdotoolInjector


LOGGER = logging.getLogger(__name__)


def build_text_injector(config: AppConfig) -> TextInjectorBackend:
    requested = config.injector_backend
    registry: dict[str, TextInjectorBackend] = {
        "fcitx5": Fcitx5Injector(),
        "xdotool": XdotoolInjector(),
        "wtype": WtypeInjector(),
        "ydotool": YdotoolInjector(config.paste_hotkey),
        "clipboard": ClipboardInjector(config.paste_hotkey),
    }

    if requested != "auto":
        injector = registry.get(requested)
        if injector is None:
            raise InjectionError(f"未知文本注入 backend: {requested}")
        return _maybe_wrap_mouse_injector(CompositeInjector([injector]), config)

    candidates: list[TextInjectorBackend] = []
    if config.prefer_fcitx5:
        candidates.append(Fcitx5Injector())
    if _is_wayland():
        candidates.extend(
            [
                ClipboardInjector(config.paste_hotkey),
                WtypeInjector(),
                YdotoolInjector(config.paste_hotkey),
                XdotoolInjector(),
            ]
        )
    else:
        candidates.extend(
            [
                XdotoolInjector(),
                ClipboardInjector(config.paste_hotkey),
                WtypeInjector(),
                YdotoolInjector(config.paste_hotkey),
            ]
        )
    available = [candidate for candidate in candidates if candidate.is_available()]
    if not available:
        LOGGER.warning("No text injector backend reports available; clipboard fallback will still be tried")
        available = [ClipboardInjector(config.paste_hotkey)]
    return _maybe_wrap_mouse_injector(CompositeInjector(available), config)


def _maybe_wrap_mouse_injector(injector: TextInjectorBackend, config: AppConfig) -> TextInjectorBackend:
    if config.paste_at_mouse:
        return MousePositionInjector(injector)
    return injector


def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"


__all__ = ["build_text_injector", "InjectionError", "TextInjectorBackend"]
