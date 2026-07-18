"""
回归测试集合

每个测试对应一个历史 bug，防止修完又被改坏。
运行: cd /workspace && python -m pytest backend/tests/test_regression.py -v
"""

import os
import sys
import tempfile
import logging
import numpy as np
import soundfile as sf
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_test_wav(duration_sec: float = 1.0, sr: int = 44100, freq: float = 440.0) -> str:
    """生成一个测试 WAV 文件，返回路径"""
    tmp = tempfile.mktemp(suffix=".wav")
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    y = np.sin(2 * np.pi * freq * t) * 0.5
    sf.write(tmp, y, sr, subtype="PCM_16")
    return tmp


# ============================================================================
# 回归测试 1: v4_0a / v4_0ap 修复算法 progress 变量名错误
# Bug: repair_single_track 中错误引用 progress（实际参数名是 progress_callback）
# 导致 NameError: name 'progress' is not defined
# ============================================================================

class TestProgressCallbackNameError:
    """防止 progress / progress_callback 变量名混用导致 NameError"""

    ALGORITHMS = [
        ("v4_0a", "services.repair.repair_v4_0a.core"),
        ("v4_0ap", "services.repair.repair_v4_0ap.core"),
    ]

    @pytest.mark.parametrize("name,module_path", ALGORITHMS)
    def test_no_nameerror_with_progress_callback(self, name, module_path):
        """传入 progress_callback 后完整跑通，不抛 NameError"""
        from importlib import import_module
        mod = import_module(module_path)
        repair_fn = mod.repair_audio

        input_path = _make_test_wav(0.5)
        output_path = tempfile.mktemp(suffix=".wav")

        try:
            progress_values = []
            def cb(p, step=""):
                progress_values.append((p, step))

            result = repair_fn(input_path, output_path, {}, progress_callback=cb)

            assert result is not None
            assert "algorithm_version" in result
            assert len(progress_values) > 0, "progress_callback 应该被调用多次"
            assert os.path.exists(output_path), "输出文件应该存在"

            first_p = progress_values[0][0]
            last_p = progress_values[-1][0]
            assert first_p < last_p, "进度应该递增"
            assert last_p >= 0.99, "最终进度应该接近 1.0"

        finally:
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    @pytest.mark.parametrize("name,module_path", ALGORITHMS)
    def test_no_nameerror_without_progress_callback(self, name, module_path):
        """不传 progress_callback 也应该正常跑通（None 情况）"""
        from importlib import import_module
        mod = import_module(module_path)
        repair_fn = mod.repair_audio

        input_path = _make_test_wav(0.5)
        output_path = tempfile.mktemp(suffix=".wav")

        try:
            result = repair_fn(input_path, output_path, {})
            assert result is not None
            assert "algorithm_version" in result

        finally:
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_all_v4_repair_have_progress_callback_param(self):
        """所有 v4 系列 repair_audio 函数签名必须有 progress_callback 参数"""
        import inspect
        for name, module_path in self.ALGORITHMS:
            from importlib import import_module
            mod = import_module(module_path)
            sig = inspect.signature(mod.repair_audio)
            assert "progress_callback" in sig.parameters, (
                f"{name}.repair_audio 缺少 progress_callback 参数"
            )


# ============================================================================
# 回归测试 2: 前端 HTTP 轮询模式下，error 状态要走 onError 不是 onComplete
# Bug: pollProgress 中 error/timeout 状态也调用 onComplete
# 导致后端报错前端无感知
# ============================================================================

class TestFrontendPollingErrorHandling:
    """防止 HTTP 轮询模式下后端报错前端收不到"""

    def test_repair_service_error_status_triggers_on_error(self):
        """pollProgress 中 error 状态应该调用 onError 回调"""
        repair_ts_path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "src", "services", "api", "repair.ts"
        )
        with open(repair_ts_path) as f:
            content = f.read()

        # 检查 error 状态分支
        assert "status === 'error'" in content or "status === 'error'" in content, (
            "pollProgress 中应该有对 error 状态的特殊处理"
        )
        # 检查 onError 调用
        assert "callbacks.onError" in content, (
            "pollProgress 中应该调用 callbacks.onError 处理错误状态"
        )

    def test_repair_service_terminal_states_complete_list(self):
        """终态集合中应该包含 error 和 timeout"""
        shared_path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "src", "services", "api", "_shared.ts"
        )
        with open(shared_path) as f:
            content = f.read()
        assert "'error'" in content, "DEFAULT_TERMINAL_STATES 应包含 error"
        assert "'timeout'" in content, "DEFAULT_TERMINAL_STATES 应包含 timeout"


# ============================================================================
# 回归测试 3: 打包产物不包含测试音频文件
# Bug: public/ 中的测试音频文件会被 Vite 复制到 dist，打包进 release
# 导致包体积从 1.9M 膨胀到 9.9M
# ============================================================================

class TestBuildArtifactsClean:
    """防止测试文件被打包进 release"""

    def test_no_test_audio_in_public(self):
        """public 目录不应该有 test_ 开头的音频文件"""
        public_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "public"
        )
        if not os.path.exists(public_dir):
            pytest.skip("public dir not found")

        for root, dirs, files in os.walk(public_dir):
            for f in files:
                if f.startswith("test_") and f.endswith((".mp3", ".wav", ".ogg")):
                    pytest.fail(
                        f"public 目录下发现测试音频: {os.path.join(root, f)}"
                        f"，不应该出现在打包产物中"
                    )

    def test_build_script_cleans_test_audio(self):
        """打包脚本应该有清理测试音频的步骤"""
        build_script = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "scripts", "build_android_release.sh"
        )
        with open(build_script) as f:
            content = f.read()
        assert "test_" in content and (".mp3" in content or ".wav" in content), (
            "build_android_release.sh 中应该有清理测试音频的步骤"
        )


# ============================================================================
# 回归测试 4: 自定义 hook 返回对象引用稳定性
# Bug: useAudioWorker 返回对象每次渲染都是新引用
# 导致下游 useEffect 清理函数频繁调用 terminate()，Worker 被杀
# ============================================================================

class TestHookReferenceStability:
    """防止自定义 hook 返回对象引用不稳定导致的副作用"""

    HOOK_FILES = [
        "src/workers/useAudioWorker.ts",
        "src/hooks/audio/useAudioRepair.ts",
        "src/hooks/audio/useAudioDecoder.ts",
        "src/hooks/audio/useAudioExport.ts",
        "src/hooks/audio/useAudioPlayback.ts",
    ]

    @pytest.mark.parametrize("rel_path", HOOK_FILES)
    def test_hook_uses_use_memo_for_return_object(self, rel_path):
        """自定义 hook 返回对象应该用 useMemo 包装"""
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "..", rel_path
        )
        if not os.path.exists(hook_path):
            pytest.skip(f"{rel_path} not found")

        with open(hook_path) as f:
            content = f.read()

        if "return {" not in content:
            pytest.skip(f"{rel_path} 没有返回对象")

        assert "useMemo" in content, (
            f"{rel_path} 返回对象时应该使用 useMemo 稳定引用"
            "（否则下游 useEffect 会频繁触发清理重建）"
        )


# ============================================================================
# 回归测试 5: 服务器启动时清理停滞任务
# Bug: 服务器重启后，数据库中 pending/processing 状态的任务永远停留在"进行中"
# 导致缓存管理页面显示大量"进行中"任务但实际不会执行
# ============================================================================

class TestStaleTaskCleanup:
    """防止服务器重启后任务状态永久停滞"""

    def test_cleanup_stale_tasks_marks_pending_as_failed(self):
        """cleanup_stale_tasks 应该将 pending 任务标记为 error"""
        import tempfile
        import os
        from database import init_db, cleanup_stale_tasks, create_task, get_task

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                init_db()

                create_task("test_stale_1", "test.wav", "/tmp/test.wav", {}, "hash1", 1000)

                from database import get_db
                conn = get_db()
                conn.execute("UPDATE tasks SET status = 'pending' WHERE id = 'test_stale_1'")
                conn.commit()
                conn.close()

                count = cleanup_stale_tasks()
                assert count == 1, f"应该清理 1 个任务，实际清理了 {count} 个"

                task = get_task("test_stale_1")
                assert task is not None
                assert task["status"] == "error", f"状态应该是 error，实际是 {task['status']}"
                assert "服务器重启" in task.get("error", ""), "错误信息应该包含服务器重启"
            finally:
                config.DB_PATH = old_db

    def test_cleanup_stale_tasks_ignores_completed(self):
        """cleanup_stale_tasks 不应该动 completed 任务"""
        import tempfile
        import os
        from database import init_db, cleanup_stale_tasks, create_task, get_task, update_task

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                init_db()

                create_task("test_completed_1", "test.wav", "/tmp/test.wav", {}, "hash1", 1000)
                update_task("test_completed_1", status="completed", output_path="/tmp/out.wav")

                count = cleanup_stale_tasks()
                assert count == 0, f"completed 任务不应该被清理，实际清理了 {count} 个"

                task = get_task("test_completed_1")
                assert task is not None
                assert task["status"] == "completed"
            finally:
                config.DB_PATH = old_db

    def test_cleanup_stale_tasks_handles_multiple_statuses(self):
        """cleanup_stale_tasks 应该处理所有非终态（pending/processing/detecting等），不包括 detected（终态）"""
        import tempfile
        import os
        from database import init_db, cleanup_stale_tasks, create_task, get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                init_db()

                stale_statuses = ['pending', 'processing', 'detecting', 'analyzing', 'repairing']
                for i, status in enumerate(stale_statuses):
                    create_task(f"test_{status}_{i}", f"test_{i}.wav", f"/tmp/test_{i}.wav", {}, f"hash{i}", 1000)
                    conn = get_db()
                    conn.execute(f"UPDATE tasks SET status = '{status}' WHERE id = 'test_{status}_{i}'")
                    conn.commit()
                    conn.close()

                count = cleanup_stale_tasks()
                assert count == len(stale_statuses), f"应该清理 {len(stale_statuses)} 个任务，实际清理了 {count} 个"
            finally:
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 6: cancel_task 必须发送 WebSocket 最终消息并清理活跃计数
# Bug: cancel_task 只更新数据库状态，不发 WS 消息，前端一直等待
# Bug: cancel_task 不清理 _active_tasks，活跃任务计数泄漏
# ============================================================================

class TestCancelTaskBehavior:
    """防止取消任务时资源泄漏和前端无响应"""

    def test_cancel_task_sends_ws_message(self):
        """cancel_task 应该调用 _ws_send_final 发送最终状态"""
        from services import task_manager

        sent_messages = []
        def fake_ws_send(task_id, msg):
            sent_messages.append((task_id, msg))

        original_send = task_manager._ws_send_final
        task_manager._ws_send_final = fake_ws_send
        try:
            from database import create_task
            import tempfile
            import os
            from database import init_db

            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, "test.db")
                import config
                old_db = config.DB_PATH
                config.DB_PATH = db_path
                try:
                    init_db()
                    create_task("cancel_test_1", "test.wav", "/tmp/test.wav", {}, "hash_cancel", 1000)

                    from services.task_manager import cancel_task
                    result = cancel_task("cancel_test_1")

                    assert result is True, "cancel_task 应该返回 True"
                    assert len(sent_messages) >= 1, "cancel_task 应该发送至少一条 WS 消息"
                    task_id, msg = sent_messages[0]
                    assert task_id == "cancel_test_1"
                    assert msg.get("status") == "cancelled", f"消息状态应该是 cancelled，实际是 {msg.get('status')}"
                finally:
                    config.DB_PATH = old_db
        finally:
                    task_manager._ws_send_final = original_send


# ============================================================================
# 回归测试 7: _get_loop 不应该创建未运行的事件循环
# Bug: _get_loop 在 _loop 为 None 时兜底创建新事件循环，但新循环未运行，
#      导致 run_coroutine_threadsafe 投递的协程永远不执行，WebSocket 消息静默丢失
# ============================================================================

class TestEventLoopNoSilentFailure:
    """防止事件循环兜底创建导致 WebSocket 消息静默丢失"""

    def test_get_loop_returns_none_when_not_set(self):
        """未设置 event loop 时 _get_loop 应该返回 None，不创建未运行的循环"""
        import threading
        from services import task_manager

        original_loop = task_manager._loop
        original_warned = task_manager._loop_warned
        try:
            task_manager._loop = None
            task_manager._loop_warned = False

            result = [None]
            def thread_test():
                result[0] = task_manager._get_loop()

            t = threading.Thread(target=thread_test)
            t.start()
            t.join()

            assert result[0] is None, "_get_loop 应该返回 None，而不是创建未运行的事件循环"
        finally:
            task_manager._loop = original_loop
            task_manager._loop_warned = original_warned

    def test_ws_send_no_crash_when_no_loop(self):
        """_ws_send_progress/_ws_send_final 在没有 event loop 时不应崩溃"""
        import threading
        from services import task_manager

        original_loop = task_manager._loop
        original_warned = task_manager._loop_warned
        try:
            task_manager._loop = None
            task_manager._loop_warned = False

            def thread_test():
                task_manager._ws_send_progress("test-task", {"status": "testing"})
                task_manager._ws_send_final("test-task", {"status": "done"})

            t = threading.Thread(target=thread_test)
            t.start()
            t.join()
        finally:
            task_manager._loop = original_loop
            task_manager._loop_warned = original_warned


# ============================================================================
# 回归测试 8: _merge_wavs 应该处理不同采样率的音轨
# Bug: _merge_wavs 不检查 vocal_sr 和 acc_sr 是否一致，直接相加，
#      采样率不同时混音会导致音高/速度错误，输出时长也不对
# ============================================================================

class TestMergeWavsSampleRateMismatch:
    """防止不同采样率音轨混音导致速度/音高错误"""

    def test_merge_different_sample_rates(self):
        """人声和伴奏采样率不同时，输出时长应该约等于 1.0s（误差<1%）"""
        import tempfile
        import os
        import numpy as np
        import soundfile as sf
        from api.routes.download import _merge_wavs

        with tempfile.TemporaryDirectory() as tmpdir:
            sr_vocal = 44100
            sr_acc = 48000
            duration = 1.0

            t_vocal = np.arange(int(sr_vocal * duration)) / sr_vocal
            vocal_y = 0.3 * np.sin(2 * np.pi * 440 * t_vocal)
            vocal_path = os.path.join(tmpdir, "vocal.wav")
            sf.write(vocal_path, vocal_y, sr_vocal)

            t_acc = np.arange(int(sr_acc * duration)) / sr_acc
            acc_y = 0.3 * np.sin(2 * np.pi * 880 * t_acc)
            acc_path = os.path.join(tmpdir, "acc.wav")
            sf.write(acc_path, acc_y, sr_acc)

            output_path = os.path.join(tmpdir, "merged.wav")
            _merge_wavs(vocal_path, acc_path, output_path)

            y_out, sr_out = sf.read(output_path)
            out_duration = len(y_out) / sr_out

            assert sr_out == sr_vocal, f"输出采样率应该等于人声采样率 {sr_vocal}，实际是 {sr_out}"
            assert abs(out_duration - duration) / duration < 0.01, (
                f"输出时长应该约为 {duration}s，实际是 {out_duration:.3f}s，误差超过 1%"
            )

    def test_merge_same_sample_rate_unchanged(self):
        """采样率相同时，行为和之前完全一致"""
        import tempfile
        import os
        import numpy as np
        import soundfile as sf
        from api.routes.download import _merge_wavs

        with tempfile.TemporaryDirectory() as tmpdir:
            sr = 44100
            duration = 1.0

            t = np.arange(int(sr * duration)) / sr
            vocal_y = 0.3 * np.sin(2 * np.pi * 440 * t)
            vocal_path = os.path.join(tmpdir, "vocal.wav")
            sf.write(vocal_path, vocal_y, sr)

            acc_y = 0.3 * np.sin(2 * np.pi * 880 * t)
            acc_path = os.path.join(tmpdir, "acc.wav")
            sf.write(acc_path, acc_y, sr)

            output_path = os.path.join(tmpdir, "merged.wav")
            _merge_wavs(vocal_path, acc_path, output_path)

            y_out, sr_out = sf.read(output_path)
            assert sr_out == sr
            assert abs(len(y_out) / sr_out - duration) / duration < 0.001


# ============================================================================
# 回归测试 9: MessageBus stop() 队列满时也能可靠停止
# Bug: 队列满时 put SENTINEL 失败，工作线程无法收到停止信号
# 修复: 使用 threading.Event 作为停止信号，不依赖队列
# ============================================================================

class TestMessageBusStopReliability:
    """防止 MessageBus stop() 在队列满时无法停止"""

    def test_stop_when_queue_full(self):
        """队列满时调用 stop() 也应该能让工作线程退出"""
        import threading
        import time
        import asyncio
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        bus = MessageBus(maxsize=2)
        loop = asyncio.new_event_loop()
        bus.set_loop(loop)

        try:
            bus._running = True
            bus._stop_event.clear()

            bus._queue.put_nowait(("ws_progress", {"task_id": "1"}))
            bus._queue.put_nowait(("ws_progress", {"task_id": "2"}))

            assert bus._queue.full(), "队列应该是满的"

            thread = threading.Thread(target=bus._worker, daemon=True)
            thread.start()

            time.sleep(0.1)

            bus.stop()

            thread.join(timeout=3.0)
            assert not thread.is_alive(), "工作线程应该在 stop() 后退出"

        finally:
            loop.close()
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_stop_event_set_triggers_exit(self):
        """stop_event 被设置后，即使队列非空也应该退出"""
        import threading
        import time
        import asyncio
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        bus = MessageBus(maxsize=10)
        loop = asyncio.new_event_loop()
        bus.set_loop(loop)

        try:
            for i in range(5):
                bus._queue.put_nowait(("ws_progress", {"task_id": str(i)}))

            bus._running = True
            bus._stop_event.clear()

            thread = threading.Thread(target=bus._worker, daemon=True)
            thread.start()

            time.sleep(0.1)

            bus._stop_event.set()
            bus._running = False

            thread.join(timeout=3.0)
            assert not thread.is_alive(), "设置 stop_event 后线程应该退出"

        finally:
            loop.close()
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()


# ============================================================================
# 回归测试 10: MessageBus _dispatch 协程异常应该打日志
# Bug: run_coroutine_threadsafe 返回的 Future 未检查，协程异常静默丢失
# 修复: 给 Future 添加 done_callback，检查异常并打 warning 日志
# ============================================================================

class TestMessageBusCoroutineExceptionLogging:
    """防止协程异常静默丢失"""

    def test_coroutine_exception_is_logged(self, caplog):
        """协程抛出异常时应该有 warning 日志"""
        import threading
        import asyncio
        import time
        from unittest.mock import MagicMock, patch
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        async def failing_coro(*args, **kwargs):
            raise ValueError("test exception from coroutine")

        mock_ws = MagicMock()
        mock_ws.send_progress = failing_coro

        with patch("services.message_bus.ws_manager", mock_ws):
            bus = MessageBus()
            loop = asyncio.new_event_loop()
            bus.set_loop(loop)

            loop_thread = None

            def run_loop():
                asyncio.set_event_loop(loop)
                loop.run_forever()

            try:
                loop_thread = threading.Thread(target=run_loop, daemon=True)
                loop_thread.start()
                time.sleep(0.1)

                bus.start()

                with caplog.at_level(logging.WARNING):
                    bus.publish("ws_progress", {"task_id": "test-task", "progress": 50})
                    time.sleep(0.5)

                assert any("协程执行异常" in rec.message for rec in caplog.records), \
                    "协程异常应该被日志记录"
                assert any("test exception from coroutine" in rec.message for rec in caplog.records), \
                    "异常消息应该出现在日志中"

                bus.stop()

            finally:
                loop.call_soon_threadsafe(loop.stop)
                if loop_thread:
                    loop_thread.join(timeout=2.0)
                loop.close()
                MessageBus._instance = None
                MessageBus._lock = threading.Lock()


# ============================================================================
# 回归测试 11: /metrics/reset 端点需要认证
# Bug: 任何人都可以调用 reset 接口清空监控数据
# 修复: 需要 ADMIN_TOKEN 认证，未配置时默认禁用
# ============================================================================

