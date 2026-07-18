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
            assert first[1]["id"] == 2, \
                f"最老的消息（id=1）应该被丢弃，队首应该是 id=2，实际是 {first[1]['id']}"

            second = bus._queue.get_nowait()
            assert second[1]["id"] == 3

            third = bus._queue.get_nowait()
            assert third[1]["id"] == 4

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
