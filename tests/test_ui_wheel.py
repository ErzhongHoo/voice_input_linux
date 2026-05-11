from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from voice_input.audio.devices import InputDeviceInfo
from voice_input.config import ASR_PROVIDER_QWEN, AppConfig
from voice_input.ui.control_panel import NoWheelSpinBox as ControlPanelNoWheelSpinBox
from voice_input.ui.hotkey_capture import HotkeyCaptureEdit, captured_hotkey_from_qt_key
from voice_input.ui.settings import NoWheelSpinBox as SettingsNoWheelSpinBox
from voice_input.ui.settings import SettingsDialog


class FakeWheelEvent:
    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True


def test_settings_spin_boxes_ignore_mouse_wheel() -> None:
    _app()

    for spin_box_class in (ControlPanelNoWheelSpinBox, SettingsNoWheelSpinBox):
        spin_box = spin_box_class()
        spin_box.setRange(0, 10)
        spin_box.setValue(5)
        event = FakeWheelEvent()

        spin_box.wheelEvent(event)  # type: ignore[arg-type]

        assert event.ignored is True
        assert spin_box.value() == 5


def test_settings_asr_provider_hides_inactive_fields(monkeypatch) -> None:
    monkeypatch.setattr("voice_input.ui.settings.list_input_devices", lambda rescan=False: [])
    _app()
    dialog = SettingsDialog(AppConfig(asr_provider="doubao"))
    try:
        assert dialog.endpoint.isHidden() is False
        assert dialog.qwen_endpoint.isHidden() is True

        qwen_index = dialog.asr_provider.findData(ASR_PROVIDER_QWEN)
        dialog.asr_provider.setCurrentIndex(qwen_index)

        assert dialog.endpoint.isHidden() is True
        assert dialog.qwen_endpoint.isHidden() is False
    finally:
        dialog.close()


def test_settings_model_test_result_is_inline(monkeypatch) -> None:
    monkeypatch.setattr("voice_input.ui.settings.list_input_devices", lambda rescan=False: [])
    _app()
    dialog = SettingsDialog(AppConfig())
    try:
        dialog._connection_test_started_at = 1.0
        dialog._handle_model_connection_failed("qwen_asr", "API Key 为空\n请先填写阿里云百炼 API Key")

        assert dialog.qwen_test_status.text().startswith("失败:")
        assert "API Key" in dialog.qwen_test_status.toolTip()
        assert dialog.test_qwen_connection.isEnabled() is True
    finally:
        dialog.close()


def test_settings_refresh_reports_new_microphone(monkeypatch) -> None:
    device_lists = [
        [InputDeviceInfo(index=0, name="Built-in Mic", channels=1, default_samplerate=16000)],
        [
            InputDeviceInfo(index=0, name="Built-in Mic", channels=1, default_samplerate=16000),
            InputDeviceInfo(index=1, name="USB Mic", channels=1, default_samplerate=48000),
        ],
    ]

    def fake_list_input_devices(rescan: bool = False) -> list[InputDeviceInfo]:
        return device_lists.pop(0)

    monkeypatch.setattr("voice_input.ui.settings.list_input_devices", fake_list_input_devices)
    _app()
    dialog = SettingsDialog(AppConfig())
    try:
        dialog._populate_input_devices(rescan=True)

        assert dialog._selected_input_device() == ""
        assert "发现新麦克风" in dialog.input_device_notice.text()
        assert "USB Mic" in dialog.input_device_notice.toolTip()
    finally:
        dialog.close()


def test_hotkey_capture_maps_right_alt_scan_code() -> None:
    captured = captured_hotkey_from_qt_key(Qt.Key.Key_Alt, native_scan_code=108)

    assert captured is not None
    assert captured.hotkey_key == "right_alt"
    assert captured.evdev_key == "KEY_RIGHTALT"


def test_hotkey_capture_maps_letter_and_evdev_fallback() -> None:
    _app()
    captured = captured_hotkey_from_qt_key(Qt.Key.Key_A)
    editor = HotkeyCaptureEdit()
    editor.setHotkey("f8", "")

    assert captured is not None
    assert captured.hotkey_key == "a"
    assert captured.evdev_key == "KEY_A"
    assert editor.text() == "F8"
    assert editor.evdev_key() == "KEY_F8"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])
