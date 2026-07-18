from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any

from services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

_SENTINEL = object()
DEFAULT_MAXSIZE = 10000
_PUBLISH_RETRY_TIMEOUT = 2.0
_IMPORTANT_CHANNELS = {"ws_final"}


def _wrap_envelope(channel: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": channel,
        "channel": channel,
        "timestamp": time.time(),
        "data": data,
    }


class MessageBus:
    _instance: MessageBus | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, maxsize: int = DEFAULT_MAXSIZE) -> MessageBus:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running: bool = False
        self._stopped: bool = False
        self._maxsize: int = maxsize
        self._stop_event: threading.Event = threading.Event()
        self._dropped_count: int = 0

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        logger.debug("[MessageBus] 事件循环已设置")

    def start(self) -> None:
        if self._running:
            logger.warning("[MessageBus] 已在运行中，忽略重复启动")
            return
        if self._thread is not None and self._thread.is_alive():
            logger.warning("[MessageBus] 投递线程仍在运行，先等待其退出")
            self.stop()
        self._running = True
        self._stopped = False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, name="MessageBus-Worker", daemon=True)
        self._thread.start()
        logger.debug("[MessageBus] 投递线程已启动")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stopped = True
        self._stop_event.set()
        try:
            self._queue.put_nowait(_SENTINEL)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("[MessageBus] 投递线程在超时时间内未退出")
            self._thread = None
        logger.debug("[MessageBus] 投递线程已停止")

    def publish(self, channel: str, data: dict[str, Any]) -> bool:
        if not self._running:
            if self._stopped:
                logger.warning(f"[MessageBus] 消息总线已停止，拒绝消息 channel={channel}")
            else:
                logger.warning(f"[MessageBus] 消息总线未启动，拒绝消息 channel={channel}")
            return False
        if self._loop is not None and self._loop.is_closed():
            logger.warning(f"[MessageBus] 事件循环已关闭，拒绝消息 channel={channel}")
            return False
        envelope = _wrap_envelope(channel, data)
        is_important = channel in _IMPORTANT_CHANNELS
        try:
            if is_important:
                self._queue.put((channel, envelope), timeout=_PUBLISH_RETRY_TIMEOUT)
            else:
                self._queue.put_nowait((channel, envelope))
            return True
        except queue.Full:
            if is_important:
                logger.error(
                    f"[MessageBus] 重要消息入队超时（{_PUBLISH_RETRY_TIMEOUT}s），丢弃 channel={channel}, "
                    f"maxsize={self._maxsize}, dropped_total={self._dropped_count}"
                )
            else:
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait((channel, envelope))
                    self._dropped_count += 1
                    logger.warning(
                        f"[MessageBus] 队列已满，丢弃最老消息并加入新消息 channel={channel}, "
                        f"maxsize={self._maxsize}, dropped_total={self._dropped_count}"
                    )
                    return True
                except (queue.Empty, queue.Full):
                    self._dropped_count += 1
                    logger.warning(
                        f"[MessageBus] 队列操作失败，丢弃消息 channel={channel}, "
                        f"maxsize={self._maxsize}, dropped_total={self._dropped_count}"
                    )
            return False

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if item is _SENTINEL or self._stop_event.is_set():
                break
            channel, data = item
            try:
                self._dispatch(channel, data)
            except Exception as e:
                logger.warning(f"[MessageBus] 分发消息失败 channel={channel}: {e}")

    def _dispatch(self, channel: str, envelope: dict[str, Any]) -> None:
        if self._loop is None:
            logger.warning(f"[MessageBus] 事件循环未设置，无法投递消息 channel={channel}")
            return
        if self._loop.is_closed():
            logger.warning(f"[MessageBus] 事件循环已关闭，无法投递消息 channel={channel}")
            return

        data = envelope.get("data", envelope)

        def _on_future_done(fut: Future, ch: str, tid: str) -> None:
            try:
                exc = fut.exception()
                if exc is not None:
                    logger.warning(
                        f"[MessageBus] 协程执行异常 channel={ch}, task_id={tid}: {exc}"
                    )
            except Exception as e:
                logger.warning(
                    f"[MessageBus] 获取协程异常失败 channel={ch}, task_id={tid}: {e}"
                )

        try:
            if channel == "ws_progress":
                task_id = data.get("task_id", "")
                fut = asyncio.run_coroutine_threadsafe(
                    ws_manager.send_progress(task_id, data),
                    self._loop,
                )
                fut.add_done_callback(lambda f, ch=channel, tid=task_id: _on_future_done(f, ch, tid))
            elif channel == "ws_final":
                task_id = data.get("task_id", "")
                fut = asyncio.run_coroutine_threadsafe(
                    ws_manager.send_final(task_id, data),
                    self._loop,
                )
                fut.add_done_callback(lambda f, ch=channel, tid=task_id: _on_future_done(f, ch, tid))
            elif channel == "render_cache_update":
                task_id = data.get("task_id", "")
                files = data.get("files", [])
                fut = asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast_render_cache_update(task_id, files),
                    self._loop,
                )
                fut.add_done_callback(lambda f, ch=channel, tid=task_id: _on_future_done(f, ch, tid))
            else:
                logger.warning(f"[MessageBus] 未知 channel: {channel}")
        except Exception as e:
            logger.warning(f"[MessageBus] run_coroutine_threadsafe 失败 channel={channel}: {e}")


_message_bus = MessageBus()


def get_message_bus() -> MessageBus:
    return _message_bus


def publish_ws_progress(task_id: str, data: dict[str, Any]) -> None:
    payload = dict(data)
    payload.setdefault("task_id", task_id)
    _message_bus.publish("ws_progress", payload)


def publish_ws_final(task_id: str, data: dict[str, Any]) -> None:
    payload = dict(data)
    payload.setdefault("task_id", task_id)
    _message_bus.publish("ws_final", payload)


def publish_render_cache_update(task_id: str, files: list[dict]) -> None:
    _message_bus.publish("render_cache_update", {"task_id": task_id, "files": files})
