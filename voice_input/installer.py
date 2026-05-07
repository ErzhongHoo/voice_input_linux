from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys

from .config import ensure_config_file, load_config


APP_ID = "voice-input-linux"
APP_NAME = "Voice Input Linux"
SERVICE_NAME = f"{APP_ID}.service"


def install_all(start_service: bool = True) -> int:
    desktop_status = install_desktop()
    service_status = install_service(start=start_service)
    return desktop_status or service_status


def uninstall_all(stop_service: bool = True) -> int:
    service_status = uninstall_service(stop=stop_service)
    desktop_status = uninstall_desktop()
    return service_status or desktop_status


def install_service(start: bool = True) -> int:
    config = load_config()
    ensure_config_file(config.config_file, config)

    service_path = service_unit_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_path.write_text(_service_unit(config.config_file), encoding="utf-8")

    status = _run(["systemctl", "--user", "daemon-reload"])
    if status != 0:
        return status
    command = ["systemctl", "--user", "enable", SERVICE_NAME]
    if start:
        command.insert(3, "--now")
    status = _run(command)
    if status != 0:
        return status
    print(f"已安装用户服务: {service_path}")
    return 0


def uninstall_service(stop: bool = True) -> int:
    service_path = service_unit_path()
    command = ["systemctl", "--user", "disable", SERVICE_NAME]
    if stop:
        command.insert(3, "--now")
    _run(command, check=False)
    if service_path.exists():
        service_path.unlink()
    status = _run(["systemctl", "--user", "daemon-reload"], check=False)
    print(f"已移除用户服务: {service_path}")
    return status


def install_desktop() -> int:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    applications_dir = applications_path()
    icons_dir = data_home / "icons" / "hicolor" / "scalable" / "apps"
    applications_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    desktop_path = desktop_entry_path()
    desktop_path.write_text(_desktop_entry(), encoding="utf-8")
    desktop_path.chmod(0o755)

    with as_file(files("voice_input.resources").joinpath(f"{APP_ID}.svg")) as icon_path:
        shutil.copy2(icon_path, icons_dir / f"{APP_ID}.svg")

    _run(["update-desktop-database", str(applications_dir)], check=False)
    _run(["gtk-update-icon-cache", "-q", str(data_home / "icons" / "hicolor")], check=False)
    print(f"已安装桌面入口: {desktop_path}")
    return 0


def uninstall_desktop() -> int:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    desktop_path = desktop_entry_path()
    icon_path = data_home / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"
    for path in (desktop_path, icon_path):
        if path.exists():
            path.unlink()
    _run(["update-desktop-database", str(data_home / "applications")], check=False)
    _run(["gtk-update-icon-cache", "-q", str(data_home / "icons" / "hicolor")], check=False)
    print("已移除桌面入口和图标")
    return 0


def service_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME


def applications_path() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "applications"


def desktop_entry_path() -> Path:
    return applications_path() / f"{APP_ID}.desktop"


def is_service_installed() -> bool:
    return service_unit_path().exists()


def is_service_enabled() -> bool:
    return _systemctl_quiet("is-enabled", SERVICE_NAME)


def is_service_active() -> bool:
    return _systemctl_quiet("is-active", SERVICE_NAME)


def is_desktop_installed() -> bool:
    return desktop_entry_path().exists()


def toggle_command_text() -> str:
    return shlex.join(_launcher_command("toggle"))


def _service_unit(config_file: str) -> str:
    command = _launcher_command("run")
    working_directory = Path.home() if _is_appimage() else _project_root()
    return "\n".join(
        [
            "[Unit]",
            f"Description={APP_NAME} desktop dictation service",
            "After=graphical-session.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={_systemd_arg(str(working_directory))}",
            f"Environment=VOICE_INPUT_CONFIG_FILE={_systemd_arg(config_file)}",
            f"ExecStart={' '.join(_systemd_arg(arg) for arg in command)}",
            "Restart=on-failure",
            "RestartSec=2",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def _desktop_entry() -> str:
    with as_file(files("voice_input.resources").joinpath(f"{APP_ID}.desktop")) as desktop_path:
        template = desktop_path.read_text(encoding="utf-8")
    launcher = " ".join(_desktop_arg(arg) for arg in _launcher_command())
    return template.replace("Exec=voice-input-linux", f"Exec={launcher}")


def _launcher_command(command: str | None = None) -> list[str]:
    appimage = os.environ.get("VOICE_INPUT_APPIMAGE") or os.environ.get("APPIMAGE")
    suffix = [command] if command else []
    if appimage:
        return [appimage, *suffix]
    if getattr(sys, "frozen", False):
        return [sys.executable, *suffix]
    return ["/usr/bin/env", f"PYTHONPATH={_project_root()}", sys.executable, "-m", "voice_input.main", *suffix]


def _is_appimage() -> bool:
    return bool(os.environ.get("VOICE_INPUT_APPIMAGE") or os.environ.get("APPIMAGE"))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _systemd_arg(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or any(ch in value for ch in ('"', "'", "\\")):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _desktop_arg(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or any(ch in value for ch in ('"', "'", "\\", "$")):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'
    return value


def _run(command: list[str], check: bool = True) -> int:
    executable = shutil.which(command[0])
    if executable is None:
        return 0 if not check else _missing_command(command[0])
    proc = subprocess.run([executable, *command[1:]], text=True, check=False)
    if proc.returncode != 0 and check:
        print(f"命令失败: {' '.join(command)}", file=sys.stderr)
    return proc.returncode


def _systemctl_quiet(command: str, unit: str) -> bool:
    if shutil.which("systemctl") is None:
        return False
    proc = subprocess.run(
        ["systemctl", "--user", command, "--quiet", unit],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def _missing_command(command: str) -> int:
    print(f"缺少命令: {command}", file=sys.stderr)
    return 127
