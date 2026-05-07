from __future__ import annotations

from collections.abc import Callable
import logging
import threading
from typing import Any

from .base import HotkeyBackend, HotkeyError


LOGGER = logging.getLogger(__name__)


class EvdevHotkeyBackend(HotkeyBackend):
    name = "evdev"

    def __init__(self, key_code: str = "KEY_RIGHTALT", device_path: str | None = None) -> None:
        self.key_code = key_code
        self.device_path = device_path
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._devices: list[Any] = []

    def is_available(self) -> bool:
        try:
            from evdev import InputDevice, ecodes, list_devices
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("evdev unavailable: %s", exc)
            return False

        paths = [self.device_path] if self.device_path else list_devices()
        for path in filter(None, paths):
            try:
                device = InputDevice(path)
                capabilities = device.capabilities().get(ecodes.EV_KEY, [])
                if ecodes.ecodes.get(self.key_code, -1) in capabilities:
                    device.close()
                    return True
                device.close()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Cannot probe input device %s: %s", path, exc)
        return False

    def start(self, callback: Callable[[], None]) -> None:
        try:
            from evdev import InputDevice, ecodes, list_devices
        except Exception as exc:  # noqa: BLE001
            raise HotkeyError(f"evdev 不可用: {exc}") from exc

        key_value = ecodes.ecodes.get(self.key_code)
        if key_value is None:
            raise HotkeyError(f"未知 evdev key code: {self.key_code}")

        paths = [self.device_path] if self.device_path else list_devices()
        self._devices = []
        errors: list[str] = []
        for path in filter(None, paths):
            try:
                device = InputDevice(path)
                capabilities = device.capabilities().get(ecodes.EV_KEY, [])
                if key_value in capabilities:
                    self._devices.append(device)
            except PermissionError as exc:
                errors.append(f"{path}: 权限不足 ({exc})")
            except OSError as exc:
                errors.append(f"{path}: {exc}")

        if not self._devices:
            details = "; ".join(errors) if errors else "没有找到包含该按键的 input 设备"
            raise HotkeyError(f"evdev 无法监听 {self.key_code}: {details}")

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            args=(callback, key_value),
            daemon=True,
            name="evdev-hotkey",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for device in self._devices:
            try:
                device.close()
            except OSError:
                pass
        self._devices = []
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _read_loop(self, callback: Callable[[], None], key_value: int) -> None:
        from evdev import categorize, ecodes

        while not self._stop.is_set():
            for device in list(self._devices):
                try:
                    for event in device.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        key_event = categorize(event)
                        if key_event.scancode == key_value and key_event.keystate == key_event.key_down:
                            callback()
                except BlockingIOError:
                    continue
                except OSError as exc:
                    LOGGER.debug("evdev read failed for %s: %s", getattr(device, "path", "?"), exc)
                    try:
                        self._devices.remove(device)
                    except ValueError:
                        pass
            self._stop.wait(0.02)

