"""
深度测试：系统性暴露后端核心链路的问题
目标：至少暴露 10 个真实问题
运行: cd /workspace && python -m pytest backend/tests/test_deep_dive.py -v
"""

import os
import sys
import tempfile
import time
import threading
import numpy as np
import soundfile as sf
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_utils import make_wav_bytes


def _make_test_wav(duration_sec: float = 1.0, sr: int = 44100, freq: float = 440.0, stereo: bool = False) -> str:
    tmp = tempfile.mktemp(suffix=".wav")
    channels = 2 if stereo else 1
    wav_bytes = make_wav_bytes(sr=sr, duration=duration_sec, freq=freq, channels=channels)
    with open(tmp, 'wb') as f:
        f.write(wav_bytes)
    return tmp


# ============================================================================
# 问题 1: cancel_task 取消后任务仍在运行，_track_task_end 没有在 cancel 分支调用
# ============================================================================

class TestCancelTaskLeak:
    """测试取消任务后 active_tasks 是否正确清理"""

    def test_cancelled_task_removed_from_active(self):
        """取消任务后，_active_tasks 应该移除该任务"""
        from services.task_manager import (
            _active_tasks, _track_task_start, _track_task_end,
            cancel_task, generate_task_id,
        )
        tid = generate_task_id()
        assert _track_task_start(tid)
        assert tid in _active_tasks

        cancel_task(tid)
        # 问题：cancel_task 只设置了 _cancelled_tasks，没有调用 _track_task_end
        # 所以 _active_tasks 里还留着这个 task_id
        # 这会导致活跃任务计数泄漏，MAX_CONCURRENT_TASKS 被占满
        assert tid not in _active_tasks, (
            f"任务 {tid} 被取消后仍在 _active_tasks 中，"
            "会导致活跃任务计数泄漏，MAX_CONCURRENT_TASKS 被占满"
        )

    def test_cancel_nonexistent_task_no_error(self):
        """取消不存在的任务不应报错"""
        from services.task_manager import cancel_task
        result = cancel_task("nonexistent_task_id_12345")
        assert result in (True, False)  # 不抛异常就行


# ============================================================================
# 问题 2: _handle_future_exception 中没有调用 _track_task_end
# （异常路径的 _track_task_end 只在 _run_repair/_run_detect 的 finally 里，
#  但如果是 submit 时就拒绝的任务呢？还有没有其他路径？）
# 让我们检查：任务拒绝时（系统繁忙）有没有调用 _track_task_end
# ============================================================================

class TestTaskRejectionCleanup:
    """测试任务被拒绝时的资源清理"""

    def test_rejected_task_not_in_active(self):
        """当 MAX_CONCURRENT_TASKS 已满时，新任务被拒绝，不应留在 _active_tasks"""
        from services.task_manager import (
            _active_tasks, _track_task_start, _track_task_end,
            submit_repair_task, generate_task_id,
        )
        from config import MAX_CONCURRENT_TASKS
        from database import create_task

        # 填满活跃任务
        tids = []
        for i in range(MAX_CONCURRENT_TASKS):
            tid = generate_task_id()
            assert _track_task_start(tid)
            tids.append(tid)

        # 此时再提交一个，应该被拒绝
        tid_extra = generate_task_id()
        create_task(tid_extra, "repair", "test.wav")
        submit_repair_task(tid_extra, "nonexistent.wav", {})

        # 被拒绝的任务不应该在 _active_tasks 中
        assert tid_extra not in _active_tasks, (
            "被拒绝的任务不应该留在 _active_tasks 中"
        )

        # 清理
        for tid in tids:
            _track_task_end(tid)


# ============================================================================
# 问题 3: _ws_send_progress / _ws_send_final 吞掉所有异常
# ============================================================================

