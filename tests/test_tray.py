from PySide6.QtWidgets import QApplication

from voice_input.ui import tray as tray_module
from voice_input.ui.tray import TrayController


class _Signal:
    def connect(self, callback) -> None:
        self.callback = callback


class _FakeTray:
    def __init__(self, icon) -> None:
        self._icon = icon
        self._visible = False
        self.activated = _Signal()
        self.icons: list[str] = []
        self.tooltips: list[str] = []
        self.messages: list[tuple[str, str, str, int]] = []

    def setToolTip(self, tooltip: str) -> None:  # noqa: N802
        self.tooltips.append(tooltip)

    def setContextMenu(self, menu) -> None:  # noqa: N802
        self.menu = menu

    def isVisible(self) -> bool:  # noqa: N802
        return self._visible

    def show(self) -> None:
        self._visible = True

    def hide(self) -> None:
        self._visible = False

    def setIcon(self, icon: str) -> None:  # noqa: N802
        self._icon = icon
        self.icons.append(icon)

    def icon(self) -> str:
        return self._icon

    def showMessage(self, title: str, message: str, icon: str, timeout: int) -> None:  # noqa: N802
        self.message = (title, message, icon, timeout)
        self.messages.append(self.message)


def test_tray_recording_state_updates_text_without_replacing_icon(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(tray_module, "QSystemTrayIcon", _FakeTray)
    monkeypatch.setattr(TrayController, "_icon", lambda self, recording: "recording" if recording else "idle")

    controller = TrayController(lambda: None, lambda: None, lambda: None, lambda: None)
    fake_tray = controller.tray

    controller.set_recording(False)
    controller.set_recording(True)
    controller.set_recording(True)
    controller.set_recording(False)
    controller.set_recording(False)

    assert fake_tray.icons == []
    assert fake_tray.tooltips == ["Voice Input Linux", "Voice Input Linux - 录音中", "Voice Input Linux"]


def test_tray_deduplicates_repeated_notifications(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(tray_module, "QSystemTrayIcon", _FakeTray)
    monkeypatch.setattr(TrayController, "_icon", lambda self, recording: "recording" if recording else "idle")

    controller = TrayController(lambda: None, lambda: None, lambda: None, lambda: None)
    fake_tray = controller.tray

    controller.notify("语音输入错误", "请检查网络")
    controller.notify("语音输入错误", "请检查网络")
    controller.notify("语音输入错误", "请检查模型")

    assert fake_tray.messages == [
        ("语音输入错误", "请检查网络", "idle", 5000),
        ("语音输入错误", "请检查模型", "idle", 5000),
    ]
