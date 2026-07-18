"""
回归测试集合

每个测试对应一个历史 bug，防止修完又被改坏。
运行: cd /workspace && python -m pytest backend/tests/test_regression.py -v
"""

import os
import sys
import tempfile
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
        """cleanup_stale_tasks 应该将 pending 任务标记为 failed"""
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
                assert task["status"] == "failed", f"状态应该是 failed，实际是 {task['status']}"
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
        """cleanup_stale_tasks 应该处理所有非终态（pending/processing/detecting等）"""
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

                stale_statuses = ['pending', 'processing', 'detecting', 'detected', 'analyzing']
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
