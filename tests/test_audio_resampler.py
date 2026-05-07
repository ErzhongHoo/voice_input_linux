import numpy as np

from voice_input.audio.resampler import pcm16_to_mono_16k


def test_resamples_48k_to_16k() -> None:
    samples = np.arange(4800, dtype="<i2")
    output = pcm16_to_mono_16k(samples.tobytes(), source_rate=48000, source_channels=1)
    assert len(output) == 1600 * 2


def test_downmixes_stereo() -> None:
    stereo = np.array([[1000, -1000], [2000, 2000]], dtype="<i2")
    output = pcm16_to_mono_16k(stereo.tobytes(), source_rate=16000, source_channels=2)
    mono = np.frombuffer(output, dtype="<i2")
    assert mono.tolist() == [0, 2000]

