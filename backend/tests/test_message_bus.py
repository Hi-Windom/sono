from __future__ import annotations

import asyncio
import logging
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from services.message_bus import MessageBus, _SENTINEL


def _reset_singleton():
    MessageBus._instance = None
    MessageBus._lock = threading.Lock()


@pytest.fixture(autouse=True)
def reset_singleton():
    _reset_singleton()
    yield
    _reset_singleton()


@pytest.fixture
def mock_ws_manager():
    with patch("services.message_bus.ws_manager") as mock:
        mock.send_progress = MagicMock()
        mock.send_final = MagicMock()
        mock.broadcast_render_cache_update = MagicMock()
        yield mock


class TestMessageBusSingleton:
    def test_singleton_instance(self):
        bus1 = MessageBus()
        bus2 = MessageBus()
        assert bus1 is bus2

    def test_singleton_thread_safety(self):
        instances = []

        def create_instance():
            instances.append(MessageBus())

        threads = [threading.Thread(target=create_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(inst is instances[0] for inst in instances)
        assert len(set(id(i) for i in instances)) == 1


class TestMessageBusLifecycle:
    def test_start_and_stop(self):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        try:
            assert bus._running is False
            bus.start()
            assert bus._running is True
            assert bus._thread is not None
            assert bus._thread.is_alive()
            bus.stop()
            assert bus._running is False
            assert bus._thread is None
        finally:
            loop.close()

    def test_double_start_no_error(self):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        try:
            bus.start()
            thread_id = id(bus._thread)
            bus.start()
            assert id(bus._thread) == thread_id
            bus.stop()
        finally:
            loop.close()

    def test_stop_before_start_no_error(self):
        bus = MessageBus()
        bus.stop()
        assert bus._running is False

    def test_set_loop(self):
        loop = asyncio.new_event_loop()
        try:
            bus = MessageBus()
            assert bus._loop is None
            bus.set_loop(loop)
            assert bus._loop is loop
        finally:
            loop.close()


class TestMessageBusPublish:
    def test_publish_ws_progress_dispatched(self, mock_ws_manager):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus.start()
        try:
            bus.publish("ws_progress", {"task_id": "task-1", "progress": 50})
            time.sleep(0.2)
        finally:
            bus.stop()
            loop.close()

    def test_publish_ws_final_dispatched(self, mock_ws_manager):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus.start()
        try:
            bus.publish("ws_final", {"task_id": "task-1", "status": "done"})
            time.sleep(0.2)
        finally:
            bus.stop()
            loop.close()

    def test_publish_render_cache_update_dispatched(self, mock_ws_manager):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus.start()
        try:
            bus.publish("render_cache_update", {"task_id": "task-1", "files": [{"name": "a.wav"}]})
            time.sleep(0.2)
        finally:
            bus.stop()
            loop.close()

    def test_publish_when_not_started_logs_warning(self, caplog):
        bus = MessageBus()
        with caplog.at_level(logging.WARNING):
            bus.publish("ws_progress", {"task_id": "t1"})
        assert "消息总线未启动" in caplog.text


class TestMessageBusNoLoop:
    def test_dispatch_without_loop_logs_warning(self, caplog):
        bus = MessageBus()
        bus._running = True
        with caplog.at_level(logging.WARNING):
            bus._dispatch("ws_progress", {"task_id": "t1"})
        assert "事件循环未设置" in caplog.text

    def test_dispatch_with_closed_loop_logs_warning(self, caplog):
        bus = MessageBus()
        loop = asyncio.new_event_loop()
        loop.close()
        bus.set_loop(loop)
        bus._running = True
        with caplog.at_level(logging.WARNING):
            bus._dispatch("ws_progress", {"task_id": "t1"})
        assert "事件循环已关闭" in caplog.text


class TestMessageBusQueueFull:
    def test_queue_full_drops_message(self, caplog):
        bus = MessageBus(maxsize=1)
        bus._running = True
        bus.publish("ws_progress", {"task_id": "1"})
        with caplog.at_level(logging.WARNING):
            bus.publish("ws_progress", {"task_id": "2"})
        assert "队列已满" in caplog.text

    def test_queue_size_zero_unbounded(self):
        bus = MessageBus(maxsize=0)
        bus._running = True
        for i in range(100):
            bus.publish("ws_progress", {"task_id": f"task-{i}"})
        assert bus._queue.qsize() == 100


class TestMessageBusConcurrency:
    def test_multithreaded_publish(self, mock_ws_manager):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus.start()
        try:
            num_threads = 5
            msgs_per_thread = 20
            errors = []

            def publisher(thread_id: int):
                try:
                    for i in range(msgs_per_thread):
                        bus.publish("ws_progress", {"task_id": f"thread-{thread_id}", "index": i})
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=publisher, args=(i,)) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
            time.sleep(0.3)
        finally:
            bus.stop()
            loop.close()


class TestConvenienceFunctions:
    def test_publish_ws_progress_func(self, mock_ws_manager):
        from services.message_bus import publish_ws_progress

        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus.start()
        try:
            publish_ws_progress("task-42", {"progress": 75})
            time.sleep(0.2)
        finally:
            bus.stop()
            loop.close()

    def test_publish_ws_final_func(self, mock_ws_manager):
        from services.message_bus import publish_ws_final

        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus.start()
        try:
            publish_ws_final("task-42", {"status": "completed"})
            time.sleep(0.2)
        finally:
            bus.stop()
            loop.close()

    def test_publish_render_cache_update_func(self, mock_ws_manager):
        from services.message_bus import publish_render_cache_update

        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus.start()
        try:
            files = [{"name": "out.wav", "size": 1024}]
            publish_render_cache_update("task-42", files)
            time.sleep(0.2)
        finally:
            bus.stop()
            loop.close()


class TestMessageBusUnknownChannel:
    def test_unknown_channel_logs_warning(self, caplog):
        loop = asyncio.new_event_loop()
        try:
            bus = MessageBus()
            bus.set_loop(loop)
            with caplog.at_level(logging.WARNING):
                bus._dispatch("unknown_channel", {"task_id": "t1"})
            assert "未知 channel" in caplog.text
        finally:
            loop.close()


class TestMessageBusWithRunningLoop:
    def test_run_coroutine_threadsafe_executes(self, mock_ws_manager):
        result_event = threading.Event()
        result_holder = {"called": False}

        async def mock_send(task_id, data):
            result_holder["called"] = True
            result_holder["task_id"] = task_id
            result_holder["data"] = data
            result_event.set()

        mock_ws_manager.send_progress = mock_send

        loop = asyncio.new_event_loop()
        loop_thread = None

        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        try:
            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()
            time.sleep(0.1)

            bus = MessageBus()
            bus.set_loop(loop)
            bus.start()

            bus.publish("ws_progress", {"task_id": "task-123", "progress": 42})

            assert result_event.wait(timeout=2.0), "协程未在超时时间内执行"
            assert result_holder["called"] is True
            assert result_holder["task_id"] == "task-123"

            bus.stop()
        finally:
            loop.call_soon_threadsafe(loop.stop)
            if loop_thread:
                loop_thread.join(timeout=2.0)
            loop.close()
