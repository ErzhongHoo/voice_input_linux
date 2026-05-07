from voice_input.installer import _desktop_entry, _launcher_command, _service_unit, toggle_command_text


def test_appimage_launcher_defaults_to_no_argument(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    assert _launcher_command() == ["/tmp/VoiceInputLinux.AppImage"]
    assert _launcher_command("run") == ["/tmp/VoiceInputLinux.AppImage", "run"]


def test_desktop_entry_launches_control_panel_by_default(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    entry = _desktop_entry()
    assert "Exec=/tmp/VoiceInputLinux.AppImage\n" in entry
    assert "Exec=/tmp/VoiceInputLinux.AppImage settings" in entry
    assert "Exec=/tmp/VoiceInputLinux.AppImage toggle" in entry


def test_service_unit_uses_run_command(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    unit = _service_unit("/tmp/voice-input-linux.env")
    assert "ExecStart=/tmp/VoiceInputLinux.AppImage run" in unit


def test_toggle_command_text_uses_launcher(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    assert toggle_command_text() == "/tmp/VoiceInputLinux.AppImage toggle"
