from __future__ import annotations

from types import SimpleNamespace
import sys

import numpy as np

from voice_input.audio.devices import list_input_devices, measure_input_device_level


def test_list_input_devices_filters_output_only_devices(monkeypatch) -> None:
    fake_sounddevice = SimpleNamespace(
        query_devices=lambda: [
            {
                "name": "Built-in Output",
                "max_input_channels": 0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "USB Mic",
                "max_input_channels": 1,
                "default_samplerate": 44100.0,
            },
        ]
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    devices = list_input_devices()

    assert len(devices) == 1
    assert devices[0].index == 1
    assert devices[0].name == "USB Mic"
    assert devices[0].channels == 1
    assert devices[0].default_samplerate == 44100
    assert devices[0].config_value == "USB Mic"
    assert devices[0].label == "1: USB Mic (1ch, 44100Hz)"


def test_list_input_devices_can_rescan_portaudio(monkeypatch) -> None:
    calls = []

    class FakeSoundDevice:
        _initialized = 1

        def _terminate(self):
            calls.append("terminate")
            self._initialized -= 1

        def _initialize(self):
            calls.append("initialize")
            self._initialized += 1

        def query_devices(self):
            calls.append("query")
            return [
                {
                    "name": "Hotplug Mic",
                    "max_input_channels": 1,
                    "default_samplerate": 48000.0,
                }
            ]

    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice())

    devices = list_input_devices(rescan=True)

    assert calls == ["terminate", "initialize", "query"]
    assert devices[0].name == "Hotplug Mic"


def test_input_device_level_uses_selected_device(monkeypatch) -> None:
    calls = {}

    def query_devices(device, kind):
        calls["query"] = (device, kind)
        return {"default_samplerate": 16000.0}

    def rec(frames, samplerate, channels, dtype, device):
        calls["rec"] = (frames, samplerate, channels, dtype, device)
        return np.array([[0], [16384], [-32768]], dtype=np.int16)

    fake_sounddevice = SimpleNamespace(
        query_devices=query_devices,
        rec=rec,
        wait=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    peak, rms = measure_input_device_level(" 8 ", duration_seconds=0.001, channels=1)

    assert calls["query"] == (8, "input")
    assert calls["rec"] == (16, 16000, 1, "int16", 8)
    assert peak == 1.0
    assert 0.6 < rms < 0.7