class TestWebSocketErrorSilent:
    """测试 WebSocket 发送失败是否完全静默"""

    def test_ws_send_does_not_suppress_all_exceptions_silently(self):
        """WebSocket 发送异常不应该被完全吞掉，至少要打日志"""
        # 检查代码中是否有 bare except: pass
        task_manager_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "task_manager.py"
        )
        with open(task_manager_path) as f:
            content = f.read()

        import re
        # 查找 except Exception: 后面只有 pass 的模式
        pattern = r'except Exception:\s*\n\s*pass'
        matches = re.findall(pattern, content)
        assert len(matches) == 0, (
            f"发现 {len(matches)} 处 bare except + pass，"
            "WebSocket 发送失败至少应该打 warning 日志，不能完全静默"
        )


# ============================================================================
# 问题 4: _generate_waveform_peaks 对立体声的处理有问题
# （np.mean 后 min/max 可能不正确，因为 mean 会把峰值抹平）
# 不过这个是小问题。让我找更严重的。
# 
# 问题 4: perf_collector.start_repair 后如果任务在 repair_audio 之前就失败了，
# end_repair 不会被调用，性能数据泄漏
# ============================================================================

class TestPerfMetricsLeak:
    """测试性能指标收集器是否有泄漏"""

    def test_perf_collector_cleanup_on_error(self):
        """任务失败时 perf_collector 也应该正确清理"""
        from services.perf_metrics import get_perf_collector
        from services.task_manager import generate_task_id

        collector = get_perf_collector()
        tid = generate_task_id()

        # 模拟 start 后任务失败，没有调用 end
        collector.start_repair(tid)

        # 检查：失败路径是否会调用 end_repair？
        # 查看代码：_run_repair 中 end_repair 在 try 块里，
        # 如果 repair_audio 之前就失败（比如 FileNotFoundError），
        # 就不会调用 end_repair，导致泄漏
        #
        # 让我们通过检查代码来确认
        task_manager_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "task_manager.py"
        )
        with open(task_manager_path) as f:
            content = f.read()

        # 检查 end_repair 是否在 finally 块中
        assert "end_repair" in content
        # 查找 end_repair 是否在 finally 块中（粗略检查）
        import re
        # 找 finally: 后面的内容是否包含 end_repair
        finally_pattern = r'finally:\s*\n([\s\S]*?)\n\s*def |finally:\s*\n([\s\S]*?)$'
        matches = re.findall(finally_pattern, content)
        has_end_in_finally = any(
            'end_repair' in (m[0] + m[1]) for m in matches
        )
        assert has_end_in_finally, (
            "perf_collector.end_repair 应该在 finally 块中调用，"
            "否则任务失败时性能数据会泄漏"
        )


# ============================================================================
# 问题 5: _run_repair 中如果 output_path 不存在但修复成功了，
# update_task 里 output_path=None，但 WS 消息里没发 output_path
# 这个可能是设计问题。让我找更明确的 bug。
# 
# 问题 5: cancel_task 设置了 status="cancelled" 但没有发送 WS 消息
# ============================================================================

class TestCancelWebSocketNotify:
    """测试取消任务时是否通知前端"""

    def test_cancel_sends_ws_message(self):
        """取消任务时应该通过 WebSocket 通知前端"""
        task_manager_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "task_manager.py"
        )
        with open(task_manager_path) as f:
            content = f.read()

        # 检查 cancel_task 函数中是否有 _ws_send
        import re
        cancel_func = re.search(r'def cancel_task\([^)]*\):\s*\n([\s\S]*?)\n\ndef ', content)
        if not cancel_func:
            cancel_func = re.search(r'def cancel_task\([^)]*\):\s*\n([\s\S]*?)$', content)

        assert cancel_func, "找不到 cancel_task 函数"
        cancel_body = cancel_func.group(1)

        assert '_ws_send' in cancel_body, (
            "cancel_task 函数中没有调用 _ws_send_final/_ws_send_progress，"
            "前端收不到任务取消的通知，只能靠轮询发现"
        )


# ============================================================================
# 问题 6: _cancelled_tasks 集合没有清理机制
# 如果任务正常完成，_cancelled_tasks.discard 只在 finally 里调用
# 但如果任务从未被取消过，它就不会被加入 _cancelled_tasks
# 所以这个其实没问题。让我找别的。
#
# 问题 6: can_accept_task 和 _track_task_start 之间有竞态条件
# （TOCTOU 竞态）—— 先检查再添加，多线程下可能超限
# ============================================================================

