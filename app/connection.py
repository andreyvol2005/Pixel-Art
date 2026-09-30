import asyncio
from typing import List, Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, message: Any):
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)


manager = ConnectionManager()