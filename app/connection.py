import asyncio
from typing import List, Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> int:
        """Принимает соединение. Возвращает новое количество активных."""
        await ws.accept()
        async with self._lock:
            self.active.append(ws)
            return len(self.active)

    async def disconnect(self, ws: WebSocket) -> int:
        """Убирает соединение. Возвращает новое количество активных."""
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)
            return len(self.active)

    async def count(self) -> int:
        async with self._lock:
            return len(self.active)

    async def broadcast(self, message: Any):
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)


manager = ConnectionManager()