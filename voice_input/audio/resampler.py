from __future__ import annotations

import numpy as np


def pcm16_to_mono_16k(
    data: bytes,
    source_rate: int,
    source_channels: int,
    target_rate: int = 16000,
) -> bytes:
    """Convert little-endian signed PCM16 to mono target-rate PCM16.

    The recorder requests 16 kHz mono directly, so this is mainly a helper for
    future backends that return a different native format.
    """

    if not data:
        return b""

    samples = np.frombuffer(data, dtype="<i2").astype(np.float32)
    if source_channels > 1:
        samples = samples.reshape(-1, source_channels).mean(axis=1)

    if source_rate != target_rate and samples.size > 1:
        duration = samples.size / float(source_rate)
        target_size = max(1, int(duration * target_rate))
        source_x = np.linspace(0.0, duration, num=samples.size, endpoint=False)
        target_x = np.linspace(0.0, duration, num=target_size, endpoint=False)
        samples = np.interp(target_x, source_x, samples)

    clipped = np.clip(samples, -32768, 32767).astype("<i2")
    return clipped.tobytes()