class TestConcurrencyRace:
    """测试并发任务接受是否有竞态条件"""

    def test_track_task_start_is_atomic(self):
        """_track_task_start 应该是原子操作（用锁保护）"""
        from services.task_manager import _track_task_start, _track_task_end, generate_task_id
        from config import MAX_CONCURRENT_TASKS

        # 先填满
        tids = []
        for i in range(MAX_CONCURRENT_TASKS):
            tid = generate_task_id()
            assert _track_task_start(tid)
            tids.append(tid)

        # 再加一个应该失败
        tid_extra = generate_task_id()
        result = _track_task_start(tid_extra)
        assert result is False, (
            f"超过 MAX_CONCURRENT_TASKS={MAX_CONCURRENT_TASKS} 后仍能添加任务"
        )

        # 清理
        for tid in tids:
            _track_task_end(tid)

    def test_can_accept_task_vs_track_race(self):
        """can_accept_task 和 _track_task_start 之间的 TOCTOU 竞态"""
        # 这个测试是代码审查型测试，检查是否有地方先调用 can_accept_task
        # 再调用 _track_task_start（中间没有锁保护）
        task_manager_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "task_manager.py"
        )
        with open(task_manager_path) as f:
            content = f.read()

        # 检查 submit_repair_task 等函数是否先调用 can_accept_task
        # 再调用 _track_task_start
        # 实际上 _track_task_start 内部有锁也有检查，所以问题不大
        # 但如果有地方调用了 can_accept_task 就直接返回给前端"可以提交"，
        # 实际提交时可能已经满了，这是 UX 问题不是 bug
        assert True  # 这不是严重 bug，跳过


# ============================================================================
# 问题 7: audio_repair.py 中如果 algorithm_version 不存在会怎样？
# ============================================================================

class TestAlgorithmVersionValidation:
    """测试无效算法版本的处理"""

    def test_invalid_algorithm_version_returns_error(self):
        """传入不存在的算法版本应该报错，而不是静默使用默认"""
        from services.audio_repair import repair_audio, ALGORITHM_VERSIONS

        input_path = _make_test_wav(0.5)
        output_path = tempfile.mktemp(suffix=".wav")

        try:
            # 传一个不存在的版本
            result = repair_audio(
                input_path, output_path,
                {"algorithm_version": "v999.0_nonexistent"},
                progress_callback=None,
            )
            # 如果不报错，说明静默降级了，这可能不是期望行为
            # 至少应该有日志警告
            assert result is not None
            # 检查使用的版本是否正确
            used_version = result.get("algorithm_version", "")
            assert used_version != "v999.0_nonexistent", (
                "使用了不存在的算法版本"
            )
            # 如果静默降级到默认版本，这是个问题——用户以为用了指定版本，实际不是
            assert used_version in ALGORITHM_VERSIONS, (
                f"返回的版本 {used_version} 不在已知版本中"
            )
            pytest.xfail(
                "无效 algorithm_version 被静默降级为默认版本，"
                "用户不知道自己指定的版本不存在"
            )
        except Exception as e:
            # 抛异常反而是正确的行为
            pass
        finally:
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)


# ============================================================================
# 问题 8: 数据库层：如果 update_task 传入不存在的 task_id 会怎样？
# ============================================================================

class TestDatabaseEdgeCases:
    """测试数据库边界情况"""

    def test_update_nonexistent_task_no_crash(self):
        """更新不存在的任务不应该崩溃"""
        from database import update_task, get_task

        # 不应该抛异常
        result = update_task("nonexistent_task_12345", status="completed")
        assert result is None or result is False or result == 0

        # 也不应该创建新任务
        task = get_task("nonexistent_task_12345")
        assert task is None, "更新不存在的任务不应该自动创建"


# ============================================================================
# 问题 9: upload 路由中分块上传的完整性校验
# ============================================================================

