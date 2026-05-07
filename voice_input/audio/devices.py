from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class InputDeviceInfo:
    index: int
    name: str
    channels: int
    default_samplerate: int

    @property
    def config_value(self) -> str:
        return self.name

    @property
    def label(self) -> str:
        rate = f", {self.default_samplerate}Hz" if self.default_samplerate else ""
        return f"{self.index}: {self.name} ({self.channels}ch{rate})"


def list_input_devices() -> list[InputDeviceInfo]:
    try:
        import sounddevice as sd
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"sounddevice 不可用: {exc}") from exc

    try:
        raw_devices = sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"无法读取音频输入设备: {exc}") from exc

    devices: list[InputDeviceInfo] = []
    for index, raw_device in enumerate(raw_devices):
        channels = int(raw_device.get("max_input_channels", 0) or 0)
        if channels <= 0:
            continue
        name = str(raw_device.get("name") or f"Input {index}")
        rate = int(float(raw_device.get("default_samplerate") or 0))
        devices.append(
            InputDeviceInfo(
                index=index,
                name=name,
                channels=channels,
                default_samplerate=rate,
            )
        )
    return devices


def measure_input_device_level(
    device: str | int | None,
    duration_seconds: float = 1.0,
    channels: int = 1,
) -> tuple[float, float]:
    try:
        import sounddevice as sd
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"sounddevice 不可用: {exc}") from exc

    normalized_device = _normalize_device(device)
    try:
        info = sd.query_devices(normalized_device, "input")
        sample_rate = int(float(info.get("default_samplerate") or 48000))
        frames = max(1, int(sample_rate * duration_seconds))
        data = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            device=normalized_device,
        )
        sd.wait()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"麦克风测试失败: {exc}") from exc

    samples = np.asarray(data, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        return 0.0, 0.0
    peak = float(np.max(np.abs(samples))) / 32768.0
    rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0
    return min(1.0, peak), min(1.0, rms)


def _normalize_device(device: str | int | None) -> str | int | None:
    if isinstance(device, str):
        value = device.strip()
        if value == "":
            return None
        if value.isdigit():
            return int(value)
        return value
    return device
