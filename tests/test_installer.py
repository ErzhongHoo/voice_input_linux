from voice_input.installer import (
    _desktop_entry,
    _launcher_command,
    _service_unit,
    desktop_entry_path,
    desktop_shortcut_path,
    install_desktop,
    is_desktop_installed,
    toggle_command_text,
)


def test_appimage_launcher_defaults_to_no_argument(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    assert _launcher_command() == [
        "/usr/bin/env",
        "APPIMAGE_EXTRACT_AND_RUN=1",
        "/tmp/VoiceInputLinux.AppImage",
    ]
    assert _launcher_command("run") == [
        "/usr/bin/env",
        "APPIMAGE_EXTRACT_AND_RUN=1",
        "/tmp/VoiceInputLinux.AppImage",
        "run",
    ]


def test_desktop_entry_launches_control_panel_by_default(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    entry = _desktop_entry()
    assert "Exec=/usr/bin/env APPIMAGE_EXTRACT_AND_RUN=1 /tmp/VoiceInputLinux.AppImage\n" in entry
    assert "Exec=/usr/bin/env APPIMAGE_EXTRACT_AND_RUN=1 /tmp/VoiceInputLinux.AppImage settings" in entry
    assert "Exec=/usr/bin/env APPIMAGE_EXTRACT_AND_RUN=1 /tmp/VoiceInputLinux.AppImage toggle" in entry
    assert "Icon=voice-input-linux\n" in entry


def test_service_unit_uses_run_command(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    unit = _service_unit("/tmp/voice-input-linux.env")
    assert "ExecStart=/usr/bin/env APPIMAGE_EXTRACT_AND_RUN=1 /tmp/VoiceInputLinux.AppImage run" in unit


def test_toggle_command_text_uses_launcher(monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    assert toggle_command_text() == "/usr/bin/env APPIMAGE_EXTRACT_AND_RUN=1 /tmp/VoiceInputLinux.AppImage toggle"


def test_desktop_shortcut_path_uses_user_desktop_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DESKTOP_DIR", raising=False)
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    (config_dir / "user-dirs.dirs").write_text('XDG_DESKTOP_DIR="$HOME/DesktopCustom"\n', encoding="utf-8")

    assert desktop_shortcut_path() == tmp_path / "DesktopCustom" / "voice-input-linux.desktop"


def test_install_desktop_writes_menu_entry_and_desktop_shortcut(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setenv("APPIMAGE", "/tmp/VoiceInputLinux.AppImage")
    monkeypatch.setattr("voice_input.installer._run", lambda command, check=True: 0)

    assert not is_desktop_installed()

    status = install_desktop()

    assert status == 0
    assert desktop_entry_path().exists()
    assert desktop_shortcut_path().exists()

    svg_icon_path = tmp_path / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "voice-input-linux.svg"
    png_icon_path = tmp_path / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "voice-input-linux.png"
    assert svg_icon_path.exists()
    assert png_icon_path.exists()
    assert "Icon=voice-input-linux\n" in desktop_entry_path().read_text(encoding="utf-8")
    assert "Icon=voice-input-linux\n" in desktop_shortcut_path().read_text(encoding="utf-8")
