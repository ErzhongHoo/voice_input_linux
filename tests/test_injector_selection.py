from voice_input.config import AppConfig
from voice_input.inject import build_text_injector
from voice_input.inject.clipboard_injector import ClipboardInjector
from voice_input.inject.wtype_injector import WtypeInjector
from voice_input.inject.xdotool_injector import XdotoolInjector
from voice_input.inject.ydotool_injector import YdotoolInjector


def test_wayland_auto_prefers_clipboard_before_direct_typing(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    _mark_available(monkeypatch)

    injector = build_text_injector(AppConfig(prefer_fcitx5=False, paste_at_mouse=False))

    assert injector.name.startswith("clipboard-paste(ctrl+v) -> wtype")


def test_x11_auto_prefers_xdotool_before_clipboard(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    _mark_available(monkeypatch)

    injector = build_text_injector(AppConfig(prefer_fcitx5=False, paste_at_mouse=False))

    assert injector.name.startswith("xdotool -> clipboard-paste(ctrl+v)")


def _mark_available(monkeypatch) -> None:
    for backend in (ClipboardInjector, WtypeInjector, XdotoolInjector, YdotoolInjector):
        monkeypatch.setattr(backend, "is_available", lambda self: True)