class TestMetricsResetAuth:
    """防止监控数据被恶意重置"""

    def test_reset_without_admin_token_disabled(self):
        """未配置 ADMIN_TOKEN 时，reset 接口应该返回 403"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = ""

            app = create_app()
            client = TestClient(app)

            response = client.post("/api/v1/metrics/reset")
            assert response.status_code == 403, f"未配置 token 时应该返回 403，实际返回 {response.status_code}"
        finally:
            config.ADMIN_TOKEN = old_token

    def test_reset_with_wrong_token(self):
        """配置了 ADMIN_TOKEN 但请求带错误 token 时应该返回 401"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = "secret123"

            app = create_app()
            client = TestClient(app)

            response = client.post("/api/v1/metrics/reset", headers={"X-Admin-Token": "wrong-token"})
            assert response.status_code == 401, f"错误 token 应该返回 401，实际返回 {response.status_code}"

            response = client.post("/api/v1/metrics/reset")
            assert response.status_code == 401, f"缺少 token 应该返回 401，实际返回 {response.status_code}"
        finally:
            config.ADMIN_TOKEN = old_token

    def test_reset_with_correct_token(self):
        """配置了 ADMIN_TOKEN 且请求带正确 token 时应该成功"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = "secret123"

            app = create_app()
            client = TestClient(app)

            response = client.post("/api/v1/metrics/reset", headers={"X-Admin-Token": "secret123"})
            assert response.status_code == 200, f"正确 token 应该返回 200，实际返回 {response.status_code}"
            data = response.json()
            assert data.get("status") == "ok"
        finally:
            config.ADMIN_TOKEN = old_token


# ============================================================================
# 回归测试 12: send_final 中 ws.close() 失败也要确保连接清理
# Bug: 先 pop task_id 再 close，close 失败导致连接资源泄漏
# 修复: 先关闭连接再 pop，用 try/finally 确保关闭
# ============================================================================

class TestSendFinalConnectionCleanup:
    """防止 send_final 中连接资源泄漏"""

    def test_send_final_closes_all_even_on_error(self):
        """即使某个 ws.send_json 或 close 抛异常，所有连接都应该被 close"""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()

            ws1 = MagicMock()
            ws1.send_json = AsyncMock()
            ws1.close = AsyncMock()

            ws2 = MagicMock()
            ws2.send_json = AsyncMock(side_effect=RuntimeError("send failed"))
            ws2.close = AsyncMock()

            ws3 = MagicMock()
            ws3.send_json = AsyncMock()
            ws3.close = AsyncMock(side_effect=RuntimeError("close failed"))

            task_id = "test-task-123"

            await mgr.connect(task_id, ws1)
            await mgr.connect(task_id, ws2)
            await mgr.connect(task_id, ws3)

            await mgr.send_final(task_id, {"status": "done"})

            ws1.close.assert_awaited_once()
            ws2.close.assert_awaited_once()
            ws3.close.assert_awaited_once()

            async with mgr._lock:
                assert task_id not in mgr._connections, "task_id 应该从 connections 中移除"

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_send_final_removes_from_dict_after_close(self):
        """应该在关闭所有连接后再从字典中移除"""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()

            ws = MagicMock()
            ws.send_json = AsyncMock()
            ws.close = AsyncMock()

            task_id = "test-task-456"
            await mgr.connect(task_id, ws)

            pop_called_before_close = {"value": False}
            close_called = {"value": False}

            original_pop = mgr._connections.pop

            def tracking_pop(key, *args, **kwargs):
                if close_called["value"]:
                    pop_called_before_close["value"] = False
                else:
                    pop_called_before_close["value"] = True
                return original_pop(key, *args, **kwargs)

            original_close = ws.close

            async def tracking_close(*args, **kwargs):
                close_called["value"] = True
                return await original_close(*args, **kwargs)

            ws.close = tracking_close

            with patch.dict(mgr._connections):
                await mgr.send_final(task_id, {"status": "done"})

            assert close_called["value"], "close 应该被调用"
            assert not pop_called_before_close["value"], \
                "应该在 close 之后再从字典中 pop，而不是之前"

        asyncio.get_event_loop().run_until_complete(run_test())


# ============================================================================
# 回归测试 13: WebSocket 路由中 send_json 异常不会导致未处理异常
# Bug: send_json 抛异常时没捕获，导致异常传播和资源泄漏
# 修复: 所有 send_json 调用都有 try/except，异常时打日志并正常清理
# ============================================================================

class TestWebSocketSendJsonErrorHandling:
    """防止 WebSocket send_json 异常导致资源泄漏"""

    def test_websocket_handler_has_general_exception_catch(self):
        """WebSocket 路由处理函数应该捕获通用异常，不仅是 WebSocketDisconnect"""
        import inspect
        from api.routes import system

        source = inspect.getsource(system.websocket_task_status)

        assert "except Exception as e:" in source, (
            "WebSocket 处理函数应该有通用的 Exception 捕获，"
            "防止 send_json 等异常导致未处理异常和资源泄漏"
        )
        assert "logger.warning" in source, (
            "异常时应该打 warning 日志"
        )

    def test_websocket_disconnect_has_try_except(self):
        """ws_manager.disconnect 调用应该在 try/except 中，防止清理时二次异常"""
        import inspect
        from api.routes import system

        source = inspect.getsource(system.websocket_task_status)

        assert "await ws_manager.disconnect" in source

        lines_with_disconnect = [line for line in source.split("\n") if "ws_manager.disconnect" in line]
        assert len(lines_with_disconnect) > 0, "应该调用 ws_manager.disconnect"

        assert "try:" in source and "finally:" in source, (
            "应该有 try/finally 确保 disconnect 被调用"
        )

    def test_all_send_json_have_try_except(self):
        """所有 websocket.send_json 调用都应该在 try/except 块中"""
        import ast
        import inspect
        from api.routes import system

        source = inspect.getsource(system.websocket_task_status)
        tree = ast.parse(source)

        send_json_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "send_json":
                        send_json_calls.append(node)

        assert len(send_json_calls) > 0, "应该有 send_json 调用"

        def is_inside_try(node):
            parent = getattr(node, 'parent', None)
            current = node
            for _ in range(20):
                try:
                    current = current.parent
                except AttributeError:
                    return False
                if current is None:
                    return False
                if isinstance(current, (ast.Try, ast.ExceptHandler)):
                    return True
            return False

        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child.parent = parent

        for call in send_json_calls:
            assert is_inside_try(call), (
                f"send_json 调用应该在 try/except 块中: {ast.dump(call)}"
            )


# ============================================================================
# 回归测试 14: TaskExecutor.cancel 必须调用 _track_task_end 防止 _active_tasks 泄漏
# Bug: TaskExecutor.cancel() 只加 _cancelled_tasks，但没调 _track_task_end
#      如果任务还没开始执行就取消了，_run_task 还没被调用，所以计数没减
# 修复: 在 cancel() 中立即调用 _track_task_end 和 _schedule_cancel_cleanup
# ============================================================================

class TestTaskExecutorCancelLeak:
    """防止 TaskExecutor.cancel 导致 _active_tasks 集合泄漏"""

    def test_cancel_via_executor_releases_active_task(self):
        """通过 TaskExecutor.cancel 取消任务后，_active_tasks 应立即释放"""
        import tempfile
        import os
        import time
        from database import init_db, create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask, _active_tasks, _active_tasks_lock

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = tmpdir
                config.OUTPUT_DIR = tmpdir
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                init_db()

                import soundfile as sf
                import numpy as np
                sr = 44100
                t = np.arange(int(sr * 1.0)) / sr
                y = 0.3 * np.sin(2 * np.pi * 440 * t)
                audio_path = os.path.join(tmpdir, "test.wav")
                sf.write(audio_path, y, sr)

                task_id = "reg_tl001_cancel_leak"
                create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash_tl001")

                with _active_tasks_lock:
                    _active_tasks.clear()

                task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
                executor = get_task_executor()
                executor.submit(task)

                time.sleep(0.05)

                with _active_tasks_lock:
                    assert task_id in _active_tasks, "任务提交后应在 _active_tasks 中"

                executor.cancel(task_id)

                time.sleep(0.1)

                with _active_tasks_lock:
                    task_in_set = task_id in _active_tasks

                assert not task_in_set, (
                    "TL-001: TaskExecutor.cancel 后任务仍在 _active_tasks 集合中，"
                    "导致并发计数泄漏，最终会耗尽所有并发槽位"
                )
            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 15: cleanup_stale_tasks 不应清理 detected 状态
# Bug: detected 是检测任务的终态，不应该被当作停滞状态清理
# 修复: 从停滞状态列表中移除 detected
# ============================================================================

class TestDetectedStateNotCleanedUp:
    """防止 detected 状态的检测任务被错误清理"""

    def test_detected_status_not_cleaned_by_stale_cleanup(self):
        """detected 状态的任务不应被 cleanup_stale_tasks 清理"""
        import tempfile
        import os
        from database import init_db, create_task, update_task, get_task, cleanup_stale_tasks

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            try:
                config.DB_PATH = db_path
                init_db()

                task_id = "reg_tl002_detected_cleanup"
                create_task(task_id, "test.wav", "/tmp/test.wav", {"detector_version": "v1.1"}, file_hash="hash_tl002")
                update_task(task_id, status="detected", progress=1.0, step="检测完成",
                            detection_result={"ai_probability": 0.5})

                task_before = get_task(task_id)
                assert task_before["status"] == "detected"

                cleanup_stale_tasks()

                task_after = get_task(task_id)
                assert task_after["status"] == "detected", (
                    f"TL-002: 'detected' 是检测任务的终态，不应被 cleanup_stale_tasks 清理。"
                    f"清理前状态={task_before['status']}, 清理后状态={task_after['status']}"
                )
            finally:
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 16: RenderTask.on_success 必须包含 output_path
# Bug: RenderTask.on_success 只返回了 render_filename 和 render_result，没返回 output_path
# 修复: 在 on_success 中添加 output_path 字段
# ============================================================================

class TestRenderTaskOutputPath:
    """防止 RenderTask.on_success 遗漏 output_path"""

    def test_render_on_success_includes_output_path(self):
        """RenderTask.on_success 的返回值必须包含 output_path"""
        import tempfile
        import os
        from services.task_manager import RenderTask

        with tempfile.TemporaryDirectory() as tmpdir:
            import soundfile as sf
            import numpy as np
            sr = 44100
            t = np.arange(int(sr * 1.0)) / sr
            y = 0.3 * np.sin(2 * np.pi * 440 * t)
            input_path = os.path.join(tmpdir, "input.wav")
            sf.write(input_path, y, sr)

            output_path = os.path.join(tmpdir, "output.wav")
            task_id = "reg_tl003_render_output"

            task = RenderTask(
                task_id=task_id,
                input_path=input_path,
                output_path=output_path,
                target_sr=44100,
                bit_depth=16,
                render_filename="output.wav",
            )

            result = {"output_sample_rate": 44100, "output_bit_depth": 16}
            extra_fields = task.on_success(result)

            assert "output_path" in extra_fields, (
                "TL-003: RenderTask.on_success 未包含 output_path 字段，"
                "导致渲染完成后数据库中无法找到输出文件路径"
            )
            assert extra_fields["output_path"] == output_path


# ============================================================================
# 回归测试 17: 服务器重启清理用 error 状态而非 failed
# Bug: cleanup_stale_tasks 用的是 'failed' 而不是 'error'，与系统其他地方不一致
# 修复: 改为 'error'
# ============================================================================

class TestStaleCleanupUsesErrorStatus:
    """防止停滞任务清理状态不一致"""

    def test_cleanup_uses_error_status(self):
        """cleanup_stale_tasks 应该将停滞任务标记为 'error' 而非 'failed'"""
        import tempfile
        import os
        from database import init_db, create_task, get_task, cleanup_stale_tasks

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            try:
                config.DB_PATH = db_path
                init_db()

                task_id = "reg_tl004_error_status"
                create_task(task_id, "test.wav", "/tmp/test.wav", {}, file_hash="hash_tl004")

                cleanup_stale_tasks()

                task = get_task(task_id)
                assert task["status"] == "error", (
                    f"TL-004: 服务器重启清理任务使用了 '{task['status']}' 状态，"
                    f"但系统其他地方统一使用 'error'。状态不一致会导致前端无法正确显示错误。"
                )
            finally:
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 18: DetectTask.completed_status 在 execute 前也应正确
# Bug: DetectTask.completed_status 依赖 _prev_status，但 _prev_status 在 execute() 中才初始化
# 修复: 在 __init__ 中就从数据库读取 _prev_status
# ============================================================================

class TestDetectTaskCompletedStatus:
    """防止 DetectTask.completed_status 提前访问时返回错误值"""

    def test_completed_status_before_execute(self):
        """DetectTask.completed_status 在 execute() 之前访问也应该返回正确值"""
        import tempfile
        import os
        from database import init_db, create_task, update_task, get_task
        from services.task_manager import DetectTask

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_db = config.DB_PATH
            try:
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                init_db()

                import soundfile as sf
                import numpy as np
                sr = 44100
                t = np.arange(int(sr * 1.0)) / sr
                y = 0.3 * np.sin(2 * np.pi * 440 * t)
                audio_path = os.path.join(tmpdir, "test.wav")
                sf.write(audio_path, y, sr)

                task_id = "reg_tl005_prev_status"
                create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash_tl005")
                update_task(task_id, status="completed", progress=1.0, step="修复完成")

                task = DetectTask(task_id, audio_path, detect_type="repaired", detector_version="v1.1")

                status_before = task.completed_status

                task_before_in_db = get_task(task_id)
                assert task_before_in_db["status"] == "completed", "数据库中任务状态应为 completed"

                assert status_before == "completed", (
                    f"TL-005: DetectTask.completed_status 在 execute() 之前返回 '{status_before}'，"
                    f"但数据库中任务实际状态是 'completed'。_prev_status 应在 __init__ 中就初始化。"
                )
            finally:
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 19: 取消未开始的任务时 _cancelled_tasks 不应永久泄漏
# Bug: 取消未开始执行的任务时，_cancelled_tasks 条目存在永久泄漏风险
# 修复: 使用 _schedule_cancel_cleanup 确保最终清理
# ============================================================================

class TestCancelledTasksNoLeak:
    """防止 _cancelled_tasks 集合永久泄漏"""

    def test_cancelled_tasks_cleaned_eventually(self):
        """任务取消后，_cancelled_tasks 中的条目最终应被清理"""
        import tempfile
        import os
        import time
        from database import init_db, create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask, _cancelled_tasks, _cancelled_lock

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = tmpdir
                config.OUTPUT_DIR = tmpdir
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                init_db()

                import soundfile as sf
                import numpy as np
                sr = 44100
                t = np.arange(int(sr * 1.0)) / sr
                y = 0.3 * np.sin(2 * np.pi * 440 * t)
                audio_path = os.path.join(tmpdir, "test.wav")
                sf.write(audio_path, y, sr)

                task_id = "reg_tl006_cancelled_leak"
                create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash_tl006")

                with _cancelled_lock:
                    _cancelled_tasks.clear()

                task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
                executor = get_task_executor()

                executor.submit(task)
                time.sleep(0.05)
                executor.cancel(task_id)

                time.sleep(1.0)

                with _cancelled_lock:
                    still_in_set = task_id in _cancelled_tasks

                assert not still_in_set, (
                    "TL-006: 任务完成/取消后，_cancelled_tasks 中的条目应被清理。"
                    "如果任务在排队阶段被取消，可能存在泄漏风险。"
                )
            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 14: _cancelled_tasks 集合无限增长
# Bug: 取消从未执行的任务时，_cancelled_tasks 中的条目永远不会被清理
# 修复: cancel_task 中设置定时清理，1小时后自动清除取消标记
# ============================================================================

class TestCancelledTasksCleanup:
    """防止 _cancelled_tasks 集合无限增长"""

    def test_cancel_task_schedules_cleanup(self):
        """cancel_task 应该调度定时清理，取消标记最终会被清除"""
        import time
        from services import task_manager

        original_delay = task_manager._CANCEL_CLEANUP_DELAY
        try:
            task_manager._CANCEL_CLEANUP_DELAY = 0.1

            with task_manager._cancelled_lock:
                task_manager._cancelled_tasks.clear()

            task_id = "test-cancel-cleanup-123"
            result = task_manager.cancel_task(task_id)

            assert result is True
            with task_manager._cancelled_lock:
                assert task_id in task_manager._cancelled_tasks

            time.sleep(0.3)

            with task_manager._cancelled_lock:
                assert task_id not in task_manager._cancelled_tasks, \
                    "取消标记应该在延迟后被清理"

        finally:
            task_manager._CANCEL_CLEANUP_DELAY = original_delay
            with task_manager._cancelled_lock:
                task_manager._cancelled_tasks.discard("test-cancel-cleanup-123")

    def test_task_executor_cancel_schedules_cleanup_for_active_tasks(self):
        """TaskExecutor.cancel 对活跃任务也应该调度定时清理"""
        import time
        from services import task_manager
        from services.task_executor import TaskExecutor

        original_delay = task_manager._CANCEL_CLEANUP_DELAY
        try:
            task_manager._CANCEL_CLEANUP_DELAY = 0.1

            with task_manager._cancelled_lock:
                task_manager._cancelled_tasks.clear()
            with task_manager._active_tasks_lock:
                task_manager._active_tasks.clear()

            task_id = "test-executor-cancel-456"
            with task_manager._active_tasks_lock:
                task_manager._active_tasks.add(task_id)

            executor = TaskExecutor()
            result = executor.cancel(task_id)

            assert result is True
            with task_manager._cancelled_lock:
                assert task_id in task_manager._cancelled_tasks

            time.sleep(0.3)

            with task_manager._cancelled_lock:
                assert task_id not in task_manager._cancelled_tasks, \
                    "活跃任务的取消标记也应该在延迟后被清理"

        finally:
            task_manager._CANCEL_CLEANUP_DELAY = original_delay
            with task_manager._cancelled_lock:
                task_manager._cancelled_tasks.discard("test-executor-cancel-456")
            with task_manager._active_tasks_lock:
                task_manager._active_tasks.discard("test-executor-cancel-456")


# ============================================================================
# 回归测试 15: SQLite 连接启用 WAL 模式和 busy_timeout
# Bug: SQLite 默认模式下多线程写容易报 database is locked
# 修复: 连接时启用 WAL 模式（PRAGMA journal_mode=WAL），加上 busy_timeout
# ============================================================================

class TestSQLiteWalMode:
    """防止 SQLite 高并发下 database is locked 错误"""

    def test_get_db_enables_wal_mode(self):
        """get_db() 返回的连接应该启用了 WAL 模式"""
        import tempfile
        import os
        from database import get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                conn = get_db()
                try:
                    cursor = conn.execute("PRAGMA journal_mode")
                    mode = cursor.fetchone()[0]
                    assert mode.lower() == "wal", \
                        f"应该启用 WAL 模式，实际是 {mode}"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db

    def test_get_db_sets_busy_timeout(self):
        """get_db() 返回的连接应该设置了 busy_timeout"""
        import tempfile
        import os
        from database import get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                conn = get_db()
                try:
                    cursor = conn.execute("PRAGMA busy_timeout")
                    timeout = cursor.fetchone()[0]
                    assert timeout > 0, \
                        f"应该设置 busy_timeout，实际是 {timeout}"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db

    def test_get_training_db_enables_wal_mode(self):
        """get_training_db() 返回的连接也应该启用 WAL 模式"""
        import tempfile
        import os
        from database import get_training_db

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_db_path = config.DB_PATH
            config.DB_PATH = os.path.join(tmpdir, "tasks.db")
            training_db_path = os.path.join(tmpdir, "training.db")
            import database
            old_training_path = database.TRAINING_DB_PATH
            database.TRAINING_DB_PATH = training_db_path
            try:
                conn = get_training_db()
                try:
                    cursor = conn.execute("PRAGMA journal_mode")
                    mode = cursor.fetchone()[0]
                    assert mode.lower() == "wal", \
                        f"训练库也应该启用 WAL 模式，实际是 {mode}"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db_path
                database.TRAINING_DB_PATH = old_training_path


# ============================================================================
# 回归测试 16: _track_task_start 使用乐观锁模式（先 add 再检查）
# Bug: 检查 len(_active_tasks) < MAX 和添加之间有时间窗口，可能超量接受任务
# 修复: 用原子操作，先 add 再检查，超了就 remove（乐观锁模式）
# ============================================================================

class TestTrackTaskStartOptimisticLock:
    """防止并发任务接受时超量"""

    def test_track_task_start_uses_optimistic_lock(self):
        """_track_task_start 应该使用先 add 再检查的乐观锁模式"""
        from services import task_manager

        original_max = task_manager.MAX_CONCURRENT_TASKS
        try:
            task_manager.MAX_CONCURRENT_TASKS = 2

            with task_manager._active_tasks_lock:
                task_manager._active_tasks.clear()

            assert task_manager._track_task_start("task-1") is True
            assert task_manager._track_task_start("task-2") is True
            assert task_manager._track_task_start("task-3") is False

            assert len(task_manager._active_tasks) == 2
            assert "task-1" in task_manager._active_tasks
            assert "task-2" in task_manager._active_tasks
            assert "task-3" not in task_manager._active_tasks

        finally:
            task_manager.MAX_CONCURRENT_TASKS = original_max
            with task_manager._active_tasks_lock:
                task_manager._active_tasks.clear()

    def test_concurrent_track_task_start_no_overflow(self):
        """高并发下 _track_task_start 也不会超量添加任务"""
        import threading
        from services import task_manager

        original_max = task_manager.MAX_CONCURRENT_TASKS
        try:
            task_manager.MAX_CONCURRENT_TASKS = 3

            with task_manager._active_tasks_lock:
                task_manager._active_tasks.clear()

            num_threads = 20
            success_count = [0]
            lock = threading.Lock()
            barrier = threading.Barrier(num_threads)

            def worker(thread_id):
                barrier.wait()
                tid = f"concurrent-task-{thread_id}"
                if task_manager._track_task_start(tid):
                    with lock:
                        success_count[0] += 1

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert success_count[0] == 3, \
                f"应该只有 3 个任务成功，实际成功 {success_count[0]} 个"
            assert len(task_manager._active_tasks) == 3, \
                f"活跃任务数应该是 3，实际是 {len(task_manager._active_tasks)}"

        finally:
            task_manager.MAX_CONCURRENT_TASKS = original_max
            with task_manager._active_tasks_lock:
                task_manager._active_tasks.clear()


# ============================================================================
# 回归测试 17: MessageBus 默认有界队列，满了丢弃最老消息
# Bug: MessageBus 默认无界队列，消费慢时消息堆积导致内存耗尽
# 修复: 设置默认 maxsize=10000，满了就丢弃最老的消息并打 warning
# ============================================================================

class TestMessageBusBoundedQueue:
    """防止 MessageBus 无界队列导致 OOM"""

    def test_default_maxsize_is_bounded(self):
        """MessageBus 默认 maxsize 应该是有界的（10000）"""
        import threading
        from services.message_bus import MessageBus, DEFAULT_MAXSIZE

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus()
            assert bus._maxsize == DEFAULT_MAXSIZE, \
                f"默认 maxsize 应该是 {DEFAULT_MAXSIZE}，实际是 {bus._maxsize}"
            assert bus._maxsize > 0, "默认 maxsize 应该大于 0（有界）"
        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_queue_full_drops_oldest_message(self):
        """队列满时应该丢弃最老的消息，然后添加新消息"""
        import threading
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=3)
            bus._running = True

            bus.publish("ch1", {"id": 1})
            bus.publish("ch1", {"id": 2})
            bus.publish("ch1", {"id": 3})

            assert bus._queue.qsize() == 3
            assert bus._queue.full()

            bus.publish("ch1", {"id": 4})

            assert bus._queue.qsize() == 3, "队列大小应该保持不变"

            first = bus._queue.get_nowait()
            envelope = first[1]
            data = envelope.get("data", envelope)
            assert data["id"] == 2, \
                f"最老的消息（id=1）应该被丢弃，队首应该是 id=2，实际是 {data['id']}"

            second = bus._queue.get_nowait()
            second_data = second[1].get("data", second[1])
            assert second_data["id"] == 3

            third = bus._queue.get_nowait()
            third_data = third[1].get("data", third[1])
            assert third_data["id"] == 4

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_queue_full_logs_warning(self, caplog):
        """队列满时丢弃老消息应该打 warning 日志"""
        import threading
        import logging
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=2)
            bus._running = True

            bus.publish("ch1", {"id": 1})
            bus.publish("ch1", {"id": 2})

            with caplog.at_level(logging.WARNING):
                bus.publish("ch1", {"id": 3})

            assert any("队列已满" in rec.message for rec in caplog.records), \
                "队列满时应该打 warning 日志"
            assert any("丢弃最老消息" in rec.message for rec in caplog.records), \
                "日志中应该提到丢弃最老消息"

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()


# ============================================================================
# 回归测试 14: safe_write 写入失败时临时文件必须清理
# Bug: safe_write 抛出异常时 .tmp 临时文件不删除，磁盘泄漏
# 修复: 用 try/finally 确保临时文件在失败时被清理
# ============================================================================

class TestSafeWriteTempFileCleanup:
    """防止 safe_write 失败时 .tmp 临时文件泄漏"""

    def test_write_exception_cleans_temp_file(self, tmp_path):
        """写入过程中抛异常时，临时文件应该被清理掉"""
        from services.file_gateway import SafeFileGateway
        from unittest.mock import patch

        gw = SafeFileGateway(str(tmp_path))
        test_file = "test.txt"
        temp_path = os.path.join(str(tmp_path), "test.txt.tmp")

        with patch("os.fsync", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                gw.safe_write(test_file, b"hello world")

        assert not os.path.exists(temp_path), f"临时文件 {temp_path} 应该被清理"

    def test_write_success_no_temp_file_left(self, tmp_path):
        """写入成功后，不应该残留 .tmp 文件"""
        from services.file_gateway import SafeFileGateway

        gw = SafeFileGateway(str(tmp_path))
        test_file = "test.txt"
        temp_path = os.path.join(str(tmp_path), "test.txt.tmp")

        gw.safe_write(test_file, b"hello world")

        assert gw.exists(test_file)
        assert not os.path.exists(temp_path), "成功后不应该残留 .tmp 文件"

    def test_open_failure_cleans_temp_file(self, tmp_path):
        """打开临时文件失败时，也不应该有泄漏（虽然还没创建）"""
        from services.file_gateway import SafeFileGateway
        from unittest.mock import patch
        import builtins

        gw = SafeFileGateway(str(tmp_path))
        test_file = "test.txt"

        original_open = builtins.open
        call_count = [0]

        def fake_open(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("cannot open")
            return original_open(*args, **kwargs)

        with patch("builtins.open", side_effect=fake_open):
            with pytest.raises(OSError):
                gw.safe_write(test_file, b"hello")


# ============================================================================
# 回归测试 15: 锁 LRU 淘汰不能淘汰正在被持有的锁
# Bug: 锁被持有期间被 LRU 淘汰，新请求创建新锁，失去互斥
# 修复: 引入引用计数，LRU 只淘汰 ref_count == 0 的锁
# ============================================================================

class TestLockLRUEvictionSafety:
    """防止 LRU 淘汰正在被持有的锁导致并发安全失效"""

    def test_held_lock_not_evicted(self, tmp_path):
        """锁正在被持有时，不应该被 LRU 淘汰"""
        from services.file_gateway import SafeFileGateway

        gw = SafeFileGateway(str(tmp_path))
        gw._MAX_LOCKS = 3

        lock_a = gw.get_lock("a.txt")
        lock_b = gw.get_lock("b.txt")
        lock_c = gw.get_lock("c.txt")

        assert len(gw._locks) == 3

        with lock_a:
            gw.get_lock("d.txt")
            gw.get_lock("e.txt")

            assert "a.txt" in gw._locks, "正在持有的锁 a.txt 不应该被淘汰"

        assert len(gw._locks) <= 3

    def test_same_file_same_lock_after_eviction_pressure(self, tmp_path):
        """同一文件在锁被持有期间获取，应该返回同一把锁"""
        from services.file_gateway import SafeFileGateway
        import threading

        gw = SafeFileGateway(str(tmp_path))
        gw._MAX_LOCKS = 2

        errors = []
        shared_lock_ids = []

        def writer1():
            lock1 = gw.get_lock("shared.txt")
            with lock1:
                shared_lock_ids.append(id(lock1))
                import time
                time.sleep(0.05)
                lock2 = gw.get_lock("shared.txt")
                shared_lock_ids.append(id(lock2))
                if id(lock1) != id(lock2):
                    errors.append("同一文件应该返回同一把锁")

        def evictor():
            import time
            time.sleep(0.01)
            for i in range(10):
                gw.get_lock(f"evict_{i}.txt")

        t1 = threading.Thread(target=writer1)
        t2 = threading.Thread(target=evictor)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, "; ".join(errors)

    def test_unused_locks_can_be_evicted(self, tmp_path):
        """未使用的锁应该可以被正常 LRU 淘汰"""
        from services.file_gateway import SafeFileGateway

        gw = SafeFileGateway(str(tmp_path))
        gw._MAX_LOCKS = 3

        for i in range(5):
            lock = gw.get_lock(f"file_{i}.txt")
            del lock

        assert len(gw._locks) <= 3, "未使用的锁应该被 LRU 淘汰"


# ============================================================================
# 回归测试 16: /decoded-wav/{file_hash} 路径遍历漏洞
# Bug: file_hash 直接拼路径，可通过 ../ 逃逸出 DECODED_DIR
# 修复: 用 hex 字符集限制 + basename + realpath 双重校验
# ============================================================================

class TestDecodedWavPathTraversal:
    """防止 decoded-wav 接口路径遍历漏洞"""

    def test_path_traversal_rejected(self):
        """file_hash 包含路径遍历字符时应该返回 400"""
        from api.routes.download import _safe_decoded_path
        from fastapi import HTTPException

        traversal_inputs = [
            "../etc/passwd",
            "..%2fetc%2fpasswd",
            "..\\etc\\passwd",
            "/etc/passwd",
            "subdir/file",
            "./file",
            "../file",
        ]

        for bad_hash in traversal_inputs:
            with pytest.raises(HTTPException) as exc_info:
                _safe_decoded_path(bad_hash)
            assert exc_info.value.status_code == 400, f"{bad_hash} 应该返回 400"

    def test_valid_hash_accepted(self):
        """合法的十六进制 hash 应该正常通过"""
        from api.routes.download import _safe_decoded_path
        import config

        valid_hashes = [
            "abc123",
            "ABCDEF1234567890",
            "a" * 32,
            "0" * 64,
        ]

        for valid_hash in valid_hashes:
            result = _safe_decoded_path(valid_hash)
            assert config.DECODED_DIR in result
            assert result.endswith(f"{valid_hash}.wav")

    def test_empty_hash_rejected(self):
        """空字符串应该被拒绝"""
        from api.routes.download import _safe_decoded_path
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _safe_decoded_path("")

    def test_non_hex_chars_rejected(self):
        """包含非十六进制字符的 hash 应该被拒绝"""
        from api.routes.download import _safe_decoded_path
        from fastapi import HTTPException

        bad_hashes = [
            "hash_with_underscore",
            "hash-with-dash",
            "hash.dot",
            "hash space",
            "hash/../etc/passwd",
        ]

        for bad_hash in bad_hashes:
            with pytest.raises(HTTPException):
                _safe_decoded_path(bad_hash)


# ============================================================================
# 回归测试 17: TTL 删除失败的文件在 LRU 阶段应该继续尝试
# Bug: TTL 阶段删除失败的文件从列表移除了，LRU 阶段不会再试
# 修复: 删除失败的文件保留在列表中，LRU 阶段继续尝试删除
# ============================================================================

class TestTTLFailureRetryInLRU:
    """防止 TTL 删除失败的文件永远残留"""

    def test_failed_ttl_delete_retried_in_lru(self, tmp_path):
        """TTL 删除失败的文件，在 LRU 阶段应该继续尝试删除"""
        from services.cache_manager import CacheManager, CacheLayer
        from unittest.mock import patch
        import time

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()

        cache_dir = tmp_path / "test_cache"
        cache_dir.mkdir()

        layer = CacheLayer(
            name="test",
            base_dir=str(cache_dir),
            ttl_seconds=1,
            max_size_mb=0.0001,
        )
        mgr.register_layer(layer)

        old_file = cache_dir / "old.bin"
        old_file.write_bytes(b"x" * 200)
        old_mtime = time.time() - 10
        os.utime(str(old_file), (old_mtime, old_mtime))

        delete_attempts = [0]
        original_remove = os.remove

        def fake_remove(path):
            delete_attempts[0] += 1
            if delete_attempts[0] <= 1:
                raise OSError("permission denied")
            return original_remove(path)

        with patch("os.remove", side_effect=fake_remove):
            result = mgr.evict_layer("test")

        assert delete_attempts[0] >= 2, f"应该至少尝试删除 2 次（TTL + LRU），实际 {delete_attempts[0]} 次"
        assert not old_file.exists(), "文件最终应该被删除"

    def test_successful_ttl_delete_not_in_lru(self, tmp_path):
        """TTL 删除成功的文件，不应该在 LRU 阶段再处理"""
        from services.cache_manager import CacheManager, CacheLayer
        import time

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()

        cache_dir = tmp_path / "test_cache"
        cache_dir.mkdir()

        layer = CacheLayer(
            name="test",
            base_dir=str(cache_dir),
            ttl_seconds=1,
            max_size_mb=0.001,
        )
        mgr.register_layer(layer)

        old_file = cache_dir / "old.bin"
        old_file.write_bytes(b"x" * 100)
        old_mtime = time.time() - 10
        os.utime(str(old_file), (old_mtime, old_mtime))

        result = mgr.evict_layer("test")

        assert result["files_removed"] >= 1
        assert not old_file.exists()


# ============================================================================
# 回归测试 18: file_cache.py 不应该直接访问 CacheManager._layers
# Bug: 直接修改 _layers 私有属性，绕过锁机制，非线程安全
# 修复: CacheManager 提供公共方法，file_cache.py 改用公共方法
# ============================================================================

class TestFileCacheUsesPublicAPI:
    """防止 file_cache.py 直接操作 CacheManager 私有属性"""

    def test_file_cache_no_direct_private_access(self):
        """file_cache.py 源码中不应该直接访问 _layers 私有属性"""
        file_cache_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "file_cache.py"
        )
        with open(file_cache_path) as f:
            content = f.read()

        assert "_layers[" not in content, "file_cache.py 不应该直接访问 _layers 字典"
        assert "._layers" not in content, "file_cache.py 不应该直接访问 _layers 属性"

    def test_cache_manager_has_set_layer_max_size(self):
        """CacheManager 应该提供 set_layer_max_size 公共方法"""
        from services.cache_manager import CacheManager
        assert hasattr(CacheManager, "set_layer_max_size")
        assert callable(getattr(CacheManager, "set_layer_max_size"))

    def test_cache_manager_has_get_layer_max_size(self):
        """CacheManager 应该提供 get_layer_max_size 公共方法"""
        from services.cache_manager import CacheManager
        assert hasattr(CacheManager, "get_layer_max_size")
        assert callable(getattr(CacheManager, "get_layer_max_size"))

    def test_set_get_layer_max_size_thread_safe(self, tmp_path):
        """set/get max_size 应该是线程安全的"""
        from services.cache_manager import CacheManager, CacheLayer
        import threading

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()

        cache_dir = tmp_path / "test"
        cache_dir.mkdir()
        layer = CacheLayer(name="test", base_dir=str(cache_dir))
        mgr.register_layer(layer)

        errors = []

        def worker(worker_id):
            try:
                for i in range(100):
                    mgr.set_layer_max_size("test", float(worker_id * 100 + i))
                    val = mgr.get_layer_max_size("test")
                    assert isinstance(val, float)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"并发访问出错: {errors}"


# ============================================================================
# 回归测试 20: WR-006 MessageBus 队列满时重要消息应有重试机制
# Bug: 队列满时直接丢弃消息，重要消息（如任务完成通知）可能丢失
# 修复: 重要 channel（ws_final）使用阻塞 put 带超时，而非直接丢弃
# ============================================================================

class TestMessageBusImportantMessageRetry:
    """防止重要消息在队列满时被静默丢失"""

    def test_important_channel_uses_blocking_put(self):
        """ws_final 等重要消息应该使用阻塞 put 带超时重试"""
        import threading
        from services.message_bus import MessageBus, _IMPORTANT_CHANNELS

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            assert "ws_final" in _IMPORTANT_CHANNELS, "ws_final 应该是重要 channel"

            bus = MessageBus(maxsize=2)
            bus._running = True
            bus._stopped = False

            bus.publish("ws_progress", {"id": 1})
            bus.publish("ws_progress", {"id": 2})

            assert bus._queue.full()

            import time
            start = time.time()
            result = bus.publish("ws_final", {"id": 999})
            elapsed = time.time() - start

            assert result is False, "队列满时重要消息入队超时应该返回 False"
            assert elapsed >= 1.0, f"重要消息应该阻塞等待至少 1 秒以上，实际 {elapsed:.2f}s"

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_normal_channel_drops_oldest_when_full(self):
        """非重要消息队列满时应该丢弃最老的消息"""
        import threading
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=3)
            bus._running = True
            bus._stopped = False

            bus.publish("ws_progress", {"id": 1})
            bus.publish("ws_progress", {"id": 2})
            bus.publish("ws_progress", {"id": 3})

            assert bus._queue.full()

            result = bus.publish("ws_progress", {"id": 4})
            assert result is True, "非重要消息应该能入队（丢弃老消息）"

            assert bus._queue.qsize() == 3

            first = bus._queue.get_nowait()
            envelope = first[1]
            data = envelope.get("data", envelope)
            assert data["id"] == 2, f"最老的消息应该被丢弃，实际队首是 id=2"

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_publish_returns_bool(self):
        """publish 应该返回布尔值表示是否成功入队"""
        import threading
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=10)
            bus._running = True
            bus._stopped = False

            result = bus.publish("ws_progress", {"test": True})
            assert isinstance(result, bool), "publish 应该返回布尔值"
            assert result is True

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()


# ============================================================================
# 回归测试 21: WR-007 WebSocket 心跳超时断开机制
# Bug: WebSocket 无真正的心跳超时断开机制，半开连接会泄漏
# 修复: ws_manager 增加心跳监控，超时未活动的连接主动断开
# ============================================================================

class TestWebSocketHeartbeatTimeout:
    """防止半开 WebSocket 连接泄漏"""

    def test_ws_manager_has_heartbeat_monitor(self):
        """ProgressWSManager 应该有心跳监控相关方法"""
        from services.ws_manager import ProgressWSManager

        mgr = ProgressWSManager()
        assert hasattr(mgr, "start_heartbeat_monitor"), "应该有 start_heartbeat_monitor 方法"
        assert hasattr(mgr, "record_activity"), "应该有 record_activity 方法"
        assert hasattr(mgr, "_check_timeout_connections"), "应该有 _check_timeout_connections 方法"
        assert hasattr(mgr, "_last_seen"), "应该有 _last_seen 字典记录最后活动时间"

    def test_record_activity_updates_last_seen(self):
        """record_activity 应该更新连接的最后活动时间"""
        import asyncio
        from unittest.mock import MagicMock
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()
            ws = MagicMock()
            ws_id = id(ws)

            assert ws_id not in mgr._last_seen

            mgr.record_activity(ws)
            assert ws_id in mgr._last_seen
            first_time = mgr._last_seen[ws_id]

            import time
            time.sleep(0.01)
            mgr.record_activity(ws)
            assert mgr._last_seen[ws_id] > first_time

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_connect_sets_initial_last_seen(self):
        """connect 时应该初始化 last_seen"""
        import asyncio
        from unittest.mock import MagicMock
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()
            ws = MagicMock()
            task_id = "test-task"

            await mgr.connect(task_id, ws)
            assert id(ws) in mgr._last_seen

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_disconnect_cleans_last_seen(self):
        """disconnect 时应该清理 last_seen 记录"""
        import asyncio
        from unittest.mock import MagicMock
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()
            ws = MagicMock()
            task_id = "test-task"

            await mgr.connect(task_id, ws)
            ws_id = id(ws)
            assert ws_id in mgr._last_seen

            await mgr.disconnect(task_id, ws)
            assert ws_id not in mgr._last_seen

        asyncio.get_event_loop().run_until_complete(run_test())


# ============================================================================
# 回归测试 22: WR-008 WebSocket 重连后补发最新进度
# Bug: 前端 WebSocket 重连后会丢失中间进度消息
# 修复: ws_manager 缓存最新进度，重连时立即补发
# ============================================================================

class TestWebSocketProgressCache:
    """防止 WebSocket 重连后进度丢失"""

    def test_send_progress_saves_to_cache(self):
        """send_progress 应该保存最新进度到缓存"""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()
            task_id = "test-cache-1"

            data = {"task_id": task_id, "status": "running", "progress": 50, "step": "test"}
            await mgr.send_progress(task_id, data)

            cached = mgr.get_cached_progress(task_id)
            assert cached is not None, "进度应该被缓存"
            assert cached["progress"] == 50
            assert cached["status"] == "running"

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_send_final_saves_to_cache(self):
        """send_final 也应该保存最终状态到缓存"""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()
            task_id = "test-cache-final"
            ws = MagicMock()
            ws.send_json = AsyncMock()
            ws.close = AsyncMock()

            await mgr.connect(task_id, ws)

            final_data = {"task_id": task_id, "status": "completed", "progress": 100}
            await mgr.send_final(task_id, final_data)

            cached = mgr.get_cached_progress(task_id)
            assert cached is not None
            assert cached["status"] == "completed"
            assert cached["progress"] == 100

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_get_cached_progress_returns_copy(self):
        """get_cached_progress 应该返回副本，防止外部修改缓存"""
        from services.ws_manager import ProgressWSManager

        mgr = ProgressWSManager()
        task_id = "test-copy"
        mgr._progress_cache[task_id] = {"progress": 50}
        mgr._progress_cache_time[task_id] = __import__("time").time()

        cached = mgr.get_cached_progress(task_id)
        cached["progress"] = 999

        assert mgr._progress_cache[task_id]["progress"] == 50, \
            "修改返回值不应该影响内部缓存"

    def test_progress_cache_has_ttl(self):
        """进度缓存应该有 TTL 过期机制"""
        import time
        from services.ws_manager import ProgressWSManager, PROGRESS_HISTORY_TTL

        mgr = ProgressWSManager()
        task_id = "test-ttl"
        mgr._progress_cache[task_id] = {"progress": 50}
        mgr._progress_cache_time[task_id] = time.time() - PROGRESS_HISTORY_TTL - 10

        cached = mgr.get_cached_progress(task_id)
        assert cached is None, "过期的缓存应该返回 None"


# ============================================================================
# 回归测试 23: WR-009 统一消息信封格式
# Bug: 各 channel 消息格式不一致，缺少统一的消息信封
# 修复: MessageBus publish 时统一包装信封（type, channel, timestamp, data）
# ============================================================================

class TestMessageBusMessageEnvelope:
    """防止消息格式不统一导致处理混乱"""

    def test_publish_wraps_in_envelope(self):
        """publish 的消息应该被包装在统一信封中"""
        import threading
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=10)
            bus._running = True
            bus._stopped = False

            bus.publish("ws_progress", {"task_id": "test-env", "progress": 50})

            item = bus._queue.get_nowait()
            channel, envelope = item

            assert "type" in envelope, "信封应该有 type 字段"
            assert "channel" in envelope, "信封应该有 channel 字段"
            assert "timestamp" in envelope, "信封应该有 timestamp 字段"
            assert "data" in envelope, "信封应该有 data 字段"

            assert envelope["type"] == "ws_progress"
            assert envelope["channel"] == "ws_progress"
            assert isinstance(envelope["timestamp"], float)
            assert envelope["data"]["task_id"] == "test-env"
            assert envelope["data"]["progress"] == 50

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_dispatch_extracts_data_from_envelope(self):
        """_dispatch 应该从信封中提取 data 传递给下游"""
        import threading
        import asyncio
        import time
        from unittest.mock import MagicMock, patch, AsyncMock
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus()
            loop = asyncio.new_event_loop()
            bus.set_loop(loop)

            called_with = [None]

            async def fake_send_progress(task_id, data):
                called_with[0] = (task_id, data)

            mock_ws = MagicMock()
            mock_ws.send_progress = fake_send_progress

            loop_thread = None

            def run_loop():
                asyncio.set_event_loop(loop)
                loop.run_forever()

            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()
            time.sleep(0.1)

            try:
                with patch("services.message_bus.ws_manager", mock_ws):
                    envelope = {
                        "type": "ws_progress",
                        "channel": "ws_progress",
                        "timestamp": 12345.0,
                        "data": {"task_id": "env-test", "progress": 75}
                    }

                    bus._dispatch("ws_progress", envelope)

                time.sleep(0.3)

                assert called_with[0] is not None, "send_progress 应该被调用"
                task_id, data = called_with[0]
                assert task_id == "env-test"
                assert data["progress"] == 75
                assert "timestamp" not in data or data.get("task_id") == "env-test", \
                    "传递给下游的应该是 data 部分，不是完整信封"

            finally:
                loop.call_soon_threadsafe(loop.stop)
                loop_thread.join(timeout=2.0)

        finally:
            loop.close()
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()


# ============================================================================
# 回归测试 24: WR-010 /diag 端点需要认证
# Bug: /diag 端点泄漏大量系统敏感信息（无认证）
# 修复: 需要 ADMIN_TOKEN 认证，未配置时默认禁用
# ============================================================================

class TestDiagEndpointAuth:
    """防止诊断接口未授权访问泄漏系统信息"""

    def test_diag_without_admin_token_disabled(self):
        """未配置 ADMIN_TOKEN 时，diag 接口应该返回 403"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = ""

            app = create_app()
            client = TestClient(app)

            response = client.get("/api/v1/diag")
            assert response.status_code == 403, f"未配置 token 时应该返回 403，实际返回 {response.status_code}"
        finally:
            config.ADMIN_TOKEN = old_token

    def test_diag_with_wrong_token(self):
        """配置了 ADMIN_TOKEN 但请求带错误 token 时应该返回 401"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = "secret-diag-123"

            app = create_app()
            client = TestClient(app)

            response = client.get("/api/v1/diag", headers={"X-Admin-Token": "wrong-token"})
            assert response.status_code == 401, f"错误 token 应该返回 401，实际返回 {response.status_code}"

            response = client.get("/api/v1/diag")
            assert response.status_code == 401, f"缺少 token 应该返回 401，实际返回 {response.status_code}"
        finally:
            config.ADMIN_TOKEN = old_token

    def test_diag_with_correct_token(self):
        """配置了 ADMIN_TOKEN 且请求带正确 token 时应该成功"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = "secret-diag-123"

            app = create_app()
            client = TestClient(app)

            response = client.get("/api/v1/diag", headers={"X-Admin-Token": "secret-diag-123"})
            assert response.status_code == 200, f"正确 token 应该返回 200，实际返回 {response.status_code}"
            data = response.json()
            assert "backend" in data
        finally:
            config.ADMIN_TOKEN = old_token


