from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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
from voice_input.config import (
    ASR_PROVIDER_QWEN,
    DOUBAO_MODE_CUSTOM,
    DOUBAO_MODE_REALTIME,
    DOUBAO_MODE_REALTIME_FINAL,
    DOUBAO_MODE_STREAM_INPUT,
    DEFAULT_ORGANIZER_ENDPOINT,
    DEFAULT_ORGANIZER_MODEL,
    DEFAULT_QWEN_ASR_ENDPOINT,
    DEFAULT_QWEN_ASR_LANGUAGE,
    DEFAULT_QWEN_ASR_MODEL,
    DEFAULT_QWEN_ASR_VAD_SILENCE_MS,
    ORGANIZER_PROVIDER_DEEPSEEK,
    ORGANIZER_PROVIDER_OPENAI_COMPATIBLE,
    AppConfig,
    config_to_env,
    doubao_endpoint_for_mode,
)
from voice_input.inject.base import InjectionError
from voice_input.inject.clipboard_injector import copy_to_clipboard
from voice_input.installer import install_service, toggle_command_text


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        parent: QWidget | None = None,
        on_auto_save: Callable[[dict[str, str]], bool | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("Voice Input Linux 设置")
        self.setMinimumSize(760, 620)
        self.config = config
        self._on_auto_save = on_auto_save
        self._syncing_settings = True
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(700)
        self._auto_save_timer.timeout.connect(self._auto_save)

        self.config_path = QLineEdit(config.config_file or str(Path.cwd() / ".env"))
        self.config_path.setReadOnly(True)

        self.asr_provider = NoWheelComboBox()
        self.asr_provider.addItem("豆包 ASR", "doubao")
        self.asr_provider.addItem("阿里云百炼千问 ASR", ASR_PROVIDER_QWEN)
        _set_combo_data(self.asr_provider, config.asr_provider)
        self.asr_provider.currentIndexChanged.connect(self._handle_asr_provider_changed)

        self.mock_text = QLineEdit(config.mock_text)
        self.doubao_mode = NoWheelComboBox()
        self.doubao_mode.addItem("实时 + 二遍识别（推荐）", DOUBAO_MODE_REALTIME_FINAL)
        self.doubao_mode.addItem("实时逐字", DOUBAO_MODE_REALTIME)
        self.doubao_mode.addItem("整句返回（更稳，慢一点）", DOUBAO_MODE_STREAM_INPUT)
        self.doubao_mode.addItem("自定义 Endpoint", DOUBAO_MODE_CUSTOM)
        _set_combo_data(self.doubao_mode, config.doubao_mode)
        self.doubao_mode.currentIndexChanged.connect(self._handle_doubao_mode_changed)
        self.endpoint = QLineEdit(config.effective_doubao_endpoint())
        self.app_key = SecretLineEdit(config.doubao_app_key)
        self.access_key = SecretLineEdit(config.doubao_access_key)
        self.resource_id = QLineEdit(config.doubao_resource_id)
        self.doubao_enable_punc = QCheckBox("模型自动标点")
        self.doubao_enable_punc.setChecked(config.doubao_enable_punc)
        self.doubao_enable_itn = QCheckBox("数字规整 ITN")
        self.doubao_enable_itn.setChecked(config.doubao_enable_itn)
        self.doubao_enable_ddc = QCheckBox("语义顺滑")
        self.doubao_enable_ddc.setChecked(config.doubao_enable_ddc)
        self.doubao_enable_nonstream = QCheckBox("二遍识别")
        self.doubao_enable_nonstream.setChecked(config.effective_doubao_enable_nonstream())
        self._handle_doubao_mode_changed()
        self.qwen_endpoint = QLineEdit(config.qwen_endpoint)
        self.qwen_api_key = SecretLineEdit(config.qwen_api_key)
        self.qwen_model = QLineEdit(config.qwen_model)
        self.qwen_language = QLineEdit(config.qwen_language)
        self.qwen_enable_server_vad = QCheckBox("服务端 VAD 自动断句")
        self.qwen_enable_server_vad.setChecked(config.qwen_enable_server_vad)
        self.qwen_vad_threshold = NoWheelDoubleSpinBox()
        self.qwen_vad_threshold.setRange(-1.0, 1.0)
        self.qwen_vad_threshold.setSingleStep(0.1)
        self.qwen_vad_threshold.setDecimals(2)
        self.qwen_vad_threshold.setValue(config.qwen_vad_threshold)
        self.qwen_vad_silence_ms = NoWheelSpinBox()
        self.qwen_vad_silence_ms.setRange(200, 6000)
        self.qwen_vad_silence_ms.setSingleStep(100)
        self.qwen_vad_silence_ms.setValue(config.qwen_vad_silence_ms)
        self.organizer_provider = NoWheelComboBox()
        self.organizer_provider.addItem("DeepSeek", ORGANIZER_PROVIDER_DEEPSEEK)
        self.organizer_provider.addItem("OpenAI 兼容接口", ORGANIZER_PROVIDER_OPENAI_COMPATIBLE)
        _set_combo_data(self.organizer_provider, config.organizer_provider)
        self.organizer_provider.currentIndexChanged.connect(self._handle_organizer_provider_changed)
        self.organizer_endpoint = QLineEdit(config.organizer_endpoint)
        self.organizer_api_key = SecretLineEdit(config.organizer_api_key)
        self.organizer_model = QLineEdit(config.organizer_model)
        self.organizer_timeout = NoWheelSpinBox()
        self.organizer_timeout.setRange(5, 180)
        self.organizer_timeout.setSingleStep(5)
        self.organizer_timeout.setValue(config.organizer_timeout)

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
        self.append_final_punctuation = QCheckBox("保留/补末尾句号")
        self.append_final_punctuation.setToolTip("关闭后会删除 ASR 返回的最终句号，也不会自动补句号。")
        self.append_final_punctuation.setChecked(config.append_final_punctuation)
        self.toggle_command = QLineEdit(toggle_command_text())
        self.toggle_command.setReadOnly(True)
        self.copy_toggle_command = QPushButton("复制")
        self.copy_toggle_command.clicked.connect(self._copy_toggle_command)
        self.prepare_wayland_button = QPushButton("安装并启动后台服务")
        self.prepare_wayland_button.clicked.connect(self._prepare_wayland_shortcut)
        self.test_asr_connection = QPushButton("测试")
        self.test_asr_connection.setMinimumWidth(96)
        self.test_asr_connection.clicked.connect(lambda: self._start_model_connection_test("asr"))
        self.test_qwen_connection = QPushButton("测试")
        self.test_qwen_connection.setMinimumWidth(96)
        self.test_qwen_connection.clicked.connect(lambda: self._start_model_connection_test("qwen_asr"))
        self.test_organizer_connection = QPushButton("测试")
        self.test_organizer_connection.setMinimumWidth(96)
        self.test_organizer_connection.clicked.connect(lambda: self._start_model_connection_test("organizer"))
        self.asr_test_status = self._inline_status()
        self.qwen_test_status = self._inline_status()
        self.organizer_test_status = self._inline_status()

        self.sample_rate = NoWheelSpinBox()
        self.sample_rate.setRange(8000, 96000)
        self.sample_rate.setSingleStep(1000)
        self.sample_rate.setValue(config.sample_rate)
        self.channels = NoWheelSpinBox()
        self.channels.setRange(1, 2)
        self.channels.setValue(config.channels)
        self.chunk_ms = NoWheelSpinBox()
        self.chunk_ms.setRange(20, 1000)
        self.chunk_ms.setSingleStep(20)
        self.chunk_ms.setValue(config.chunk_ms)
        self.input_device_combo = NoWheelComboBox()
        self.input_device_combo.setEditable(True)
        self.input_device_combo.setMinimumWidth(380)
        self.refresh_input_devices = QPushButton("刷新")
        self.refresh_input_devices.setMinimumWidth(96)
        self.refresh_input_devices.clicked.connect(lambda: self._populate_input_devices(show_error=True, rescan=True))
        self.test_input_device = QPushButton("测试")
        self.test_input_device.setMinimumWidth(96)
        self.test_input_device.clicked.connect(self._toggle_input_device_test)
        self.input_device_notice = self._inline_status("", "muted")
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
        self._input_device_refresh_timer = QTimer(self)
        self._input_device_refresh_timer.setInterval(5000)
        self._input_device_refresh_timer.timeout.connect(self._auto_refresh_input_devices)
        self._populate_input_devices(rescan=True)
        self._input_device_refresh_timer.start()
        self._test_thread: QThread | None = None
        self._test_worker: MicrophoneTestWorker | None = None
        self._connection_test_thread: threading.Thread | None = None
        self._connection_test_started_at = 0.0
        self._connection_test_closing = False
        self._connection_test_signals = ModelConnectionSignals(self)
        self._connection_test_signals.finished.connect(self._handle_model_connection_success)
        self._connection_test_signals.failed.connect(self._handle_model_connection_failed)

        self.overlay_theme = NoWheelComboBox()
        self.overlay_theme.addItems(["auto", "light", "dark"])
        self.overlay_theme.setCurrentText(config.overlay_theme)
        self.log_level = NoWheelComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level.setCurrentText(config.log_level)
        self._asr_form: QFormLayout | None = None
        self._asr_form_rows: dict[str, list[int]] = {"doubao": [], ASR_PROVIDER_QWEN: []}

        tabs = QTabWidget()
        tabs.addTab(self._asr_tab(), "ASR")
        tabs.addTab(self._desktop_tab(), "桌面")
        tabs.addTab(self._advanced_tab(), "高级")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        path_row = QFormLayout()
        path_row.addRow("配置文件", self.config_path)
        layout.addLayout(path_row)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self._update_asr_provider_visibility()
        self._apply_style()
        self._connect_auto_save_fields()
        self._syncing_settings = False

    def _connect_auto_save_fields(self) -> None:
        text_fields = [
            self.mock_text,
            self.endpoint,
            self.app_key.line,
            self.access_key.line,
            self.resource_id,
            self.qwen_endpoint,
            self.qwen_api_key.line,
            self.qwen_model,
            self.qwen_language,
            self.organizer_endpoint,
            self.organizer_api_key.line,
            self.organizer_model,
            self.hotkey_key,
            self.evdev_key,
            self.evdev_device,
        ]
        for field in text_fields:
            field.textEdited.connect(self._schedule_auto_save)

        combo_fields = [
            self.doubao_mode,
            self.organizer_provider,
            self.hotkey_backend,
            self.injector_backend,
            self.paste_hotkey,
            self.input_device_combo,
            self.overlay_theme,
            self.log_level,
        ]
        for combo in combo_fields:
            combo.currentIndexChanged.connect(self._schedule_auto_save)
        self.input_device_combo.editTextChanged.connect(self._schedule_auto_save)

        spin_fields = [
            self.sample_rate,
            self.channels,
            self.chunk_ms,
            self.qwen_vad_threshold,
            self.qwen_vad_silence_ms,
            self.organizer_timeout,
        ]
        for spin in spin_fields:
            spin.valueChanged.connect(self._schedule_auto_save)

        check_fields = [
            self.doubao_enable_punc,
            self.doubao_enable_itn,
            self.doubao_enable_ddc,
            self.doubao_enable_nonstream,
            self.qwen_enable_server_vad,
            self.prefer_fcitx5,
            self.paste_at_mouse,
            self.append_final_punctuation,
        ]
        for field in check_fields:
            field.toggled.connect(self._schedule_auto_save)

    def _apply_style(self) -> None:
        dark = self.palette().window().color().lightness() < 128
        if dark:
            bg = "#111827"
            panel = "#1f2937"
            field = "#111827"
            border = "#374151"
            text = "#f9fafb"
            muted = "#9ca3af"
            hover = "#273244"
            tab_checked = "#1e3a8a"
            focus = "#60a5fa"
            accent = "#2563eb"
            accent_hover = "#1d4ed8"
            accent_pressed = "#1e40af"
            selected_text = "#dbeafe"
        else:
            bg = "#f5f7fb"
            panel = "#ffffff"
            field = "#f8fafc"
            border = "#d9e0ea"
            text = "#101828"
            muted = "#667085"
            hover = "#f2f4f7"
            tab_checked = "#dbeafe"
            focus = "#2563eb"
            accent = "#2563eb"
            accent_hover = "#1d4ed8"
            accent_pressed = "#1e40af"
            selected_text = "#1d4ed8"

        self.setStyleSheet(
            f"""
            QDialog#SettingsDialog {{
                background: {bg};
                color: {text};
                font-size: 14px;
            }}
            QLabel {{
                color: {text};
            }}
            QLabel#SeparatorLabel {{
                color: {muted};
                font-size: 12px;
                font-weight: 600;
                padding-top: 6px;
                padding-bottom: 2px;
            }}
            QLabel#InlineStatus {{
                color: {muted};
                min-height: 30px;
                padding: 2px 0;
            }}
            QLabel#InlineStatus[state="ok"] {{
                color: #15803d;
                font-weight: 600;
            }}
            QLabel#InlineStatus[state="warn"] {{
                color: #b42318;
                font-weight: 600;
            }}
            QLabel#InlineStatus[state="info"] {{
                color: {focus};
                font-weight: 600;
            }}
            QTabWidget::pane {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
                top: -1px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {muted};
                border: 1px solid transparent;
                border-bottom: 0;
                padding: 9px 16px;
                margin-right: 4px;
                min-height: 24px;
                font-size: 15px;
                font-weight: 600;
            }}
            QTabBar::tab:hover {{
                background: {hover};
                color: {text};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QTabBar::tab:selected {{
                background: {tab_checked};
                color: {selected_text};
                border-color: {focus};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 700;
            }}
            QLineEdit,
            QComboBox,
            QSpinBox,
            QDoubleSpinBox,
            QPlainTextEdit {{
                background: {field};
                border: 1px solid {border};
                border-radius: 8px;
                color: {text};
                padding: 7px 12px;
                min-height: 34px;
                selection-background-color: {focus};
                selection-color: #ffffff;
            }}
            QLineEdit[readOnly="true"] {{
                color: {muted};
            }}
            QPlainTextEdit {{
                padding: 10px 12px;
            }}
            QLineEdit:focus,
            QComboBox:focus,
            QSpinBox:focus,
            QDoubleSpinBox:focus,
            QPlainTextEdit:focus {{
                border-color: {focus};
            }}
            QComboBox {{
                padding-right: 34px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: 0;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {focus};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {panel};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px;
                outline: 0;
                selection-background-color: {tab_checked};
                selection-color: {selected_text};
            }}
            QCheckBox {{
                color: {text};
                min-height: 30px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {border};
                background: {field};
            }}
            QCheckBox::indicator:hover {{
                border-color: {focus};
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border-color: {accent};
            }}
            QPushButton {{
                min-height: 38px;
                border-radius: 8px;
                padding: 8px 16px;
                border: 1px solid {border};
                background: {panel};
                color: {text};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {hover};
                border-color: {focus};
            }}
            QPushButton:pressed {{
                background: {tab_checked};
                color: {selected_text};
            }}
            QPushButton:disabled {{
                background: {field};
                color: {muted};
                border-color: {border};
            }}
            QDialogButtonBox QPushButton {{
                min-width: 96px;
            }}
            QProgressBar {{
                background: {field};
                border: 1px solid {border};
                border-radius: 8px;
                min-height: 18px;
            }}
            QProgressBar::chunk {{
                background: {accent};
                border-radius: 7px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 4px 2px 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {border};
                border-radius: 4px;
                min-height: 32px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            """
        )

    def _schedule_auto_save(self) -> None:
        if self._syncing_settings:
            return
        self._auto_save_timer.start()

    def _auto_save(self) -> None:
        if self._on_auto_save is None:
            return
        env = self.to_env()
        env["_VOICE_INPUT_SAVE_NOTIFICATION"] = "false"
        self._on_auto_save(env)

    def to_env(self) -> dict[str, str]:
        updated = AppConfig(
            asr_provider=str(self.asr_provider.currentData() or "doubao"),
            mock_text=self.mock_text.text().strip() or "这是一次语音输入测试。",
            doubao_endpoint=self.endpoint.text().strip(),
            doubao_app_key=self.app_key.text().strip(),
            doubao_access_key=self.access_key.text().strip(),
            doubao_resource_id=self.resource_id.text().strip(),
            doubao_protocol=self.config.doubao_protocol,
            doubao_mode=str(self.doubao_mode.currentData() or DOUBAO_MODE_REALTIME_FINAL),
            doubao_enable_punc=self.doubao_enable_punc.isChecked(),
            doubao_enable_itn=self.doubao_enable_itn.isChecked(),
            doubao_enable_ddc=self.doubao_enable_ddc.isChecked(),
            doubao_enable_nonstream=self.doubao_enable_nonstream.isChecked(),
            qwen_endpoint=self.qwen_endpoint.text().strip() or DEFAULT_QWEN_ASR_ENDPOINT,
            qwen_api_key=self.qwen_api_key.text().strip(),
            qwen_model=self.qwen_model.text().strip() or DEFAULT_QWEN_ASR_MODEL,
            qwen_language=self.qwen_language.text().strip() or DEFAULT_QWEN_ASR_LANGUAGE,
            qwen_enable_server_vad=self.qwen_enable_server_vad.isChecked(),
            qwen_vad_threshold=self.qwen_vad_threshold.value(),
            qwen_vad_silence_ms=self.qwen_vad_silence_ms.value() or DEFAULT_QWEN_ASR_VAD_SILENCE_MS,
            organizer_provider=str(self.organizer_provider.currentData() or ORGANIZER_PROVIDER_DEEPSEEK),
            organizer_endpoint=self.organizer_endpoint.text().strip(),
            organizer_api_key=self.organizer_api_key.text().strip(),
            organizer_model=self.organizer_model.text().strip(),
            organizer_timeout=self.organizer_timeout.value(),
            hotkey_backend=self.hotkey_backend.currentText(),
            hotkey_key=self.hotkey_key.text().strip() or "right_alt",
            evdev_device=self.evdev_device.text().strip(),
            evdev_key=self.evdev_key.text().strip() or "KEY_RIGHTALT",
            injector_backend=self.injector_backend.currentText(),
            prefer_fcitx5=self.prefer_fcitx5.isChecked(),
            paste_at_mouse=self.paste_at_mouse.isChecked(),
            paste_hotkey=self.paste_hotkey.currentText(),
            append_final_punctuation=self.append_final_punctuation.isChecked(),
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
        self._asr_form = form
        self._asr_form_rows = {"doubao": [], ASR_PROVIDER_QWEN: []}
        form.addRow("识别服务", self._field_with_button(self.asr_provider, self.test_asr_connection, self.asr_test_status))
        self._add_asr_provider_row("doubao", _separator("豆包 / 火山引擎"))
        self._add_asr_provider_row("doubao", "识别模式", self.doubao_mode)
        self._add_asr_provider_row("doubao", "Endpoint", self.endpoint)
        self._add_asr_provider_row("doubao", "App Key", self.app_key)
        self._add_asr_provider_row("doubao", "Access Key / Token", self.access_key)
        self._add_asr_provider_row("doubao", "Resource ID", self.resource_id)
        self._add_asr_provider_row("doubao", "", self.doubao_enable_punc)
        self._add_asr_provider_row("doubao", "", self.doubao_enable_itn)
        self._add_asr_provider_row("doubao", "", self.doubao_enable_ddc)
        self._add_asr_provider_row("doubao", "", self.doubao_enable_nonstream)
        self._add_asr_provider_row(ASR_PROVIDER_QWEN, _separator("阿里云百炼 / 千问 ASR"))
        self._add_asr_provider_row(ASR_PROVIDER_QWEN, "Endpoint", self.qwen_endpoint)
        self._add_asr_provider_row(ASR_PROVIDER_QWEN, "API Key", self.qwen_api_key)
        self._add_asr_provider_row(
            ASR_PROVIDER_QWEN,
            "Model",
            self._field_with_button(self.qwen_model, self.test_qwen_connection, self.qwen_test_status),
        )
        self._add_asr_provider_row(ASR_PROVIDER_QWEN, "Language", self.qwen_language)
        self._add_asr_provider_row(ASR_PROVIDER_QWEN, "", self.qwen_enable_server_vad)
        self._add_asr_provider_row(ASR_PROVIDER_QWEN, "VAD 阈值", self.qwen_vad_threshold)
        self._add_asr_provider_row(ASR_PROVIDER_QWEN, "静音断句 ms", self.qwen_vad_silence_ms)
        form.addRow(_separator("整理模型"))
        form.addRow("Provider", self._field_with_button(self.organizer_provider, self.test_organizer_connection, self.organizer_test_status))
        form.addRow("Endpoint", self.organizer_endpoint)
        form.addRow("API Key", self.organizer_api_key)
        form.addRow("Model", self.organizer_model)
        form.addRow("Timeout 秒", self.organizer_timeout)
        note = QLabel("Key 只保存到本机配置文件，不会写入日志。下一次录音使用新的模型配置。")
        note.setWordWrap(True)
        form.addRow(note)
        return tab

    def _handle_doubao_mode_changed(self) -> None:
        mode = str(self.doubao_mode.currentData() or DOUBAO_MODE_REALTIME_FINAL)
        endpoint = doubao_endpoint_for_mode(mode)
        if endpoint:
            self.endpoint.setText(endpoint)
        self.endpoint.setReadOnly(mode != DOUBAO_MODE_CUSTOM)
        if mode == DOUBAO_MODE_REALTIME_FINAL:
            self.doubao_enable_nonstream.setChecked(True)
        elif mode in {DOUBAO_MODE_REALTIME, DOUBAO_MODE_STREAM_INPUT}:
            self.doubao_enable_nonstream.setChecked(False)
        self.doubao_enable_nonstream.setEnabled(mode == DOUBAO_MODE_CUSTOM)
        self._schedule_auto_save()

    def _handle_asr_provider_changed(self) -> None:
        self._update_asr_provider_visibility()
        self._schedule_auto_save()

    def _update_asr_provider_visibility(self) -> None:
        if self._asr_form is None:
            return
        provider = str(self.asr_provider.currentData() or "doubao")
        show_qwen = provider == ASR_PROVIDER_QWEN
        for row in self._asr_form_rows.get("doubao", []):
            self._asr_form.setRowVisible(row, not show_qwen)
        for row in self._asr_form_rows.get(ASR_PROVIDER_QWEN, []):
            self._asr_form.setRowVisible(row, show_qwen)

    def _add_asr_provider_row(self, provider: str, label: object, field: QWidget | None = None) -> None:
        if self._asr_form is None:
            return
        row = self._asr_form.rowCount()
        if field is None:
            self._asr_form.addRow(label)  # type: ignore[arg-type]
        else:
            self._asr_form.addRow(label, field)  # type: ignore[arg-type]
        self._asr_form_rows.setdefault(provider, []).append(row)

    def _handle_organizer_provider_changed(self) -> None:
        provider = str(self.organizer_provider.currentData() or ORGANIZER_PROVIDER_DEEPSEEK)
        if provider == ORGANIZER_PROVIDER_DEEPSEEK:
            if not self.organizer_endpoint.text().strip():
                self.organizer_endpoint.setText(DEFAULT_ORGANIZER_ENDPOINT)
            if not self.organizer_model.text().strip():
                self.organizer_model.setText(DEFAULT_ORGANIZER_MODEL)
        self._schedule_auto_save()

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
        form.addRow("末尾句号", self.append_final_punctuation)
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

    def _field_with_button(self, field: QWidget, button: QPushButton, status: QLabel | None = None) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(field, 1)
        layout.addWidget(button)
        if status is not None:
            layout.addWidget(status)
        return row

    def _start_model_connection_test(self, kind: str) -> None:
        if self._connection_test_thread is not None and self._connection_test_thread.is_alive():
            self._set_connection_test_status(kind, "已有测试在进行", "info")
            return
        config = AppConfig.from_mapping(self.to_env())
        if kind == "qwen_asr":
            config.asr_provider = ASR_PROVIDER_QWEN
        button = self._connection_test_button(kind)
        button.setText("测试中")
        self._set_connection_test_status(kind, "测试中...", "info")
        for test_button in self._connection_test_buttons():
            test_button.setEnabled(False)

        self._connection_test_closing = False
        self._connection_test_started_at = time.monotonic()
        thread = threading.Thread(
            target=self._run_model_connection_test,
            args=(kind, config),
            daemon=True,
        )
        self._connection_test_thread = thread
        thread.start()

    def _run_model_connection_test(self, kind: str, config: AppConfig) -> None:
        try:
            from voice_input.model_checks import check_asr_connection, check_organizer_connection

            if kind in {"asr", "qwen_asr"}:
                message = check_asr_connection(config)
            elif kind == "organizer":
                message = check_organizer_connection(config)
            else:
                raise ValueError(f"未知测试类型: {kind}")
        except Exception as exc:  # noqa: BLE001
            if not self._connection_test_closing:
                self._connection_test_signals.failed.emit(kind, str(exc))
            return
        if not self._connection_test_closing:
            self._connection_test_signals.finished.emit(kind, message)

    def _handle_model_connection_success(self, kind: str, message: str) -> None:
        if self._connection_test_closing:
            return
        self._set_connection_test_status(kind, f"成功 {self._connection_test_elapsed():.1f}s", "ok", message)
        self._clear_model_connection_test()

    def _handle_model_connection_failed(self, kind: str, message: str) -> None:
        if self._connection_test_closing:
            return
        self._set_connection_test_status(kind, f"失败: {_short_text(message, 42)}", "warn", message)
        self._clear_model_connection_test()

    def _clear_model_connection_test(self) -> None:
        self._connection_test_thread = None
        self._connection_test_started_at = 0.0
        for button in self._connection_test_buttons():
            button.setText("测试")
            button.setEnabled(True)

    def _connection_test_button(self, kind: str) -> QPushButton:
        if kind == "qwen_asr":
            return self.test_qwen_connection
        if kind == "organizer":
            return self.test_organizer_connection
        return self.test_asr_connection

    def _connection_test_buttons(self) -> list[QPushButton]:
        return [self.test_asr_connection, self.test_qwen_connection, self.test_organizer_connection]

    def _connection_test_status_label(self, kind: str) -> QLabel:
        if kind == "qwen_asr":
            return self.qwen_test_status
        if kind == "organizer":
            return self.organizer_test_status
        return self.asr_test_status

    def _set_connection_test_status(self, kind: str, text: str, state: str, tooltip: str = "") -> None:
        self._set_inline_status(self._connection_test_status_label(kind), text, state, tooltip)

    def _connection_test_elapsed(self) -> float:
        if self._connection_test_started_at <= 0:
            return 0.0
        return max(0.0, time.monotonic() - self._connection_test_started_at)

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
        form.addRow("", self.input_device_notice)
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
        self._connection_test_closing = True
        self._input_device_refresh_timer.stop()
        if self._auto_save_timer.isActive():
            self._auto_save_timer.stop()
            self._auto_save()
        if self._test_worker is not None:
            self._test_worker.stop()
        if self._test_thread is not None and self._test_thread.isRunning():
            self._test_thread.wait(1000)
        super().closeEvent(event)

    def _auto_refresh_input_devices(self) -> None:
        if not self.isVisible() or self._test_thread is not None or self.input_device_combo.hasFocus():
            return
        self._populate_input_devices(rescan=True)

    def _populate_input_devices(self, show_error: bool = False, rescan: bool = False) -> None:
        previous = (
            self._selected_input_device()
            if self.input_device_combo.count()
            else self.config.input_device.strip()
        )
        had_existing_devices = self.input_device_combo.count() > 0
        known_devices = self._input_device_values()
        self.input_device_combo.blockSignals(True)
        self.input_device_combo.clear()
        self.input_device_combo.addItem("系统默认麦克风", "")

        devices: list[InputDeviceInfo] = []
        try:
            devices = list_input_devices(rescan=rescan)
        except Exception as exc:  # noqa: BLE001
            if previous:
                self.input_device_combo.addItem(f"当前配置: {previous}", previous)
                self.input_device_combo.setCurrentIndex(1)
            if show_error:
                self._set_inline_status(self.input_device_notice, f"读取失败: {_short_text(str(exc), 54)}", "warn", str(exc))
                QMessageBox.warning(self, "无法读取麦克风", str(exc))
            self.input_device_combo.blockSignals(False)
            return

        selected_index = 0
        new_devices: list[str] = []
        for device in devices:
            self.input_device_combo.addItem(device.label, device.config_value)
            if had_existing_devices and device.config_value not in known_devices:
                new_devices.append(device.label)
            if previous and (previous == device.config_value or previous == str(device.index)):
                selected_index = self.input_device_combo.count() - 1

        missing_previous = bool(previous and selected_index == 0)
        if previous and selected_index == 0:
            self.input_device_combo.addItem(f"当前配置: {previous}", previous)
            selected_index = self.input_device_combo.count() - 1

        self.input_device_combo.setCurrentIndex(selected_index)
        self.input_device_combo.blockSignals(False)
        if new_devices:
            self._set_inline_status(
                self.input_device_notice,
                f"发现新麦克风: {_short_text(new_devices[0], 48)}",
                "info",
                "\n".join(new_devices),
            )
        elif missing_previous:
            self._set_inline_status(self.input_device_notice, "当前麦克风未在列表中，已保留配置", "warn")
        elif show_error:
            self._set_inline_status(self.input_device_notice, f"已刷新: {len(devices)} 个可用麦克风", "muted")

    def _input_device_values(self) -> set[str]:
        values: set[str] = set()
        for index in range(self.input_device_combo.count()):
            value = str(self.input_device_combo.itemData(index) or "").strip()
            if value:
                values.add(value)
        return values

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

    def _inline_status(self, text: str = "未测试", state: str = "muted") -> QLabel:
        label = QLabel()
        label.setObjectName("InlineStatus")
        label.setMinimumWidth(150)
        label.setMaximumWidth(260)
        label.setWordWrap(True)
        self._set_inline_status(label, text, state)
        return label

    def _set_inline_status(self, label: QLabel, text: str, state: str, tooltip: str = "") -> None:
        label.setText(text)
        label.setProperty("state", state)
        label.setToolTip(tooltip or text)
        self._refresh_style(label)

    def _refresh_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


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


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


def _set_combo_data(combo: QComboBox, data: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == data:
            combo.setCurrentIndex(index)
            return


def _separator(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SeparatorLabel")
    return label


def _short_text(text: str, limit: int) -> str:
    value = " ".join(text.split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


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


class ModelConnectionSignals(QObject):
    finished = Signal(str, str)
    failed = Signal(str, str)


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
