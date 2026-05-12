from __future__ import annotations

import math
import time

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class WaveformWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(132, 32)
        self._levels = [0.08] * 18

    def update_level(self, level: float) -> None:
        self._levels = self._levels[1:] + [max(0.04, min(1.0, level))]
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: D401
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#38bdf8")
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        bar_width = 4
        gap = 3
        center = self.height() / 2
        for index, level in enumerate(self._levels):
            phase = math.sin((time.monotonic() * 8) + index) * 0.08
            height = max(3, (level + phase) * self.height())
            x = index * (bar_width + gap)
            painter.drawRoundedRect(x, center - height / 2, bar_width, height, 2, 2)
        painter.end()


class OverlayWindow(QWidget):
    def __init__(self, theme: str = "auto") -> None:
        super().__init__(None, _overlay_window_flags())
        self.theme = theme
        self.setWindowTitle("VoiceInputOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(320)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start: QPoint | None = None
        self._drag_window_start: QPoint | None = None
        self._manual_position: QPoint | None = None
        self._positioning_generation = 0

        self.icon_label = QLabel("MIC")
        self.icon_label.setFixedWidth(28)
        self.status_label = QLabel("录音中")
        self.timer_label = QLabel("00:00")
        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        self.preview_label.setMaximumWidth(260)
        self.waveform = WaveformWidget()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(self.icon_label)
        row.addWidget(self.status_label)
        row.addWidget(self.waveform)
        row.addWidget(self.timer_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addLayout(row)
        layout.addWidget(self.preview_label)
        self._install_drag_handlers()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._started_at = 0.0
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._apply_style()

    def show_recording(self, status: str = "录音中") -> None:
        self._hide_timer.stop()
        self._manual_position = None
        self._started_at = time.monotonic()
        self.icon_label.setText("MIC")
        self.status_label.setText(status)
        self.timer_label.setText("00:00")
        self.preview_label.setText("")
        self.waveform.show()
        self._timer.start(250)
        self._show_positioned()

    def show_recognizing(self) -> None:
        self._timer.stop()
        self.icon_label.setText("...")
        self.status_label.setText("正在识别...")
        self.timer_label.setText("")
        self.preview_label.setText("")
        self.waveform.hide()
        self._show_positioned()

    def set_recording_status(self, status: str) -> None:
        self.status_label.setText(status)
        if not self.isVisible():
            self._show_positioned()

    def show_organizing(self) -> None:
        self._timer.stop()
        self.icon_label.setText("...")
        self.status_label.setText("正在整理...")
        self.timer_label.setText("")
        self.preview_label.setText("")
        self.waveform.hide()
        self._show_positioned()

    def show_result(self, text: str) -> None:
        self._timer.stop()
        self.icon_label.setText("OK")
        self.status_label.setText("已输入")
        self.timer_label.setText("")
        preview = text if len(text) <= 80 else text[:77] + "..."
        self.preview_label.setText(preview)
        self.waveform.hide()
        self._show_positioned()
        self._hide_timer.start(1000)

    def show_error(self, message: str) -> None:
        self._timer.stop()
        self.icon_label.setText("!")
        self.status_label.setText("出错")
        self.timer_label.setText("")
        self.preview_label.setText(message)
        self.waveform.hide()
        self._show_positioned()
        self._hide_timer.start(4500)

    def update_level(self, level: float) -> None:
        if self.isVisible():
            self.waveform.update_level(level)

    def _tick(self) -> None:
        elapsed = max(0, int(time.monotonic() - self._started_at))
        self.timer_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def _show_positioned(self) -> None:
        self.adjustSize()
        screen = self._target_screen()
        if screen:
            geometry = screen.availableGeometry()
            target_pos = self._target_position(geometry)
            self._move_to(target_pos)
        self.show()
        self.raise_()
        if screen:
            self._positioning_generation += 1
            generation = self._positioning_generation
            for delay in [10, 50, 100, 200]:
                QTimer.singleShot(delay, lambda p=target_pos, g=generation: self._move_if_current(p, g))

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        if isinstance(event, QMouseEvent) and self._handle_drag_event(event):
            return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._handle_drag_event(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._handle_drag_event(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._handle_drag_event(event):
            return
        super().mouseReleaseEvent(event)

    def _handle_drag_event(self, event: QMouseEvent) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_window_start = self.pos()
            self._positioning_generation += 1
            self._set_drag_cursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return True
        if event_type == QEvent.Type.MouseMove and self._drag_start is not None and self._drag_window_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            self._move_to(self._drag_window_start + delta)
            event.accept()
            return True
        if event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self._drag_window_start = None
            self._manual_position = self._clamp_to_screen(self.pos())
            self._move_to(self._manual_position)
            self._set_drag_cursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return True
        return False

    def _install_drag_handlers(self) -> None:
        for widget in [self, self.icon_label, self.status_label, self.timer_label, self.preview_label, self.waveform]:
            widget.installEventFilter(self)
            widget.setCursor(Qt.CursorShape.OpenHandCursor)

    def _set_drag_cursor(self, cursor: Qt.CursorShape) -> None:
        for widget in [self, self.icon_label, self.status_label, self.timer_label, self.preview_label, self.waveform]:
            widget.setCursor(cursor)

    def _target_screen(self) -> object:
        if self._manual_position is not None:
            center = self._manual_position + QPoint(self.width() // 2, self.height() // 2)
            return QApplication.screenAt(center) or QApplication.primaryScreen()
        return QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()

    def _target_position(self, geometry: object) -> QPoint:
        if self._manual_position is not None:
            return self._clamp_position(self._manual_position, geometry)
        return self._default_position(geometry)

    def _move_if_current(self, point: QPoint, generation: int) -> None:
        if generation != self._positioning_generation or self._drag_start is not None or self._manual_position is not None:
            return
        self._move_to(point)

    def _move_to(self, point: QPoint) -> None:
        self.move(point)
        handle = self.windowHandle()
        if handle is not None:
            handle.setPosition(point)

    def _default_position(self, geometry: object) -> QPoint:
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + geometry.height() - self.height() - 80
        return QPoint(x, y)

    def _clamp_to_screen(self, point: QPoint) -> QPoint:
        screen = QApplication.screenAt(point + QPoint(self.width() // 2, self.height() // 2)) or QApplication.primaryScreen()
        if screen is None:
            return point
        return self._clamp_position(point, screen.availableGeometry())

    def _clamp_position(self, point: QPoint, geometry: object) -> QPoint:
        x = min(max(point.x(), geometry.x()), geometry.x() + geometry.width() - self.width())
        y = min(max(point.y(), geometry.y()), geometry.y() + geometry.height() - self.height())
        return QPoint(x, y)

    def _apply_style(self) -> None:
        dark = self.theme == "dark"
        if self.theme == "auto":
            palette = QApplication.palette()
            dark = palette.window().color().lightness() < 128

        if dark:
            bg = "rgba(24, 24, 27, 235)"
            fg = "#f8fafc"
            muted = "#cbd5e1"
        else:
            bg = "rgba(255, 255, 255, 245)"
            fg = "#111827"
            muted = "#475569"

        self.setStyleSheet(
            f"""
            OverlayWindow {{
                background: {bg};
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 50px;
            }}
            QLabel {{
                color: {fg};
                font-size: 13px;
            }}
            QLabel#muted {{
                color: {muted};
            }}
            """
        )


def _overlay_window_flags() -> Qt.WindowType:
    flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus
    return flags | Qt.WindowType.WindowStaysOnTopHint
