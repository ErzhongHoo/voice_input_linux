from __future__ import annotations

import asyncio

from .base import AsrClient


class MockAsrClient(AsrClient):
    def __init__(self, final_text: str = "这是一次语音输入测试。") -> None:
        self.final_text = final_text
        self.total_bytes = 0
        self.started = False

    async def start_session(self) -> None:
        self.started = True

    async def send_audio_chunk(self, chunk: bytes) -> None:
        self.total_bytes += len(chunk)

    async def finish_session(self) -> None:
        await asyncio.sleep(0.2)

    async def get_partial_text(self) -> str:
        return ""

    async def get_final_text(self) -> str:
        return self.final_text