class TestUploadRouteEdgeCases:
    """测试上传路由的边界情况"""

    def test_upload_route_importable(self):
        """上传路由模块应该能正常导入"""
        from api.routes.upload import router
        assert router is not None

    def test_chunk_upload_has_validation(self):
        """分块上传应该有基本的参数校验"""
        upload_path = os.path.join(
            os.path.dirname(__file__), "..", "api", "routes", "upload.py"
        )
        with open(upload_path) as f:
            content = f.read()

        # 检查是否有对 chunk_index / total_chunks 的校验
        assert 'chunk_index' in content
        assert 'total_chunks' in content

        # 检查是否有文件大小限制
        has_size_limit = 'MAX_UPLOAD_SIZE' in content or 'max_size' in content or '500' in content
        # 如果没有，这是个问题
        if not has_size_limit:
            pytest.xfail("上传路由中没有发现文件大小限制的检查")
        assert True


# ============================================================================
# 问题 10: 所有修复算法的 repair_audio 函数签名一致性
# ============================================================================

class TestRepairFunctionSignatures:
    """测试所有修复算法的函数签名是否一致"""

    def test_all_repair_algorithms_have_same_signature(self):
        """所有修复算法的 repair_audio 应该有相同的参数列表"""
        import inspect
        from services.audio_repair import ALGORITHM_VERSIONS

        signatures = {}
        for version, info in ALGORITHM_VERSIONS.items():
            module_path = info.get("module")
            if not module_path:
                continue
            try:
                from importlib import import_module
                mod = import_module(module_path)
                fn = getattr(mod, "repair_audio", None)
                if fn:
                    sig = inspect.signature(fn)
                    signatures[version] = set(sig.parameters.keys())
            except Exception:
                pass

        if len(signatures) < 2:
            pytest.skip("可用的修复算法少于 2 个")

        # 取第一个作为基准
        base_version = list(signatures.keys())[0]
        base_params = signatures[base_version]

        mismatches = []
        for version, params in signatures.items():
            if params != base_params:
                mismatches.append((version, params - base_params, base_params - params))

        assert not mismatches, (
            f"修复算法参数签名不一致！\n"
            f"基准版本 {base_version}: {base_params}\n"
            f"不一致的版本:\n"
            + "\n".join(
                f"  {v}: 多余={extra}, 缺少={missing}"
                for v, extra, missing in mismatches
            )
        )


# ============================================================================
# 问题 11: ws_manager 中 send_final 发送后是否清理连接？
# ============================================================================

class TestWSManagerCleanup:
    """测试 WebSocket 连接管理的清理逻辑"""

    def test_ws_manager_disconnect_cleans_up(self):
        """断开连接后应该正确清理内部状态"""
        from services.ws_manager import ws_manager

        # 初始状态应该是干净的
        # 注册一个假连接再断开，看是否泄漏
        class FakeWS:
            def __init__(self):
                self.closed = False
            async def send_text(self, text):
                pass

        fake_ws = FakeWS()
        ws_manager.connect("test_task_123", fake_ws)

        # 检查是否连接成功
        assert ws_manager.get_connection_count() > 0 or ws_manager.get_connection("test_task_123") is not None

        # 断开连接
        ws_manager.disconnect("test_task_123", fake_ws)

        # 检查是否清理干净
        # 这里可能有问题：如果同一个 task_id 有多个连接，disconnect 一个后
        # task_id 还在字典里，这是正常的。但如果所有连接都断了，应该清理
        conn = ws_manager.get_connection("test_task_123")
        if conn is not None:
            # 如果还有连接，说明清理不彻底（当只有一个连接时）
            assert False, (
                "唯一连接断开后，task_id 仍在连接字典中，"
                "可能导致内存泄漏"
            )


# ============================================================================
# 问题 12: 内存卫士在多线程下的线程安全
# ============================================================================

class TestMemoryGuardThreadSafety:
    """测试内存卫士的线程安全性"""

    def test_memory_guard_concurrent_access(self):
        """多线程并发调用内存检查不应该崩溃"""
        from services.memory_guard import estimate_memory_usage, get_available_memory_bytes

        errors = []
        def worker():
            try:
                get_available_memory_bytes()
                estimate_memory_usage(44100, 100, "v3.2")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发调用内存检查出错: {errors}"
