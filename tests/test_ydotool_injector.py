import subprocess

from voice_input.inject.ydotool_injector import YdotoolInjector


def test_ydotool_types_ascii_text(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(YdotoolInjector, "is_available", lambda self: True)
    monkeypatch.setattr("voice_input.inject.ydotool_injector.copy_to_clipboard", lambda text: calls.append(["copy", text]))

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("voice_input.inject.ydotool_injector.subprocess.run", fake_run)

    YdotoolInjector().inject_text("hello")

    assert calls == [["ydotool", "type", "--", "hello"]]


def test_ydotool_pastes_non_ascii_text(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(YdotoolInjector, "is_available", lambda self: True)
    monkeypatch.setattr("voice_input.inject.ydotool_injector.copy_to_clipboard", lambda text: calls.append(["copy", text]))

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("voice_input.inject.ydotool_injector.subprocess.run", fake_run)

    YdotoolInjector("ctrl+shift+v").inject_text("你好")

    assert calls == [
        ["copy", "你好"],
        ["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"],
    ]
