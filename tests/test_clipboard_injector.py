from voice_input.inject.clipboard_injector import PASTE_SHORTCUTS, ClipboardInjector, normalize_paste_hotkey


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