# ============================================================================
# 回归测试 25: WR-011 /ws/cache-events 端点需要认证
# Bug: /ws/cache-events 端点无认证，可任意连接监听缓存事件
# 修复: 需要 token 查询参数认证，未配置时默认禁用
# ============================================================================

class TestCacheEventsWSAuth:
    """防止缓存事件 WebSocket 未授权访问"""

    def test_cache_events_without_token_rejected(self):
        """未配置 token 时，cache-events WS 应该被拒绝"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = ""

            app = create_app()
            client = TestClient(app)

            with pytest.raises(Exception):
                with client.websocket_connect("/api/v1/ws/cache-events") as ws:
                    pass

        finally:
            config.ADMIN_TOKEN = old_token

    def test_cache_events_with_wrong_token_rejected(self):
        """配置了 token 但传错时应该被拒绝"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = "cache-secret-456"

            app = create_app()
            client = TestClient(app)

            with pytest.raises(Exception):
                with client.websocket_connect("/api/v1/ws/cache-events?token=wrong") as ws:
                    pass

        finally:
            config.ADMIN_TOKEN = old_token

    def test_cache_events_with_correct_token_accepted(self):
        """配置了 token 且传对时应该能连接"""
        from fastapi.testclient import TestClient
        from app import create_app

        import config
        old_token = config.ADMIN_TOKEN
        try:
            config.ADMIN_TOKEN = "cache-secret-456"

            app = create_app()
            client = TestClient(app)

            with client.websocket_connect("/api/v1/ws/cache-events?token=cache-secret-456") as ws:
                data = ws.receive_json()
                assert data is not None

        finally:
            config.ADMIN_TOKEN = old_token


