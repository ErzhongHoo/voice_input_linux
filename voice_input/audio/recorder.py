from __future__ import annotations

from collections.abc import Callable
import logging

import numpy as np

from .resampler import pcm16_to_mono_16k


LOGGER = logging.getLogger(__name__)


class RecorderError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_ms: int = 200,
        device: str | int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_ms = chunk_ms
        self.device = _normalize_device(device)
        self._source_rate = sample_rate
        self._stream = None
        self._on_chunk: Callable[[bytes], None] | None = None
        self._on_level: Callable[[float], None] | None = None
        self._on_error: Callable[[str], None] | None = None

    def start(
        self,
        on_chunk: Callable[[bytes], None],
        on_level: Callable[[float], None],
        on_error: Callable[[str], None],
    ) -> None:
        if self._stream is not None:
            raise RecorderError("录音已经在运行")
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001
            raise RecorderError(f"sounddevice 不可用: {exc}") from exc

        self._on_chunk = on_chunk
        self._on_level = on_level
        self._on_error = on_error
        self._source_rate = self._pick_source_rate(sd)
        blocksize = max(1, int(self._source_rate * self.chunk_ms / 1000))
        LOGGER.info(
            "Opening audio input device=%r source_rate=%s target_rate=%s channels=%s chunk_ms=%s",
            self.device,
            self._source_rate,
            self.sample_rate,
            self.channels,
            self.chunk_ms,
        )

        def callback(indata: bytes, frames: int, time_info: object, status: object) -> None:
            if status:
                LOGGER.warning("Audio input status: %s", status)
            raw = bytes(indata)
            data = pcm16_to_mono_16k(
                raw,
                source_rate=self._source_rate,
                source_channels=self.channels,
                target_rate=self.sample_rate,
            )
            try:
                if self._on_chunk:
                    self._on_chunk(data)
                if self._on_level:
                    self._on_level(_rms_level(data))
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Audio callback failed")
                if self._on_error:
                    self._on_error(str(exc))

        try:
            self._stream = sd.RawInputStream(
                samplerate=self._source_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=blocksize,
                callback=callback,
                device=self.device,
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            self._stream = None
            raise RecorderError(f"无法打开默认麦克风: {exc}") from exc

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception as exc:  # noqa: BLE001
            raise RecorderError(f"停止录音失败: {exc}") from exc
        finally:
            self._stream = None

    def _pick_source_rate(self, sd: object) -> int:
        try:
            info = sd.query_devices(self.device, "input")
            return int(info.get("default_samplerate") or self.sample_rate)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Cannot query input device %r, using target rate %s: %s", self.device, self.sample_rate, exc)
            return self.sample_rate


def _rms_level(data: bytes) -> float:
    if not data:
        return 0.0
    samples = np.frombuffer(data, dtype="<i2").astype(np.float32)
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(samples * samples)))
    return min(1.0, rms / 32768.0 * 5.0)


def _normalize_device(device: str | int | None) -> str | int | None:
    if isinstance(device, str):
        value = device.strip()
        if value == "":
            return None
        if value.isdigit():
            return int(value)
        return value
    return device
