from voice_input.ui.settings import stop_microphone_thread


class _Worker:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _Thread:
    def __init__(self, waits: list[bool]) -> None:
        self._waits = waits
        self.running = True
        self.quit_requested = False
        self.terminated = False
        self.wait_ms: list[int] = []

    def isRunning(self) -> bool:  # noqa: N802
        return self.running

    def quit(self) -> None:
        self.quit_requested = True

    def wait(self, wait_ms: int) -> bool:
        self.wait_ms.append(wait_ms)
        result = self._waits.pop(0)
        if result:
            self.running = False
        return result

    def terminate(self) -> None:
        self.terminated = True


def test_stop_microphone_thread_waits_for_clean_shutdown() -> None:
    worker = _Worker()
    thread = _Thread([True])

    stopped = stop_microphone_thread(worker, thread, 2500)

    assert stopped is True
    assert worker.stopped is True
    assert thread.quit_requested is True
    assert thread.terminated is False
    assert thread.wait_ms == [2500]


def test_stop_microphone_thread_terminates_forced_shutdown_after_timeout() -> None:
    worker = _Worker()
    thread = _Thread([False, True])

    stopped = stop_microphone_thread(worker, thread, 2500, force=True)

    assert stopped is True
    assert worker.stopped is True
    assert thread.quit_requested is True
    assert thread.terminated is True
    assert thread.wait_ms == [2500, 1000]