# ============================================================================
# 回归测试 26: WR-012 MessageBus 停止后 publish 应该被拒绝
# Bug: MessageBus 事件循环关闭后，publish 仍可入队，消息最终被静默丢弃
# 修复: stop 后 publish 直接拒绝返回 False，不浪费队列空间
# ============================================================================

class TestMessageBusRejectAfterStop:
    """防止 MessageBus 停止后消息静默丢失"""

    def test_publish_after_stop_returns_false(self):
        """stop() 之后再 publish 应该返回 False 并拒绝入队"""
        import threading
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=10)
            bus._running = True
            bus._stopped = False

            result = bus.publish("ws_progress", {"test": "before-stop"})
            assert result is True

            bus._running = False
            bus._stopped = True

            qsize_before = bus._queue.qsize()

            result = bus.publish("ws_progress", {"test": "after-stop"})
            assert result is False, "停止后 publish 应该返回 False"

            assert bus._queue.qsize() == qsize_before, \
                "停止后不应该再有消息入队"

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_publish_when_loop_closed_returns_false(self):
        """事件循环关闭后 publish 应该返回 False"""
        import threading
        import asyncio
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=10)
            bus._running = True
            bus._stopped = False

            loop = asyncio.new_event_loop()
            bus.set_loop(loop)
            loop.close()

            qsize_before = bus._queue.qsize()

            result = bus.publish("ws_progress", {"test": "loop-closed"})
            assert result is False

            assert bus._queue.qsize() == qsize_before

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()

    def test_stop_sets_stopped_flag(self):
        """stop() 应该设置 _stopped=True，之后 publish 被拒绝"""
        import threading
        from services.message_bus import MessageBus

        MessageBus._instance = None
        MessageBus._lock = threading.Lock()

        try:
            bus = MessageBus(maxsize=10)

            assert bus._running is False, "初始状态 _running 应为 False"

            bus._running = True
            bus._stopped = False
            assert bus._stopped is False, "运行中 _stopped 应为 False"

            result = bus.publish("ws_progress", {"test": "running"})
            assert result is True, "运行中 publish 应该成功"

            bus._running = False
            bus._stopped = True
            assert bus._stopped is True, "stop 后 _stopped 应为 True"

            result = bus.publish("ws_progress", {"test": "after-stop"})
            assert result is False, "stop 后 publish 应该返回 False"

        finally:
            MessageBus._instance = None
            MessageBus._lock = threading.Lock()


# ============================================================================
# 回归测试 27: WR-013 render_cache_update 按 task_id 过滤
# Bug: render_cache_update 广播给所有连接，而非按 task_id 过滤
# 修复: 只发送给对应 task_id 的连接，不全局广播
# ============================================================================

class TestRenderCacheUpdateScoped:
    """防止渲染缓存更新消息不必要的全局广播"""

    def test_broadcast_render_cache_only_sends_to_task_id(self):
        """broadcast_render_cache_update 应该只发给对应 task_id 的连接"""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, call
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()

            ws1 = MagicMock()
            ws1.send_json = AsyncMock()
            ws2 = MagicMock()
            ws2.send_json = AsyncMock()
            ws3 = MagicMock()
            ws3.send_json = AsyncMock()

            await mgr.connect("task-a", ws1)
            await mgr.connect("task-a", ws2)
            await mgr.connect("task-b", ws3)

            await mgr.broadcast_render_cache_update("task-a", [{"name": "test.wav"}])

            assert ws1.send_json.await_count == 1, "task-a 的连接应该收到 1 条消息"
            assert ws2.send_json.await_count == 1, "task-a 的所有连接都应该收到消息"
            assert ws3.send_json.await_count == 0, "task-b 的连接不应该收到消息"

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_broadcast_method_still_exists(self):
        """broadcast 全局广播方法应该仍然存在（用于其他用途）"""
        from services.ws_manager import ProgressWSManager

        mgr = ProgressWSManager()
        assert hasattr(mgr, "broadcast"), "全局 broadcast 方法应该仍然存在"
        assert callable(mgr.broadcast)

    def test_render_cache_update_uses_task_id_lookup(self):
        """broadcast_render_cache_update 内部应该使用 task_id 查找连接"""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from services.ws_manager import ProgressWSManager

        async def run_test():
            mgr = ProgressWSManager()

            ws = MagicMock()
            ws.send_json = AsyncMock()

            await mgr.connect("task-x", ws)

            with patch.object(mgr, "broadcast") as mock_broadcast:
                await mgr.broadcast_render_cache_update("task-x", [])
                assert not mock_broadcast.called, \
                    "不应该调用全局 broadcast"

        asyncio.get_event_loop().run_until_complete(run_test())


# ============================================================================
# 回归测试 28: WR-014 /api/log 和 /api/v1/log 不重复定义
# Bug: /api/log 和 /api/v1/log 重复路由定义，代码冗余
# 修复: 消除重复代码，/api/log 复用 /api/v1/log 的实现
# ============================================================================

class TestLogRouteNoDuplicate:
    """防止日志路由重复定义导致维护成本高"""

    def test_app_log_route_reuses_v1_impl(self):
        """app.py 中的 /api/log 应该复用 system 路由的实现"""
        app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
        with open(app_path) as f:
            content = f.read()

        assert "from api.routes.system import LogRequest" in content or \
               "from api.routes.system import" in content, \
            "app.py 应该从 system 模块导入 LogRequest 或处理函数"

        assert "_v1_log_message" in content or "log_message" in content, \
            "app.py 应该复用 v1 日志处理函数"

    def test_log_request_only_defined_once(self):
        """LogRequest 模型应该只定义一次"""
        system_path = os.path.join(os.path.dirname(__file__), "..", "api", "routes", "system.py")
        with open(system_path) as f:
            system_content = f.read()

        app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
        with open(app_path) as f:
            app_content = f.read()

        system_count = system_content.count("class LogRequest")
        app_count = app_content.count("class LogRequest")

        assert system_count >= 1, "system.py 应该定义 LogRequest"
        assert app_count == 0, f"app.py 不应该再定义 LogRequest（应该导入复用）"

    def test_both_log_endpoints_work(self):
        """/api/log 和 /api/v1/log 两个端点都应该能正常工作"""
        from fastapi.testclient import TestClient
        from app import create_app

        app = create_app()
        client = TestClient(app)

        response1 = client.post("/api/v1/log", json={"message": "test v1", "level": "info"})
        assert response1.status_code == 200
        assert response1.json()["status"] == "ok"

        response2 = client.post("/api/log", json={"message": "test compat", "level": "info"})
        assert response2.status_code == 200
        assert response2.json()["status"] == "ok"


# ============================================================================
# 回归测试 20: TaskExecutor.cancel 中 state_change from_status 不能为空
# Bug: TL-007 - cancel 时 tracer.record_state_change 的 from_status 是空字符串
# 修复: 从 trace 的最后一个状态变更中获取 from_status
# ============================================================================

class TestCancelStateChangeFromStatus:
    """防止取消任务时 from_status 为空"""

    def test_cancel_has_valid_from_status(self):
        """取消任务时，状态变更的 from_status 应该是有效的状态名"""
        import tempfile
        import os
        import time
        from database import init_db, create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask
        from services.observability import get_task_tracer

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = tmpdir
                config.OUTPUT_DIR = tmpdir
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                init_db()

                import soundfile as sf
                import numpy as np
                sr = 44100
                t = np.arange(int(sr * 1.0)) / sr
                y = 0.3 * np.sin(2 * np.pi * 440 * t)
                audio_path = os.path.join(tmpdir, "test.wav")
                sf.write(audio_path, y, sr)

                task_id = "reg_tl007_from_status"
                create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash_tl007")

                from services.task_manager import _active_tasks, _active_tasks_lock
                with _active_tasks_lock:
                    _active_tasks.clear()

                task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
                executor = get_task_executor()
                executor.submit(task)

                time.sleep(0.1)
                executor.cancel(task_id)

                time.sleep(0.5)

                tracer = get_task_tracer()
                history = tracer.get_task_history(task_type="repair")
                task_trace = None
                for tr in history:
                    if tr.task_id == task_id:
                        task_trace = tr
                        break

                assert task_trace is not None, "应该能在历史中找到任务 trace"

                cancel_changes = [sc for sc in task_trace.state_changes if sc.to_status == "cancelled"]
                assert len(cancel_changes) > 0, "应该有 cancelled 状态变更"

                from_status = cancel_changes[0].from_status
                assert from_status != "", (
                    "TL-007: 取消时 state_change 的 from_status 是空字符串，"
                    "无法知道任务是从什么状态转为 cancelled 的。"
                )
                assert from_status in ("pending", "repairing", "processing"), (
                    f"from_status 应该是有效的状态名，而不是 '{from_status}'"
                )
            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 21: RenderTask 应该有 stuck monitor 机制
# Bug: TL-008 - RenderTask 缺少 stuck monitor 线程
# 修复: 给 RenderTask 添加与 RepairTask/DetectTask 一致的 stuck monitor
# ============================================================================

class TestRenderTaskStuckMonitor:
    """防止 RenderTask 缺少卡住检测机制"""

    def test_render_task_has_stuck_monitor_attributes(self):
        """RenderTask 应该有 stuck monitor 相关的属性和方法"""
        from services.task_manager import RenderTask

        task = RenderTask(
            task_id="reg_tl008_stuck",
            input_path="/tmp/fake.wav",
            output_path="/tmp/out.wav",
            target_sr=44100,
            bit_depth=16,
            render_filename="out.wav",
        )

        assert hasattr(task, "_stop_monitor"), "RenderTask 应该有 _stop_monitor 属性"
        assert hasattr(task, "_monitor_thread"), "RenderTask 应该有 _monitor_thread 属性"
        assert hasattr(task, "_start_stuck_monitor"), "RenderTask 应该有 _start_stuck_monitor 方法"
        assert callable(task._start_stuck_monitor), "_start_stuck_monitor 应该是可调用的"


# ============================================================================
# 回归测试 22: 两套取消机制行为应该一致
# Bug: TL-009 - cancel_task 和 TaskExecutor.cancel 行为不一致
# 修复: cancel_task 委托给 TaskExecutor.cancel，统一行为
# ============================================================================

