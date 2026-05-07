from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from voice_input.audio.devices import InputDeviceInfo, list_input_devices, measure_input_device_level
from voice_input.config import AppConfig, config_to_env
from voice_input.inject.base import InjectionError
from voice_input.inject.clipboard_injector import copy_to_clipboard
from voice_input.installer import install_service, toggle_command_text


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Voice Input Linux 设置")
        self.setMinimumWidth(620)
        self.config = config

        self.config_path = QLineEdit(config.config_file or str(Path.cwd() / ".env"))
        self.config_path.setReadOnly(True)

        self.asr_provider = NoWheelComboBox()
        self.asr_provider.addItem("豆包 ASR", "doubao")
        self.asr_provider.setCurrentIndex(0)

        self.mock_text = QLineEdit(config.mock_text)
        self.endpoint = QLineEdit(config.doubao_endpoint)
        self.app_key = SecretLineEdit(config.doubao_app_key)
        self.access_key = SecretLineEdit(config.doubao_access_key)
        self.resource_id = QLineEdit(config.doubao_resource_id)

        self.hotkey_backend = NoWheelComboBox()
        self.hotkey_backend.addItems(["auto", "pynput", "evdev", "none"])
        self.hotkey_backend.setCurrentText(config.hotkey_backend)
        self.hotkey_key = QLineEdit(config.hotkey_key)
        self.evdev_key = QLineEdit(config.evdev_key)
        self.evdev_device = QLineEdit(config.evdev_device)

        self.injector_backend = NoWheelComboBox()
        self.injector_backend.addItems(["auto", "fcitx5", "xdotool", "wtype", "ydotool", "clipboard"])
        self.injector_backend.setCurrentText(config.injector_backend)
        self.prefer_fcitx5 = QCheckBox("优先尝试 fcitx5 DBus commit text")
        self.prefer_fcitx5.setChecked(config.prefer_fcitx5)
        self.paste_at_mouse = QCheckBox("识别结束后先点击当前鼠标位置，再粘贴")
        self.paste_at_mouse.setChecked(config.paste_at_mouse)
        self.paste_hotkey = NoWheelComboBox()
        self.paste_hotkey.addItems(["ctrl+v", "ctrl+shift+v", "shift+insert"])
        if config.paste_hotkey not in {"ctrl+v", "ctrl+shift+v", "shift+insert"}:
            self.paste_hotkey.addItem(config.paste_hotkey)
        self.paste_hotkey.setCurrentText(config.paste_hotkey)
        self.toggle_command = QLineEdit(toggle_command_text())
        self.toggle_command.setReadOnly(True)
        self.copy_toggle_command = QPushButton("复制")
        self.copy_toggle_command.clicked.connect(self._copy_toggle_command)
        self.prepare_wayland_button = QPushButton("安装并启动后台服务")
        self.prepare_wayland_button.clicked.connect(self._prepare_wayland_shortcut)

        self.sample_rate = QSpinBox()
        self.sample_rate.setRange(8000, 96000)
        self.sample_rate.setSingleStep(1000)
        self.sample_rate.setValue(config.sample_rate)
        self.channels = QSpinBox()
        self.channels.setRange(1, 2)
        self.channels.setValue(config.channels)
        self.chunk_ms = QSpinBox()
        self.chunk_ms.setRange(20, 1000)
        self.chunk_ms.setSingleStep(20)
        self.chunk_ms.setValue(config.chunk_ms)
        self.input_device_combo = NoWheelComboBox()
        self.input_device_combo.setEditable(True)
        self.input_device_combo.setMinimumWidth(380)
        self.refresh_input_devices = QPushButton("刷新")
        self.refresh_input_devices.setFixedWidth(72)
        self.refresh_input_devices.clicked.connect(lambda: self._populate_input_devices(show_error=True))
        self.test_input_device = QPushButton("测试")
        self.test_input_device.setFixedWidth(72)
        self.test_input_device.clicked.connect(self._toggle_input_device_test)
        self.input_level = QProgressBar()
        self.input_level.setRange(0, 100)
        self.input_level.setTextVisible(False)
        self.input_level_animation = MicrophoneLevelAnimation()
        self.input_test_time = QLabel("00:00")
        self.input_test_time.setMinimumWidth(48)
        self.input_test_result = QLabel("未测试")
        self._input_test_started_at = 0.0
        self._input_test_timer = QTimer(self)
        self._input_test_timer.setInterval(250)
        self._input_test_timer.timeout.connect(self._update_input_test_time)
        self._populate_input_devices()
        self._test_thread: QThread | None = None
        self._test_worker: MicrophoneTestWorker | None = None

        self.overlay_theme = NoWheelComboBox()
        self.overlay_theme.addItems(["auto", "light", "dark"])
        self.overlay_theme.setCurrentText(config.overlay_theme)
        self.log_level = NoWheelComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level.setCurrentText(config.log_level)

        tabs = QTabWidget()
        tabs.addTab(self._asr_tab(), "ASR")
        tabs.addTab(self._desktop_tab(), "桌面")
        tabs.addTab(self._advanced_tab(), "高级")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        path_row = QFormLayout()
        path_row.addRow("配置文件", self.config_path)
        layout.addLayout(path_row)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def to_env(self) -> dict[str, str]:
        updated = AppConfig(
            asr_provider=str(self.asr_provider.currentData() or "doubao"),
            mock_text=self.mock_text.text().strip() or "这是一次语音输入测试。",
            doubao_endpoint=self.endpoint.text().strip(),
            doubao_app_key=self.app_key.text().strip(),
            doubao_access_key=self.access_key.text().strip(),
            doubao_resource_id=self.resource_id.text().strip(),
            doubao_protocol=self.config.doubao_protocol,
            hotkey_backend=self.hotkey_backend.currentText(),
            hotkey_key=self.hotkey_key.text().strip() or "right_alt",
            evdev_device=self.evdev_device.text().strip(),
            evdev_key=self.evdev_key.text().strip() or "KEY_RIGHTALT",
            injector_backend=self.injector_backend.currentText(),
            prefer_fcitx5=self.prefer_fcitx5.isChecked(),
            paste_at_mouse=self.paste_at_mouse.isChecked(),
            paste_hotkey=self.paste_hotkey.currentText(),
            sample_rate=self.sample_rate.value(),
            channels=self.channels.value(),
            chunk_ms=self.chunk_ms.value(),
            input_device=self._selected_input_device(),
            overlay_theme=self.overlay_theme.currentText(),
            log_level=self.log_level.currentText(),
            socket_path=self.config.socket_path,
            config_file=self.config.config_file,
        )
        return config_to_env(updated)

    def _asr_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow("识别服务", self.asr_provider)
        form.addRow(_separator("豆包 / 火山引擎"))
        form.addRow("Endpoint", self.endpoint)
        form.addRow("App Key", self.app_key)
        form.addRow("Access Key / Token", self.access_key)
        form.addRow("Resource ID", self.resource_id)
        note = QLabel("Key 只保存到本机配置文件，不会写入日志。保存后下一次录音立即使用新 ASR 配置。")
        note.setWordWrap(True)
        form.addRow(note)
        return tab

    def _desktop_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow("快捷键 backend", self.hotkey_backend)
        form.addRow("pynput 键名", self.hotkey_key)
        form.addRow("evdev 键码", self.evdev_key)
        form.addRow("evdev 设备", self.evdev_device)
        form.addRow(_separator("文字输入"))
        form.addRow("输入 backend", self.injector_backend)
        form.addRow("", self.prefer_fcitx5)
        form.addRow("", self.paste_at_mouse)
        form.addRow("粘贴快捷键", self.paste_hotkey)
        form.addRow(_separator("Wayland 快捷键"))
        note = QLabel("把 toggle 命令绑定到系统或 compositor 的全局快捷键；后台服务需要先运行。")
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow("toggle 命令", self._toggle_command_widget())
        form.addRow("", self.prepare_wayland_button)
        return tab

    def _toggle_command_widget(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.toggle_command, 1)
        layout.addWidget(self.copy_toggle_command)
        return row

    def _copy_toggle_command(self) -> None:
        try:
            copy_to_clipboard(self.toggle_command.text())
        except InjectionError as exc:
            QMessageBox.warning(self, "复制失败", str(exc))
            return
        QMessageBox.information(self, "已复制", "toggle 命令已复制到剪贴板。")

    def _prepare_wayland_shortcut(self) -> None:
        try:
            status = install_service(start=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "后台服务设置失败", str(exc))
            return
        if status == 0:
            QMessageBox.information(self, "后台服务已启动", "现在可以把 toggle 命令绑定到系统全局快捷键。")
        else:
            QMessageBox.warning(self, "后台服务设置失败", f"安装或启动失败，退出码: {status}")

    def _advanced_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow("采样率", self.sample_rate)
        form.addRow("声道数", self.channels)
        form.addRow("分包毫秒", self.chunk_ms)
        form.addRow("麦克风", self._input_device_selector())
        form.addRow("麦克风测试", self._input_test_widget())
        form.addRow("浮窗主题", self.overlay_theme)
        form.addRow("日志级别", self.log_level)
        help_text = QPlainTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(110)
        help_text.setPlainText(
            "默认录音格式是 16kHz / 单声道 / PCM int16 little-endian。\n"
            "麦克风可直接下拉选择；留空表示系统默认麦克风，也可手动输入 sounddevice 设备名。\n"
            "修改 socket 路径请直接编辑配置文件，运行中的 CLI 控制依赖当前 socket。"
        )
        form.addRow(help_text)
        return tab

    def _input_device_selector(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.input_device_combo, 1)
        layout.addWidget(self.refresh_input_devices)
        layout.addWidget(self.test_input_device)
        return row

    def _input_test_widget(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.input_level, 1)
        layout.addWidget(self.input_level_animation)
        layout.addWidget(self.input_test_time)
        layout.addWidget(self.input_test_result)
        return row

    def _toggle_input_device_test(self) -> None:
        if self._test_thread is not None:
            self._stop_input_device_test()
            return
        self._start_input_device_test()

    def _start_input_device_test(self) -> None:
        if self._test_thread is not None:
            return
        self.input_level.setValue(0)
        self.input_level_animation.set_level(0.0)
        self.input_test_time.setText("00:00")
        self.input_test_result.setText("测试中...")
        self.test_input_device.setText("停止")
        self.refresh_input_devices.setEnabled(False)
        self._input_test_started_at = time.monotonic()
        self._input_test_timer.start()

        worker = MicrophoneTestWorker(
            device=self._selected_input_device() or None,
            channels=self.channels.value(),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.level_changed.connect(self._handle_input_test_level_changed)
        worker.finished.connect(self._handle_input_test_finished)
        worker.failed.connect(self._handle_input_test_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_input_test_worker)
        self._test_worker = worker
        self._test_thread = thread
        thread.start()

    def _stop_input_device_test(self) -> None:
        if self._test_worker is None:
            return
        self.input_test_result.setText("停止中...")
        self.test_input_device.setEnabled(False)
        self._test_worker.stop()

    def _handle_input_test_level_changed(self, peak: float, rms: float) -> None:
        level = max(peak, min(1.0, rms * 5.0))
        self.input_level.setValue(round(level * 100))
        self.input_level_animation.set_level(level)

    def _handle_input_test_finished(self, peak: float, rms: float) -> None:
        level = max(peak, min(1.0, rms * 5.0))
        self.input_level.setValue(round(level * 100))
        self.input_level_animation.set_level(level)
        if peak >= 0.03 or rms >= 0.005:
            self.input_test_result.setText(f"有声音 peak={peak:.3f}")
        else:
            self.input_test_result.setText(f"声音很小 peak={peak:.3f}")

    def _handle_input_test_failed(self, message: str) -> None:
        self.input_level.setValue(0)
        self.input_level_animation.set_level(0.0)
        self.input_test_result.setText("测试失败")
        QMessageBox.warning(self, "麦克风测试失败", message)

    def _clear_input_test_worker(self) -> None:
        self._input_test_timer.stop()
        self._update_input_test_time()
        self._test_thread = None
        self._test_worker = None
        self.test_input_device.setText("测试")
        self.test_input_device.setEnabled(True)
        self.refresh_input_devices.setEnabled(True)

    def _update_input_test_time(self) -> None:
        if self._input_test_started_at <= 0:
            self.input_test_time.setText("00:00")
            return
        elapsed = max(0, int(time.monotonic() - self._input_test_started_at))
        self.input_test_time.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def closeEvent(self, event: object) -> None:  # noqa: D401
        if self._test_worker is not None:
            self._test_worker.stop()
        if self._test_thread is not None and self._test_thread.isRunning():
            self._test_thread.wait(1000)
        super().closeEvent(event)

    def _populate_input_devices(self, show_error: bool = False) -> None:
        previous = (
            self._selected_input_device()
            if self.input_device_combo.count()
            else self.config.input_device.strip()
        )
        self.input_device_combo.blockSignals(True)
        self.input_device_combo.clear()
        self.input_device_combo.addItem("系统默认麦克风", "")

        devices: list[InputDeviceInfo] = []
        try:
            devices = list_input_devices()
        except Exception as exc:  # noqa: BLE001
            if previous:
                self.input_device_combo.addItem(f"当前配置: {previous}", previous)
                self.input_device_combo.setCurrentIndex(1)
            if show_error:
                QMessageBox.warning(self, "无法读取麦克风", str(exc))
            self.input_device_combo.blockSignals(False)
            return

        selected_index = 0
        for device in devices:
            self.input_device_combo.addItem(device.label, device.config_value)
            if previous and (previous == device.config_value or previous == str(device.index)):
                selected_index = self.input_device_combo.count() - 1

        if previous and selected_index == 0:
            self.input_device_combo.addItem(f"当前配置: {previous}", previous)
            selected_index = self.input_device_combo.count() - 1

        self.input_device_combo.setCurrentIndex(selected_index)
        self.input_device_combo.blockSignals(False)

    def _selected_input_device(self) -> str:
        current_index = self.input_device_combo.currentIndex()
        data = self.input_device_combo.currentData()
        if (
            current_index >= 0
            and data is not None
            and self.input_device_combo.currentText() == self.input_device_combo.itemText(current_index)
        ):
            return str(data).strip()
        return self.input_device_combo.currentText().strip()

    def _validate_and_accept(self) -> None:
        if self.asr_provider.currentData() == "doubao":
            missing = []
            if not self.endpoint.text().strip():
                missing.append("Endpoint")
            if not self.app_key.text().strip():
                missing.append("App Key")
            if not self.access_key.text().strip():
                missing.append("Access Key")
            if missing:
                QMessageBox.warning(self, "配置不完整", "豆包 ASR 缺少: " + "、".join(missing))
                return
        self.accept()


class SecretLineEdit(QWidget):
    def __init__(self, value: str = "") -> None:
        super().__init__()
        self.line = QLineEdit(value)
        self.line.setEchoMode(QLineEdit.EchoMode.Password)
        self.reveal = QPushButton("显示")
        self.reveal.setCheckable(True)
        self.reveal.setFixedWidth(56)
        self.reveal.clicked.connect(self._toggle_reveal)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.line)
        row.addWidget(self.reveal)

    def text(self) -> str:
        return self.line.text()

    def _toggle_reveal(self, checked: bool) -> None:
        self.line.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.reveal.setText("隐藏" if checked else "显示")


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


