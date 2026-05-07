from __future__ import annotations

from abc import ABC, abstractmethod


class AsrError(RuntimeError):
    pass


class AsrClient(ABC):
    @abstractmethod
    async def start_session(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_audio_chunk(self, chunk: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def finish_session(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_partial_text(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_final_text(self) -> str:
        raise NotImplementedError