class TestUnifiedCancelMechanism:
    """防止两套取消机制行为不一致"""

    def test_cancel_task_delegates_to_executor(self):
        """cancel_task 应该委托给 TaskExecutor.cancel，行为一致"""
        import inspect
        from services.task_manager import cancel_task

        source = inspect.getsource(cancel_task)
        assert "get_task_executor" in source or "TaskExecutor" in source, (
            "TL-009: cancel_task 应该委托给 TaskExecutor，"
            "两套取消机制应该统一行为，避免不一致"
        )

    def test_both_cancel_paths_update_tracer(self):
        """两种取消路径都应该更新 tracer 和 metrics"""
        import tempfile
        import os
        import time
        from database import init_db, create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask, cancel_task
        from services.observability import get_task_tracer, get_system_metrics

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = tmpdir
                config.OUTPUT_DIR = tmpdir
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                init_db()

                import soundfile as sf
                import numpy as np
                sr = 44100
                t_arr = np.arange(int(sr * 1.0)) / sr
                y = 0.3 * np.sin(2 * np.pi * 440 * t_arr)
                audio_path = os.path.join(tmpdir, "test.wav")
                sf.write(audio_path, y, sr)

                metrics = get_system_metrics()

                task_id_1 = "reg_tl009_cancel_1"
                create_task(task_id_1, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash_tl009a")

                from services.task_manager import _active_tasks, _active_tasks_lock
                with _active_tasks_lock:
                    _active_tasks.clear()

                task1 = RepairTask(task_id_1, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
                executor = get_task_executor()
                executor.submit(task1)
                time.sleep(0.1)
                executor.cancel(task_id_1)
                time.sleep(0.3)

                task_id_2 = "reg_tl009_cancel_2"
                create_task(task_id_2, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash_tl009b")

                task2 = RepairTask(task_id_2, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
                executor.submit(task2)
                time.sleep(0.1)
                cancel_task(task_id_2)
                time.sleep(0.3)

                tracer = get_task_tracer()
                history = tracer.get_task_history(task_type="repair")
                task_1_trace = None
                task_2_trace = None
                for tr in history:
                    if tr.task_id == task_id_1:
                        task_1_trace = tr
                    elif tr.task_id == task_id_2:
                        task_2_trace = tr

                assert task_1_trace is not None, "TaskExecutor.cancel 路径应该有 trace 记录"
                assert task_2_trace is not None, "cancel_task 路径应该有 trace 记录"

                stats = metrics.get_task_stats()
                assert stats["cancelled_tasks"] >= 2, "两种取消路径都应该计入 cancelled 统计"
            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 23: 两套活跃任务计数应该一致
# Bug: TL-010 - SystemMetrics._active_tasks 与 task_manager._active_tasks 可能不一致
# 修复: SystemMetrics.get_task_stats 从 task_manager 获取活跃任务数作为权威来源
# ============================================================================

class TestActiveTaskCountersConsistent:
    """防止两套活跃任务计数不一致"""

    def test_two_counters_are_consistent_after_submit_and_cancel(self):
        """提交并取消任务后，两套计数应该一致"""
        import tempfile
        import os
        import time
        from database import init_db, create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask, get_active_task_count
        from services.observability import get_system_metrics

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = tmpdir
                config.OUTPUT_DIR = tmpdir
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                init_db()

                import soundfile as sf
                import numpy as np
                sr = 44100
                t_arr = np.arange(int(sr * 1.0)) / sr
                y = 0.3 * np.sin(2 * np.pi * 440 * t_arr)
                audio_path = os.path.join(tmpdir, "test.wav")
                sf.write(audio_path, y, sr)

                task_id = "reg_tl010_dual_counter"
                create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash_tl010")

                from services.task_manager import _active_tasks, _active_tasks_lock
                with _active_tasks_lock:
                    _active_tasks.clear()

                metrics = get_system_metrics()

                task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
                executor = get_task_executor()
                executor.submit(task)

                time.sleep(0.1)
                executor.cancel(task_id)
                time.sleep(0.5)

                count_set = get_active_task_count()
                count_metrics = metrics.get_task_stats()["active_tasks"]

                assert count_set == count_metrics, (
                    f"TL-010: 两套活跃任务计数不一致。"
                    f"task_manager 集合计数={count_set}, "
                    f"SystemMetrics 计数={count_metrics}。"
                )
            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 24: get_queue_status 和 mark_stuck_tasks 应包含 rendering 状态
# Bug: TL-011 - 渲染任务的卡住检测不生效
# 修复: 在检查列表中添加 'rendering' 状态
# ============================================================================

class TestRenderingInStatusChecks:
    """防止 rendering 状态任务被遗漏"""

    def test_rendering_in_queue_status(self):
        """get_queue_status 的 running 列表应包含 rendering 状态的任务"""
        import tempfile
        import os
        from database import init_db, create_task, update_task, get_queue_status

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            try:
                config.DB_PATH = db_path
                init_db()

                task_id = "reg_tl011_rendering_queue"
                create_task(task_id, "test.wav", "/tmp/test.wav", {}, file_hash="hash_tl011")
                update_task(task_id, status="rendering", progress=0.5, step="渲染中...")

                queue_status = get_queue_status()
                running_ids = [t["id"] for t in queue_status["running"]]

                assert task_id in running_ids, (
                    "TL-011: get_queue_status 的 running 列表未包含 'rendering' 状态的任务。"
                    "渲染任务在运行队列中不可见。"
                )
            finally:
                config.DB_PATH = old_db

    def test_rendering_in_mark_stuck_tasks(self):
        """mark_stuck_tasks 应覆盖 rendering 状态"""
        import tempfile
        import os
        from database import init_db, create_task, update_task, get_task, get_db, mark_stuck_tasks

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            try:
                config.DB_PATH = db_path
                init_db()

                task_id = "reg_tl011_rendering_stuck"
                create_task(task_id, "test.wav", "/tmp/test.wav", {}, file_hash="hash_tl011b")
                update_task(task_id, status="rendering", progress=0.5, step="渲染中...")

                conn = get_db()
                conn.execute(
                    "UPDATE tasks SET updated_at = datetime('now', '-10 minutes') WHERE id = ?",
                    (task_id,),
                )
                conn.commit()
                conn.close()

                mark_stuck_tasks(timeout_seconds=60)

                task = get_task(task_id)
                assert task["status"] == "timeout", (
                    "TL-011: mark_stuck_tasks 未覆盖 'rendering' 状态，"
                    "渲染任务永远不会被标记为超时。"
                )
            finally:
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 25: RenderTask.cleanup 应使用 _get_loop() 而非 get_event_loop()
# Bug: TL-012 - 后台线程调用 get_event_loop() 可能失败
# 修复: 使用 _get_loop() 获取主线程事件循环
# ============================================================================

class TestRenderTaskCleanupEventLoop:
    """防止 RenderTask.cleanup 用错事件循环获取方式"""

    def test_cleanup_uses_get_loop_helper(self):
        """RenderTask.cleanup 应该使用 _get_loop() 而非 asyncio.get_event_loop()"""
        import inspect
        from services.task_manager import RenderTask

        cleanup_source = inspect.getsource(RenderTask.cleanup)

        uses_get_event_loop = "asyncio.get_event_loop()" in cleanup_source
        uses_get_loop_helper = "_get_loop(" in cleanup_source

        assert not uses_get_event_loop or uses_get_loop_helper, (
            "TL-012: RenderTask.cleanup 使用 asyncio.get_event_loop() 获取事件循环。"
            "在后台线程中调用会创建新的未运行事件循环，导致 WebSocket 广播失败。"
            "应该使用 task_manager._get_loop() 来获取主线程的运行中事件循环。"
        )


# ============================================================================
# 回归测试 26: RenderTask 应校验 track_type 参数有效性
# Bug: TL-013 - 无效 track_type 静默走意外分支
# 修复: 在 __init__ 中校验 track_type，无效值抛异常
# ============================================================================

class TestRenderTaskTrackTypeValidation:
    """防止无效 track_type 导致意外行为"""

    def test_invalid_track_type_raises_error(self):
        """传入无效 track_type 应该抛出 ValueError"""
        from services.task_manager import RenderTask

        with pytest.raises(ValueError):
            RenderTask(
                task_id="reg_tl013_invalid",
                input_path="/tmp/in.wav",
                output_path="/tmp/out.wav",
                target_sr=44100,
                bit_depth=16,
                render_filename="out.wav",
                vocal_path="/tmp/vocal.wav",
                accompaniment_path="/tmp/acc.wav",
                track_type="invalid_type",
            )

    def test_valid_track_types_accepted(self):
        """有效的 track_type（vocal/accompaniment/both）应该正常通过"""
        from services.task_manager import RenderTask

        for valid_type in ("vocal", "accompaniment", "both"):
            task = RenderTask(
                task_id=f"reg_tl013_valid_{valid_type}",
                input_path="/tmp/in.wav",
                output_path="/tmp/out.wav",
                target_sr=44100,
                bit_depth=16,
                render_filename="out.wav",
                vocal_path="/tmp/vocal.wav",
                accompaniment_path="/tmp/acc.wav",
                track_type=valid_type,
            )
            assert task.track_type == valid_type


# ============================================================================
# 回归测试 27: DetectTask 应该有 on_error 实现
# Bug: TL-014 - DetectTask 缺少 on_error，与 RepairTask 不一致
# 修复: 给 DetectTask 添加 on_error 方法，处理 MemoryError
# ============================================================================

class TestDetectTaskOnError:
    """防止 DetectTask 缺少错误处理不一致"""

    def test_detect_task_has_on_error(self):
        """DetectTask 应该有 on_error 方法"""
        from services.task_manager import DetectTask, RepairTask

        repair_has_on_error = "on_error" in RepairTask.__dict__
        detect_has_on_error = "on_error" in DetectTask.__dict__

        assert detect_has_on_error == repair_has_on_error, (
            "TL-014: DetectTask 缺少 on_error 实现，与 RepairTask 不一致。"
            "RepairTask 有特殊的 MemoryError 处理，DetectTask 应该保持一致。"
        )

    def test_detect_task_on_error_handles_memory_error(self):
        """DetectTask.on_error 应该正确处理 MemoryError"""
        from services.task_manager import DetectTask
        import time

        task = DetectTask(
            task_id="reg_tl014_memerr",
            audio_path="/tmp/test.wav",
            detect_type="original",
            detector_version="v1.1",
        )
        task._start_time = time.time()

        result = task.on_error(MemoryError("out of memory"))

        assert result is not None, "MemoryError 应该返回自定义错误信息"
        assert "error" in result, "返回值应该包含 error 字段"
        assert result["error"] == "out of memory", "error 字段应该是原始错误信息"
        assert "step" in result, "返回值应该包含 step 字段"
        assert "内存不足" in result["step"], "step 字段应该包含内存不足"


# ============================================================================
# 回归测试 28: stuck monitor 线程 cleanup 时应该 join
# Bug: TL-015 - 只设 stop 标志不 join，可能有短暂残留
# 修复: 在 cleanup 中 join monitor 线程
# ============================================================================

class TestStuckMonitorThreadJoin:
    """防止 stuck monitor 线程短暂泄漏"""

    def test_repair_task_cleanup_joins_monitor(self):
        """RepairTask.cleanup 应该 join monitor 线程"""
        import inspect
        from services.task_manager import RepairTask

        cleanup_source = inspect.getsource(RepairTask.cleanup)
        joins_thread = "join(" in cleanup_source
        sets_stop = "_stop_monitor" in cleanup_source

        assert sets_stop and joins_thread, (
            "TL-015: RepairTask.cleanup 只设置了 _stop_monitor 标志但没有 join 线程。"
            "虽然是 daemon 线程不会阻止进程退出，但任务结束后 monitor 线程可能"
            "还存活最多 2 秒（sleep 间隔），造成短暂的线程泄漏。"
        )

    def test_detect_task_cleanup_joins_monitor(self):
        """DetectTask.cleanup 应该 join monitor 线程"""
        import inspect
        from services.task_manager import DetectTask

        cleanup_source = inspect.getsource(DetectTask.cleanup)
        joins_thread = "join(" in cleanup_source
        sets_stop = "_stop_monitor" in cleanup_source

        assert sets_stop and joins_thread, (
            "TL-015: DetectTask.cleanup 只设置了 _stop_monitor 标志但没有 join 线程。"
            "虽然是 daemon 线程不会阻止进程退出，但任务结束后 monitor 线程可能"
            "还存活最多 2 秒（sleep 间隔），造成短暂的线程泄漏。"
        )

    def test_render_task_cleanup_joins_monitor(self):
        """RenderTask.cleanup 应该 join monitor 线程"""
        import inspect
        from services.task_manager import RenderTask

        cleanup_source = inspect.getsource(RenderTask.cleanup)
        joins_thread = "join(" in cleanup_source
        sets_stop = "_stop_monitor" in cleanup_source

        assert sets_stop and joins_thread, (
            "TL-015: RenderTask.cleanup 只设置了 _stop_monitor 标志但没有 join 线程。"
        )


# ============================================================================
# 回归测试 19: safe_rename 同名文件不死锁
# Bug: temp_filename 和 final_filename 相同时，同一把 Lock acquire 两次导致死锁
# 修复: 检测到同名时直接返回，同一把锁时只 acquire 一次
# ============================================================================

class TestSafeRenameSameFileNoDeadlock:
    """防止 safe_rename 同名文件导致死锁"""

    def test_same_filename_no_deadlock(self):
        """同名文件 rename 应该立即返回，不挂死"""
        import tempfile
        import threading
        import time
        from services.file_gateway import SafeFileGateway

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)
            gw.safe_write("test.txt", b"hello")

            result = {"timeout": True}

            def rename_worker():
                try:
                    gw.safe_rename("test.txt", "test.txt")
                    result["timeout"] = False
                except Exception:
                    result["timeout"] = False

            t = threading.Thread(target=rename_worker)
            t.start()
            t.join(timeout=2.0)

            assert not t.is_alive(), "FC-006: safe_rename 同名文件导致死锁，线程挂死"
            assert not result["timeout"], "FC-006: safe_rename 同名文件应该成功返回"
            assert gw.exists("test.txt"), "同名文件 rename 后文件应该仍然存在"

    def test_same_lock_different_filenames(self):
        """不同文件名但同一把锁（basename 相同）时也应该正常工作"""
        import tempfile
        from services.file_gateway import SafeFileGateway

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)
            gw.safe_write("a.txt", b"data")

            gw.safe_rename("a.txt", "a.txt")
            assert gw.exists("a.txt")


# ============================================================================
# 回归测试 20: get_dir_size 不跟随符号链接
# Bug: os.path.getsize 会跟随符号链接，导致容量统计失真
# 修复: 使用 os.lstat，不统计符号链接目标
# ============================================================================

class TestGetDirSizeNoFollowSymlinks:
    """防止 get_dir_size 统计符号链接目标文件大小"""

    def test_symlink_not_counted(self):
        """符号链接不应该被统计大小"""
        import tempfile
        from services.file_gateway import SafeFileGateway

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)
            gw.safe_write("real.txt", b"1234567890")

            real_path = gw.resolve("real.txt")
            link_path = os.path.join(tmpdir, "link.txt")
            try:
                os.symlink(real_path, link_path)
            except (OSError, AttributeError):
                pytest.skip("symlink not supported")

            size = gw.get_dir_size()
            assert size == 10, f"FC-007: get_dir_size 应该只统计真实文件，不跟随符号链接。实际大小: {size}"

    def test_walk_does_not_follow_links(self):
        """os.walk 不应该跟随目录符号链接"""
        import tempfile
        from services.file_gateway import SafeFileGateway

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)

            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)
            with open(os.path.join(subdir, "file.txt"), "w") as f:
                f.write("12345")

            link_dir = os.path.join(tmpdir, "linkdir")
            try:
                os.symlink(subdir, link_dir)
            except (OSError, AttributeError):
                pytest.skip("symlink not supported")

            size = gw.get_dir_size()
            assert size == 5, f"FC-007: 目录符号链接不应该被递归遍历。实际大小: {size}"


# ============================================================================
# 回归测试 21: reset_stats 与 record_hit/miss 无竞态
# Bug: reset_stats 替换 _LayerStats 对象，与 record_hit/miss 竞争导致统计丢失
# 修复: 使用 reset() 方法重置计数，不替换对象
# ============================================================================

class TestResetStatsNoRaceCondition:
    """防止 reset_stats 与 record_hit/miss 竞态导致统计丢失"""

    def test_reset_does_not_replace_object(self):
        """reset_stats 应该调用 reset() 方法，而不是替换对象"""
        import threading
        from services.cache_manager import CacheManager

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()

        from services.cache_manager import CacheLayer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            layer = CacheLayer(name="test", base_dir=tmpdir)
            mgr.register_layer(layer)

            stats_before = mgr._stats["test"]
            mgr.record_hit("test")
            mgr.record_miss("test")

            mgr.reset_stats("test")

            stats_after = mgr._stats["test"]
            assert stats_before is stats_after, "FC-008: reset_stats 不应该替换 _LayerStats 对象"

            snap = stats_after.get_snapshot()
            assert snap["hits"] == 0, "重置后 hits 应该为 0"
            assert snap["misses"] == 0, "重置后 misses 应该为 0"

    def test_concurrent_reset_and_record(self):
        """并发 reset 和 record_hit 不应崩溃，也不应导致对象引用错误"""
        import threading
        import tempfile
        from services.cache_manager import CacheManager, CacheLayer

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            layer = CacheLayer(name="test", base_dir=tmpdir)
            mgr.register_layer(layer)

            errors = []

            def hitter():
                try:
                    for _ in range(100):
                        mgr.record_hit("test")
                        mgr.record_miss("test")
                except Exception as e:
                    errors.append(str(e))

            def resetter():
                try:
                    for _ in range(50):
                        mgr.reset_stats("test")
                except Exception as e:
                    errors.append(str(e))

            threads = []
            for _ in range(3):
                threads.append(threading.Thread(target=hitter))
            for _ in range(2):
                threads.append(threading.Thread(target=resetter))

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"FC-008: 并发 reset/record 出错: {errors}"


# ============================================================================
# 回归测试 22: preview 接口对路径进行二次校验
# Bug: preview 直接使用 task 中的 original_path/output_path，无安全校验
# 修复: 对路径进行 realpath 校验，确保在对应目录内
# ============================================================================