def _separator(text: str) -> QFrame:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.HLine)
    frame.setToolTip(text)
    frame.setAccessibleName(text)
    return frame


class MicrophoneLevelAnimation(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(82, 24)
        self._level = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: D401
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0ea5e9"))

        bar_width = 5
        gap = 5
        center = self.height() / 2
        now = time.monotonic()
        for index in range(8):
            phase = (math.sin(now * 9 + index * 0.75) + 1.0) / 2.0
            height = 4 + (self.height() - 4) * max(self._level, 0.12) * (0.45 + phase * 0.55)
            x = index * (bar_width + gap)
            painter.drawRoundedRect(x, center - height / 2, bar_width, height, 2, 2)
        painter.end()


class MicrophoneTestWorker(QObject):
    level_changed = Signal(float, float)
    finished = Signal(float, float)
    failed = Signal(str)

    def __init__(self, device: str | int | None, channels: int) -> None:
        super().__init__()
        self.device = device
        self.channels = channels
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        max_peak = 0.0
        max_rms = 0.0
        try:
            while self._running:
                peak, rms = measure_input_device_level(self.device, duration_seconds=0.15, channels=self.channels)
                max_peak = max(max_peak, peak)
                max_rms = max(max_rms, rms)
                self.level_changed.emit(peak, rms)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(max_peak, max_rms)
