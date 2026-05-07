import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ProgressWSManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        if task_id in self._connections:
            for old_ws in self._connections[task_id]:
                try:
                    await old_ws.close()
                except Exception:
                    pass
            self._connections[task_id].clear()
        else:
            self._connections[task_id] = []
        self._connections[task_id].append(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket):
        if task_id in self._connections:
            try:
                self._connections[task_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[task_id]:
                del self._connections[task_id]

    async def send_progress(self, task_id: str, data: dict):
        if task_id not in self._connections:
            return
        disconnected = []
        for ws in self._connections[task_id]:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(task_id, ws)

    async def send_final(self, task_id: str, data: dict):
        if task_id not in self._connections:
            return
        for ws in self._connections[task_id]:
            try:
                await ws.send_json(data)
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
        if task_id in self._connections:
            del self._connections[task_id]


ws_manager = ProgressWSManager()