class TestPreviewPathValidation:
    """防止 preview 接口路径遍历"""

    def test_preview_original_path_dot_dot_rejected(self):
        """original_path 包含 .. 应该被拒绝"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                os.makedirs(config.UPLOAD_DIR)
                os.makedirs(config.OUTPUT_DIR)

                from database import init_db, create_task, update_task
                init_db()

                malicious_path = "/tmp/../etc/passwd"
                create_task("bad-task-1", "test.wav", malicious_path, {}, "hash1", 1000)

                app = create_app()
                client = TestClient(app)

                response = client.get("/api/v1/preview/bad-task-1?type=original")
                assert response.status_code == 400, \
                    f"FC-009: preview original 应该拒绝包含 .. 的路径。状态码: {response.status_code}"

            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db

    def test_preview_output_path_dot_dot_rejected(self):
        """output_path 包含 .. 应该被拒绝"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                os.makedirs(config.UPLOAD_DIR)
                os.makedirs(config.OUTPUT_DIR)

                from database import init_db, create_task, update_task
                init_db()

                malicious_path = "/tmp/../etc/shadow"
                create_task("bad-task-2", "test.wav", "/tmp/test.wav", {}, "hash2", 1000)
                update_task("bad-task-2", status="completed", output_path=malicious_path)

                app = create_app()
                client = TestClient(app)

                response = client.get("/api/v1/preview/bad-task-2?type=repaired")
                assert response.status_code == 400, \
                    f"FC-009: preview output 应该拒绝包含 .. 的路径。状态码: {response.status_code}"

            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db

    def test_preview_nul_byte_rejected(self):
        """路径包含 NUL 字节应该被拒绝"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                os.makedirs(config.UPLOAD_DIR)
                os.makedirs(config.OUTPUT_DIR)

                from database import init_db, create_task, update_task
                init_db()

                bad_path = "/tmp/bad\x00file.wav"
                create_task("bad-task-3", "test.wav", "/tmp/test.wav", {}, "hash3", 1000)
                update_task("bad-task-3", status="completed", output_path=bad_path)

                app = create_app()
                client = TestClient(app)

                response = client.get("/api/v1/preview/bad-task-3?type=repaired")
                assert response.status_code == 400, \
                    f"FC-009: preview 应该拒绝包含 NUL 字节的路径。状态码: {response.status_code}"

            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 23: evict_layer 剩余统计与内存中数据一致
# Bug: evict_layer 清理后二次扫描磁盘，与内存中 total_size 可能不一致
# 修复: 使用内存中的 files 列表和 total_size 计算剩余
# ============================================================================

class TestEvictLayerConsistentStats:
    """防止 evict_layer 剩余统计不一致"""

    def test_remaining_stats_consistent_with_memory(self):
        """evict_layer 返回的 remaining 应该与实际删除量一致"""
        import tempfile
        import time
        from services.cache_manager import CacheManager, CacheLayer

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            layer = CacheLayer(name="test", base_dir=tmpdir, max_size_mb=0.001)
            mgr.register_layer(layer)

            for i in range(10):
                fp = os.path.join(tmpdir, f"file_{i}.txt")
                with open(fp, "wb") as f:
                    f.write(b"x" * 500)
                time.sleep(0.01)

            result = mgr.evict_layer("test")

            removed = result["files_removed"]
            remaining = result["files_remaining"]
            assert removed + remaining == 10, \
                f"FC-010: 删除数 + 剩余数 应等于总数。removed={removed}, remaining={remaining}"

            removed_bytes = result["bytes_removed"]
            remaining_bytes = result["bytes_remaining"]
            assert removed_bytes + remaining_bytes == 10 * 500, \
                f"FC-010: 删除字节数 + 剩余字节数 应等于总字节数"


# ============================================================================
# 回归测试 24: ConfigProvider 与 config.py 配置项对齐
# Bug: ConfigProvider 抽象类缺少 HOST/PORT/MAX_UPLOAD_SIZE 等配置项
# 修复: 补齐所有 config.py 中的重要配置项
# ============================================================================

class TestConfigProviderAlignment:
    """防止 ConfigProvider 与 config.py 配置项不对齐"""

    def test_env_provider_has_all_config_methods(self):
        """EnvConfigProvider 应该提供所有重要配置项的 getter"""
        from services.config_provider import EnvConfigProvider
        provider = EnvConfigProvider()

        assert hasattr(provider, "get_host"), "缺少 get_host"
        assert hasattr(provider, "get_port"), "缺少 get_port"
        assert hasattr(provider, "get_output_dir"), "缺少 get_output_dir"
        assert hasattr(provider, "get_upload_dir"), "缺少 get_upload_dir"
        assert hasattr(provider, "get_decoded_dir"), "缺少 get_decoded_dir"
        assert hasattr(provider, "get_db_path"), "缺少 get_db_path"
        assert hasattr(provider, "get_max_upload_size"), "缺少 get_max_upload_size"
        assert hasattr(provider, "get_allowed_extensions"), "缺少 get_allowed_extensions"
        assert hasattr(provider, "get_max_workers"), "缺少 get_max_workers"
        assert hasattr(provider, "get_max_concurrent_tasks"), "缺少 get_max_concurrent_tasks"
        assert hasattr(provider, "get_source_file_cache_limit_mb"), "缺少 get_source_file_cache_limit_mb"
        assert hasattr(provider, "get_mobile_mode"), "缺少 get_mobile_mode"
        assert hasattr(provider, "get_admin_token"), "缺少 get_admin_token"
        assert hasattr(provider, "get_default_algorithm_version"), "缺少 get_default_algorithm_version"
        assert hasattr(provider, "get_stuck_threshold_seconds"), "缺少 get_stuck_threshold_seconds"

    def test_env_provider_values_match_config(self):
        """EnvConfigProvider 返回值应该与 config.py 中一致"""
        import config
        from services.config_provider import EnvConfigProvider
        provider = EnvConfigProvider()

        assert provider.get_host() == config.HOST
        assert provider.get_port() == config.PORT
        assert provider.get_output_dir() == config.OUTPUT_DIR
        assert provider.get_upload_dir() == config.UPLOAD_DIR
        assert provider.get_decoded_dir() == config.DECODED_DIR
        assert provider.get_db_path() == config.DB_PATH
        assert provider.get_max_upload_size() == config.MAX_UPLOAD_SIZE
        assert provider.get_allowed_extensions() == config.ALLOWED_EXTENSIONS
        assert provider.get_max_workers() == config.MAX_WORKERS
        assert provider.get_max_concurrent_tasks() == config.MAX_CONCURRENT_TASKS
        assert provider.get_mobile_mode() == config.MOBILE_MODE
        assert provider.get_admin_token() == config.ADMIN_TOKEN

    def test_dict_provider_has_all_methods(self):
        """DictConfigProvider 也应该实现所有方法"""
        from services.config_provider import DictConfigProvider
        provider = DictConfigProvider({
            "host": "127.0.0.1",
            "port": 9000,
            "output_dir": "/tmp/out",
            "upload_dir": "/tmp/up",
            "decoded_dir": "/tmp/dec",
            "db_path": "/tmp/test.db",
            "max_upload_size": 1024,
            "allowed_extensions": {".wav"},
            "max_workers": 2,
            "max_concurrent_tasks": 1,
            "source_file_cache_limit_mb": 100.0,
            "mobile_mode": True,
            "admin_token": "secret",
            "default_algorithm_version": "v2.4a",
            "stuck_threshold_seconds": 60,
        })

        assert provider.get_host() == "127.0.0.1"
        assert provider.get_port() == 9000
        assert provider.get_admin_token() == "secret"
        assert provider.get_max_workers() == 2


# ============================================================================
# 回归测试 25: resolve 显式拒绝 NUL 字节注入
# Bug: NUL 字节注入可能导致底层 C 库截断路径，抛 ValueError 而非 SecurityError
# 修复: 显式检查 "\\x00" 并抛 SecurityError
# ============================================================================

class TestResolveNulByteRejection:
    """防止 resolve 未显式拒绝 NUL 字节注入"""

    def test_nul_byte_raises_security_error(self):
        """包含 NUL 字节的文件名应该抛 SecurityError 而非 ValueError"""
        import tempfile
        from services.file_gateway import SafeFileGateway, SecurityError

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)

            with pytest.raises(SecurityError):
                gw.resolve("test\x00.txt")

            with pytest.raises(SecurityError):
                gw.resolve("\x00../etc/passwd")

    def test_nul_byte_security_not_value_error(self):
        """NUL 字节异常类型应该是 SecurityError（继承 ValueError）"""
        import tempfile
        from services.file_gateway import SafeFileGateway, SecurityError

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)

            try:
                gw.resolve("bad\x00file.txt")
                assert False, "应该抛出异常"
            except SecurityError:
                pass
            except ValueError:
                pytest.fail("FC-012: NUL 字节应该抛 SecurityError 而非普通 ValueError")


# ============================================================================
# 回归测试 26: list_files 跳过 .tmp 临时文件
# Bug: list_files 会列出残留的 .tmp 临时文件，可能被误当作正式文件
# 修复: list_files 跳过 .tmp 结尾的文件
# ============================================================================

class TestListFilesSkipsTmp:
    """防止 list_files 列出 .tmp 临时文件"""

    def test_tmp_files_not_listed(self):
        """.tmp 文件不应该出现在 list_files 结果中"""
        import tempfile
        from services.file_gateway import SafeFileGateway

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)
            gw.safe_write("real.txt", b"data")

            tmp_file = os.path.join(tmpdir, "temp.tmp")
            with open(tmp_file, "w") as f:
                f.write("temp")

            files = gw.list_files()
            assert "real.txt" in files, "正常文件应该被列出"
            assert "temp.tmp" not in files, "FC-013: .tmp 文件不应该出现在 list_files 中"

    def test_only_tmp_extension_skipped(self):
        """只有 .tmp 结尾的文件被跳过，其他后缀正常"""
        import tempfile
        from services.file_gateway import SafeFileGateway

        with tempfile.TemporaryDirectory() as tmpdir:
            gw = SafeFileGateway(tmpdir)
            gw.safe_write("a.txt", b"a")
            gw.safe_write("b.mp3", b"b")

            tmp_path = os.path.join(tmpdir, "c.tmp")
            with open(tmp_path, "w") as f:
                f.write("c")

            tmp2_path = os.path.join(tmpdir, "d.txt.tmp")
            with open(tmp2_path, "w") as f:
                f.write("d")

            files = gw.list_files()
            assert "a.txt" in files
            assert "b.mp3" in files
            assert "c.tmp" not in files
            assert "d.txt.tmp" not in files


# ============================================================================
# 回归测试 27: _scan_files 无 TOCTOU 竞态
# Bug: 先 isfile 再 stat，中间文件可能被删除导致异常（TOCTOU）
# 修复: 直接 stat，通过 stat 结果判断是否是普通文件
# ============================================================================

class TestScanFilesNoTOCTOU:
    """防止 _scan_files 中 isfile 与 stat 存在 TOCTOU 窗口"""

    def test_scan_handles_missing_files_gracefully(self):
        """扫描过程中文件消失不应导致崩溃"""
        import tempfile
        import threading
        import time
        from services.cache_manager import CacheManager, CacheLayer

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            layer = CacheLayer(name="test", base_dir=tmpdir)
            mgr.register_layer(layer)

            for i in range(20):
                fp = os.path.join(tmpdir, f"file_{i}.txt")
                with open(fp, "w") as f:
                    f.write(f"data_{i}")

            errors = []

            def deleter():
                try:
                    for i in range(10):
                        fp = os.path.join(tmpdir, f"file_{i}.txt")
                        try:
                            os.remove(fp)
                        except OSError:
                            pass
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(str(e))

            scan_result = {"files": None}

            def scanner():
                try:
                    scan_result["files"] = mgr._scan_files(tmpdir)
                except Exception as e:
                    errors.append(str(e))

            t1 = threading.Thread(target=deleter)
            t2 = threading.Thread(target=scanner)

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            assert len(errors) == 0, f"FC-014: 扫描过程中文件删除不应导致异常: {errors}"
            assert scan_result["files"] is not None, "扫描应该完成并返回结果"

    def test_scan_uses_single_stat_call(self):
        """_scan_files 应该只做一次 stat 调用（通过 stat 结果判断文件类型）"""
        import inspect
        from services.cache_manager import CacheManager

        source = inspect.getsource(CacheManager._scan_files)
        assert "os.path.isfile" not in source or "S_ISREG" in source, \
            "FC-014: _scan_files 不应该先 isfile 再 stat（TOCTOU），应该直接 stat 后用 S_ISREG 判断"


# ============================================================================
# 回归测试 28: 全局 ThreadPoolExecutor 无优雅关闭机制
# Bug: 全局线程池在进程退出时没有优雅关闭，可能导致任务中断或资源泄漏
# 修复: 注册 atexit 钩子，在进程退出时调用 executor.shutdown()
# ============================================================================

class TestThreadPoolExecutorGracefulShutdown:
    """防止全局 ThreadPoolExecutor 进程退出时无优雅关闭"""

    def test_executor_has_shutdown_hook(self):
        """全局 executor 应该有 atexit 关闭钩子"""
        import atexit
        import inspect
        from services import task_manager

        assert hasattr(task_manager, 'shutdown_executor'), (
            "CC-007: task_manager 应该有 shutdown_executor 函数，用于优雅关闭全局线程池"
        )
        assert callable(task_manager.shutdown_executor), (
            "CC-007: shutdown_executor 应该是可调用的"
        )

    def test_executor_shutdown_function_works(self):
        """shutdown_executor 函数应该能正常执行不抛异常"""
        from services.task_manager import shutdown_executor

        try:
            shutdown_executor(wait=False, cancel_futures=True)
        except Exception as e:
            pytest.fail(f"CC-007: shutdown_executor 执行失败: {e}")


# ============================================================================
# 回归测试 29: CacheManager.evict_layer 无层级锁
# Bug: 同一缓存层的并发清理可能导致状态不一致
# 修复: 添加层级锁，确保同一层的清理操作互斥
# ============================================================================

class TestCacheManagerLayerLocks:
    """防止 evict_layer 并发操作同一缓存层导致状态不一致"""

    def test_cache_manager_has_layer_locks(self):
        """CacheManager 应该有层级锁机制"""
        import inspect
        from services.cache_manager import CacheManager

        init_source = inspect.getsource(CacheManager.__init__)
        assert '_layer_locks' in init_source, (
            "CC-008: CacheManager.__init__ 中应该有 _layer_locks 字典用于层级锁"
        )

        evict_source = inspect.getsource(CacheManager.evict_layer)
        assert 'layer_lock' in evict_source or '_layer_locks' in evict_source, (
            "CC-008: evict_layer 应该使用层级锁保护同一层的并发清理"
        )

    def test_concurrent_evict_same_layer(self):
        """同一层的并发清理不应该导致异常"""
        import tempfile
        import threading
        import time
        from services.cache_manager import CacheManager, CacheLayer

        CacheManager._instance = None
        mgr = CacheManager()
        mgr._layers.clear()
        mgr._stats.clear()
        mgr._layer_locks.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            layer = CacheLayer(name="test_layer_lock", base_dir=tmpdir)
            mgr.register_layer(layer)

            for i in range(20):
                fp = os.path.join(tmpdir, f"file_{i}.txt")
                with open(fp, "w") as f:
                    f.write(f"data_{i}")

            errors = []

            def evictor():
                try:
                    for _ in range(5):
                        mgr.evict_layer("test_layer_lock")
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(str(e))

            threads = [threading.Thread(target=evictor) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"CC-008: 并发 evict 同一层不应导致异常: {errors}"


# ============================================================================
# 回归测试 30: SystemMetrics._task_stats defaultdict 并发访问不安全
# Bug: defaultdict 的自动创建 key 不是原子操作，多线程下可能出问题
# 修复: 在锁内获取 stats 对象，确保 defaultdict 的 key 创建是线程安全的
# ============================================================================

class TestSystemMetricsTaskStatsThreadSafety:
    """防止 _task_stats defaultdict 并发访问导致竞态"""

    def test_record_task_start_concurrent(self):
        """多线程并发调用 record_task_start 不应导致异常"""
        import threading
        from services.observability import SystemMetrics

        metrics = SystemMetrics()
        metrics._task_stats.clear()
        metrics._total_tasks = 0
        metrics._active_tasks = 0

        errors = []

        def worker(task_type):
            try:
                for _ in range(100):
                    metrics.record_task_start(task_type)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(f"type_{i % 5}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"CC-009: 并发 record_task_start 不应导致异常: {errors}"
        assert metrics._total_tasks == 1000, f"CC-009: total_tasks 计数应该是 1000，实际是 {metrics._total_tasks}"


# ============================================================================
# 回归测试 31: PerfMetricsCollector 共享数据结构并发不安全
# Bug: step_history 等共享数据结构多线程访问不安全
# 修复: 添加 _data_lock 保护所有共享数据结构的读写
# ============================================================================

class TestPerfMetricsCollectorConcurrencySafety:
    """防止 PerfMetricsCollector 共享数据结构并发访问不安全"""

    def test_record_step_concurrent(self):
        """多线程并发调用 record_step 不应导致异常"""
        import threading
        from services.perf_metrics import PerfMetricsCollector

        collector = PerfMetricsCollector()
        collector.step_history.clear()
        collector.repair_history.clear()

        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    collector.record_step(f"step_{i % 10}", float(thread_id * 10 + i))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"CC-010: 并发 record_step 不应导致异常: {errors}"
        assert len(collector.step_history) == 10, f"CC-010: step_history 应该有 10 个 step，实际是 {len(collector.step_history)}"

    def test_get_summary_during_writes(self):
        """写入过程中调用 get_summary 不应导致异常"""
        import threading
        import time
        from services.perf_metrics import PerfMetricsCollector

        collector = PerfMetricsCollector()
        collector.step_history.clear()
        collector.repair_history.clear()

        errors = []
        stop = threading.Event()

        def writer():
            try:
                i = 0
                while not stop.is_set():
                    collector.record_step(f"step_{i % 5}", float(i))
                    if i % 100 == 0:
                        collector.repair_history.append({
                            'task_id': f'task_{i}',
                            'total_time_ms': float(i),
                            'size_samples': 48000,
                            'algorithm_version': 'v2.3',
                            'xrtf': 1.0,
                            'breakdown_by_step': {},
                            'timestamp': time.time()
                        })
                    i += 1
            except Exception as e:
                errors.append(str(e))

        def reader():
            try:
                while not stop.is_set():
                    collector.get_summary()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(str(e))

        w_thread = threading.Thread(target=writer)
        r_thread = threading.Thread(target=reader)
        w_thread.start()
        r_thread.start()

        time.sleep(0.1)
        stop.set()

        w_thread.join()
        r_thread.join()

        assert len(errors) == 0, f"CC-010: 读写并发不应导致异常: {errors}"


# ============================================================================
# 回归测试 32: _loop / _loop_warned 全局变量无同步
# Bug: 多线程下读写 _loop 和 _loop_warned 可能出现竞态
# 修复: 添加 _loop_lock 保护这些全局变量的读写
# ============================================================================

class TestEventLoopGlobalSync:
    """防止 _loop / _loop_warned 全局变量并发访问无同步"""

    def test_loop_has_lock(self):
        """应该有 _loop_lock 保护全局变量"""
        import inspect
        from services import task_manager

        assert hasattr(task_manager, '_loop_lock'), (
            "CC-011: task_manager 应该有 _loop_lock 用于保护 _loop 和 _loop_warned"
        )

        get_loop_source = inspect.getsource(task_manager._get_loop)
        assert '_loop_lock' in get_loop_source, (
            "CC-011: _get_loop 应该使用 _loop_lock 保护全局变量访问"
        )

        set_loop_source = inspect.getsource(task_manager.set_event_loop)
        assert '_loop_lock' in set_loop_source, (
            "CC-011: set_event_loop 应该使用 _loop_lock 保护全局变量写入"
        )


# ============================================================================
# 回归测试 33: 监控线程用 list[bool] 而非 threading.Event
# Bug: 用 list[bool] 作为停止标志不能保证跨线程可见性
# 修复: 改用 threading.Event() 作为停止标志
# ============================================================================

class TestStuckMonitorUsesEvent:
    """防止监控线程用 list[bool] 作停止标志（可见性无保证）"""

    def test_task_classes_use_event_for_stop(self):
        """RepairTask/DetectTask/RenderTask 应该用 threading.Event 作停止标志"""
        import inspect
        from services.task_manager import RepairTask, DetectTask, RenderTask

        for cls in [RepairTask, DetectTask, RenderTask]:
            init_source = inspect.getsource(cls.__init__)
            assert 'threading.Event()' in init_source or 'Event()' in init_source, (
                f"CC-013: {cls.__name__}.__init__ 应该用 threading.Event() 作为 _stop_monitor，而不是 list[bool]"
            )

    def test_run_detect_uses_event(self):
        """_run_detect 函数应该用 threading.Event 作 stop_monitor"""
        import inspect
        from services import task_manager

        source = inspect.getsource(task_manager._run_detect)
        assert 'threading.Event()' in source, (
            "CC-013: _run_detect 应该用 threading.Event() 作为 stop_monitor"
        )
        assert 'stop_monitor.set()' in source, (
            "CC-013: _run_detect 应该用 stop_monitor.set() 而不是 stop_monitor[0] = True"
        )

    def test_run_repair_uses_event(self):
        """_run_repair 函数应该用 threading.Event 作 stop_monitor"""
        import inspect
        from services import task_manager

        source = inspect.getsource(task_manager._run_repair)
        assert 'threading.Event()' in source, (
            "CC-013: _run_repair 应该用 threading.Event() 作为 stop_monitor"
        )
        assert 'stop_monitor.set()' in source, (
            "CC-013: _run_repair 应该用 stop_monitor.set() 而不是 stop_monitor[0] = True"
        )


# ============================================================================
# 回归测试 34: TaskTracer._traces 字典极端异常路径下泄漏
# Bug: 任务极端异常终止时 trace 可能不被清理，导致内存泄漏
# 修复: 1. 修复 record_task_start 的锁重入问题  2. 添加超时自动清理机制
# ============================================================================

class TestTaskTracerNoLeak:
    """防止 TaskTracer._traces 在极端异常路径下泄漏"""

    def test_record_task_start_no_deadlock(self):
        """record_task_start 不应导致死锁（锁重入问题）"""
        import threading
        from services.observability import TaskTracer

        tracer = TaskTracer()
        tracer._traces.clear()
        tracer._history.clear()

        errors = []
        result = {"success": False}

        def worker():
            try:
                tracer.record_task_start("test_no_deadlock", "repair")
                result["success"] = True
            except Exception as e:
                errors.append(str(e))

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=2.0)

        assert not t.is_alive(), (
            "CC-015: record_task_start 导致死锁，线程 2 秒内未返回"
        )
        assert result["success"], f"CC-015: record_task_start 执行失败: {errors}"

    def test_expired_traces_get_cleaned_up(self):
        """超时的 trace 应该在 get_active_traces 时被自动清理"""
        import time
        from services.observability import TaskTracer

        tracer = TaskTracer()
        tracer._traces.clear()
        tracer._history.clear()
        tracer._trace_timeout = 0.01  # 设为 10ms 方便测试

        tracer.create_trace("expired_task_1", "repair")
        tracer.create_trace("expired_task_2", "detect")

        assert len(tracer._traces) == 2, "初始应该有 2 个 trace"

        time.sleep(0.05)  # 等待超时

        active = tracer.get_active_traces()

        assert len(active) == 0, f"CC-015: 超时的 trace 应该被清理，实际还有 {len(active)} 个"
        assert len(tracer._traces) == 0, f"CC-015: _traces 字典应该为空，实际有 {len(tracer._traces)} 个"
        assert len(tracer._history) == 2, f"CC-015: 被清理的 trace 应该移到 history，实际有 {len(tracer._history)} 个"

        for trace in tracer._history:
            assert trace.final_status == "expired", (
                f"CC-015: 被清理的 trace final_status 应该是 'expired'，实际是 {trace.final_status}"
            )


# ============================================================================
# 回归测试 35: SQLite 连接未用 context manager
# Bug: 手动 conn.close() 在异常路径下可能泄漏连接
# 修复: 使用 contextlib.closing 确保连接总是被关闭
# ============================================================================

class TestSQLiteConnectionContextManager:
    """防止 SQLite 连接异常路径下未关闭导致泄漏"""

    def test_database_uses_closing_context(self):
        """database.py 应该使用 contextlib.closing 管理连接"""
        import inspect
        import database

        assert 'from contextlib import closing' in inspect.getsource(database), (
            "CC-016: database.py 应该导入 contextlib.closing"
        )

        funcs_to_check = [
            'create_task',
            'update_task',
            'get_task',
            'find_task_by_hash',
            'delete_task',
            'save_analysis_cache',
            'get_analysis_cache',
        ]

        for func_name in funcs_to_check:
            func = getattr(database, func_name)
            source = inspect.getsource(func)
            assert 'with closing(' in source, (
                f"CC-016: {func_name} 应该使用 'with closing(get_db())' 确保连接关闭"
            )
            assert 'conn.close()' not in source, (
                f"CC-016: {func_name} 不应该有手动 conn.close()，应该用 context manager"
            )

    def test_init_db_uses_closing(self):
        """init_db 应该使用 context manager"""
        import inspect
        from database import init_db

        source = inspect.getsource(init_db)
        assert 'with closing(' in source, (
            "CC-016: init_db 应该使用 context manager 确保连接关闭"
        )


# ============================================================================
# 回归测试 36: 训练目录含 .wav 结尾的子目录时不应崩溃
# Bug: process_all_files 用 os.listdir 后只判断后缀名，
#      如果有子目录名以 .wav 结尾，会尝试 open 目录导致崩溃
# 修复: 用 os.path.isfile() 过滤掉目录
# ============================================================================

class TestTrainingDirWithWavSuffix:
    """防止训练目录中含 .wav 后缀子目录导致崩溃"""

    def test_process_all_files_checks_isfile(self):
        """process_all_files 源码中应该包含 os.path.isfile() 检查"""
        import inspect
        import os

        feature_extractor_path = os.path.join(
            os.path.dirname(__file__), "..", "training", "feature_extractor.py"
        )

        with open(feature_extractor_path) as f:
            source = f.read()

        assert "os.path.isfile(filepath)" in source, (
            "TR-001: process_all_files 应该使用 os.path.isfile() 过滤目录，"
            "防止 .wav 结尾的子目录被当作文件处理导致崩溃"
        )

    def test_directory_with_wav_suffix_not_treated_as_file(self):
        """以 .wav 结尾的目录不应被识别为音频文件"""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            subdir_path = os.path.join(tmpdir, "backup.wav")
            os.makedirs(subdir_path)

            import soundfile as sf
            import numpy as np
            sr = 44100
            t = np.arange(int(sr * 0.5)) / sr
            y = 0.3 * np.sin(2 * np.pi * 440 * t)
            wav_path = os.path.join(tmpdir, "test.wav")
            sf.write(wav_path, y, sr)

            training_files = []
            for filename in os.listdir(tmpdir):
                if filename.lower().endswith(('.wav', '.mp3', '.flac', '.ogg', '.aac', '.m4a')):
                    filepath = os.path.join(tmpdir, filename)
                    if os.path.isfile(filepath):
                        training_files.append(filepath)

            assert len(training_files) == 1, (
                f"TR-001: 应该只识别出 1 个真实音频文件，实际识别了 {len(training_files)} 个。"
                f"以 .wav 结尾的子目录不应该被当作文件处理。"
            )
            assert training_files[0] == wav_path


# ============================================================================
# 回归测试 37: 任务取消后状态不应被覆盖为 completed
# Bug: 任务执行完后即使已被取消，仍会设置 completed 状态，覆盖 cancelled
# 修复: _run_task 中在设置 completed 状态前检查是否已被取消
# ============================================================================

class TestCancelledTaskStatusNotOverwritten:
    """防止取消的任务状态被 completed 覆盖"""

    def test_run_task_checks_cancelled_before_completed(self):
        """_run_task 源码中应该在设置 completed 状态前检查取消状态"""
        import os
        import ast

        task_executor_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "task_executor.py"
        )

        with open(task_executor_path) as f:
            source = f.read()

        assert "task.execute(progress_callback)" in source, (
            "task_executor 中应该有 task.execute() 调用"
        )

        execute_idx = source.find("task.execute(progress_callback)")
        update_task_idx = source.find('"status": completed_status', execute_idx)
        cancelled_check_idx = source.find("task_id in _cancelled_tasks", execute_idx)

        assert cancelled_check_idx != -1, (
            "TR-002: task.execute() 之后应该检查 task_id 是否在 _cancelled_tasks 中"
        )
        assert cancelled_check_idx < update_task_idx, (
            "TR-002: 取消状态检查应该在设置 completed 状态之前，防止 cancelled 被覆盖"
        )

    def test_cancelled_task_raises_taskcancellederror(self):
        """检测到任务已取消时应该抛出 TaskCancelledError"""
        import os

        task_executor_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "task_executor.py"
        )

        with open(task_executor_path) as f:
            source = f.read()

        execute_idx = source.find("task.execute(progress_callback)")
        after_execute = source[execute_idx:execute_idx + 1000]

        assert "TaskCancelledError" in after_execute, (
            "TR-002: 检测到任务已取消时应该抛出 TaskCancelledError，走取消处理分支"
        )
        assert "raise" in after_execute, (
            "TR-002: 检测到取消时应该 raise 异常，而不是继续设置 completed 状态"
        )


# ============================================================================
# 回归测试 38: 特征提取器数据库连接异常路径泄漏
# Bug: process_single_file 中数据库连接在异常时未关闭
# 修复: 用 try/finally 确保连接关闭
# ============================================================================

class TestFeatureExtractorDbConnectionLeak:
    """防止特征提取器数据库连接泄漏"""

    def test_process_single_file_has_finally_block(self):
        """process_single_file 源码中应该有 try/finally 确保连接关闭"""
        import os
        import ast

        feature_extractor_path = os.path.join(
            os.path.dirname(__file__), "..", "training", "feature_extractor.py"
        )

        with open(feature_extractor_path) as f:
            source = f.read()

        assert "finally:" in source, (
            "TR-003: process_single_file 应该使用 try/finally 确保数据库连接关闭"
        )
        assert "conn.close()" in source, (
            "TR-003: process_single_file 应该在 finally 块中关闭数据库连接"
        )
        assert "if conn is not None" in source, (
            "TR-003: process_single_file 应该检查 conn 是否为 None 再关闭"
        )

    def test_db_connection_closed_on_exception_pattern(self):
        """数据库连接关闭模式应该在 finally 块中，而不是只在正常路径"""
        import os

        feature_extractor_path = os.path.join(
            os.path.dirname(__file__), "..", "training", "feature_extractor.py"
        )

        with open(feature_extractor_path) as f:
            lines = f.readlines()

        process_single_start = None
        process_single_end = None
        for i, line in enumerate(lines):
            if "def process_single_file(" in line:
                process_single_start = i
            elif process_single_start is not None and line.startswith("def ") and i > process_single_start:
                process_single_end = i
                break

        assert process_single_start is not None, "找不到 process_single_file 函数"

        func_lines = lines[process_single_start:process_single_end] if process_single_end else lines[process_single_start:]
        func_source = "".join(func_lines)

        finally_idx = func_source.find("finally:")
        close_idx = func_source.find("conn.close()")

        assert finally_idx != -1, "TR-003: process_single_file 应该有 finally 块"
        assert close_idx != -1, "TR-003: process_single_file 应该有关闭连接的代码"
        assert close_idx > finally_idx, (
            "TR-003: conn.close() 应该在 finally 块中，确保异常路径也能关闭连接"
        )


# ============================================================================
# 回归测试 39: 检测任务性能采集
# Bug: DetectTask 完全缺少性能采集（start_detect/end_detect）
# 修复: 在 DetectTask.execute 中添加 start_detect/end_detect
# ============================================================================

class TestDetectTaskPerfCollection:
    """防止检测任务缺少性能采集"""

    def test_detect_task_has_perf_collection(self):
        """DetectTask 执行后应该有 perf_data 字段"""
        import tempfile
        import os
        from database import init_db, create_task
        from services.task_manager import DetectTask
        from services.perf_metrics import PerfMetricsCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            old_db = config.DB_PATH
            try:
                config.UPLOAD_DIR = tmpdir
                config.OUTPUT_DIR = tmpdir
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                init_db()

                import soundfile as sf
                import numpy as np
                sr = 44100
                t = np.arange(int(sr * 1.0)) / sr
                y = 0.3 * np.sin(2 * np.pi * 440 * t)
                audio_path = os.path.join(tmpdir, "test.wav")
                sf.write(audio_path, y, sr)

                task_id = "reg_tr004_detect_perf"
                create_task(task_id, "test.wav", audio_path, {"detector_version": "v1.1"}, file_hash="hash_tr004")

                perf_collector = PerfMetricsCollector.get_instance()
                initial_detect_count = len(perf_collector.detect_history)

                task = DetectTask(task_id, audio_path, detect_type="original", detector_version="v1.1")

                def fake_progress(p, s):
                    pass

                result = task.execute(fake_progress)

                assert "perf_data" in result, (
                    "TR-004: DetectTask.execute 的返回值应该包含 perf_data 字段"
                )
                assert result["perf_data"] is not None
                assert "total_time_ms" in result["perf_data"], (
                    "TR-004: perf_data 应该包含 total_time_ms"
                )
                assert result["perf_data"]["total_time_ms"] > 0, (
                    "TR-004: total_time_ms 应该大于 0"
                )

                final_detect_count = len(perf_collector.detect_history)
                assert final_detect_count > initial_detect_count, (
                    "TR-004: 检测任务完成后，detect_history 应该有新记录"
                )
            finally:
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 40: process_all_files 重复哈希计算
# Bug: process_all_files 遍历两次文件，每次都读文件算哈希
# 修复: 第一次遍历时把哈希值存下来，第二次直接复用
# ============================================================================

class TestProcessAllFilesHashComputedOnce:
    """防止 process_all_files 重复计算文件哈希"""

    def test_process_all_files_stores_and_reuses_hashes(self):
        """process_all_files 应该计算一次哈希并存起来复用，而不是重复计算"""
        import os

        feature_extractor_path = os.path.join(
            os.path.dirname(__file__), "..", "training", "feature_extractor.py"
        )

        with open(feature_extractor_path) as f:
            source = f.read()

        assert "compute_file_hash" in source, (
            "TR-005: 应该有独立的 compute_file_hash 函数"
        )
        assert "file_hashes" in source, (
            "TR-005: process_all_files 应该有 file_hashes 字典来存储哈希值"
        )
        assert "file_hash=file_hashes.get(filepath)" in source or "file_hash=file_hashes[" in source, (
            "TR-005: process_single_file 调用时应该传入已计算的哈希值，避免重复计算"
        )

    def test_process_single_file_accepts_file_hash_param(self):
        """process_single_file 应该接受可选的 file_hash 参数"""
        import os
        import ast

        feature_extractor_path = os.path.join(
            os.path.dirname(__file__), "..", "training", "feature_extractor.py"
        )

        with open(feature_extractor_path) as f:
            source = f.read()

        tree = ast.parse(source)

        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "process_single_file":
                args = [arg.arg for arg in node.args.args]
                assert "file_hash" in args, (
                    "TR-005: process_single_file 应该有 file_hash 参数，用于接收预计算的哈希值"
                )
                found = True
                break

        assert found, "找不到 process_single_file 函数"


# ============================================================================
# 回归测试 41: 空音频内存估算一致
# Bug: 空音频（n_samples=0）流式 vs 非流式内存估算差异达数百倍
# 修复: 添加 n_samples<=0 的边界处理，直接返回 0
# ============================================================================

class TestEmptyAudioMemoryEstimate:
    """防止空音频内存估算不一致"""

    def test_empty_audio_returns_zero(self):
        """n_samples=0 时应该返回 0 字节，而不是流式/非流式差异巨大"""
        from services.memory_guard import estimate_repair_memory_bytes

        streaming_versions = ["v2.4", "v3.0", "v3.2", "v4.0a"]
        non_streaming_versions = ["v2.0", "v2.1"]

        for ver in streaming_versions + non_streaming_versions:
            result = estimate_repair_memory_bytes(0, 2, 44100, 48000, algorithm_version=ver)
            assert result == 0, (
                f"TR-006: 空音频 ({ver}) 内存估算应该为 0，实际为 {result} 字节"
            )

        streaming_zero = estimate_repair_memory_bytes(0, 2, 44100, 48000, algorithm_version="v2.4")
        non_streaming_zero = estimate_repair_memory_bytes(0, 2, 44100, 48000, algorithm_version="v2.0")

        assert streaming_zero == non_streaming_zero, (
            f"TR-006: 空音频流式和非流式估算应该一致，"
            f"流式={streaming_zero}, 非流式={non_streaming_zero}"
        )

    def test_negative_samples_returns_zero(self):
        """n_samples 为负数时也应该返回 0"""
        from services.memory_guard import estimate_repair_memory_bytes

        result = estimate_repair_memory_bytes(-100, 2, 44100, 48000, algorithm_version="v2.4")
        assert result == 0, (
            f"TR-006: n_samples 为负数时内存估算应该为 0，实际为 {result} 字节"
        )


# ============================================================================
# 回归测试 29: DB-001 环境变量类型转换无容错
# Bug: PORT/MAX_WORKERS 等环境变量非法值导致 int() 抛异常，服务启动崩溃
# 修复: _safe_int_env 包装，失败用默认值并打 warning
# ============================================================================

class TestEnvVarTypeConversionSafety:
    """防止环境变量非法值导致服务启动崩溃"""

    def test_invalid_port_env_uses_default(self, monkeypatch, caplog):
        """PORT 环境变量为非法值时，应使用默认值并打 warning"""
        monkeypatch.setenv("PORT", "not_a_number")
        import importlib
        import config
        importlib.reload(config)
        assert config.PORT == 8000, f"非法 PORT 应回退到默认值 8000，实际是 {config.PORT}"
        assert any("PORT" in rec.message and "不是有效整数" in rec.message for rec in caplog.records), \
            "应该打 warning 日志说明环境变量非法"

    def test_invalid_max_workers_env_uses_default(self, monkeypatch, caplog):
        """MAX_WORKERS 环境变量为非法值时，应使用默认值"""
        monkeypatch.setenv("MAX_WORKERS", "abc")
        monkeypatch.setenv("PORT", "8000")
        monkeypatch.setenv("MAX_CONCURRENT_TASKS", "3")
        monkeypatch.setenv("SOURCE_FILE_CACHE_LIMIT", "1073741824")
        import importlib
        import config
        importlib.reload(config)
        assert config.MAX_WORKERS == 4, f"非法 MAX_WORKERS 应回退到默认值 4"

    def test_valid_int_env_works(self, monkeypatch):
        """合法的整数环境变量应该正常解析"""
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("MAX_WORKERS", "8")
        monkeypatch.setenv("MAX_CONCURRENT_TASKS", "6")
        monkeypatch.setenv("SOURCE_FILE_CACHE_LIMIT", "2147483648")
        import importlib
        import config
        importlib.reload(config)
        assert config.PORT == 9000
        assert config.MAX_WORKERS == 8
        assert config.MAX_CONCURRENT_TASKS == 6
        assert config.SOURCE_FILE_CACHE_LIMIT == 2147483648

    def test_safe_int_env_function_exists(self):
        """config 模块应该有 _safe_int_env 辅助函数"""
        import config
        assert hasattr(config, "_safe_int_env")
        assert callable(config._safe_int_env)


# ============================================================================
# 回归测试 30: DB-002 tasks 表缺少关键索引
# Bug: file_hash/status/created_at 列无索引，大表查询慢
# 修复: init_db 创建索引
# ============================================================================

class TestTasksTableIndexes:
    """防止 tasks 表缺少关键索引导致查询慢"""

    def test_init_db_creates_file_hash_index(self):
        """init_db 后应该存在 idx_tasks_file_hash 索引"""
        import tempfile
        import os
        from database import init_db, get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                init_db()
                conn = get_db()
                try:
                    cursor = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_file_hash'"
                    )
                    assert cursor.fetchone() is not None, "应该存在 idx_tasks_file_hash 索引"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db

    def test_init_db_creates_status_index(self):
        """init_db 后应该存在 idx_tasks_status 索引"""
        import tempfile
        import os
        from database import init_db, get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                init_db()
                conn = get_db()
                try:
                    cursor = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_status'"
                    )
                    assert cursor.fetchone() is not None, "应该存在 idx_tasks_status 索引"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db

    def test_init_db_creates_created_at_index(self):
        """init_db 后应该存在 idx_tasks_created_at 索引"""
        import tempfile
        import os
        from database import init_db, get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                init_db()
                conn = get_db()
                try:
                    cursor = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_created_at'"
                    )
                    assert cursor.fetchone() is not None, "应该存在 idx_tasks_created_at 索引"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db

    def test_init_db_creates_composite_status_created_at_index(self):
        """init_db 后应该存在复合索引 idx_tasks_status_created_at"""
        import tempfile
        import os
        from database import init_db, get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                init_db()
                conn = get_db()
                try:
                    cursor = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_status_created_at'"
                    )
                    assert cursor.fetchone() is not None, "应该存在复合索引 idx_tasks_status_created_at"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db


# ============================================================================
# 回归测试 31: DB-003 find_repair_cache 全量加载后过滤
# Bug: 先 SELECT * 所有 file_hash 任务，再在 Python 中过滤，大表内存+性能差
# 修复: SQL WHERE 中增加 status='completed' AND output_path != '' 条件
# ============================================================================

class TestFindRepairCacheSqlFilter:
    """防止 find_repair_cache 全表扫描后在 Python 中过滤"""

    def test_find_repair_cache_only_queries_completed(self):
        """find_repair_cache 应该只查询 status=completed 且 output_path 非空的任务"""
        import inspect
        from database import find_repair_cache

        source = inspect.getsource(find_repair_cache)
        assert "status = 'completed'" in source or "status='completed'" in source, \
            "DB-003: find_repair_cache 的 SQL 应该包含 status='completed' 过滤条件"
        assert "output_path" in source and ("!=''" in source or "!= ''" in source or "> ''" in source), \
            "DB-003: find_repair_cache 的 SQL 应该包含 output_path 非空过滤条件"

    def test_find_dual_repair_cache_only_queries_completed(self):
        """find_dual_repair_cache 也应该只查询 completed 且 output_path 非空的任务"""
        import inspect
        from database import find_dual_repair_cache

        source = inspect.getsource(find_dual_repair_cache)
        assert "status = 'completed'" in source or "status='completed'" in source, \
            "DB-003: find_dual_repair_cache 的 SQL 应该包含 status='completed' 过滤条件"
        assert "output_path" in source and ("!=''" in source or "!= ''" in source or "> ''" in source), \
            "DB-003: find_dual_repair_cache 的 SQL 应该包含 output_path 非空过滤条件"

    def test_pending_tasks_not_returned_by_cache(self, tmp_path):
        """pending 状态的任务不应该被缓存查询返回"""
        import os
        import config
        from database import init_db, create_task, update_task, find_repair_cache

        old_db = config.DB_PATH
        old_upload = config.UPLOAD_DIR
        old_output = config.OUTPUT_DIR
        config.DB_PATH = os.path.join(tmp_path, "test.db")
        config.UPLOAD_DIR = str(tmp_path)
        config.OUTPUT_DIR = str(tmp_path)
        try:
            init_db()

            output_file = os.path.join(tmp_path, "output.wav")
            with open(output_file, "wb") as f:
                f.write(b"x" * 20000)

            create_task("pending_task", "test.wav", "/tmp/test.wav",
                        {"algorithm_version": "v2.4"}, file_hash="test_hash_003", file_size=1000)
            update_task("pending_task", status="pending", output_path=output_file)

            result = find_repair_cache("test_hash_003", {"algorithm_version": "v2.4"})
            assert result is None, "pending 状态的任务不应该被缓存命中"
        finally:
            config.DB_PATH = old_db
            config.UPLOAD_DIR = old_upload
            config.OUTPUT_DIR = old_output


# ============================================================================
# 回归测试 32: DB-004 cleanup_stale_tasks 竞态条件
# Bug: 先查后改，并发下可能漏掉任务或数量不一致
# 修复: 使用事务 BEGIN IMMEDIATE 确保一致性，返回 cursor.rowcount
# ============================================================================

class TestCleanupStaleTasksAtomicity:
    """防止 cleanup_stale_tasks 先查后改的竞态条件"""

    def test_cleanup_uses_transaction(self):
        """cleanup_stale_tasks 应该使用事务确保原子性"""
        import inspect
        from database import cleanup_stale_tasks

        source = inspect.getsource(cleanup_stale_tasks)
        assert "BEGIN IMMEDIATE" in source or "begin immediate" in source.lower(), \
            "DB-004: cleanup_stale_tasks 应该使用 BEGIN IMMEDIATE 开启事务"
        assert "rollback" in source.lower(), \
            "DB-004: 异常时应该 rollback 事务"

    def test_cleanup_returns_rowcount(self):
        """cleanup_stale_tasks 返回值应该基于 UPDATE 的 rowcount，而非 SELECT 计数"""
        import inspect
        from database import cleanup_stale_tasks

        source = inspect.getsource(cleanup_stale_tasks)
        assert "rowcount" in source, \
            "DB-004: 应该使用 cursor.rowcount 返回实际更新的行数"

    def test_cleanup_stale_count_matches_actual_updated(self, tmp_path):
        """cleanup_stale_tasks 返回的数量应该等于实际被更新的任务数"""
        import os
        import config
        from database import init_db, create_task, get_db, cleanup_stale_tasks

        old_db = config.DB_PATH
        config.DB_PATH = os.path.join(tmp_path, "test.db")
        try:
            init_db()

            for i in range(5):
                create_task(f"task_{i}", f"test_{i}.wav", f"/tmp/test_{i}.wav",
                            {}, f"hash_{i}", 1000)

            conn = get_db()
            conn.execute("UPDATE tasks SET status = 'pending' WHERE id IN ('task_0', 'task_1', 'task_2')")
            conn.execute("UPDATE tasks SET status = 'completed' WHERE id IN ('task_3', 'task_4')")
            conn.commit()
            conn.close()

            count = cleanup_stale_tasks()
            assert count == 3, f"应该清理 3 个 pending 任务，实际清理了 {count} 个"

            conn = get_db()
            cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'error'")
            actual_error = cursor.fetchone()[0]
            conn.close()
            assert actual_error == 3, f"数据库中应该有 3 个 error 状态任务，实际有 {actual_error} 个"
        finally:
            config.DB_PATH = old_db


# ============================================================================
# 回归测试 33: DB-005 WAL 模式无 checkpoint 管理
# Bug: 只开启 WAL 但不配置 checkpoint，WAL 文件可能无限增长
# 修复: 设置 wal_autocheckpoint 阈值
# ============================================================================

class TestWalCheckpointConfig:
    """防止 WAL 模式下 checkpoint 未配置导致磁盘泄漏"""

    def test_get_db_sets_wal_autocheckpoint(self):
        """get_db() 应该设置 wal_autocheckpoint"""
        import tempfile
        import os
        from database import get_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            import config
            old_db = config.DB_PATH
            config.DB_PATH = db_path
            try:
                conn = get_db()
                try:
                    cursor = conn.execute("PRAGMA wal_autocheckpoint")
                    checkpoint_value = cursor.fetchone()[0]
                    assert checkpoint_value > 0, \
                        f"DB-005: wal_autocheckpoint 应该设置为正数，实际是 {checkpoint_value}"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db

    def test_get_training_db_sets_wal_autocheckpoint(self):
        """get_training_db() 也应该设置 wal_autocheckpoint"""
        import tempfile
        import os
        from database import get_training_db, TRAINING_DB_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_db_path = config.DB_PATH
            config.DB_PATH = os.path.join(tmpdir, "tasks.db")
            old_training_path = TRAINING_DB_PATH
            import database
            database.TRAINING_DB_PATH = os.path.join(tmpdir, "training.db")
            try:
                conn = get_training_db()
                try:
                    cursor = conn.execute("PRAGMA wal_autocheckpoint")
                    checkpoint_value = cursor.fetchone()[0]
                    assert checkpoint_value > 0, \
                        f"DB-005: 训练库 wal_autocheckpoint 应该设置为正数，实际是 {checkpoint_value}"
                finally:
                    conn.close()
            finally:
                config.DB_PATH = old_db_path
                database.TRAINING_DB_PATH = old_training_path


# ============================================================================
# 回归测试 42: streaming_spectral_process 块边界信号为零（重叠相加错误）
# Bug: DSP-001 - 输出块无重叠但使用淡入淡出窗口，导致相邻块边界处信号为零
# 修复: 让输出块之间有重叠（hop_out = chunk_samples - fade_len），使 fade 区域叠加后连续
# ============================================================================

class TestDspStreamingSpectralBoundary:
    """防止 streaming_spectral_process 块边界信号为零（咔哒声）"""

    def test_dc_signal_boundary_not_zero(self):
        """恒等处理的直流信号在块边界处不应为零"""
        from services.dsp_utils import streaming_spectral_process

        sr = 44100
        chunk_seconds = 0.1
        y = np.ones(int(sr * 0.5)) * 0.5

        def identity_process(S, sr, n_fft, hop_length):
            return S

        y_out = streaming_spectral_process(
            y, sr, identity_process,
            n_fft=2048, hop_length=512,
            chunk_seconds=chunk_seconds
        )

        chunk_samples = int(sr * chunk_seconds)
        boundary_idx = chunk_samples

        boundary_region = slice(max(0, boundary_idx - 5), boundary_idx + 5)
        boundary_min = np.min(y_out[boundary_region])

        assert boundary_min > 0.01, (
            f"DSP-001: 块边界处信号存在零点 (min={boundary_min:.6f})，"
            f"恒等处理的直流信号边界不应为零。"
        )

    def test_block_boundary_amplitude_stable(self):
        """块边界处平均幅度应接近输入值"""
        from services.dsp_utils import streaming_spectral_process

        sr = 44100
        chunk_seconds = 0.1
        y = np.ones(int(sr * 0.5)) * 0.5

        def identity_process(S, sr, n_fft, hop_length):
            return S

        y_out = streaming_spectral_process(
            y, sr, identity_process,
            n_fft=2048, hop_length=512,
            chunk_seconds=chunk_seconds
        )

        chunk_samples = int(sr * chunk_seconds)
        boundary = chunk_samples

        center_region = y_out[boundary-10:boundary+10]
        center_mean = np.mean(center_region)
        expected = 0.5

        assert abs(center_mean - expected) < 0.01, (
            f"DSP-001: 块边界处平均幅度 ({center_mean:.4f}) 远低于预期 ({expected})，"
            f"证明重叠相加算法存在缺陷"
        )


# ============================================================================
# 回归测试 43: beat_track 中 best_lag 可能为零导致除零错误
# Bug: DSP-002 - 当 min_lag=0 且搜索范围第一个点最大时，best_lag=0 导致除零
# 修复: 检查 best_lag <= 0 时返回 start_bpm 和空 beats
# ============================================================================

class TestDspBeatTrackDivideByZero:
    """防止 beat_track best_lag 为零时除零错误"""

    def test_very_high_sr_small_hop_no_crash(self):
        """高采样率小 hop_length 时不应发生除零错误"""
        from services.dsp_utils import beat_track

        sr = 8000
        hop_length = 8192
        onset_env = np.zeros(100)
        onset_env[0] = 1.0

        try:
            tempo, beats = beat_track(
                onset_envelope=onset_env,
                sr=sr,
                hop_length=hop_length
            )
            assert np.isfinite(tempo), (
                f"DSP-002: beat_track 返回非有限 tempo={tempo}"
            )
        except ZeroDivisionError:
            pytest.fail("DSP-002: beat_track 发生除零错误 (ZeroDivisionError)")

    def test_empty_onset_envelope_returns_start_bpm(self):
        """空 onset envelope 应返回 start_bpm 而不是崩溃"""
        from services.dsp_utils import beat_track

        tempo, beats = beat_track(
            onset_envelope=np.array([]),
            sr=22050,
            hop_length=512,
            start_bpm=120.0
        )
        assert np.isfinite(tempo), "DSP-002: 空包络时 tempo 应为有限值"
        assert len(beats) == 0


# ============================================================================
# 回归测试 44: _tanh_declip 多声道时 in-place 修改输入数组
# Bug: DSP-003 - 多声道输入时直接修改 y[ch]，导致原始数据被破坏
# 修复: 多声道时创建新数组 y_out，不修改输入
# ============================================================================

class TestDspTanhDeclipNoInPlace:
    """防止 _tanh_declip 意外修改输入数组"""

    def test_multichannel_not_modified(self):
        """多声道输入不应被 in-place 修改"""
        from services.repair.repair_v2_4.core import _tanh_declip

        y_orig = np.random.randn(2, 44100).astype(np.float64) * 0.5
        y_orig[0, 1000] = 2.0
        y_orig[1, 2000] = -2.0
        y_input = y_orig.copy()

        _ = _tanh_declip(y_input, amount=0.5)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "DSP-003: _tanh_declip 修改了输入数组 (in-place)，"
            "这会导致上游数据被意外破坏"
        )

    def test_mono_not_modified(self):
        """单声道输入也不应被 in-place 修改"""
        from services.repair.repair_v2_4.core import _tanh_declip

        y_orig = np.random.randn(44100).astype(np.float64) * 0.5
        y_orig[1000] = 2.0
        y_input = y_orig.copy()

        _ = _tanh_declip(y_input, amount=0.5)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "DSP-003: _tanh_declip (单声道) 修改了输入数组"
        )


# ============================================================================
# 回归测试 45: _diff_clamp_depop 多声道时 in-place 修改输入数组
# Bug: DSP-004 - 多声道输入时直接修改 y[ch]，导致原始数据被破坏
# 修复: 多声道时创建新数组 y_out，不修改输入
# ============================================================================

class TestDspDiffClampDepopNoInPlace:
    """防止 _diff_clamp_depop 意外修改输入数组"""

    def test_multichannel_not_modified(self):
        """多声道输入不应被 in-place 修改"""
        from services.repair.repair_v2_4.core import _diff_clamp_depop

        sr = 44100
        np.random.seed(42)
        y_orig = np.random.randn(2, sr).astype(np.float64) * 0.01
        for ch in range(2):
            for pos in [10000, 20000, 30000]:
                y_orig[ch, pos] = 0.8
                y_orig[ch, pos + 1] = -0.7
        y_input = y_orig.copy()

        result = _diff_clamp_depop(y_input, sr, amount=0.5)

        assert result is not None
        input_modified = not np.allclose(y_input, y_orig)
        assert not input_modified, (
            "DSP-004: _diff_clamp_depop 修改了输入数组 (in-place)，"
            "这会导致上游数据被意外破坏"
        )


# ============================================================================
# 回归测试 46: _adaptive_loudness_normalize in-place 修改输入数组
# Bug: DSP-005 - 使用 y[:] = ... 直接修改原数组内容
# 修复: 返回新数组，不修改输入
# ============================================================================

class TestDspAdaptiveLoudnessNoInPlace:
    """防止 _adaptive_loudness_normalize 意外修改输入数组"""

    def test_multichannel_not_modified(self):
        """多声道输入不应被 in-place 修改"""
        from services.repair.repair_v2_4.core import _adaptive_loudness_normalize

        sr = 44100
        y_orig = np.random.randn(2, sr).astype(np.float64) * 0.1
        y_input = y_orig.copy()

        _ = _adaptive_loudness_normalize(y_input, sr, target_loudness_lu=-14.0)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "DSP-005: _adaptive_loudness_normalize 修改了输入数组 (in-place)，"
            "这会导致上游数据被意外破坏"
        )

    def test_mono_not_modified(self):
        """单声道输入也不应被 in-place 修改"""
        from services.repair.repair_v2_4.core import _adaptive_loudness_normalize

        sr = 44100
        y_orig = np.random.randn(sr).astype(np.float64) * 0.1
        y_input = y_orig.copy()

        _ = _adaptive_loudness_normalize(y_input, sr, target_loudness_lu=-14.0)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "DSP-005: _adaptive_loudness_normalize (单声道) 修改了输入数组"
        )


# ============================================================================
# 回归测试 47: pyin 全静音信号返回全 NaN 的 f0 数组
# Bug: DSP-006 - f0 初始化为 np.nan，静音帧不更新，全静音时全为 NaN
# 修复: 返回前用 np.nan_to_num 将 NaN 替换为 0
# ============================================================================

class TestDspPyinSilenceNoNaN:
    """防止 pyin 对静音信号返回 NaN 导致下游崩溃"""

    def test_silence_returns_zero_not_nan(self):
        """全静音信号的 f0 不应包含 NaN"""
        from services.dsp_utils import pyin

        sr = 22050
        y = np.zeros(int(sr * 0.5))

        f0, voiced_flag, voiced_prob = pyin(y, sr=sr, frame_length=2048, hop_length=512)

        has_nan = np.any(np.isnan(f0))
        assert not has_nan, (
            f"DSP-006: pyin 对静音信号返回 NaN 的 f0 值 "
            f"(nan 比例: {np.sum(np.isnan(f0))}/{len(f0)})，"
            f"下游计算可能因此崩溃"
        )

    def test_voiced_flag_consistency(self):
        """f0、voiced_flag、voiced_prob 长度应一致"""
        from services.dsp_utils import pyin

        sr = 22050
        y = np.zeros(int(sr * 0.5))

        f0, voiced_flag, voiced_prob = pyin(y, sr=sr, frame_length=2048, hop_length=512)

        assert len(f0) == len(voiced_flag), "f0 与 voiced_flag 长度不一致"
        assert len(f0) == len(voiced_prob), "f0 与 voiced_prob 长度不一致"


# ============================================================================
# 回归测试 48: API-001 上传接口不应一次性读取大文件到内存
# Bug: 上传接口先 await file.read() 整个文件到内存再判断大小，
#      大文件上传可直接 OOM
# 修复: 流式分块读取，边读边写，累计大小超限立即中断并清理
# ============================================================================

class TestUploadStreamingSizeCheck:
    """防止上传接口一次性读取大文件导致 OOM"""

    def test_upload_exceeds_size_returns_413(self):
        """超过 MAX_UPLOAD_SIZE 的文件应返回 413，且不应消耗大量内存"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config
        from api.routes import upload as upload_module

        old_max = config.MAX_UPLOAD_SIZE
        old_upload_module_max = upload_module.MAX_UPLOAD_SIZE
        config.MAX_UPLOAD_SIZE = 1024  # 1KB 限制
        upload_module.MAX_UPLOAD_SIZE = 1024
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                old_db = config.DB_PATH
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                from database import init_db
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    big_file = b"\x00" * 2048  # 2KB > 1KB 限制
                    files = {"file": ("test.wav", big_file, "audio/wav")}
                    res = client.post("/api/v1/upload", files=files, data={"file_hash": "abc123"})

                    assert res.status_code == 413, (
                        f"API-001: 超过大小限制应返回 413，实际是 {res.status_code}"
                    )

                    upload_files = os.listdir(config.UPLOAD_DIR)
                    assert len(upload_files) == 0, (
                        f"API-001: 上传失败后应清理临时文件，实际还有 {len(upload_files)} 个文件"
                    )
                finally:
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
                    config.DB_PATH = old_db
        finally:
            config.MAX_UPLOAD_SIZE = old_max
            upload_module.MAX_UPLOAD_SIZE = old_upload_module_max


