"""Serialize WebSocket sends to avoid websockets library drain races (keepalive vs app)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def start_disconnect_watch(ws: WebSocket) -> tuple[asyncio.Event, asyncio.Task[None]]:
    """Drain inbound frames so peer close is observed without send/drain races."""
    done = asyncio.Event()

    async def _watch() -> None:
        try:
            while True:
                msg = await ws.receive()
                if msg.get('type') == 'websocket.disconnect':
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.debug('WebSocket disconnect watch ended', exc_info=True)
        finally:
            done.set()

    return done, asyncio.create_task(_watch())


async def stop_disconnect_watch(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


class SafeWebSocket:
    """Wrap FastAPI WebSocket so all outbound frames share one asyncio lock."""

    __slots__ = ('_ws', '_send_lock')

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._send_lock = asyncio.Lock()

    @property
    def raw(self) -> WebSocket:
        return self._ws

    @property
    def query_params(self):
        return self._ws.query_params

    async def accept(self) -> None:
        await self._ws.accept()

    async def close(self, code: int = 1000) -> None:
        async with self._send_lock:
            await self._ws.close(code=code)

    async def receive_json(self):
        return await self._ws.receive_json()

    async def send_bytes(self, data: bytes) -> None:
        async with self._send_lock:
            await self._ws.send_bytes(data)

    async def send_text(self, text: str) -> None:
        async with self._send_lock:
            await self._ws.send_text(text)
