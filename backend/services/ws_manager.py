from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ProgressWSManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
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

    def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        if task_id not in self._connections:
            return
        try:
            self._connections[task_id].remove(websocket)
        except ValueError:
            pass
        if not self._connections[task_id]:
            del self._connections[task_id]

    async def send_progress(self, task_id: str, data: dict[str, Any]) -> None:
        if task_id not in self._connections:
            return
        disconnected: list[WebSocket] = []
        for ws in self._connections[task_id]:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(task_id, ws)

    async def send_final(self, task_id: str, data: dict[str, Any]) -> None:
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
        self._connections.pop(task_id, None)

    async def broadcast(self, data: dict[str, Any]) -> None:
        disconnected: list[tuple[str, WebSocket]] = []
        for task_id, connections in self._connections.items():
            for ws in connections:
                try:
                    await ws.send_json(data)
                except Exception:
                    disconnected.append((task_id, ws))
        for task_id, ws in disconnected:
            self.disconnect(task_id, ws)

    async def broadcast_render_cache_update(self, task_id: str, files: list[dict]) -> None:
        message = {
            "type": "render_cache_updated",
            "task_id": task_id,
            "files": files,
        }
        await self.broadcast(message)


ws_manager = ProgressWSManager()