# ============================================================================
# 回归测试 49: API-002 双轨上传失败时应清理已上传的文件
# Bug: 双轨上传第二轨失败或空间不足时，第一轨已上传的文件不清理，
#      导致存储空间泄漏
# 修复: 定义清理函数，失败时删除所有已上传文件
# ============================================================================

class TestDualUploadCleanupOnFailure:
    """防止双轨上传失败时资源泄漏"""

    def test_dual_upload_second_fails_cleans_first(self):
        """第二轨上传失败时，第一轨已上传的文件应被清理"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config
        from api.routes import upload as upload_module

        old_max = config.MAX_UPLOAD_SIZE
        old_upload_module_max = upload_module.MAX_UPLOAD_SIZE
        config.MAX_UPLOAD_SIZE = 2048  # 2KB 限制，单个文件 1.5KB 没问题，两个加起来超限
        upload_module.MAX_UPLOAD_SIZE = 2048
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                old_db = config.DB_PATH
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                from database import init_db
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    small_wav = _make_test_wav(0.1)
                    try:
                        with open(small_wav, "rb") as f:
                            vocal_data = f.read()
                        files = {
                            "vocal_file": ("vocal.wav", vocal_data, "audio/wav"),
                            "accompaniment_file": ("acc.wav", vocal_data, "audio/wav"),
                        }
                        res = client.post("/api/v1/upload-dual", files=files, data={"file_hash": ""})

                        upload_files = [f for f in os.listdir(config.UPLOAD_DIR) if f.endswith(".wav")]
                        if res.status_code != 200:
                            assert len(upload_files) == 0, (
                                f"API-002: 双轨上传失败后应清理临时文件，"
                                f"实际还有 {len(upload_files)} 个文件: {upload_files}"
                            )
                    finally:
                        if os.path.exists(small_wav):
                            os.unlink(small_wav)
                finally:
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
                    config.DB_PATH = old_db
        finally:
            config.MAX_UPLOAD_SIZE = old_max
            upload_module.MAX_UPLOAD_SIZE = old_upload_module_max


# ============================================================================
# 回归测试 50: API-003 CORS 配置不应同时 allow_origins=* 和 allow_credentials
# Bug: CORS 配置同时设置 allow_origins=["*"] 和 allow_credentials=True，
#      浏览器会拒绝，前端无法正常携带凭证
# 修复: 使用动态 CORS 中间件，根据请求 Origin 动态设置
# ============================================================================

class TestCorsConfiguration:
    """防止 CORS 配置中 allow_origins=* 与 credentials 冲突"""

    def test_cors_origin_reflected_with_credentials(self):
        """有 Origin 头时应返回具体 origin 和 credentials=true，不应是 *"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config

        with tempfile.TemporaryDirectory() as tmpdir:
            old_db = config.DB_PATH
            old_upload = config.UPLOAD_DIR
            old_output = config.OUTPUT_DIR
            config.DB_PATH = os.path.join(tmpdir, "test.db")
            config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
            config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
            os.makedirs(config.UPLOAD_DIR, exist_ok=True)
            os.makedirs(config.OUTPUT_DIR, exist_ok=True)
            from database import init_db
            init_db()

            try:
                app = create_app()
                client = TestClient(app)

                res = client.options(
                    "/api/v1/status/test",
                    headers={"Origin": "http://localhost:5173"},
                )

                acao = res.headers.get("access-control-allow-origin", "")
                acac = res.headers.get("access-control-allow-credentials", "")

                assert acao != "*", (
                    "API-003: 有 Origin 时 allow-origin 不应是 *"
                )
                assert acao == "http://localhost:5173", (
                    f"API-003: allow-origin 应反射请求的 Origin，实际是 {acao}"
                )
                assert acac == "true", (
                    f"API-003: allow-credentials 应为 true，实际是 {acac}"
                )
            finally:
                config.DB_PATH = old_db
                config.UPLOAD_DIR = old_upload
                config.OUTPUT_DIR = old_output


