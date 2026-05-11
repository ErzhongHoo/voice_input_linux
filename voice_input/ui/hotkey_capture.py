from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget


@dataclass(frozen=True, slots=True)
class CapturedHotkey:
    hotkey_key: str
    evdev_key: str
    label: str


class HotkeyCaptureEdit(QLineEdit):
    hotkeyCaptured = Signal(str, str, str)

    def __init__(self, hotkey_key: str = "right_alt", evdev_key: str = "KEY_RIGHTALT", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hotkey_key = hotkey_key.strip() or "right_alt"
        self._evdev_key = evdev_key.strip() or "KEY_RIGHTALT"
        self._label = _label_for_hotkey(self._hotkey_key)
        self.setReadOnly(True)
        self.setPlaceholderText("点击后按下快捷键")
        self.setToolTip("点击后按一个单键作为录音快捷键；Esc 取消录入。")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_display()

    def hotkey_key(self) -> str:
        return self._hotkey_key

    def evdev_key(self) -> str:
        return self._evdev_key

    def setHotkey(self, hotkey_key: str, evdev_key: str = "") -> None:  # noqa: N802
        self._hotkey_key = hotkey_key.strip() or "right_alt"
        self._evdev_key = evdev_key.strip() or _evdev_for_hotkey(self._hotkey_key)
        self._label = _label_for_hotkey(self._hotkey_key)
        self._sync_display()

    def focusInEvent(self, event: object) -> None:  # noqa: N802
        super().focusInEvent(event)
        super().setText("按一个键...")
        self.selectAll()

    def focusOutEvent(self, event: object) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._sync_display()

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            event.accept()
            return
        captured = captured_hotkey_from_event(event)
        if captured is None:
            super().setText("不支持的按键")
            event.accept()
            return
        self._hotkey_key = captured.hotkey_key
        self._evdev_key = captured.evdev_key
        self._label = captured.label
        self._sync_display()
        self.hotkeyCaptured.emit(self._hotkey_key, self._evdev_key, self._label)
        self.clearFocus()
        event.accept()

    def _sync_display(self) -> None:
        super().setText(self._label)
        self.setToolTip(f"pynput: {self._hotkey_key}\nevdev: {self._evdev_key}\n点击后可重新录入。")


def captured_hotkey_from_event(event: QKeyEvent) -> CapturedHotkey | None:
    return captured_hotkey_from_qt_key(
        event.key(),
        text=event.text(),
        native_scan_code=event.nativeScanCode(),
    )


def captured_hotkey_from_qt_key(key: object, text: str = "", native_scan_code: int = 0) -> CapturedHotkey | None:
    key_int = _key_int(key)
    scan = int(native_scan_code or 0)

    scan_mapping = {
        37: CapturedHotkey("left_ctrl", "KEY_LEFTCTRL", "Left Ctrl"),
        50: CapturedHotkey("left_shift", "KEY_LEFTSHIFT", "Left Shift"),
        62: CapturedHotkey("right_shift", "KEY_RIGHTSHIFT", "Right Shift"),
        64: CapturedHotkey("left_alt", "KEY_LEFTALT", "Left Alt"),
        105: CapturedHotkey("right_ctrl", "KEY_RIGHTCTRL", "Right Ctrl"),
        108: CapturedHotkey("right_alt", "KEY_RIGHTALT", "Right Alt"),
        133: CapturedHotkey("left_super", "KEY_LEFTMETA", "Left Super"),
        134: CapturedHotkey("right_super", "KEY_RIGHTMETA", "Right Super"),
    }
    if scan in scan_mapping:
        return scan_mapping[scan]

    key_mapping = {
        _key_int(Qt.Key.Key_Alt): CapturedHotkey("left_alt", "KEY_LEFTALT", "Alt"),
        _key_int(Qt.Key.Key_Control): CapturedHotkey("left_ctrl", "KEY_LEFTCTRL", "Ctrl"),
        _key_int(Qt.Key.Key_Shift): CapturedHotkey("left_shift", "KEY_LEFTSHIFT", "Shift"),
        _key_int(Qt.Key.Key_Meta): CapturedHotkey("left_super", "KEY_LEFTMETA", "Super"),
        _key_int(Qt.Key.Key_Space): CapturedHotkey("space", "KEY_SPACE", "Space"),
        _key_int(Qt.Key.Key_Return): CapturedHotkey("enter", "KEY_ENTER", "Enter"),
        _key_int(Qt.Key.Key_Enter): CapturedHotkey("enter", "KEY_ENTER", "Enter"),
        _key_int(Qt.Key.Key_Tab): CapturedHotkey("tab", "KEY_TAB", "Tab"),
        _key_int(Qt.Key.Key_Backspace): CapturedHotkey("backspace", "KEY_BACKSPACE", "Backspace"),
        _key_int(Qt.Key.Key_Insert): CapturedHotkey("insert", "KEY_INSERT", "Insert"),
        _key_int(Qt.Key.Key_Delete): CapturedHotkey("delete", "KEY_DELETE", "Delete"),
        _key_int(Qt.Key.Key_Home): CapturedHotkey("home", "KEY_HOME", "Home"),
        _key_int(Qt.Key.Key_End): CapturedHotkey("end", "KEY_END", "End"),
        _key_int(Qt.Key.Key_PageUp): CapturedHotkey("page_up", "KEY_PAGEUP", "Page Up"),
        _key_int(Qt.Key.Key_PageDown): CapturedHotkey("page_down", "KEY_PAGEDOWN", "Page Down"),
        _key_int(Qt.Key.Key_Left): CapturedHotkey("left", "KEY_LEFT", "Left"),
        _key_int(Qt.Key.Key_Right): CapturedHotkey("right", "KEY_RIGHT", "Right"),
        _key_int(Qt.Key.Key_Up): CapturedHotkey("up", "KEY_UP", "Up"),
        _key_int(Qt.Key.Key_Down): CapturedHotkey("down", "KEY_DOWN", "Down"),
        _key_int(Qt.Key.Key_CapsLock): CapturedHotkey("caps_lock", "KEY_CAPSLOCK", "Caps Lock"),
    }
    if key_int in key_mapping:
        return key_mapping[key_int]

    f1 = _key_int(Qt.Key.Key_F1)
    f12 = _key_int(Qt.Key.Key_F12)
    if f1 <= key_int <= f12:
        number = key_int - f1 + 1
        return CapturedHotkey(f"f{number}", f"KEY_F{number}", f"F{number}")

    a = _key_int(Qt.Key.Key_A)
    z = _key_int(Qt.Key.Key_Z)
    if a <= key_int <= z:
        char = chr(ord("a") + key_int - a)
        return CapturedHotkey(char, f"KEY_{char.upper()}", char.upper())

    zero = _key_int(Qt.Key.Key_0)
    nine = _key_int(Qt.Key.Key_9)
    if zero <= key_int <= nine:
        char = chr(ord("0") + key_int - zero)
        return CapturedHotkey(char, f"KEY_{char}", char)

    value = text.strip().lower()
    if len(value) == 1 and value.isprintable():
        evdev = f"KEY_{value.upper()}" if value.isalnum() else ""
        if evdev:
            return CapturedHotkey(value, evdev, value.upper())
    return None


def _label_for_hotkey(hotkey_key: str) -> str:
    mapping = {
        "right_alt": "Right Alt",
        "left_alt": "Left Alt",
        "right_ctrl": "Right Ctrl",
        "left_ctrl": "Left Ctrl",
        "right_shift": "Right Shift",
        "left_shift": "Left Shift",
        "right_super": "Right Super",
        "left_super": "Left Super",
        "page_up": "Page Up",
        "page_down": "Page Down",
        "caps_lock": "Caps Lock",
    }
    key = hotkey_key.strip().lower()
    if key in mapping:
        return mapping[key]
    if len(key) == 1:
        return key.upper()
    if key.startswith("f") and key[1:].isdigit():
        return key.upper()
    return key.replace("_", " ").title()


def _evdev_for_hotkey(hotkey_key: str) -> str:
    key = hotkey_key.strip().lower()
    mapping = {
        "right_alt": "KEY_RIGHTALT",
        "left_alt": "KEY_LEFTALT",
        "right_ctrl": "KEY_RIGHTCTRL",
        "left_ctrl": "KEY_LEFTCTRL",
        "right_shift": "KEY_RIGHTSHIFT",
        "left_shift": "KEY_LEFTSHIFT",
        "right_super": "KEY_RIGHTMETA",
        "left_super": "KEY_LEFTMETA",
        "space": "KEY_SPACE",
        "enter": "KEY_ENTER",
        "tab": "KEY_TAB",
        "backspace": "KEY_BACKSPACE",
        "insert": "KEY_INSERT",
        "delete": "KEY_DELETE",
        "home": "KEY_HOME",
        "end": "KEY_END",
        "page_up": "KEY_PAGEUP",
        "page_down": "KEY_PAGEDOWN",
        "left": "KEY_LEFT",
        "right": "KEY_RIGHT",
        "up": "KEY_UP",
        "down": "KEY_DOWN",
        "caps_lock": "KEY_CAPSLOCK",
    }
    if key in mapping:
        return mapping[key]
    if key.startswith("f") and key[1:].isdigit():
        return f"KEY_F{key[1:]}"
    if len(key) == 1 and key.isalnum():
        return f"KEY_{key.upper()}"
    return "KEY_RIGHTALT"


def _key_int(key: object) -> int:
    value = getattr(key, "value", key)
    return int(value)
