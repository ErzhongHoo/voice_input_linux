from PySide6.QtWidgets import QApplication

from voice_input.ui.control_panel import NoWheelSpinBox as ControlPanelNoWheelSpinBox
from voice_input.ui.settings import NoWheelSpinBox as SettingsNoWheelSpinBox


class FakeWheelEvent:
    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True


def test_settings_spin_boxes_ignore_mouse_wheel() -> None:
    QApplication.instance() or QApplication([])

    for spin_box_class in (ControlPanelNoWheelSpinBox, SettingsNoWheelSpinBox):
        spin_box = spin_box_class()
        spin_box.setRange(0, 10)
        spin_box.setValue(5)
        event = FakeWheelEvent()

        spin_box.wheelEvent(event)  # type: ignore[arg-type]

        assert event.ignored is True
        assert spin_box.value() == 5
