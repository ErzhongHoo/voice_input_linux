from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QThread, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from voice_input.audio.devices import InputDeviceInfo, list_input_devices
from voice_input.config import (
    DOUBAO_MODE_CUSTOM,
    DOUBAO_MODE_REALTIME,
    DOUBAO_MODE_REALTIME_FINAL,
    DOUBAO_MODE_STREAM_INPUT,
    AppConfig,
    config_to_env,
    doubao_endpoint_for_mode,
)
from voice_input.history import HistoryEntry
from voice_input.installer import (
    install_desktop,
    install_service,
    is_desktop_installed,
    is_service_active,
    is_service_enabled,
    is_service_installed,
    toggle_command_text,
    uninstall_desktop,
    uninstall_service,
)
from voice_input.inject.base import InjectionError
from voice_input.inject.clipboard_injector import copy_to_clipboard
from voice_input.ui.settings import MicrophoneLevelAnimation, MicrophoneTestWorker


class ControlPanel(QWidget):
    def __init__(
        self,
        config: AppConfig,
        on_toggle_recording: Callable[[], None],
        on_settings: Callable[[], None],
        on_environment: Callable[[], None],
        on_clear_history: Callable[[], None],
        on_quit: Callable[[], None],
        on_save_settings: Callable[[dict[str, str]], bool | None] | None = None,
        history_entries: list[HistoryEntry] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._on_toggle_recording = on_toggle_recording
        self._on_settings = on_settings
        self._on_environment = on_environment
        self._on_clear_history = on_clear_history
        self._on_save_settings = on_save_settings
        self._recording = False
        self._sidebar_collapsed = False
        self._syncing_settings = False
        self._nav_buttons: list[QPushButton] = []

        self.setObjectName("ControlPanel")
        self.setWindowTitle("Voice Input Linux")
        self.setMinimumSize(920, 620)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)

        self.service_pill = self._pill("正在运行", "ok")
        self.recording_status = self._pill("待机", "muted")
        self.hotkey_status = self._pill(config.hotkey_key or "未设置", "info")
        self.asr_status = self._pill(config.asr_provider, "info")
        self.injector_status = self._pill(config.injector_backend, "info")
        self.paste_hotkey_status = self._pill(config.paste_hotkey, "info")
        self.microphone_status = self._pill("", "muted")
        self.model_microphone_status = self._pill("", "muted")
        self.autostart_status = self._pill("", "muted")
        self.desktop_status = self._pill("", "muted")
        self._set_microphone_status(config.input_device)

        self.environment_button = QPushButton("环境检查")
        self.environment_button.setObjectName("SecondaryButton")
        self.autostart_button = QPushButton("")
        self.autostart_button.setObjectName("SecondaryButton")
        self.desktop_button = QPushButton("")
        self.desktop_button.setObjectName("SecondaryButton")
        self.clear_history_button = QPushButton("清空历史")
        self.clear_history_button.setObjectName("SecondaryButton")
        self.model_save_status = self._pill("已保存", "muted")
        self.settings_save_status = self._pill("已保存", "muted")
        self.copy_toggle_button = QPushButton("复制")
        self.copy_toggle_button.setObjectName("SecondaryButton")
        self.prepare_wayland_button = QPushButton("安装并启动后台服务")
        self.prepare_wayland_button.setObjectName("SecondaryButton")

        self.config_path = QLineEdit(config.config_file)
        self.config_path.setObjectName("PathLine")
        self.config_path.setPlaceholderText("配置文件路径")
        self.history_list = QListWidget()
        self.history_list.setObjectName("HistoryList")
        self.history_list.setMinimumHeight(120)
        self.history_list.setAlternatingRowColors(True)
        self._create_settings_fields()

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(700)
        self._auto_save_timer.timeout.connect(self._auto_save_settings)

        self._set_button_icons()
        self.environment_button.clicked.connect(self._on_environment)
        self.autostart_button.clicked.connect(self._toggle_autostart)
        self.desktop_button.clicked.connect(self._toggle_desktop_entry)
        self.history_list.itemClicked.connect(self._copy_history_item)
        self.clear_history_button.clicked.connect(self._clear_history)
        self.copy_toggle_button.clicked.connect(self._copy_toggle_command)
        self.prepare_wayland_button.clicked.connect(self._prepare_wayland_shortcut)
        self._connect_auto_save_fields()

        self.pages = QStackedWidget()
        self.pages.setObjectName("ContentStack")
        self.pages.addWidget(self._home_page())
        self.pages.addWidget(self._scroll_page(self._model_page()))
        self.pages.addWidget(self._scroll_page(self._settings_page()))

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())
        root.addWidget(self.pages, 1)
        self._select_page(0)

        self._apply_style()

        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.refresh_installation_status)
        self._timer.start()
        self.refresh_installation_status()
        self._sync_config_fields(config)
        self.set_history(history_entries or [])

    def show_panel(self) -> None:
        was_visible = self.isVisible()
        self.refresh_installation_status()
        self.show()
        if not was_visible:
            self._center_on_screen()
        self.raise_()
        self.activateWindow()

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        self._set_pill(self.recording_status, "录音中" if recording else "待机", "recording" if recording else "muted")

    def update_config(self, config: AppConfig) -> None:
        self.config = config
        self._set_pill(self.hotkey_status, config.hotkey_key or "未设置", "info")
        self._set_pill(self.asr_status, config.asr_provider, "info")
        self._set_pill(self.injector_status, config.injector_backend, "info")
        self._set_pill(self.paste_hotkey_status, config.paste_hotkey, "info")
        self._set_microphone_status(config.input_device)
        self.config_path.setText(config.config_file)
        self._sync_config_fields(config)

    def set_history(self, entries: list[HistoryEntry]) -> None:
        self.history_list.clear()
        if not entries:
            item = QListWidgetItem("暂无历史记录")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.history_list.addItem(item)
            self.clear_history_button.setEnabled(False)
            return

        for entry in entries[:8]:
            item = QListWidgetItem(_history_item_text(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry.text)
            item.setToolTip(entry.text)
            self.history_list.addItem(item)
        self.history_list.setCurrentRow(0)
        self.clear_history_button.setEnabled(True)

    def refresh_installation_status(self) -> None:
        service_installed = is_service_installed()
        service_enabled = is_service_enabled()
        service_active = is_service_active()
        desktop_installed = is_desktop_installed()

        self._set_pill(self.service_pill, "服务运行中" if service_active else "手动运行", "ok" if service_active else "info")

        if service_enabled:
            service_text = "已开启"
            service_state = "ok"
        elif service_installed:
            service_text = "未启用"
            service_state = "warn"
        else:
            service_text = "未安装"
            service_state = "muted"

        self._set_pill(self.autostart_status, service_text, service_state)
        self.autostart_button.setText("关闭自启动" if service_enabled or service_installed else "开启自启动")
        self._set_pill(self.desktop_status, "已安装" if desktop_installed else "未安装", "ok" if desktop_installed else "muted")
        self.desktop_button.setText("移除桌面图标" if desktop_installed else "安装桌面图标")

    def _sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Sidebar")
        frame.setFixedWidth(196)
        self.sidebar = frame

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(8)

        collapse_row = QHBoxLayout()
        collapse_row.setContentsMargins(0, 0, 0, 0)
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("CollapseButton")
        self.collapse_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))
        self.collapse_button.setToolTip("收起菜单")
        self.collapse_button.setFixedSize(38, 38)
        self.collapse_button.clicked.connect(self._toggle_sidebar)
        collapse_row.addStretch(1)
        collapse_row.addWidget(self.collapse_button)
        layout.addLayout(collapse_row)
        layout.addSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_items = [
            ("主页", QStyle.StandardPixmap.SP_DirHomeIcon),
            ("模型", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ("设置", QStyle.StandardPixmap.SP_ComputerIcon),
        ]
        for index, (text, icon) in enumerate(nav_items):
            button = QPushButton(text)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setProperty("fullText", text)
            button.setIcon(self.style().standardIcon(icon))
            button.clicked.connect(lambda checked=False, page=index: self._select_page(page))
            self.nav_group.addButton(button, index)
            self._nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        return frame

    def _home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 44)
        layout.setSpacing(14)
        layout.addWidget(self._status_section())
        layout.addWidget(self._history_section(), 1)
        return page

    def _scroll_page(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("ContentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _model_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        frame = self._section("模型")
        frame.layout().addLayout(self._model_form())
        frame.layout().addWidget(self.model_save_status, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(frame)
        layout.addStretch(1)
        return page

    def _model_status_section(self) -> QFrame:
        frame = self._section("当前模型")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        rows = [
            ("识别服务", self.asr_status),
            ("麦克风", self.model_microphone_status),
        ]
        for row, (name, widget) in enumerate(rows):
            grid.addWidget(self._field_label(name), row, 0)
            grid.addWidget(widget, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        frame.layout().addLayout(grid)
        return frame

    def _settings_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(self._settings_actions_section())
        layout.addWidget(self._desktop_form_section())
        layout.addWidget(self._config_section())
        layout.addStretch(1)
        return page

    def _status_section(self) -> QFrame:
        frame = self._section("状态")
        frame.setMinimumHeight(136)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        rows = [
            ("当前快捷键", self.hotkey_status, "录音状态", self.recording_status),
            ("服务状态", self.service_pill, "输入 backend", self.injector_status),
            ("粘贴快捷键", self.paste_hotkey_status, "麦克风", self.microphone_status),
        ]
        for row, values in enumerate(rows):
            left_name, left_widget, right_name, right_widget = values
            grid.addWidget(self._field_label(left_name), row, 0)
            grid.addWidget(left_widget, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            if right_widget is not None:
                grid.addWidget(self._field_label(right_name), row, 2)
                grid.addWidget(right_widget, row, 3, alignment=Qt.AlignmentFlag.AlignLeft)

        frame.layout().addLayout(grid)
        return frame

    def _history_section(self) -> QFrame:
        frame = self._section("历史记录")
        frame.setMinimumHeight(196)

        frame.layout().addWidget(self.history_list)
        return frame

    def _config_section(self) -> QFrame:
        frame = self._section("配置文件")
        frame.setMinimumHeight(104)
        frame.layout().addWidget(self.config_path)
        return frame

    def _settings_actions_section(self) -> QFrame:
        frame = self._section("系统")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        rows = [
            ("环境检查", None, self.environment_button),
            ("自启动", self.autostart_status, self.autostart_button),
            ("桌面图标", self.desktop_status, self.desktop_button),
        ]
        for row, (name, status, button) in enumerate(rows):
            grid.addWidget(self._field_label(name), row, 0)
            if status is not None:
                grid.addWidget(status, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            else:
                grid.addWidget(QLabel(""), row, 1)
            grid.addWidget(button, row, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        frame.layout().addLayout(grid)
        return frame

    def _desktop_form_section(self) -> QFrame:
        frame = self._section("设置")
        frame.layout().addLayout(self._desktop_form())
        frame.layout().addWidget(self.settings_save_status, alignment=Qt.AlignmentFlag.AlignRight)
        return frame

    def _create_settings_fields(self) -> None:
        self.asr_provider_input = NoWheelComboBox()
        self.asr_provider_input.addItem("豆包 ASR", "doubao")
        self.doubao_mode_input = NoWheelComboBox()
        self.doubao_mode_input.addItem("实时 + 二遍识别（推荐）", DOUBAO_MODE_REALTIME_FINAL)
        self.doubao_mode_input.addItem("实时逐字", DOUBAO_MODE_REALTIME)
        self.doubao_mode_input.addItem("整句返回（更稳，慢一点）", DOUBAO_MODE_STREAM_INPUT)
        self.doubao_mode_input.addItem("自定义 Endpoint", DOUBAO_MODE_CUSTOM)
        self.doubao_mode_input.currentIndexChanged.connect(self._handle_doubao_mode_changed)
        self.endpoint_input = QLineEdit()
        self.app_key_input = SecretField()
        self.access_key_input = SecretField()
        self.resource_id_input = QLineEdit()
        self.doubao_enable_punc_input = QCheckBox("模型自动标点")
        self.doubao_enable_itn_input = QCheckBox("数字规整 ITN")
        self.doubao_enable_ddc_input = QCheckBox("语义顺滑")
        self.doubao_enable_nonstream_input = QCheckBox("二遍识别")
        self.input_device_combo = NoWheelComboBox()
        self.input_device_combo.setEditable(True)
        self.input_device_combo.setMinimumWidth(380)
        self.refresh_input_devices = QPushButton("刷新")
        self.refresh_input_devices.setObjectName("SecondaryButton")
        self.refresh_input_devices.setFixedWidth(72)
        self.refresh_input_devices.clicked.connect(lambda: self._populate_input_devices(show_error=True))
        self.test_input_device = QPushButton("测试")
        self.test_input_device.setObjectName("SecondaryButton")
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
        self._test_thread: QThread | None = None
        self._test_worker: MicrophoneTestWorker | None = None
        self._populate_input_devices()
        self.sample_rate_input = QSpinBox()
        self.sample_rate_input.setRange(8000, 96000)
        self.sample_rate_input.setSingleStep(1000)
        self.channels_input = QSpinBox()
        self.channels_input.setRange(1, 2)
        self.chunk_ms_input = QSpinBox()
        self.chunk_ms_input.setRange(20, 1000)
        self.chunk_ms_input.setSingleStep(20)

        self.hotkey_backend_input = NoWheelComboBox()
        self.hotkey_backend_input.addItems(["auto", "pynput", "evdev", "none"])
        self.hotkey_key_input = QLineEdit()
        self.evdev_key_input = QLineEdit()
        self.evdev_device_input = QLineEdit()
        self.injector_backend_input = NoWheelComboBox()
        self.injector_backend_input.addItems(["auto", "fcitx5", "xdotool", "wtype", "ydotool", "clipboard"])
        self.prefer_fcitx5_input = QCheckBox("优先尝试 fcitx5 DBus commit text")
        self.paste_at_mouse_input = QCheckBox("识别结束后先点击当前鼠标位置，再粘贴")
        self.paste_hotkey_input = NoWheelComboBox()
        self.paste_hotkey_input.addItems(["ctrl+v", "ctrl+shift+v", "shift+insert"])
        self.append_final_punctuation_input = QCheckBox("应用自动补句号")
        self.overlay_theme_input = NoWheelComboBox()
        self.overlay_theme_input.addItems(["auto", "light", "dark"])
        self.log_level_input = NoWheelComboBox()
        self.log_level_input.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.toggle_command_input = QLineEdit(toggle_command_text())
        self.toggle_command_input.setObjectName("PathLine")
        self.toggle_command_input.setReadOnly(True)

    def _model_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("识别服务", self.asr_provider_input)
        form.addRow(_separator("豆包 / 火山引擎"))
        form.addRow("识别模式", self.doubao_mode_input)
        form.addRow("Endpoint", self.endpoint_input)
        form.addRow("App Key", self.app_key_input)
        form.addRow("Access Key / Token", self.access_key_input)
        form.addRow("Resource ID", self.resource_id_input)
        form.addRow("", self.doubao_enable_punc_input)
        form.addRow("", self.doubao_enable_itn_input)
        form.addRow("", self.doubao_enable_ddc_input)
        form.addRow("", self.doubao_enable_nonstream_input)
        return form

    def _desktop_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow(_separator("录音"))
        form.addRow("麦克风", self._input_device_selector())
        form.addRow("麦克风测试", self._input_test_widget())
        form.addRow("采样率", self.sample_rate_input)
        form.addRow("声道数", self.channels_input)
        form.addRow("分包毫秒", self.chunk_ms_input)
        form.addRow(_separator("快捷键"))
        form.addRow("快捷键 backend", self.hotkey_backend_input)
        form.addRow("pynput 键名", self.hotkey_key_input)
        form.addRow("evdev 键码", self.evdev_key_input)
        form.addRow("evdev 设备", self.evdev_device_input)
        form.addRow(_separator("文字输入"))
        form.addRow("输入 backend", self.injector_backend_input)
        form.addRow("", self.prefer_fcitx5_input)
        form.addRow("", self.paste_at_mouse_input)
        form.addRow("粘贴快捷键", self.paste_hotkey_input)
        form.addRow("末尾标点", self.append_final_punctuation_input)
        form.addRow(_separator("Wayland 快捷键"))
        form.addRow("toggle 命令", self._toggle_command_row())
        form.addRow("", self.prepare_wayland_button)
        form.addRow(_separator("高级"))
        form.addRow("浮窗主题", self.overlay_theme_input)
        form.addRow("日志级别", self.log_level_input)
        return form

    def _toggle_command_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.toggle_command_input, 1)
        layout.addWidget(self.copy_toggle_button)
        return row

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
            channels=self.channels_input.value(),
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

    def _populate_input_devices(self, show_error: bool = False) -> None:
        previous = self._selected_input_device() if self.input_device_combo.count() else self.config.input_device.strip()
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

    def _set_selected_input_device(self, device: str) -> None:
        value = device.strip()
        for index in range(self.input_device_combo.count()):
            data = self.input_device_combo.itemData(index)
            if value == str(data or "").strip():
                self.input_device_combo.setCurrentIndex(index)
                return
        self.input_device_combo.setEditText(value)

    def _sync_config_fields(self, config: AppConfig) -> None:
        self._syncing_settings = True
        try:
            _set_combo_data(self.asr_provider_input, "doubao")
            _set_combo_data(self.doubao_mode_input, config.doubao_mode)
            self.endpoint_input.setText(config.effective_doubao_endpoint())
            self.app_key_input.setText(config.doubao_app_key)
            self.access_key_input.setText(config.doubao_access_key)
            self.resource_id_input.setText(config.doubao_resource_id)
            self.doubao_enable_punc_input.setChecked(config.doubao_enable_punc)
            self.doubao_enable_itn_input.setChecked(config.doubao_enable_itn)
            self.doubao_enable_ddc_input.setChecked(config.doubao_enable_ddc)
            self.doubao_enable_nonstream_input.setChecked(config.effective_doubao_enable_nonstream())
            self._handle_doubao_mode_changed()
            self._set_selected_input_device(config.input_device)
            self.sample_rate_input.setValue(config.sample_rate)
            self.channels_input.setValue(config.channels)
            self.chunk_ms_input.setValue(config.chunk_ms)
            self.hotkey_backend_input.setCurrentText(config.hotkey_backend)
            self.hotkey_key_input.setText(config.hotkey_key)
            self.evdev_key_input.setText(config.evdev_key)
            self.evdev_device_input.setText(config.evdev_device)
            self.injector_backend_input.setCurrentText(config.injector_backend)
            self.prefer_fcitx5_input.setChecked(config.prefer_fcitx5)
            self.paste_at_mouse_input.setChecked(config.paste_at_mouse)
            if config.paste_hotkey not in {"ctrl+v", "ctrl+shift+v", "shift+insert"}:
                self.paste_hotkey_input.addItem(config.paste_hotkey)
            self.paste_hotkey_input.setCurrentText(config.paste_hotkey)
            self.append_final_punctuation_input.setChecked(config.append_final_punctuation)
            self.overlay_theme_input.setCurrentText(config.overlay_theme)
            self.log_level_input.setCurrentText(config.log_level)
            self.toggle_command_input.setText(toggle_command_text())
        finally:
            self._syncing_settings = False

    def _settings_config(self) -> AppConfig:
        return AppConfig(
            asr_provider=str(self.asr_provider_input.currentData() or "doubao"),
            mock_text=self.config.mock_text,
            doubao_endpoint=self.endpoint_input.text().strip(),
            doubao_app_key=self.app_key_input.text().strip(),
            doubao_access_key=self.access_key_input.text().strip(),
            doubao_resource_id=self.resource_id_input.text().strip(),
            doubao_protocol=self.config.doubao_protocol,
            doubao_mode=str(self.doubao_mode_input.currentData() or DOUBAO_MODE_REALTIME_FINAL),
            doubao_enable_punc=self.doubao_enable_punc_input.isChecked(),
            doubao_enable_itn=self.doubao_enable_itn_input.isChecked(),
            doubao_enable_ddc=self.doubao_enable_ddc_input.isChecked(),
            doubao_enable_nonstream=self.doubao_enable_nonstream_input.isChecked(),
            hotkey_backend=self.hotkey_backend_input.currentText(),
            hotkey_key=self.hotkey_key_input.text().strip() or "right_alt",
            evdev_device=self.evdev_device_input.text().strip(),
            evdev_key=self.evdev_key_input.text().strip() or "KEY_RIGHTALT",
            injector_backend=self.injector_backend_input.currentText(),
            prefer_fcitx5=self.prefer_fcitx5_input.isChecked(),
            paste_at_mouse=self.paste_at_mouse_input.isChecked(),
            paste_hotkey=self.paste_hotkey_input.currentText(),
            append_final_punctuation=self.append_final_punctuation_input.isChecked(),
            sample_rate=self.sample_rate_input.value(),
            channels=self.channels_input.value(),
            chunk_ms=self.chunk_ms_input.value(),
            input_device=self._selected_input_device(),
            overlay_theme=self.overlay_theme_input.currentText(),
            log_level=self.log_level_input.currentText(),
            socket_path=self.config.socket_path,
            config_file=self.config_path.text().strip() or self.config.config_file,
        )

    def _connect_auto_save_fields(self) -> None:
        text_fields = [
            self.endpoint_input,
            self.app_key_input.line,
            self.access_key_input.line,
            self.resource_id_input,
            self.hotkey_key_input,
            self.evdev_key_input,
            self.evdev_device_input,
        ]
        for field in text_fields:
            field.textEdited.connect(self._schedule_auto_save)

        combo_fields = [
            self.asr_provider_input,
            self.doubao_mode_input,
            self.input_device_combo,
            self.hotkey_backend_input,
            self.injector_backend_input,
            self.paste_hotkey_input,
            self.overlay_theme_input,
            self.log_level_input,
        ]
        for combo in combo_fields:
            combo.currentIndexChanged.connect(self._schedule_auto_save)
        self.input_device_combo.editTextChanged.connect(self._schedule_auto_save)

        spin_fields = [self.sample_rate_input, self.channels_input, self.chunk_ms_input]
        for spin in spin_fields:
            spin.valueChanged.connect(self._schedule_auto_save)

        check_fields = [
            self.doubao_enable_punc_input,
            self.doubao_enable_itn_input,
            self.doubao_enable_ddc_input,
            self.doubao_enable_nonstream_input,
            self.prefer_fcitx5_input,
            self.paste_at_mouse_input,
            self.append_final_punctuation_input,
        ]
        for field in check_fields:
            field.toggled.connect(self._schedule_auto_save)

    def _schedule_auto_save(self) -> None:
        if self._syncing_settings:
            return
        self._set_auto_save_status("待保存", "info")
        self._auto_save_timer.start()

    def _handle_doubao_mode_changed(self) -> None:
        mode = str(self.doubao_mode_input.currentData() or DOUBAO_MODE_REALTIME_FINAL)
        endpoint = doubao_endpoint_for_mode(mode)
        if endpoint:
            self.endpoint_input.setText(endpoint)
        self.endpoint_input.setReadOnly(mode != DOUBAO_MODE_CUSTOM)
        if mode == DOUBAO_MODE_REALTIME_FINAL:
            self.doubao_enable_nonstream_input.setChecked(True)
        elif mode in {DOUBAO_MODE_REALTIME, DOUBAO_MODE_STREAM_INPUT}:
            self.doubao_enable_nonstream_input.setChecked(False)
        self.doubao_enable_nonstream_input.setEnabled(mode == DOUBAO_MODE_CUSTOM)
        self._schedule_auto_save()

    def _auto_save_settings(self) -> None:
        if self._on_save_settings is None:
            self._on_settings()
            return
        settings = self._settings_config()
        env = config_to_env(settings)
        env["VOICE_INPUT_CONFIG_FILE"] = settings.config_file
        env["_VOICE_INPUT_SAVE_NOTIFICATION"] = "false"
        self._set_auto_save_status("保存中", "info")
        saved = self._on_save_settings(env)
        self._set_auto_save_status("已保存", "muted" if saved is not False else "warn")

    def _set_auto_save_status(self, text: str, state: str) -> None:
        self._set_pill(self.model_save_status, text, state)
        self._set_pill(self.settings_save_status, text, state)

    def _copy_toggle_command(self) -> None:
        try:
            copy_to_clipboard(self.toggle_command_input.text())
        except InjectionError as exc:
            QMessageBox.warning(self, "复制失败", str(exc))

    def _prepare_wayland_shortcut(self) -> None:
        try:
            status = install_service(start=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "后台服务设置失败", str(exc))
            return
        self.refresh_installation_status()
        if status != 0:
            QMessageBox.warning(self, "后台服务设置失败", f"安装或启动失败，退出码: {status}")

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if 0 <= index < len(self._nav_buttons):
            self._nav_buttons[index].setChecked(True)

    def _toggle_sidebar(self) -> None:
        self._sidebar_collapsed = not self._sidebar_collapsed
        width = 64 if self._sidebar_collapsed else 196
        self.sidebar.setFixedWidth(width)
        icon = QStyle.StandardPixmap.SP_ArrowRight if self._sidebar_collapsed else QStyle.StandardPixmap.SP_ArrowLeft
        self.collapse_button.setIcon(self.style().standardIcon(icon))
        self.collapse_button.setToolTip("展开菜单" if self._sidebar_collapsed else "收起菜单")
        for button in self._nav_buttons:
            button.setText("" if self._sidebar_collapsed else str(button.property("fullText")))

    def _section(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("SectionFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        header.addWidget(label)
        header.addStretch(1)
        if title == "历史记录":
            header.addWidget(self.clear_history_button)
        layout.addLayout(header)
        return frame

    def _toggle_autostart(self) -> None:
        try:
            if is_service_enabled() or is_service_installed():
                status = uninstall_service(stop=False)
                action = "关闭自启动"
            else:
                status = install_service(start=False)
                action = "开启自启动"
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "自启动设置失败", str(exc))
            return
        self.refresh_installation_status()
        if status != 0:
            QMessageBox.warning(self, "自启动设置失败", f"{action}失败，退出码: {status}")

    def _toggle_desktop_entry(self) -> None:
        try:
            if is_desktop_installed():
                status = uninstall_desktop()
                action = "移除桌面图标"
            else:
                status = install_desktop()
                action = "安装桌面图标"
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "桌面图标设置失败", str(exc))
            return
        self.refresh_installation_status()
        if status != 0:
            QMessageBox.warning(self, "桌面图标设置失败", f"{action}失败，退出码: {status}")

    def _copy_history_item(self, item: QListWidgetItem) -> None:
        text = item.data(Qt.ItemDataRole.UserRole)
        if not text:
            return
        try:
            copy_to_clipboard(str(text))
        except InjectionError as exc:
            QMessageBox.warning(self, "复制失败", str(exc))

    def _clear_history(self) -> None:
        if self.history_list.count() == 0:
            return
        answer = QMessageBox.question(
            self,
            "清空历史记录",
            "确定要清空全部历史记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._on_clear_history()

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _pill(self, text: str, state: str) -> QLabel:
        label = QLabel()
        label.setObjectName("StatusPill")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(82)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._set_pill(label, text, state)
        return label

    def _set_pill(self, label: QLabel, text: str, state: str) -> None:
        label.setText(text)
        label.setProperty("state", state)
        self._refresh_style(label)

    def _set_microphone_status(self, device: str) -> None:
        value = device.strip()
        text = "系统默认" if not value else _short_text(value, 22)
        self._set_pill(self.microphone_status, text, "info" if value else "muted")
        self.microphone_status.setToolTip(value or "系统默认麦克风")
        self._set_pill(self.model_microphone_status, text, "info" if value else "muted")
        self.model_microphone_status.setToolTip(value or "系统默认麦克风")

    def _set_button_icons(self) -> None:
        icon_size = QSize(18, 18)
        buttons = [
            (self.environment_button, QStyle.StandardPixmap.SP_MessageBoxInformation),
            (self.autostart_button, QStyle.StandardPixmap.SP_ComputerIcon),
            (self.desktop_button, QStyle.StandardPixmap.SP_DirHomeIcon),
            (self.clear_history_button, QStyle.StandardPixmap.SP_DialogResetButton),
            (self.copy_toggle_button, QStyle.StandardPixmap.SP_FileDialogContentsView),
            (self.prepare_wayland_button, QStyle.StandardPixmap.SP_DialogApplyButton),
            (self.refresh_input_devices, QStyle.StandardPixmap.SP_BrowserReload),
            (self.test_input_device, QStyle.StandardPixmap.SP_MediaPlay),
        ]
        for button, icon in buttons:
            button.setIcon(self.style().standardIcon(icon))
            button.setIconSize(icon_size)
            button.setFixedHeight(42)

    def closeEvent(self, event: object) -> None:  # noqa: D401
        if self._test_worker is not None:
            self._test_worker.stop()
        if self._test_thread is not None and self._test_thread.isRunning():
            self._test_thread.wait(1000)
        super().closeEvent(event)

    def _refresh_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _center_on_screen(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.x() + (geometry.width() - self.width()) // 2,
            geometry.y() + (geometry.height() - self.height()) // 2,
        )

    def _apply_style(self) -> None:
        dark = self.palette().window().color().lightness() < 128
        if dark:
            bg = "#111827"
            panel = "#1f2937"
            sidebar = "#0f172a"
            border = "#374151"
            text = "#f9fafb"
            muted = "#9ca3af"
            field = "#111827"
            secondary = "#273244"
            secondary_hover = "#324158"
            nav_hover = "#1f2937"
            nav_checked = "#2563eb"
            focus = "#60a5fa"
        else:
            bg = "#f5f7fb"
            panel = "#ffffff"
            sidebar = "#ffffff"
            border = "#d9e0ea"
            text = "#101828"
            muted = "#667085"
            field = "#f8fafc"
            secondary = "#ffffff"
            secondary_hover = "#f2f4f7"
            nav_hover = "#eef2f7"
            nav_checked = "#dbeafe"
            focus = "#2563eb"

        self.setStyleSheet(
            f"""
            QWidget#ControlPanel {{
                background: {bg};
                color: {text};
                font-size: 14px;
            }}
            QFrame#Sidebar {{
                background: {sidebar};
                border-right: 1px solid {border};
            }}
            QWidget#ContentPage {{
                background: {bg};
            }}
            QScrollArea#ContentScroll {{
                background: {bg};
                border: 0;
            }}
            QScrollArea#ContentScroll > QWidget > QWidget {{
                background: {bg};
            }}
            QLabel#FieldLabel,
            QLabel#HintText {{
                color: {muted};
            }}
            QLabel#SeparatorLabel {{
                color: {muted};
                font-size: 13px;
                font-weight: 600;
                padding-top: 8px;
                padding-bottom: 2px;
            }}
            QFrame#SectionFrame {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel#SectionTitle {{
                color: {text};
                font-size: 16px;
                font-weight: 700;
                min-height: 24px;
            }}
            QLabel#StatusPill {{
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: 600;
                min-height: 24px;
            }}
            QLabel#StatusPill[state="ok"] {{
                background: #dcfce7;
                color: #166534;
                border: 1px solid #bbf7d0;
            }}
            QLabel#StatusPill[state="info"] {{
                background: #dbeafe;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
            }}
            QLabel#StatusPill[state="recording"] {{
                background: #fee2e2;
                color: #b42318;
                border: 1px solid #fecaca;
            }}
            QLabel#StatusPill[state="warn"] {{
                background: #fef3c7;
                color: #92400e;
                border: 1px solid #fde68a;
            }}
            QLabel#StatusPill[state="muted"] {{
                background: {field};
                color: {muted};
                border: 1px solid {border};
            }}
            QLineEdit#PathLine {{
                background: {field};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 8px 10px;
                color: {text};
            }}
            QLineEdit,
            QComboBox,
            QSpinBox {{
                background: {field};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 7px 10px;
                color: {text};
                min-height: 34px;
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
                selection-background-color: {nav_checked};
                selection-color: #1d4ed8;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 30px;
                padding: 6px 8px;
                border-radius: 6px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background: {nav_hover};
            }}
            QLineEdit:focus,
            QComboBox:focus,
            QSpinBox:focus {{
                border-color: {focus};
            }}
            QCheckBox {{
                color: {text};
                min-height: 30px;
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
            QListWidget#HistoryList {{
                background: {field};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px;
                color: {text};
            }}
            QListWidget#HistoryList::item {{
                padding: 7px 8px;
                border-radius: 6px;
            }}
            QListWidget#HistoryList::item:selected {{
                background: #dbeafe;
                color: #1d4ed8;
            }}
            QPushButton {{
                min-height: 38px;
                border-radius: 8px;
                padding: 7px 14px;
                font-weight: 600;
            }}
            QPushButton#PrimaryButton {{
                background: #2563eb;
                color: #ffffff;
                border: 1px solid #1d4ed8;
            }}
            QPushButton#PrimaryButton:hover {{
                background: #1d4ed8;
            }}
            QPushButton#PrimaryButton[recording="true"] {{
                background: #dc2626;
                border-color: #b91c1c;
            }}
            QPushButton#PrimaryButton[recording="true"]:hover {{
                background: #b91c1c;
            }}
            QPushButton#SecondaryButton {{
                background: {secondary};
                color: {text};
                border: 1px solid {border};
            }}
            QPushButton#SecondaryButton:hover {{
                background: {secondary_hover};
            }}
            QPushButton#NavButton {{
                background: transparent;
                color: {text};
                border: 1px solid transparent;
                text-align: left;
                padding: 8px 10px;
            }}
            QPushButton#NavButton:hover {{
                background: {nav_hover};
                color: {text};
            }}
            QPushButton#NavButton:checked {{
                background: {nav_checked};
                color: #1d4ed8;
                border-color: #bfdbfe;
            }}
            QToolButton#CollapseButton {{
                background: {secondary};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QToolButton#RevealButton {{
                background: {secondary};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 14px;
            }}
            QToolButton#CollapseButton:hover,
            QToolButton#RevealButton:hover {{
                background: {secondary_hover};
            }}
            QToolButton#RevealButton:checked {{
                border-color: {focus};
            }}
            """
        )


def _short_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class SecretField(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.line = QLineEdit()
        self.line.setEchoMode(QLineEdit.EchoMode.Password)
        self.reveal_button = QToolButton()
        self.reveal_button.setObjectName("RevealButton")
        self.reveal_button.setText("👁")
        self.reveal_button.setToolTip("显示密钥")
        self.reveal_button.setCheckable(True)
        self.reveal_button.setFixedSize(34, 34)
        self.reveal_button.toggled.connect(self._toggle_reveal)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.line, 1)
        layout.addWidget(self.reveal_button)

    def text(self) -> str:
        return self.line.text()

    def setText(self, value: str) -> None:  # noqa: N802
        self.line.setText(value)

    def _toggle_reveal(self, checked: bool) -> None:
        self.line.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.reveal_button.setToolTip("隐藏密钥" if checked else "显示密钥")


def _set_combo_data(combo: QComboBox, data: str) -> None:
    index = combo.findData(data)
    if index >= 0:
        combo.setCurrentIndex(index)


def _history_item_text(entry: HistoryEntry) -> str:
    timestamp = entry.created_at.replace("T", " ")[:16]
    text = " ".join(entry.text.split())
    provider = f" [{entry.asr_provider}]" if entry.asr_provider else ""
    return f"{timestamp}{provider}  {_short_text(text, 84)}"


def _separator(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SeparatorLabel")
    return label
