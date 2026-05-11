from __future__ import annotations

import asyncio
import fcntl
import logging
import os
from pathlib import Path
import queue
import socket
import sys
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .asr.base import AsrClient, AsrError
from .asr.doubao_big_asr import DoubaoBigASRClient
from .asr.mock_asr import MockAsrClient
from .asr.qwen_realtime_asr import QwenRealtimeASRClient
from .audio.recorder import AudioRecorder, RecorderError
from .config import ASR_PROVIDER_QWEN, DOUBAO_ASR_PROVIDERS, AppConfig, ensure_config_file, load_config, write_env_file
from .history import append_history, clear_history as clear_saved_history, load_history
from .hotkey.base import HotkeyBackend, HotkeyError
from .hotkey.evdev_backend import EvdevHotkeyBackend
from .hotkey.pynput_backend import PynputHotkeyBackend
from .inject import build_text_injector
from .inject.base import InjectionError, TextInjectorBackend
from .postprocess.organizer import ChatCompletionTextOrganizer
from .postprocess.processor import TextPostProcessor
from .resource_paths import resource_path
from .ui.control_panel import ControlPanel
from .ui.environment import EnvironmentDialog
from .ui.overlay import OverlayWindow
from .ui.settings import SettingsDialog
from .ui.tray import TrayController


LOGGER = logging.getLogger("voice_input")
HOTKEY_HOLD_THRESHOLD_MS = 350
RECORDING_MODE_DICTATION = "dictation"
RECORDING_MODE_PENDING_HOTKEY = "pending_hotkey"
RECORDING_MODE_ORGANIZER = "organizer"


class SingleInstanceLock:
    def __init__(self, socket_path: str) -> None:
        socket = Path(socket_path)
        self.lock_path = socket.with_suffix(".lock")
        self._file = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.lock_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        self._file.write(str(os.getpid()))
        self._file.flush()
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None


class SignalBus(QObject):
    hotkey_pressed = Signal()
    hotkey_released = Signal()
    toggle_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    settings_requested = Signal()
    show_requested = Signal()
    quit_requested = Signal()
    asr_finished = Signal(str)
    asr_failed = Signal(str)
    organizer_finished = Signal(str)
    organizer_failed = Signal(str, str)
    audio_level = Signal(float)


