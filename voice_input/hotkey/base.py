from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class HotkeyError(RuntimeError):
    pass


class HotkeyBackend(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def start(
        self,
        callback: Callable[[], None],
        release_callback: Callable[[], None] | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError
