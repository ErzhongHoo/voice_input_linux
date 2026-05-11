from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from voice_input.app import (
    RECORDING_MODE_DICTATION,
    RECORDING_MODE_ORGANIZER,
    RECORDING_MODE_PENDING_HOTKEY,
    VoiceInputApp,
)
from voice_input.config import AppConfig


def test_none_hotkey_backend_disables_internal_listener() -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(hotkey_backend="none")
    controller = VoiceInputApp(app, config)
    assert controller._create_hotkey_backend() is None


def test_right_alt_tap_starts_and_stops_organizer_mode(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    controller = VoiceInputApp(app, AppConfig(hotkey_backend="none"))
    statuses: list[str] = []
    starts: list[str] = []
    stops: list[str] = []
    controller.overlay = SimpleNamespace(
        show_error=lambda message: None,
        show_recording=lambda status="录音中": statuses.append(status),
        set_recording_status=lambda status: statuses.append(status),
        update_level=lambda level: None,
    )

    def fake_start(mode: str = RECORDING_MODE_DICTATION) -> None:
        starts.append(mode)
        controller.is_recording = True
        controller._recording_mode = mode

    def fake_stop() -> None:
        stops.append(controller._recording_mode)
        controller.is_recording = False
        controller._pending_result_mode = controller._recording_mode
        controller._recording_mode = RECORDING_MODE_DICTATION

    monkeypatch.setattr(controller, "start_recording", fake_start)
    monkeypatch.setattr(controller, "stop_recording", fake_stop)

    controller._handle_hotkey_pressed()
    controller._handle_hotkey_released()
    controller._handle_hotkey_pressed()
    controller._handle_hotkey_released()
    controller._hotkey_hold_timer.stop()

    assert starts == [RECORDING_MODE_PENDING_HOTKEY]
    assert statuses == ["整理录音中"]
    assert stops == [RECORDING_MODE_ORGANIZER]
    assert controller._pending_result_mode == RECORDING_MODE_ORGANIZER


def test_right_alt_hold_stops_as_dictation_mode(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    controller = VoiceInputApp(app, AppConfig(hotkey_backend="none"))
    starts: list[str] = []
    stops: list[str] = []
    controller.overlay = SimpleNamespace(
        show_error=lambda message: None,
        show_recording=lambda status="录音中": None,
        set_recording_status=lambda status: None,
        update_level=lambda level: None,
    )

    def fake_start(mode: str = RECORDING_MODE_DICTATION) -> None:
        starts.append(mode)
        controller.is_recording = True
        controller._recording_mode = mode

    def fake_stop() -> None:
        stops.append(controller._recording_mode)
        controller.is_recording = False
        controller._pending_result_mode = controller._recording_mode
        controller._recording_mode = RECORDING_MODE_DICTATION

    monkeypatch.setattr(controller, "start_recording", fake_start)
    monkeypatch.setattr(controller, "stop_recording", fake_stop)

    controller._handle_hotkey_pressed()
    controller._promote_hotkey_hold_recording()
    controller._handle_hotkey_released()
    controller._hotkey_hold_timer.stop()

    assert starts == [RECORDING_MODE_PENDING_HOTKEY]
    assert stops == [RECORDING_MODE_DICTATION]
    assert controller._pending_result_mode == RECORDING_MODE_DICTATION
