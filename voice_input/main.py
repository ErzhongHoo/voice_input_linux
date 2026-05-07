from __future__ import annotations

import argparse
import logging
import socket
import sys

from .config import load_config


def send_daemon_command(
    command: str,
    quiet: bool = False,
    wait_ack: bool = False,
    missing_ok: bool = False,
) -> int:
    config = load_config()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(config.socket_path)
            client.sendall(command.encode("utf-8"))
            if wait_ack:
                response = client.recv(16)
                if response.strip() != b"ok":
                    return 2
    except OSError as exc:
        if missing_ok:
            if not quiet:
                print(f"后台服务未运行，无需退出。socket: {config.socket_path}")
            return 0
        if not quiet:
            print(
                f"无法连接后台服务 socket: {config.socket_path}\n"
                f"请先运行 python -m voice_input.main run，或检查 systemd user service。\n"
                f"错误: {exc}",
                file=sys.stderr,
            )
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice-input-linux")
    parser.add_argument(
        "command",
        nargs="?",
        default="launch",
        choices=(
            "launch",
            "run",
            "show",
            "toggle",
            "start",
            "stop",
            "settings",
            "quit",
            "install",
            "uninstall",
            "install-service",
            "uninstall-service",
            "install-desktop",
            "uninstall-desktop",
        ),
        help="无参数启动控制面板；run 启动后台服务；toggle/start/stop/settings/quit 控制服务",
    )
    args = parser.parse_args(argv)

    if args.command in {"show", "toggle", "start", "stop", "settings", "quit"}:
        return send_daemon_command(args.command, missing_ok=args.command == "quit")

    if args.command in {
        "install",
        "uninstall",
        "install-service",
        "uninstall-service",
        "install-desktop",
        "uninstall-desktop",
    }:
        from .installer import (
            install_all,
            install_desktop,
            install_service,
            uninstall_all,
            uninstall_desktop,
            uninstall_service,
        )

        handlers = {
            "install": install_all,
            "uninstall": uninstall_all,
            "install-service": install_service,
            "uninstall-service": uninstall_service,
            "install-desktop": install_desktop,
            "uninstall-desktop": uninstall_desktop,
        }
        return handlers[args.command]()

    if args.command == "launch":
        if send_daemon_command("show", quiet=True, wait_ack=True) == 0:
            return 0
        if send_daemon_command("settings", quiet=True) == 0:
            return 0

    from .app import run_app

    try:
        return run_app(show_panel=args.command == "launch")
    except ImportError as exc:
        logging.exception("Failed to import desktop dependencies")
        print(f"缺少桌面依赖: {exc}", file=sys.stderr)
        print("请先执行: pip install -r requirements.txt", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
