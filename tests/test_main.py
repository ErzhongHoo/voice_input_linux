from __future__ import annotations

from types import SimpleNamespace

from voice_input import main as main_module


def test_quit_is_success_when_daemon_socket_is_missing(monkeypatch, tmp_path, capsys) -> None:
    socket_path = tmp_path / "missing.sock"
    monkeypatch.setattr(main_module, "load_config", lambda: SimpleNamespace(socket_path=str(socket_path)))

    assert main_module.main(["quit"]) == 0

    captured = capsys.readouterr()
    assert "后台服务未运行，无需退出" in captured.out
    assert captured.err == ""


def test_non_quit_command_fails_when_daemon_socket_is_missing(monkeypatch, tmp_path, capsys) -> None:
    socket_path = tmp_path / "missing.sock"
    monkeypatch.setattr(main_module, "load_config", lambda: SimpleNamespace(socket_path=str(socket_path)))

    assert main_module.main(["toggle"]) == 2

    captured = capsys.readouterr()
    assert "无法连接后台服务 socket" in captured.err