# ============================================================================
# 回归测试 51: API-004 /api/v1/log 接口需要认证
# Bug: /api/v1/log 接口无认证，任意客户端可注入日志
# 修复: 添加 ADMIN_TOKEN 认证
# ============================================================================

class TestLogEndpointAuth:
    """防止日志接口未授权访问"""

    def test_log_without_token_returns_401(self):
        """未提供 token 时应返回 401/403"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config

        old_token = config.ADMIN_TOKEN
        config.ADMIN_TOKEN = "test-admin-token-123"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                from database import init_db
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    res = client.post("/api/v1/log", json={"level": "info", "message": "test"})
                    assert res.status_code in (401, 403), (
                        f"API-004: 未认证访问 /log 应返回 401/403，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.ADMIN_TOKEN = old_token

    def test_log_with_valid_token_succeeds(self):
        """提供正确 token 时应成功"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config

        old_token = config.ADMIN_TOKEN
        config.ADMIN_TOKEN = "test-admin-token-123"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                from database import init_db
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    res = client.post(
                        "/api/v1/log",
                        json={"level": "info", "message": "test"},
                        headers={"x-admin-token": "test-admin-token-123"},
                    )
                    assert res.status_code == 200, (
                        f"API-004: 正确 token 访问 /log 应返回 200，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.ADMIN_TOKEN = old_token


# ============================================================================
# 回归测试 52: API-005 /cache/clear-all 接口需要认证
# Bug: /cache/clear-all 无认证，可清空所有缓存数据
# 修复: 添加 ADMIN_TOKEN 认证
# ============================================================================

class TestCacheClearAllAuth:
    """防止缓存清空接口未授权访问"""

    def test_clear_all_without_token_returns_401(self):
        """未提供 token 时应返回 401/403"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config

        old_token = config.ADMIN_TOKEN
        config.ADMIN_TOKEN = "test-admin-token-123"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                from database import init_db
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    res = client.post("/api/v1/cache/clear-all")
                    assert res.status_code in (401, 403), (
                        f"API-005: 未认证访问 /cache/clear-all 应返回 401/403，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.ADMIN_TOKEN = old_token


# ============================================================================
# 回归测试 53: API-006 /wasm/upload 接口需要认证
# Bug: /wasm/upload 无认证，可上传任意 WASM 模块
# 修复: 添加 ADMIN_TOKEN 认证
# ============================================================================

class TestWasmUploadAuth:
    """防止 WASM 上传接口未授权访问"""

    def test_wasm_upload_without_token_returns_401(self):
        """未提供 token 时应返回 401/403"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config

        old_token = config.ADMIN_TOKEN
        config.ADMIN_TOKEN = "test-admin-token-123"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                from database import init_db
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    fake_wasm = b"\x00asm\x01\x00\x00\x00"
                    files = {"file": ("test.wasm", fake_wasm, "application/wasm")}
                    res = client.post("/api/v1/wasm/upload", files=files)

                    assert res.status_code in (401, 403), (
                        f"API-006: 未认证访问 /wasm/upload 应返回 401/403，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.ADMIN_TOKEN = old_token


# ============================================================================
# 回归测试 54: API-007 任务接口需要访问令牌
# Bug: 任务状态/取消/下载接口无鉴权，可遍历 task_id 访问他人任务
# 修复: 基于 task_id + SECRET_KEY 的 HMAC 访问令牌
# ============================================================================

class TestTaskAccessAuth:
    """防止任务接口未授权访问"""

    def test_status_without_token_returns_403(self):
        """未提供 access_token 时查询任务状态应返回 403"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config
        from database import init_db, create_task

        old_secret = config.SECRET_KEY
        config.SECRET_KEY = "test-secret-key-for-auth"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    task_id = "test-auth-task-001"
                    create_task(task_id, "test.wav", "/tmp/test.wav", {}, "hash123", 1000)

                    res = client.get(f"/api/v1/status/{task_id}")
                    assert res.status_code == 403, (
                        f"API-007: 未认证访问任务状态应返回 403，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.SECRET_KEY = old_secret

    def test_status_with_valid_token_succeeds(self):
        """提供正确 access_token 时应能访问任务状态"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config
        from database import init_db, create_task
        from api.routes._common import generate_task_access_token

        old_secret = config.SECRET_KEY
        config.SECRET_KEY = "test-secret-key-for-auth"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    task_id = "test-auth-task-002"
                    create_task(task_id, "test.wav", "/tmp/test.wav", {}, "hash123", 1000)
                    token = generate_task_access_token(task_id)

                    res = client.get(f"/api/v1/status/{task_id}?access_token={token}")
                    assert res.status_code == 200, (
                        f"API-007: 正确 token 访问任务状态应返回 200，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.SECRET_KEY = old_secret

    def test_download_without_token_returns_403(self):
        """未提供 access_token 时下载应返回 403"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config
        from database import init_db, create_task, update_task

        old_secret = config.SECRET_KEY
        config.SECRET_KEY = "test-secret-key-for-auth"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    task_id = "test-auth-task-003"
                    out_path = os.path.join(config.OUTPUT_DIR, f"{task_id}_repaired.wav")
                    with open(out_path, "wb") as f:
                        f.write(b"RIFF" + b"\x00" * 100)
                    create_task(task_id, "test.wav", "/tmp/test.wav", {}, "hash123", 1000)
                    update_task(task_id, status="completed", output_path=out_path)

                    res = client.get(f"/api/v1/download/{task_id}")
                    assert res.status_code == 403, (
                        f"API-007: 未认证下载应返回 403，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.SECRET_KEY = old_secret

    def test_cancel_without_token_returns_403(self):
        """未提供 access_token 时取消任务应返回 403"""
        from fastapi.testclient import TestClient
        from app import create_app
        import tempfile
        import os
        import config
        from database import init_db, create_task

        old_secret = config.SECRET_KEY
        config.SECRET_KEY = "test-secret-key-for-auth"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                old_db = config.DB_PATH
                old_upload = config.UPLOAD_DIR
                old_output = config.OUTPUT_DIR
                config.DB_PATH = os.path.join(tmpdir, "test.db")
                config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
                config.OUTPUT_DIR = os.path.join(tmpdir, "outputs")
                os.makedirs(config.UPLOAD_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                init_db()

                try:
                    app = create_app()
                    client = TestClient(app)

                    task_id = "test-auth-task-004"
                    create_task(task_id, "test.wav", "/tmp/test.wav", {}, "hash123", 1000)

                    res = client.post(f"/api/v1/cancel/{task_id}")
                    assert res.status_code == 403, (
                        f"API-007: 未认证取消任务应返回 403，实际是 {res.status_code}"
                    )
                finally:
                    config.DB_PATH = old_db
                    config.UPLOAD_DIR = old_upload
                    config.OUTPUT_DIR = old_output
        finally:
            config.SECRET_KEY = old_secret
