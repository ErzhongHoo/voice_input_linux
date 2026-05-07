from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from voice_input.resource_paths import resource_path


class TrayController:
    def __init__(
        self,
        on_show: Callable[[], None],
        on_toggle: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_show = on_show
        self._on_toggle = on_toggle
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._recording = False

        self.tray = QSystemTrayIcon(self._icon(False))
        self.tray.setToolTip("Voice Input Linux")

        self.menu = QMenu()
        self.show_action = QAction("打开面板")
        self.toggle_action = QAction("开始录音")
        self.settings_action = QAction("设置")
        self.quit_action = QAction("退出")

        self.show_action.triggered.connect(self._on_show)
        self.toggle_action.triggered.connect(self._on_toggle)
        self.settings_action.triggered.connect(self._on_settings)
        self.quit_action.triggered.connect(self._on_quit)

        self.menu.addAction(self.show_action)
        self.menu.addAction(self.toggle_action)
        self.menu.addSeparator()
        self.menu.addAction(self.settings_action)
        self.menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._handle_activated)

    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        self.toggle_action.setText("停止录音" if recording else "开始录音")
        self.tray.setIcon(self._icon(recording))
        self.tray.setToolTip("Voice Input Linux - 录音中" if recording else "Voice Input Linux")

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, self.tray.icon(), 5000)

    def _handle_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_show()

    def _icon(self, recording: bool) -> QIcon:
        if not recording:
            try:
                with resource_path("voice-input-linux.svg") as icon_path:
                    bundled = QIcon(str(icon_path))
                if not bundled.isNull():
                    return bundled
            except Exception:  # noqa: BLE001
                pass
        themed = QIcon.fromTheme("audio-input-microphone")
        if not themed.isNull() and not recording:
            return themed
        size = QSize(64, 64)
        pixmap = QPixmap(size)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#d93025" if recording else "#2563eb"))
        painter.setPen(QColor("#ffffff"))
        painter.drawEllipse(8, 8, 48, 48)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(27, 16, 10, 24, 5, 5)
        painter.drawLine(22, 31, 22, 35)
        painter.drawLine(42, 31, 42, 35)
        painter.drawArc(22, 26, 20, 18, 180 * 16, 180 * 16)
        painter.drawLine(32, 40, 32, 48)
        painter.drawLine(25, 48, 39, 48)
        painter.end()
        return QIcon(pixmap)