class AsrStreamingWorker(threading.Thread):
    def __init__(
        self,
        client: AsrClient,
        on_finished: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        super().__init__(daemon=True, name="asr-streaming-worker")
        self._client = client
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._on_finished = on_finished
        self._on_error = on_error
        self._finish_requested = threading.Event()

    def send_audio_chunk(self, chunk: bytes) -> None:
        if not self._finish_requested.is_set():
            self._queue.put(chunk)

    def finish(self) -> None:
        self._finish_requested.set()
        self._queue.put(None)

    def run(self) -> None:
        try:
            final_text = asyncio.run(self._run_session())
        except Exception as exc:  # noqa: BLE001 - errors need to reach UI.
            LOGGER.exception("ASR session failed")
            self._on_error(str(exc))
            return
        self._on_finished(final_text)

    async def _run_session(self) -> str:
        await self._client.start_session()
        while True:
            chunk = await asyncio.to_thread(self._queue.get)
            if chunk is None:
                break
            await self._client.send_audio_chunk(chunk)
        await self._client.finish_session()
        return await self._client.get_final_text()


class TextOrganizerWorker(threading.Thread):
    def __init__(
        self,
        organizer: ChatCompletionTextOrganizer,
        text: str,
        on_finished: Callable[[str], None],
        on_error: Callable[[str, str], None],
    ) -> None:
        super().__init__(daemon=True, name="text-organizer-worker")
        self._organizer = organizer
        self._text = text
        self._on_finished = on_finished
        self._on_error = on_error

    def run(self) -> None:
        try:
            final_text = self._organizer.organize(self._text)
        except Exception as exc:  # noqa: BLE001 - errors need to reach UI.
            LOGGER.exception("Text organizer failed")
            self._on_error(str(exc), self._text)
            return
        self._on_finished(final_text)


class CommandServer:
    def __init__(self, socket_path: str, signal_bus: SignalBus) -> None:
        self._socket_path = Path(socket_path)
        self._signal_bus = signal_bus
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None

    def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self._socket_path.exists():
            try:
                self._socket_path.unlink()
            except OSError:
                LOGGER.warning("Could not remove stale socket %s", self._socket_path)

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self._socket_path))
        self._server.listen(5)
        self._server.settimeout(0.5)
        self._thread = threading.Thread(target=self._serve, daemon=True, name="command-server")
        self._thread.start()
        LOGGER.info("Command socket listening at %s", self._socket_path)

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            self._socket_path.unlink()
        except OSError:
            pass

    def _serve(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with conn:
                try:
                    command = conn.recv(128).decode("utf-8", errors="ignore").strip()
                except OSError:
                    continue
                LOGGER.info("Received command: %s", command)
                if command == "toggle":
                    self._signal_bus.toggle_requested.emit()
                elif command == "start":
                    self._signal_bus.start_requested.emit()
                elif command == "stop":
                    self._signal_bus.stop_requested.emit()
                elif command == "settings":
                    self._signal_bus.settings_requested.emit()
                elif command == "show":
                    self._signal_bus.show_requested.emit()
                elif command == "quit":
                    self._signal_bus.quit_requested.emit()
                try:
                    conn.sendall(b"ok")
                except OSError:
                    pass


class VoiceInputApp:
    def __init__(self, qt_app: QApplication, config: AppConfig) -> None:
        self.qt_app = qt_app
        self.config = config
        self.signals = SignalBus()
        self.recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            chunk_ms=config.chunk_ms,
            device=config.input_device or None,
        )
        self.postprocessor = TextPostProcessor(append_final_punctuation=config.append_final_punctuation)
        self.injector: TextInjectorBackend = build_text_injector(config)
        self.history_entries = load_history()
        self.overlay = OverlayWindow(theme=config.overlay_theme)
        self.control_panel = ControlPanel(
            config=config,
            on_toggle_recording=self.toggle_recording,
            on_settings=self.show_settings,
            on_environment=self.show_environment,
            on_clear_history=self.clear_history,
            on_quit=self.quit,
            on_save_settings=self.save_panel_settings,
            history_entries=self.history_entries,
        )
        self.tray = TrayController(
            on_show=self.show_control_panel,
            on_toggle=self.toggle_recording,
            on_settings=self.show_settings,
            on_quit=self.quit,
        )
        self.hotkey: HotkeyBackend | None = None
        self.command_server = CommandServer(config.socket_path, self.signals)
        self.asr_worker: AsrStreamingWorker | None = None
        self.organizer_worker: TextOrganizerWorker | None = None
        self.is_recording = False
        self._recording_mode = RECORDING_MODE_DICTATION
        self._pending_result_mode = RECORDING_MODE_DICTATION
        self._hotkey_down = False
        self._ignore_next_hotkey_release = False
        self._hotkey_pressed_at = 0.0
        self._hotkey_hold_timer = QTimer()
        self._hotkey_hold_timer.setSingleShot(True)
        self._hotkey_hold_timer.setInterval(HOTKEY_HOLD_THRESHOLD_MS)
        self._hotkey_hold_timer.timeout.connect(self._promote_hotkey_hold_recording)
        self._recording_max_level = 0.0
        self._recording_chunks = 0

        self.signals.hotkey_pressed.connect(self._handle_hotkey_pressed)
        self.signals.hotkey_released.connect(self._handle_hotkey_released)
        self.signals.toggle_requested.connect(self.toggle_recording)
        self.signals.start_requested.connect(lambda: self.start_recording(RECORDING_MODE_DICTATION))
        self.signals.stop_requested.connect(self.stop_recording)
        self.signals.settings_requested.connect(self.show_settings)
        self.signals.show_requested.connect(self.show_control_panel)
        self.signals.quit_requested.connect(self.quit)
        self.signals.asr_finished.connect(self._handle_asr_finished)
        self.signals.asr_failed.connect(self._handle_asr_failed)
        self.signals.organizer_finished.connect(self._handle_organizer_finished)
        self.signals.organizer_failed.connect(self._handle_organizer_failed)
        self.signals.audio_level.connect(self.overlay.update_level)

    def start(self) -> None:
        self.tray.show()
        self.command_server.start()
        self._start_hotkey()
        LOGGER.info("Configuration: %s", self.config.masked())
        LOGGER.info("Text injector candidates: %s", self.injector.name)

    def show_control_panel(self) -> None:
        self.control_panel.show_panel()

    def _start_hotkey(self) -> None:
        try:
            self.hotkey = self._create_hotkey_backend()
            if self.hotkey is None:
                message = "未启用全局快捷键，请使用托盘或 compositor 调用 CLI toggle。"
                LOGGER.warning(message)
                self.tray.notify("Voice Input Linux", message)
                return
            self.hotkey.start(
                lambda: self.signals.hotkey_pressed.emit(),
                lambda: self.signals.hotkey_released.emit(),
            )
            LOGGER.info("Hotkey backend started: %s", self.hotkey.name)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to start hotkey backend")
            self.hotkey = None
            self.tray.notify("快捷键不可用", str(exc))

    def _create_hotkey_backend(self) -> HotkeyBackend | None:
        backend = self.config.hotkey_backend
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()

        if backend in {"none", "disabled", "off"}:
            return None
        if backend == "pynput":
            return PynputHotkeyBackend(self.config.hotkey_key)
        if backend == "evdev":
            return EvdevHotkeyBackend(self.config.evdev_key, self.config.evdev_device or None)
        if backend != "auto":
            raise HotkeyError(f"未知快捷键 backend: {backend}")

        candidates: list[Callable[[], HotkeyBackend]]
        if session_type == "wayland":
            candidates = [
                lambda: EvdevHotkeyBackend(self.config.evdev_key, self.config.evdev_device or None),
                lambda: PynputHotkeyBackend(self.config.hotkey_key),
            ]
        else:
            candidates = [
                lambda: PynputHotkeyBackend(self.config.hotkey_key),
                lambda: EvdevHotkeyBackend(self.config.evdev_key, self.config.evdev_device or None),
            ]

        errors: list[str] = []
        for factory in candidates:
            try:
                candidate = factory()
                if candidate.is_available():
                    return candidate
                errors.append(f"{candidate.name} unavailable")
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        LOGGER.warning("No hotkey backend available: %s", "; ".join(errors))
        return None

    def toggle_recording(self) -> None:
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording(RECORDING_MODE_DICTATION)

    def _handle_hotkey_pressed(self) -> None:
        if self._hotkey_down:
            return
        self._hotkey_down = True
        self._ignore_next_hotkey_release = False
        self._hotkey_pressed_at = time.monotonic()

        if self.is_recording:
            self._ignore_next_hotkey_release = True
            self._hotkey_hold_timer.stop()
            self.stop_recording()
            LOGGER.info("Hotkey tap stopped recording; mode=%s", self._pending_result_mode)
            return

        self.start_recording(RECORDING_MODE_PENDING_HOTKEY)
        if self.is_recording:
            self._hotkey_hold_timer.start()

    def _handle_hotkey_released(self) -> None:
        self._hotkey_down = False
        if self._ignore_next_hotkey_release:
            self._ignore_next_hotkey_release = False
            return
        if not self.is_recording:
            return

        self._hotkey_hold_timer.stop()
        held_ms = (time.monotonic() - self._hotkey_pressed_at) * 1000
        if self._recording_mode == RECORDING_MODE_PENDING_HOTKEY and held_ms < HOTKEY_HOLD_THRESHOLD_MS:
            self._recording_mode = RECORDING_MODE_ORGANIZER
            self.overlay.set_recording_status("整理录音中")
            LOGGER.info("Hotkey tap started organizer-mode recording")
            return

        if self._recording_mode == RECORDING_MODE_PENDING_HOTKEY:
            self._recording_mode = RECORDING_MODE_DICTATION
        if self._recording_mode == RECORDING_MODE_DICTATION:
            self.stop_recording()

    def _promote_hotkey_hold_recording(self) -> None:
        if self._hotkey_down and self.is_recording and self._recording_mode == RECORDING_MODE_PENDING_HOTKEY:
            self._recording_mode = RECORDING_MODE_DICTATION
            self.overlay.set_recording_status("短句录音中")
            LOGGER.info("Hotkey hold promoted to dictation mode")

    def start_recording(self, mode: str = RECORDING_MODE_DICTATION) -> None:
        if self.is_recording:
            return
        if self.organizer_worker and self.organizer_worker.is_alive():
            self.overlay.show_error("上一段语音还在整理")
            return
        try:
            client = self._create_asr_client()
            self._recording_mode = mode
            self._recording_max_level = 0.0
            self._recording_chunks = 0
            self.asr_worker = AsrStreamingWorker(
                client=client,
                on_finished=lambda text: self.signals.asr_finished.emit(text),
                on_error=lambda error: self.signals.asr_failed.emit(error),
            )
            self.asr_worker.start()
            self.recorder.start(
                on_chunk=self._handle_audio_chunk,
                on_level=self._handle_audio_level,
                on_error=lambda error: self.signals.asr_failed.emit(error),
            )
        except (AsrError, RecorderError, OSError) as exc:
            LOGGER.exception("Failed to start recording")
            if self.asr_worker:
                self.asr_worker.finish()
                self.asr_worker = None
            self.overlay.show_error(str(exc))
            self.tray.notify("无法开始录音", str(exc))
            return

        self.is_recording = True
        self.tray.set_recording(True)
        self.control_panel.set_recording(True)
        status = "整理录音中" if mode == RECORDING_MODE_ORGANIZER else "录音中"
        self.overlay.show_recording(status)
        LOGGER.info("Recording started; mode=%s", mode)

    def stop_recording(self) -> None:
        if not self.is_recording:
            return
        self.is_recording = False
        self._hotkey_hold_timer.stop()
        if self._recording_mode == RECORDING_MODE_PENDING_HOTKEY:
            self._recording_mode = RECORDING_MODE_DICTATION
        self._pending_result_mode = self._recording_mode
        self._recording_mode = RECORDING_MODE_DICTATION
        try:
            self.recorder.stop()
        except RecorderError as exc:
            LOGGER.warning("Recorder stop failed: %s", exc)
        self.tray.set_recording(False)
        self.control_panel.set_recording(False)
        self.overlay.show_recognizing()
        if self.asr_worker:
            self.asr_worker.finish()
        LOGGER.info(
            "Recording stopped; audio stats chunks=%s max_level=%.4f",
            self._recording_chunks,
            self._recording_max_level,
        )
        LOGGER.info("Recording stopped; waiting for ASR final text")

    def _handle_audio_chunk(self, chunk: bytes) -> None:
        worker = self.asr_worker
        self._recording_chunks += 1
        if worker:
            worker.send_audio_chunk(chunk)

    def _handle_audio_level(self, level: float) -> None:
        self._recording_max_level = max(self._recording_max_level, level)
        self.signals.audio_level.emit(level)

    def _handle_asr_finished(self, text: str) -> None:
        self.asr_worker = None
        mode = self._pending_result_mode
        self._pending_result_mode = RECORDING_MODE_DICTATION
        final_text = self.postprocessor.process(text)
        if not final_text:
            LOGGER.warning(
                "ASR final text is empty; recording max_level=%.4f chunks=%s",
                self._recording_max_level,
                self._recording_chunks,
            )
            self.overlay.show_error("识别结果为空")
            return

        if mode == RECORDING_MODE_ORGANIZER:
            self._start_text_organizer(final_text)
            return

        self._commit_final_text(final_text, self.config.asr_provider)

    def _start_text_organizer(self, text: str) -> None:
        organizer = ChatCompletionTextOrganizer(
            endpoint=self.config.organizer_endpoint,
            api_key=self.config.organizer_api_key,
            model=self.config.organizer_model,
            provider=self.config.organizer_provider,
            timeout=self.config.organizer_timeout,
        )
        self.overlay.show_organizing()
        self.organizer_worker = TextOrganizerWorker(
            organizer=organizer,
            text=text,
            on_finished=lambda final_text: self.signals.organizer_finished.emit(final_text),
            on_error=lambda error, fallback: self.signals.organizer_failed.emit(error, fallback),
        )
        self.organizer_worker.start()
        LOGGER.info(
            "Organizer-mode text organizer started; provider=%s model=%s text length=%s",
            self.config.organizer_provider,
            self.config.organizer_model,
            len(text),
        )

    def _handle_organizer_finished(self, text: str) -> None:
        self.organizer_worker = None
        final_text = self.postprocessor.process(text)
        if not final_text:
            self.overlay.show_error("整理结果为空")
            return
        self._commit_final_text(final_text, f"{self.config.asr_provider}+{self.config.organizer_provider}")

    def _handle_organizer_failed(self, message: str, fallback_text: str) -> None:
        self.organizer_worker = None
        LOGGER.error("Organizer-mode text organizer failed: %s", message)
        self.tray.notify("整理模型失败", "已输入原始识别文本。")
        self._commit_final_text(fallback_text, self.config.asr_provider)

    def _commit_final_text(self, final_text: str, provider: str) -> None:
        try:
            self.history_entries = append_history(final_text, provider)
            self.control_panel.set_history(self.history_entries)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed to write history: %s", exc)

        try:
            self.injector.inject_text(final_text)
        except InjectionError as exc:
            LOGGER.exception("Text injection failed")
            self.overlay.show_error(f"无法输入文字: {exc}")
            self.tray.notify("无法输入文字", str(exc))
            return

        self.overlay.show_result(final_text)
        LOGGER.info("Text injected, length=%s", len(final_text))

    def _handle_asr_failed(self, message: str) -> None:
        worker = self.asr_worker
        self._hotkey_hold_timer.stop()
        self._hotkey_down = False
        self._ignore_next_hotkey_release = False
        self._recording_mode = RECORDING_MODE_DICTATION
        self._pending_result_mode = RECORDING_MODE_DICTATION
        if self.is_recording:
            self.is_recording = False
            try:
                self.recorder.stop()
            except RecorderError:
                pass
            self.tray.set_recording(False)
            self.control_panel.set_recording(False)
        if worker and worker.is_alive():
            worker.finish()
        self.asr_worker = None
        LOGGER.error("ASR/recording error: %s", message)
        self.overlay.show_error(message)
        self.tray.notify("语音输入错误", message)

    def _create_asr_client(self) -> AsrClient:
        if self.config.asr_provider == "mock":
            return MockAsrClient(self.config.mock_text)
        if self.config.asr_provider in DOUBAO_ASR_PROVIDERS:
            return DoubaoBigASRClient(
                endpoint=self.config.effective_doubao_endpoint(),
                app_key=self.config.doubao_app_key,
                access_key=self.config.doubao_access_key,
                resource_id=self.config.doubao_resource_id,
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                enable_punc=self.config.doubao_enable_punc,
                enable_itn=self.config.doubao_enable_itn,
                enable_ddc=self.config.doubao_enable_ddc,
                enable_nonstream=self.config.effective_doubao_enable_nonstream(),
            )
        if self.config.asr_provider == ASR_PROVIDER_QWEN:
            return QwenRealtimeASRClient(
                endpoint=self.config.qwen_endpoint,
                api_key=self.config.qwen_api_key,
                model=self.config.qwen_model,
                language=self.config.qwen_language,
                sample_rate=self.config.sample_rate,
                enable_server_vad=self.config.qwen_enable_server_vad,
                vad_threshold=self.config.qwen_vad_threshold,
                vad_silence_ms=self.config.qwen_vad_silence_ms,
            )
        raise AsrError(f"未知 ASR provider: {self.config.asr_provider}")

    def show_settings(self) -> None:
        if self.is_recording:
            QMessageBox.warning(None, "Voice Input Linux 设置", "录音中不能修改设置，请先停止录音。")
            return
        dialog = SettingsDialog(self.config, on_auto_save=self.save_panel_settings)
        dialog.exec()

    def save_panel_settings(self, env: dict[str, str]) -> bool:
        if self.is_recording:
            QMessageBox.warning(self.control_panel, "Voice Input Linux 设置", "录音中不能修改设置，请先停止录音。")
            return False
        show_notification = env.pop("_VOICE_INPUT_SAVE_NOTIFICATION", "true") != "false"
        config_file = env.pop("VOICE_INPUT_CONFIG_FILE", self.config.config_file) or self.config.config_file
        try:
            write_env_file(config_file, env)
            self._apply_new_config(load_config(config_file))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to save settings")
            QMessageBox.critical(self.control_panel, "保存设置失败", str(exc))
            return False
        if show_notification:
            self.tray.notify("设置已保存", f"配置文件: {self.config.config_file}")
        return True

    def show_environment(self) -> None:
        dialog = EnvironmentDialog(self.config, self.control_panel)
        dialog.exec()

    def clear_history(self) -> None:
        try:
            clear_saved_history()
            self.history_entries = []
            self.control_panel.set_history(self.history_entries)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to clear history")
            QMessageBox.critical(self.control_panel, "清空历史记录失败", str(exc))

    def _apply_new_config(self, new_config: AppConfig) -> None:
        old_socket_path = self.config.socket_path
        self.config = new_config
        self.control_panel.update_config(new_config)
        self.recorder = AudioRecorder(
            sample_rate=new_config.sample_rate,
            channels=new_config.channels,
            chunk_ms=new_config.chunk_ms,
            device=new_config.input_device or None,
        )
        self.postprocessor = TextPostProcessor(append_final_punctuation=new_config.append_final_punctuation)
        self.injector = build_text_injector(new_config)
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        self._start_hotkey()

        if new_config.socket_path != old_socket_path:
            self.command_server.stop()
            self.command_server = CommandServer(new_config.socket_path, self.signals)
            self.command_server.start()

        LOGGER.info("Settings reloaded: %s", self.config.masked())
        LOGGER.info("Text injector candidates: %s", self.injector.name)

    def quit(self) -> None:
        self._hotkey_hold_timer.stop()
        if self.is_recording:
            self.stop_recording()
        if self.hotkey:
            self.hotkey.stop()
        self.command_server.stop()
        self.tray.hide()
        self.control_panel.close()
        self.qt_app.quit()


def configure_logging(config: AppConfig) -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def run_app(show_panel: bool = False) -> int:
    config = load_config()
    ensure_config_file(config.config_file, config)
    configure_logging(config)
    instance_lock = SingleInstanceLock(config.socket_path)
    if not instance_lock.acquire():
        message = f"Voice Input Linux 已在运行，跳过重复启动。socket={config.socket_path}"
        LOGGER.warning(message)
        print(message, file=sys.stderr)
        return 0
    try:
        qt_app = QApplication.instance() or QApplication([])
        qt_app.setApplicationName("Voice Input Linux")
        qt_app.setDesktopFileName("voice-input-linux")
        try:
            with resource_path("voice-input-linux.svg") as icon_path:
                qt_app.setWindowIcon(QIcon(str(icon_path)))
        except Exception:  # noqa: BLE001
            pass
        qt_app.setQuitOnLastWindowClosed(False)
        controller = VoiceInputApp(qt_app, config)
        controller.start()
        if show_panel:
            controller.show_control_panel()
        return int(qt_app.exec())
    finally:
        instance_lock.release()
