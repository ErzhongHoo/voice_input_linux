import subprocess

from voice_input.inject.base import InjectionError
from voice_input.inject.clipboard_injector import (
    PASTE_SHORTCUTS,
    ClipboardInjector,
    _desktop_subprocess_env,
    copy_to_clipboard,
    normalize_paste_hotkey,
)


def test_normalize_paste_hotkey_aliases() -> None:
    assert normalize_paste_hotkey("Control+Shift+V") == "ctrl+shift+v"
    assert normalize_paste_hotkey("shift+ctrl+v") == "ctrl+shift+v"
    assert normalize_paste_hotkey("shift-ins") == "shift+insert"
    assert normalize_paste_hotkey("shift+insert") == "shift+insert"
    assert normalize_paste_hotkey("unknown") == "ctrl+v"


def test_clipboard_injector_names_configured_shortcut() -> None:
    injector = ClipboardInjector("ctrl+shift+v")
    assert injector.paste_hotkey == "ctrl+shift+v"
    assert injector.name == "clipboard-paste(ctrl+shift+v)"


def test_supported_shortcuts_have_ydotool_sequences() -> None:
    assert PASTE_SHORTCUTS["ctrl+v"]["ydotool"] == ["29:1", "47:1", "47:0", "29:0"]
    assert PASTE_SHORTCUTS["ctrl+shift+v"]["ydotool"] == ["29:1", "42:1", "47:1", "47:0", "42:0", "29:0"]
    assert PASTE_SHORTCUTS["shift+insert"]["ydotool"] == ["42:1", "110:1", "110:0", "42:0"]


def test_clipboard_injector_uses_shared_copy(monkeypatch) -> None:
    copied = []

    monkeypatch.setattr("voice_input.inject.clipboard_injector.copy_to_clipboard", copied.append)
    monkeypatch.setattr(ClipboardInjector, "_paste", lambda self: None)

    ClipboardInjector().inject_text("hello")

    assert copied == ["hello"]


def test_clipboard_injector_does_not_report_available_for_xdotool_only(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("voice_input.inject.clipboard_injector._qt_clipboard_available", lambda: False)
    monkeypatch.setattr(
        "voice_input.inject.clipboard_injector.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "xdotool" else None,
    )

    assert ClipboardInjector().is_available() is False


def test_copy_to_clipboard_falls_back_after_wl_copy_failure(monkeypatch) -> None:
    calls = []

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(
        "voice_input.inject.clipboard_injector.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "wl-copy" else None,
    )
    monkeypatch.setattr("voice_input.inject.clipboard_injector._kde_klipper_available", lambda: False)
    monkeypatch.setattr("voice_input.inject.clipboard_injector._qt_clipboard_available", lambda: False)

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "wl-copy failed")

    monkeypatch.setattr("voice_input.inject.clipboard_injector.subprocess.run", fake_run)
    monkeypatch.setattr("pyperclip.copy", lambda text: calls.append(["pyperclip", text]))

    copy_to_clipboard("hello")

    assert calls == [["wl-copy"], ["pyperclip", "hello"]]


def test_copy_to_clipboard_reports_all_failed_backends(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("voice_input.inject.clipboard_injector._qt_clipboard_available", lambda: False)
    monkeypatch.setattr(
        "voice_input.inject.clipboard_injector.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "xclip" else None,
    )
    monkeypatch.setattr(
        "voice_input.inject.clipboard_injector._copy_with_x_selection",
        lambda command, text: (_ for _ in ()).throw(InjectionError("xclip failed")),
    )
    monkeypatch.setattr("pyperclip.copy", lambda text: (_ for _ in ()).throw(RuntimeError("pyperclip failed")))

    try:
        copy_to_clipboard("hello")
    except InjectionError as exc:
        message = str(exc)
    else:
        raise AssertionError("copy_to_clipboard should fail")

    assert "xclip: xclip failed" in message
    assert "pyperclip: pyperclip failed" in message


def test_desktop_subprocess_env_restores_original_library_path(monkeypatch) -> None:
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/bundled")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib")

    assert _desktop_subprocess_env()["LD_LIBRARY_PATH"] == "/usr/lib"


def test_desktop_subprocess_env_removes_appimage_library_path(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInput.AppImage")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/bundled")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    assert "LD_LIBRARY_PATH" not in _desktop_subprocess_env()
