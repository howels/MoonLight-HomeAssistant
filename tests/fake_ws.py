"""A stand-in for aiohttp's WebSocket, so tests can push frames without a socket."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import WSMsgType
from aiohttp.http_websocket import WSMessage


class FakeWebSocket:
    """One WebSocket. `feed` queues a text frame. `close` ends the iterator."""

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self._messages: asyncio.Queue[WSMessage | None] = asyncio.Queue()
        self.closed = False

    async def send_json(self, data: Any, dumps: Any = None) -> None:
        """Record a frame the integration sent."""
        self.sent.append(data)

    async def receive(self, timeout: float | None = None) -> WSMessage:
        """The first frame, or a timeout when the device has not spoken yet."""
        if self._messages.empty():
            raise TimeoutError
        message = self._messages.get_nowait()
        if message is None:
            raise StopAsyncIteration
        return message

    def feed(self, payload: dict[str, Any]) -> None:
        """Queue one text frame, as the device would push it."""
        self._messages.put_nowait(WSMessage(WSMsgType.TEXT, json.dumps(payload), None))

    def feed_close(self) -> None:
        """Queue a close, as a dropped device socket."""
        self._messages.put_nowait(WSMessage(WSMsgType.CLOSED, None, None))

    def __aiter__(self) -> FakeWebSocket:
        return self

    async def __anext__(self) -> WSMessage:
        message = await self._messages.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def close(self) -> None:
        """End the iterator."""
        self.closed = True
        await self._messages.put(None)
