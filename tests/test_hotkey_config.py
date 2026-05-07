from PySide6.QtWidgets import QApplication

from voice_input.app import VoiceInputApp
from voice_input.config import AppConfig


def test_none_hotkey_backend_disables_internal_listener() -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(hotkey_backend="none")
    controller = VoiceInputApp(app, config)
    assert controller._create_hotkey_backend() is None

