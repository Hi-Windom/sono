"""
Bug Digest Phase 2 - WebSocket & API Routes 深度挖掘测试

Bug 清单（共14个）：
======== 高严重程度 ========
BUG-001 [高] MessageBus stop() 队列满时无法放入 SENTINEL，工作线程无法停止
BUG-002 [高] MessageBus _dispatch 中 run_coroutine_threadsafe 的 Future 未检查，协程异常静默丢失
BUG-003 [高] WebSocket 路由中 send_json 异常未被捕获，导致未处理异常和连接泄漏
BUG-004 [高] /metrics/reset 端点无认证，可任意重置所有监控数据
BUG-005 [高] send_final 中直接 pop task_id 但 ws.close() 失败会导致连接资源泄漏

======== 中严重程度 ========
BUG-006 [中] MessageBus 队列满时直接丢弃消息，无重试机制
BUG-007 [中] WebSocket 无真正的心跳超时断开机制，半开连接会泄漏
BUG-008 [中] 前端 WebSocket 重连后会丢失中间进度消息
BUG-009 [中] 各 channel 消息格式不一致，缺少统一的消息信封
BUG-010 [中] /diag 端点泄漏大量系统敏感信息（无认证）

======== 低严重程度 ========
BUG-011 [低] /ws/cache-events 端点无认证，可任意连接监听缓存事件
BUG-012 [低] MessageBus 事件循环关闭后，publish 仍可入队，消息最终被静默丢弃
BUG-013 [低] render_cache_update 广播给所有连接，而非按 task_id 过滤
BUG-014 [低] /api/log 和 /api/v1/log 重复路由定义
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from services.message_bus import MessageBus, _SENTINEL
from services.ws_manager import ProgressWSManager


def _reset_message_bus_singleton():
    MessageBus._instance = None
    MessageBus._lock = threading.Lock()


@pytest.fixture(autouse=True)
def reset_singleton():
    _reset_message_bus_singleton()
    yield
    _reset_message_bus_singleton()


@pytest.fixture
def mock_ws_manager():
    with patch("services.message_bus.ws_manager") as mock:
        mock.send_progress = AsyncMock()
        mock.send_final = AsyncMock()
        mock.broadcast_render_cache_update = AsyncMock()
        yield mock


# ============================================================
# BUG-001 [高] MessageBus stop() 队列满时无法放入 SENTINEL
# ============================================================
class TestBug001StopWhenQueueFull:
    def test_stop_with_full_queue_cannot_put_sentinel(self):
        """队列满时，stop() 无法放入 SENTINEL，工作线程可能无法正常退出。

        复现步骤：
        1. 创建 maxsize=1 的 MessageBus
        2. 启动总线，放一条消息占满队列
        3. 调用 stop()，它会尝试 put_nowait(_SENTINEL)
        4. 由于队列满，put_nowait 抛出 queue.Full 被捕获并忽略
        5. 工作线程永远收不到 SENTINEL，只能依赖 timeout 轮询 _running 标志
        """
        bus = MessageBus(maxsize=1)
        bus._running = True
        bus._queue.put_nowait(("ws_progress", {"task_id": "t1"}))

        assert bus._queue.full()

        sentinel_put_success = False
        try:
            bus._queue.put_nowait(_SENTINEL)
            sentinel_put_success = True
        except queue.Full:
            sentinel_put_success = False

        assert sentinel_put_success is False, (
            "BUG-001 验证失败：队列满时 SENTINEL 应该放不进去，"
            "导致 stop() 无法可靠地通知工作线程退出"
        )

    def test_stop_relies_on_running_flag_when_sentinel_fails(self):
        """当 SENTINEL 投递失败时，stop() 仅依赖 _running 标志停止线程，
        这意味着工作线程最多需要等待 timeout=1.0 秒才能退出。"""
        loop = asyncio.new_event_loop()
        bus = MessageBus(maxsize=1)
        bus.set_loop(loop)

        try:
            bus.start()
            time.sleep(0.1)

            for _ in range(2):
                try:
                    bus._queue.put_nowait(("ws_progress", {"task_id": "t1"}))
                except queue.Full:
                    pass

            start = time.time()
            bus.stop()
            elapsed = time.time() - start

            assert bus._thread is None
        finally:
            loop.close()


# ============================================================
# BUG-002 [高] run_coroutine_threadsafe 的 Future 未检查，协程异常静默丢失
# ============================================================
class TestBug002FutureExceptionSilentlyDropped:
    def test_dispatch_coroutine_exception_not_captured(self, mock_ws_manager, caplog):
        """_dispatch 中调用 run_coroutine_threadsafe 后没有检查 Future 结果，
        如果协程内部抛出异常，异常会被静默吞掉，日志中不会体现。"""

        async def failing_coro(*args, **kwargs):
            raise RuntimeError("协程内部发生错误")

        mock_ws_manager.send_progress = failing_coro

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
            bus._running = True

            with caplog.at_level(logging.WARNING):
                bus._dispatch("ws_progress", {"task_id": "task-1", "progress": 50})
                time.sleep(0.3)

            found_exception_warning = any(
                "协程内部发生错误" in record.message or "RuntimeError" in record.message
                for record in caplog.records
            )

            assert found_exception_warning is False, (
                "BUG-002 验证预期：协程内部异常应该被静默吞掉，"
                "因为 run_coroutine_threadsafe 返回的 Future 没有被检查"
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            if loop_thread:
                loop_thread.join(timeout=2.0)
            loop.close()

    def test_run_coroutine_threadsafe_returns_future_not_checked(self):
        """验证 run_coroutine_threadsafe 返回的 Future 没有被 add_done_callback 或 await。"""
        import inspect
        source = inspect.getsource(MessageBus._dispatch)
        assert "run_coroutine_threadsafe(" in source
        assert "add_done_callback" not in source, (
            "如果有 add_done_callback 说明异常可能被处理了"
        )
        assert ".result()" not in source, (
            "如果有 .result() 说明 Future 结果被检查了"
        )


# ============================================================
# BUG-003 [高] WebSocket send_json 异常未被 WebSocketDisconnect 捕获
# ============================================================
class TestBug003WebSocketSendExceptionUnhandled:
    def test_send_json_exception_not_websocket_disconnect(self):
        """WebSocket 路由只捕获 WebSocketDisconnect，但 send_json() 失败时
        抛出的通常是 RuntimeError 或 ConnectionClosed 等其他异常，
        这些异常不会被捕获，会向上传播导致未处理异常。"""
        from fastapi import WebSocketDisconnect

        class FakeSendError(Exception):
            pass

        assert not issubclass(FakeSendError, WebSocketDisconnect)

        async def _test():
            ws_manager = ProgressWSManager()

            mock_ws1 = MagicMock()
            mock_ws1.send_json = AsyncMock(side_effect=FakeSendError("连接已断开"))

            await ws_manager.connect("task-1", mock_ws1)

            try:
                await ws_manager.send_progress("task-1", {"task_id": "task-1", "progress": 50})
            except FakeSendError:
                pytest.fail("send_progress 应该内部处理发送失败，不应抛出异常")

            assert len(ws_manager._connections.get("task-1", [])) == 0, (
                "发送失败的连接应该被清理掉"
            )

        asyncio.run(_test())

    def test_system_route_websocket_only_catches_disconnect(self):
        """验证 system.py 中的 WebSocket 路由只捕获了 WebSocketDisconnect。"""
        import inspect
        from api.routes import system

        source = inspect.getsource(system.websocket_task_status)
        assert "WebSocketDisconnect" in source

        catch_count = source.count("except WebSocketDisconnect:")
        assert catch_count >= 1

        general_catch_count = source.count("except Exception")
        assert general_catch_count == 0, (
            "BUG-003：如果没有通用的 Exception 捕获，"
            "send_json 失败时的非 WebSocketDisconnect 异常会泄漏"
        )


# ============================================================
# BUG-004 [高] /metrics/reset 端点无认证
# ============================================================
class TestBug004MetricsResetNoAuth:
    def test_metrics_reset_route_exists(self):
        """验证 /metrics/reset 路由存在。"""
        from api.routes.metrics import router

        routes = [r.path for r in router.routes]
        assert "/metrics/reset" in routes

    def test_metrics_reset_has_no_auth_dependency(self):
        """验证 /metrics/reset 没有认证依赖。"""
        import inspect
        from api.routes.metrics import router

        reset_route = None
        for route in router.routes:
            if route.path == "/metrics/reset":
                reset_route = route
                break

        assert reset_route is not None

        dependencies = getattr(reset_route, "dependencies", None)
        assert dependencies is None or len(dependencies) == 0, (
            "BUG-004：如果有 dependencies，可能有认证；否则无认证"
        )

    def test_all_metrics_endpoints_no_auth(self):
        """验证所有 metrics 端点都没有认证。"""
        from api.routes.metrics import router

        for route in router.routes:
            deps = getattr(route, "dependencies", None)
            assert deps is None or len(deps) == 0, (
                f"路由 {route.path} 不应该有认证依赖"
            )


# ============================================================
# BUG-005 [高] send_final 中 ws.close() 失败导致连接资源泄漏
# ============================================================
class TestBug005SendFinalCloseLeak:
    def test_send_final_pops_before_close(self):
        """send_final 中先 pop 了 task_id，再逐个关闭连接。
        如果 ws.close() 失败，虽然字典中已移除，但 ws 对象本身可能仍持有资源。"""

        async def _test():
            ws_manager = ProgressWSManager()

            mock_ws1 = MagicMock()
            mock_ws1.send_json = AsyncMock()
            mock_ws1.close = AsyncMock(side_effect=RuntimeError("关闭失败"))

            mock_ws2 = MagicMock()
            mock_ws2.send_json = AsyncMock()
            mock_ws2.close = AsyncMock()

            await ws_manager.connect("task-1", mock_ws1)
            await ws_manager.connect("task-1", mock_ws2)

            assert len(ws_manager._connections["task-1"]) == 2

            await ws_manager.send_final("task-1", {"task_id": "task-1", "status": "done"})

            assert "task-1" not in ws_manager._connections, (
                "send_final 应该从字典中移除 task_id"
            )

            assert mock_ws1.close.called
            assert mock_ws2.close.called

        asyncio.run(_test())

    def test_send_final_does_not_retry_close(self):
        """ws.close() 失败后没有重试或清理逻辑。"""

        async def _test():
            ws_manager = ProgressWSManager()

            mock_ws = MagicMock()
            mock_ws.send_json = AsyncMock()
            mock_ws.close = AsyncMock(side_effect=RuntimeError("关闭失败"))

            await ws_manager.connect("task-1", mock_ws)

            try:
                await ws_manager.send_final("task-1", {"task_id": "task-1", "status": "done"})
            except Exception:
                pytest.fail("send_final 不应该抛出异常")

            assert mock_ws.close.call_count == 1, (
                "close 失败后没有重试机制"
            )

        asyncio.run(_test())


# ============================================================
# BUG-006 [中] MessageBus 队列满时直接丢弃消息，无重试机制
# ============================================================
class TestBug006QueueFullDropsMessage:
    def test_publish_drops_when_queue_full(self, caplog):
        """队列满时 publish 直接丢弃消息，只记录 warning，没有重试。"""
        bus = MessageBus(maxsize=2)
        bus._running = True

        bus.publish("ws_progress", {"task_id": "1"})
        bus.publish("ws_progress", {"task_id": "2"})

        assert bus._queue.qsize() == 2

        with caplog.at_level(logging.WARNING):
            bus.publish("ws_progress", {"task_id": "3"})

        assert "队列已满" in caplog.text
        assert bus._queue.qsize() == 2, (
            "第三条消息被丢弃了，队列大小仍为2"
        )

    def test_no_retry_logic_in_publish(self):
        """验证 publish 中没有重试逻辑。"""
        import inspect
        source = inspect.getsource(MessageBus.publish)
        assert "retry" not in source.lower()
        assert "put_nowait" in source
        assert "put(" not in source, (
            "如果用的是阻塞式 put，说明可能有等待逻辑；但实际是 put_nowait"
        )


# ============================================================
# BUG-007 [中] WebSocket 无心跳超时断开机制，半开连接泄漏
# ============================================================
class TestBug007NoHeartbeatTimeout:
    def test_ws_manager_has_no_heartbeat_tracking(self):
        """ProgressWSManager 没有记录最后活动时间，没有超时断开机制。"""
        ws_manager = ProgressWSManager()

        assert not hasattr(ws_manager, "_last_activity")
        assert not hasattr(ws_manager, "_timeout")
        assert not hasattr(ws_manager, "_heartbeat_task")

    def test_system_ws_route_heartbeat_is_client_driven(self):
        """system.py 中的 WebSocket 心跳是等待客户端消息超时后服务端发心跳，
        但如果客户端半开连接（网络断了但TCP没断），receive_text 不会返回，
        需要等TCP超时（可能几十秒到几分钟）才能发现。"""
        import inspect
        from api.routes import system

        source = inspect.getsource(system.websocket_task_status)

        assert "wait_for(websocket.receive_text()" in source
        assert "heartbeat" in source

        assert "ping" not in source.lower() or "pong" not in source.lower(), (
            "如果有 ping/pong 机制，说明有正确的心跳检测"
        )

    def test_cache_events_ws_route_no_heartbeat_timeout_disconnect(self):
        """cache.py 中的 /ws/cache-events 同样没有真正的心跳超时断开。"""
        import inspect
        from api.routes import cache

        source = inspect.getsource(cache.websocket_cache_events)

        assert "wait_for(websocket.receive_text()" in source
        assert "heartbeat" in source
        assert "close()" not in source.split("except asyncio.TimeoutError:")[1].split("except WebSocketDisconnect:")[0], (
            "超时后只发心跳，不断开连接"
        )


# ============================================================
# BUG-008 [中] WebSocket 重连后丢失中间消息
# ============================================================
class TestBug008ReconnectLosesMessages:
    def test_no_message_history_for_reconnect(self):
        """ws_manager 没有消息历史存储，新连接只能收到之后的消息。"""
        ws_manager = ProgressWSManager()

        assert not hasattr(ws_manager, "_message_history")
        assert not hasattr(ws_manager, "_history")
        assert not hasattr(ws_manager, "_last_messages")

    def test_connect_does_not_send_historical_messages(self):
        """connect() 方法只添加连接，不发送任何历史消息。"""

        async def _test():
            ws_manager = ProgressWSManager()

            mock_ws = MagicMock()
            mock_ws.send_json = AsyncMock()

            await ws_manager.connect("task-1", mock_ws)

            assert mock_ws.send_json.call_count == 0, (
                "connect 时没有发送任何历史/当前状态消息"
            )

        asyncio.run(_test())

    def test_system_route_sends_only_current_state_on_connect(self):
        """system.py 中的 WebSocket 路由连接时只发送当前状态，
        没有重放历史进度的机制。"""
        import inspect
        from api.routes import system

        source = inspect.getsource(system.websocket_task_status)

        assert "await websocket.accept()" in source
        assert "get_task(task_id)" in source

        history_indicators = ["history", "replay", "missed", "since"]
        found_history = any(h in source.lower() for h in history_indicators)
        assert not found_history, (
            "如果有历史消息重放机制，应该能找到相关关键词"
        )


# ============================================================
# BUG-009 [中] 各 channel 消息格式不一致
# ============================================================
class TestBug009InconsistentMessageFormat:
    def test_ws_progress_passes_raw_data(self):
        """ws_progress channel 直接将 data 传给 send_progress。"""
        import inspect
        source = inspect.getsource(MessageBus._dispatch)

        assert 'channel == "ws_progress"' in source
        assert 'ws_manager.send_progress(task_id, data)' in source

    def test_ws_final_passes_raw_data(self):
        """ws_final channel 直接将 data 传给 send_final。"""
        import inspect
        source = inspect.getsource(MessageBus._dispatch)

        assert 'channel == "ws_final"' in source
        assert 'ws_manager.send_final(task_id, data)' in source

    def test_render_cache_update_wraps_in_envelope(self):
        """render_cache_update channel 自己构造了带 type 字段的消息信封。"""
        import inspect
        from services.ws_manager import ProgressWSManager

        source = inspect.getsource(ProgressWSManager.broadcast_render_cache_update)

        assert '"type": "render_cache_updated"' in source
        assert '"task_id": task_id' in source
        assert '"files": files' in source

    def test_message_format_inconsistency(self):
        """对比三种 channel 的消息格式：
        - ws_progress / ws_final: 直接透传 data，没有统一的 type 字段
        - render_cache_update: 有 type 字段
        这导致客户端需要用不同逻辑解析不同类型的消息。"""
        from services.message_bus import publish_ws_progress, publish_ws_final, publish_render_cache_update

        import inspect
        src_progress = inspect.getsource(publish_ws_progress)
        src_final = inspect.getsource(publish_ws_final)
        src_cache = inspect.getsource(publish_render_cache_update)

        assert 'payload.setdefault("task_id", task_id)' in src_progress
        assert 'payload.setdefault("task_id", task_id)' in src_final
        assert '"task_id": task_id' in src_cache
        assert '"files": files' in src_cache

        assert '"type"' not in src_progress
        assert '"type"' not in src_final


# ============================================================
# BUG-010 [中] /diag 端点泄漏大量系统敏感信息
# ============================================================
class TestBug010DiagEndpointLeakSensitiveInfo:
    def test_diag_endpoint_exists(self):
        """验证 /diag 端点存在。"""
        from api.routes.system import router

        routes = [r.path for r in router.routes]
        assert "/diag" in routes

    def test_diag_endpoint_no_auth(self):
        """验证 /diag 端点没有认证。"""
        from api.routes.system import router

        diag_route = None
        for route in router.routes:
            if route.path == "/diag":
                diag_route = route
                break

        assert diag_route is not None
        deps = getattr(diag_route, "dependencies", None)
        assert deps is None or len(deps) == 0

    def test_diag_returns_sensitive_system_info(self):
        """/diag 端点返回大量敏感系统信息。"""
        import inspect
        from api.routes import system

        source = inspect.getsource(system.diagnostics)

        sensitive_fields = [
            "memory_info",
            "storage_info",
            "gpu_info",
            "system",
            "process",
            "directories",
            "cpu_percent",
            "memory_mb",
            "pid",
            "hostname",
        ]

        found_sensitive = [f for f in sensitive_fields if f in source]
        assert len(found_sensitive) >= 5, (
            f"diag 端点返回了 {len(found_sensitive)} 类敏感信息字段"
        )


# ============================================================
# BUG-011 [低] /ws/cache-events 端点无认证
# ============================================================
class TestBug011CacheEventsWsNoAuth:
    def test_cache_events_websocket_exists(self):
        """验证 /ws/cache-events WebSocket 路由存在。"""
        from api.routes.cache import router

        routes = [r.path for r in router.routes]
        assert "/ws/cache-events" in routes

    def test_cache_events_ws_no_auth(self):
        """验证 /ws/cache-events 没有认证。"""
        from api.routes.cache import router

        ws_route = None
        for route in router.routes:
            if route.path == "/ws/cache-events":
                ws_route = route
                break

        assert ws_route is not None
        deps = getattr(ws_route, "dependencies", None)
        assert deps is None or len(deps) == 0

    def test_cache_events_accepts_any_connection(self):
        """cache-events WebSocket 直接 accept，不验证任何 token 或身份。"""
        import inspect
        from api.routes import cache

        source = inspect.getsource(cache.websocket_cache_events)

        assert "await websocket.accept()" in source

        auth_indicators = ["token", "auth", "apikey", "verify", "validate"]
        found_auth = any(a in source.lower() for a in auth_indicators)
        assert not found_auth, (
            "如果有认证逻辑，应该能找到相关关键词"
        )


# ============================================================
# BUG-012 [低] 事件循环关闭后 publish 仍可入队
# ============================================================
class TestBug012PublishAfterLoopClosed:
    def test_publish_does_not_check_loop_status(self, caplog):
        """publish() 只检查 _running，不检查 loop 是否关闭。
        消息会入队，但 _dispatch 时才发现 loop 已关闭，消息被丢弃。"""
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        bus.set_loop(loop)
        bus._running = True

        loop.close()

        bus.publish("ws_progress", {"task_id": "t1"})

        assert bus._queue.qsize() == 1, (
            "消息成功入队了，尽管 loop 已经关闭"
        )

        with caplog.at_level(logging.WARNING):
            bus._dispatch("ws_progress", {"task_id": "t1"})

        assert "事件循环已关闭" in caplog.text

    def test_publish_only_checks_running_flag(self):
        """验证 publish 只检查 _running，不检查 loop。"""
        import inspect
        source = inspect.getsource(MessageBus.publish)

        assert "self._running" in source
        assert "_loop" not in source or "is_closed" not in source, (
            "如果 publish 中检查了 loop 状态，就不会有这个问题"
        )


# ============================================================
# BUG-013 [低] render_cache_update 广播给所有连接
# ============================================================
class TestBug013RenderCacheBroadcastToAll:
    def test_broadcast_render_cache_sends_to_all_tasks(self):
        """broadcast_render_cache_update 调用 broadcast，发给所有连接，
        而不是只发给特定 task_id 的连接。"""

        async def _test():
            ws_manager = ProgressWSManager()

            mock_ws1 = MagicMock()
            mock_ws1.send_json = AsyncMock()
            mock_ws2 = MagicMock()
            mock_ws2.send_json = AsyncMock()

            await ws_manager.connect("task-A", mock_ws1)
            await ws_manager.connect("task-B", mock_ws2)

            await ws_manager.broadcast_render_cache_update("task-A", [{"name": "out.wav"}])

            assert mock_ws1.send_json.called
            assert mock_ws2.send_json.called, (
                "BUG-013：render_cache_update 应该只发给 task-A 的连接，"
                "但实际发给了所有连接（包括 task-B）"
            )

        asyncio.run(_test())

    def test_dispatch_uses_broadcast_not_send(self):
        """验证 message_bus 中 render_cache_update 使用的是 broadcast 方法。"""
        import inspect
        source = inspect.getsource(MessageBus._dispatch)

        assert "broadcast_render_cache_update" in source
        assert "send_progress" in source
        assert "send_final" in source

        from services.ws_manager import ProgressWSManager
        src_broadcast = inspect.getsource(ProgressWSManager.broadcast_render_cache_update)
        assert "self.broadcast(message)" in src_broadcast


# ============================================================
# BUG-014 [低] /api/log 和 /api/v1/log 重复路由
# ============================================================
class TestBug014DuplicateLogRoutes:
    def test_app_level_log_route(self):
        """app.py 中有 /api/log 路由。"""
        import inspect
        from app import create_app

        source = inspect.getsource(create_app)
        assert '@app.post("/api/log")' in source or '"/api/log"' in source

    def test_system_level_log_route(self):
        """system.py 中有 /log 路由（会变成 /api/v1/log）。"""
        from api.routes.system import router

        routes = [r.path for r in router.routes]
        assert "/log" in routes

    def test_duplicate_log_routes_both_exist(self):
        """验证存在两个功能相同的日志接口：
        - /api/log (app 级)
        - /api/v1/log (system 路由，带 v1 前缀)"""
        import inspect
        from api.routes import system
        from app import create_app

        sys_source = inspect.getsource(system.log_message)
        app_source = inspect.getsource(create_app)

        assert 'logger.error(request.message)' in sys_source
        assert 'logger.error(request.message)' in app_source or 'logger.error(request.message)' in app_source

        assert "level == \"error\"" in sys_source
        assert "level == \"error\"" in app_source or "level == \"error\"" in app_source
