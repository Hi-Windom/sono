from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 60.0
PROGRESS_HISTORY_TTL = 3600.0


class ProgressWSManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._last_seen: dict[int, float] = {}
        self._progress_cache: dict[str, dict[str, Any]] = {}
        self._progress_cache_time: dict[str, float] = {}
        self._heartbeat_task: asyncio.Task | None = None

    async def start_heartbeat_monitor(self) -> None:
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

    async def _heartbeat_monitor(self) -> None:
        while True:
            try:
                await asyncio.sleep(10.0)
                await self._check_timeout_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[ws_manager] 心跳监控异常: {e}")

    async def _check_timeout_connections(self) -> None:
        now = time.time()
        timeout_connections: list[tuple[str, WebSocket]] = []
        async with self._lock:
            for task_id, conns in list(self._connections.items()):
                for ws in conns:
                    ws_id = id(ws)
                    last = self._last_seen.get(ws_id, 0.0)
                    if now - last > HEARTBEAT_TIMEOUT:
                        timeout_connections.append((task_id, ws))
        for task_id, ws in timeout_connections:
            logger.warning(f"[ws_manager] 连接心跳超时，主动断开 task_id={task_id}")
            try:
                await ws.close(code=1001, reason="heartbeat timeout")
            except Exception:
                pass
            await self.disconnect(task_id, ws)

    def record_activity(self, websocket: WebSocket) -> None:
        self._last_seen[id(websocket)] = time.time()

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if task_id not in self._connections:
                self._connections[task_id] = []
            self._connections[task_id].append(websocket)
            self._last_seen[id(websocket)] = time.time()

    async def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if task_id not in self._connections:
                return
            try:
                self._connections[task_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[task_id]:
                del self._connections[task_id]
            self._last_seen.pop(id(websocket), None)

    def _save_progress(self, task_id: str, data: dict[str, Any]) -> None:
        self._progress_cache[task_id] = dict(data)
        self._progress_cache_time[task_id] = time.time()

    def get_cached_progress(self, task_id: str) -> dict[str, Any] | None:
        cached = self._progress_cache.get(task_id)
        if cached is None:
            return None
        cached_time = self._progress_cache_time.get(task_id, 0.0)
        if time.time() - cached_time > PROGRESS_HISTORY_TTL:
            self._progress_cache.pop(task_id, None)
            self._progress_cache_time.pop(task_id, None)
            return None
        return dict(cached)

    def _cleanup_expired_progress(self) -> None:
        now = time.time()
        expired = [
            tid for tid, t in self._progress_cache_time.items()
            if now - t > PROGRESS_HISTORY_TTL
        ]
        for tid in expired:
            self._progress_cache.pop(tid, None)
            self._progress_cache_time.pop(tid, None)

    async def send_progress(self, task_id: str, data: dict[str, Any]) -> None:
        self._save_progress(task_id, data)
        async with self._lock:
            connections = list(self._connections.get(task_id, []))
        disconnected: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning(f"[ws_manager] send_progress 发送失败 task_id={task_id}: {e}")
                disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(task_id, ws)

    async def send_final(self, task_id: str, data: dict[str, Any]) -> None:
        self._save_progress(task_id, data)
        async with self._lock:
            connections = list(self._connections.get(task_id, []))
        for ws in connections:
            try:
                try:
                    await ws.send_json(data)
                except Exception as e:
                    logger.warning(f"[ws_manager] send_final 发送消息失败 task_id={task_id}: {e}")
            finally:
                try:
                    await ws.close()
                except Exception as e:
                    logger.warning(f"[ws_manager] send_final 关闭连接失败 task_id={task_id}: {e}")
        async with self._lock:
            self._connections.pop(task_id, None)

    async def broadcast(self, data: dict[str, Any]) -> None:
        async with self._lock:
            all_connections = [(tid, ws) for tid, conns in self._connections.items() for ws in conns]
        disconnected: list[tuple[str, WebSocket]] = []
        for task_id, ws in all_connections:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning(f"[ws_manager] broadcast 发送失败 task_id={task_id}: {e}")
                disconnected.append((task_id, ws))
        for task_id, ws in disconnected:
            await self.disconnect(task_id, ws)

    async def broadcast_render_cache_update(self, task_id: str, files: list[dict]) -> None:
        message = {
            "type": "render_cache_updated",
            "task_id": task_id,
            "files": files,
        }
        async with self._lock:
            connections = list(self._connections.get(task_id, []))
        disconnected: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"[ws_manager] broadcast_render_cache_update 发送失败 task_id={task_id}: {e}")
                disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(task_id, ws)


ws_manager = ProgressWSManager()
