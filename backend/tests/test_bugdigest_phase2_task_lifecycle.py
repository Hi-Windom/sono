"""
================================================================================
BUG DIGEST - Phase 2: 任务生命周期相关问题
================================================================================

扫描范围：
  - backend/services/task_base.py (BaseTask)
  - backend/services/task_executor.py (TaskExecutor)
  - backend/services/task_manager.py (RepairTask, DetectTask, RenderTask, 旧代码)
  - backend/services/observability.py (TaskTracer, 与任务的集成)
  - backend/database.py (任务数据库操作)

问题清单（共 15 个）：
================================================================================
【高严重程度 - High】
  BUG-001: TaskExecutor.cancel 未调用 _track_task_end，导致 _active_tasks 集合泄漏
  BUG-002: cleanup_stale_tasks 错误地将 'detected' 状态视为停滞状态（detected 是检测任务终态）
  BUG-003: RenderTask.on_success 未保存 output_path 到数据库
  BUG-004: 服务器重启清理用 'failed' 状态，与系统其他地方的 'error' 状态不一致
  BUG-005: DetectTask.completed_status 依赖 _prev_status，但 _prev_status 在 execute 中才初始化
  BUG-006: 取消任务后若任务还没开始执行，_cancelled_tasks 中条目永远不清理（TaskExecutor 路径）

【中严重程度 - Medium】
  BUG-007: TaskExecutor.cancel 中 tracer.record_state_change 的 from_status 是空字符串
  BUG-008: RenderTask 缺少 stuck monitor 线程（与 RepairTask/DetectTask 不一致）
  BUG-009: 两套取消机制并存且行为不一致（cancel_task vs TaskExecutor.cancel）
  BUG-010: SystemMetrics._active_tasks 与 task_manager._active_tasks 两套计数可能不一致
  BUG-011: get_queue_status 和 mark_stuck_tasks 未包含 'rendering' 状态
  BUG-012: RenderTask.cleanup 中使用 asyncio.get_event_loop() 而非 _get_loop()

【低严重程度 - Low】
  BUG-013: RenderTask._execute_dual 未校验 track_type 参数有效性
  BUG-014: DetectTask 缺少 on_error 实现（与 RepairTask 不一致）
  BUG-015: stuck monitor 线程只设 stop 标志不 join，可能有短暂残留

================================================================================
说明：
  - 每个测试用例都设计为能复现问题（测试失败 = 问题存在）
  - 不修改业务代码，仅通过测试暴露问题
  - 运行方式：cd /workspace && python -m pytest backend/tests/test_bugdigest_phase2_task_lifecycle.py -v
================================================================================
"""

import sys
import os
import tempfile
import time
import threading
import numpy as np
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


@pytest.fixture()
def fresh_env():
    from database import init_db

    tmpdir = tempfile.mkdtemp()
    old_upload = None
    old_output = None
    old_db = None
    try:
        import config
        old_upload = config.UPLOAD_DIR
        old_output = config.OUTPUT_DIR
        old_db = config.DB_PATH
        config.UPLOAD_DIR = tmpdir
        config.OUTPUT_DIR = tmpdir
        config.DB_PATH = os.path.join(tmpdir, "test.db")
    except Exception:
        pass

    init_db()

    import soundfile as sf
    sr = 44100
    duration = 1.0
    t = np.arange(int(sr * duration)) / sr
    y = 0.3 * np.sin(2 * np.pi * 440 * t)
    audio_path = os.path.join(tmpdir, "test.wav")
    sf.write(audio_path, y, sr)

    yield {"tmpdir": tmpdir, "audio_path": audio_path}

    try:
        import config
        if old_upload is not None:
            config.UPLOAD_DIR = old_upload
        if old_output is not None:
            config.OUTPUT_DIR = old_output
        if old_db is not None:
            config.DB_PATH = old_db
    except Exception:
        pass
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_global_state():
    try:
        from services import task_manager as _tm
        with _tm._active_tasks_lock:
            _tm._active_tasks.clear()
        with _tm._cancelled_lock:
            _tm._cancelled_tasks.clear()
    except Exception:
        pass
    try:
        from services.observability import get_system_metrics, get_task_tracer
        get_system_metrics().reset()
        get_task_tracer().clear_history()
    except Exception:
        pass
    yield


# ============================================================================
# 【高严重程度】BUG-001: TaskExecutor.cancel 未调用 _track_task_end
# ============================================================================
class TestBug001_TaskExecutorCancelLeak:
    """
    严重程度: 高
    描述: TaskExecutor.cancel() 方法中调用了 metrics.record_task_cancellation()
          但没有调用 _track_task_end()，导致 _active_tasks 集合中任务永远残留，
          最终会耗尽并发槽位，所有新任务被拒绝。
    位置: backend/services/task_executor.py:87-105
    复现步骤:
      1. 提交一个任务（任务被加入 _active_tasks）
      2. 通过 TaskExecutor.cancel() 取消任务
      3. 检查 _active_tasks 集合，任务仍然存在
    """

    def test_cancel_via_executor_leaves_active_task(self, fresh_env):
        from database import create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask, _active_tasks, _active_tasks_lock

        task_id = "bug001-cancel-leak"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash001")

        task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
        executor = get_task_executor()
        executor.submit(task)

        time.sleep(0.1)

        with _active_tasks_lock:
            assert task_id in _active_tasks, "任务提交后应在 _active_tasks 中"

        executor.cancel(task_id)

        time.sleep(0.2)

        with _active_tasks_lock:
            task_in_set = task_id in _active_tasks

        assert not task_in_set, (
            "BUG-001: TaskExecutor.cancel 后任务仍在 _active_tasks 集合中，"
            "导致并发计数泄漏，最终会耗尽所有并发槽位"
        )

    def test_active_task_count_stays_correct_after_cancel(self, fresh_env):
        from database import create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask, get_active_task_count

        task_id = "bug001-count-leak"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash001b")

        count_before = get_active_task_count()

        task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
        executor = get_task_executor()
        executor.submit(task)

        time.sleep(0.1)
        count_after_submit = get_active_task_count()
        assert count_after_submit == count_before + 1, "提交后计数应 +1"

        executor.cancel(task_id)
        time.sleep(0.5)

        count_after_cancel = get_active_task_count()
        assert count_after_cancel == count_before, (
            f"BUG-001: 取消后活跃任务数未恢复。"
            f"取消前={count_before}, 提交后={count_after_submit}, 取消后={count_after_cancel}"
        )


# ============================================================================
# 【高严重程度】BUG-002: cleanup_stale_tasks 错误清理 'detected' 状态
# ============================================================================
class TestBug002_DetectedStateCleanup:
    """
    严重程度: 高
    描述: cleanup_stale_tasks() 将 'detected' 状态列为需要清理的停滞状态，
          但 'detected' 实际上是检测任务的完成状态（终态）。服务器重启后，
          所有已完成的检测任务都会被错误地标记为 'failed'。
    位置: backend/database.py:85
    复现步骤:
      1. 创建一个状态为 'detected' 的任务
      2. 调用 cleanup_stale_tasks()
      3. 检查任务状态是否被错误修改
    """

    def test_detected_status_should_not_be_cleaned_up(self, fresh_env):
        from database import create_task, update_task, get_task, cleanup_stale_tasks

        task_id = "bug002-detected-cleanup"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"detector_version": "v1.1"}, file_hash="hash002")
        update_task(task_id, status="detected", progress=1.0, step="检测完成",
                    detection_result={"ai_probability": 0.5})

        task_before = get_task(task_id)
        assert task_before["status"] == "detected"

        cleanup_stale_tasks()

        task_after = get_task(task_id)
        assert task_after["status"] == "detected", (
            f"BUG-002: 'detected' 是检测任务的终态，不应被 cleanup_stale_tasks 清理。"
            f"清理前状态={task_before['status']}, 清理后状态={task_after['status']}"
        )

    def test_completed_status_should_not_be_cleaned_up(self, fresh_env):
        from database import create_task, update_task, get_task, cleanup_stale_tasks

        task_id = "bug002-completed-cleanup"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash002b")
        update_task(task_id, status="completed", progress=1.0, step="修复完成")

        task_before = get_task(task_id)
        assert task_before["status"] == "completed"

        cleanup_stale_tasks()

        task_after = get_task(task_id)
        assert task_after["status"] == "completed", (
            f"BUG-002: 'completed' 状态不应被清理。"
            f"清理前={task_before['status']}, 清理后={task_after['status']}"
        )

    def test_pending_status_should_be_cleaned_up(self, fresh_env):
        from database import create_task, get_task, cleanup_stale_tasks

        task_id = "bug002-pending-cleanup"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {}, file_hash="hash002c")

        task_before = get_task(task_id)
        assert task_before["status"] == "pending"

        cleanup_stale_tasks()

        task_after = get_task(task_id)
        assert task_after["status"] != "pending", (
            "'pending' 状态的任务应该被清理为失败状态"
        )


# ============================================================================
# 【高严重程度】BUG-003: RenderTask.on_success 未保存 output_path
# ============================================================================
class TestBug003_RenderTaskMissingOutputPath:
    """
    严重程度: 高
    描述: RenderTask.on_success() 只保存了 render_filename 和 render_result，
          但没有保存 output_path 到数据库。RepairTask.on_success() 会保存
          output_path，但 RenderTask 遗漏了这个关键字段。
    位置: backend/services/task_manager.py:1045-1049
    复现步骤:
      1. 检查 RenderTask.on_success 的返回值
      2. 确认其中不包含 output_path
    """

    def test_render_task_on_success_includes_output_path(self, fresh_env):
        from services.task_manager import RenderTask

        task_id = "bug003-render-output-path"
        input_path = fresh_env["audio_path"]
        output_path = os.path.join(fresh_env["tmpdir"], "output.wav")

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
            "BUG-003: RenderTask.on_success 未包含 output_path 字段，"
            "导致渲染完成后数据库中无法找到输出文件路径"
        )
        assert extra_fields["output_path"] == output_path


# ============================================================================
# 【高严重程度】BUG-004: 服务器重启清理用 'failed' 而非 'error'
# ============================================================================
class TestBug004_FailedVsErrorStatus:
    """
    严重程度: 高
    描述: cleanup_stale_tasks() 将停滞任务标记为 'failed' 状态，
          但系统其他所有地方（TaskExecutor、task_manager 等）统一使用
          'error' 状态表示失败。状态不一致会导致前端无法正确识别错误状态。
    位置: backend/database.py:102
    复现步骤:
      1. 创建一个 pending 状态的任务
      2. 调用 cleanup_stale_tasks()
      3. 检查任务状态是否为 'error'（而非 'failed'）
    """

    def test_cleanup_uses_error_status_not_failed(self, fresh_env):
        from database import create_task, get_task, cleanup_stale_tasks

        task_id = "bug004-failed-status"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {}, file_hash="hash004")

        cleanup_stale_tasks()

        task = get_task(task_id)
        assert task["status"] == "error", (
            f"BUG-004: 服务器重启清理任务使用了 '{task['status']}' 状态，"
            f"但系统其他地方统一使用 'error'。状态不一致会导致前端无法正确显示错误。"
        )


# ============================================================================
# 【高严重程度】BUG-005: DetectTask.completed_status 依赖未初始化的 _prev_status
# ============================================================================
class TestBug005_DetectTaskCompletedStatus:
    """
    严重程度: 高
    描述: DetectTask.completed_status 属性依赖 self._prev_status，但 _prev_status
          在 __init__ 中被初始化为 "pending"，真实值要到 execute() 执行时才从
          数据库读取。如果在 execute() 之前访问 completed_status（例如在
          TaskExecutor._run_task 的开头），会得到错误的默认值。
    位置: backend/services/task_manager.py:723, 748-749
    复现步骤:
      1. 创建一个 DetectTask 实例（任务在数据库中状态为 completed）
      2. 在调用 execute() 之前访问 completed_status
      3. 检查返回值是否正确
    """

    def test_completed_status_before_execute_is_wrong(self, fresh_env):
        from database import create_task, update_task, get_task
        from services.task_manager import DetectTask

        task_id = "bug005-prev-status"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash005")
        update_task(task_id, status="completed", progress=1.0, step="修复完成")

        task = DetectTask(task_id, audio_path, detect_type="repaired", detector_version="v1.1")

        status_before = task.completed_status

        task_before_in_db = get_task(task_id)
        assert task_before_in_db["status"] == "completed", "数据库中任务状态应为 completed"

        assert status_before == "completed", (
            f"BUG-005: DetectTask.completed_status 在 execute() 之前返回 '{status_before}'，"
            f"但数据库中任务实际状态是 'completed'。_prev_status 在 execute() 中才初始化，"
            f"导致提前访问时得到错误值。"
        )


# ============================================================================
# 【高严重程度】BUG-006: 取消未开始的任务，_cancelled_tasks 条目泄漏
# ============================================================================
class TestBug006_CancelledTasksLeak:
    """
    严重程度: 高
    描述: 任务在 pending 状态（还没开始执行 _run_task）时被取消，_cancelled_tasks
          中的条目只有在 _run_task 的 finally 块中才会被清理。如果任务还在
          ThreadPoolExecutor 队列中排队，_cancelled_tasks 会一直累积。
          更严重的是，如果任务在 submit 后、_run_task 开始前被取消，且任务因为
          某些原因从未被执行（比如 executor 被关闭），_cancelled_tasks 会永久泄漏。
    位置: backend/services/task_executor.py:87-105
    复现步骤:
      1. 提交一个任务
      2. 立即取消（确保 _run_task 还没开始）
      3. 检查 _cancelled_tasks 中是否还有该任务
    """

    def test_cancelled_set_is_cleaned_eventually(self, fresh_env):
        from database import create_task
        from services.task_executor import get_task_executor
        from services.task_manager import (
            RepairTask, _cancelled_tasks, _cancelled_lock,
        )

        task_id = "bug006-cancelled-leak"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash006")

        task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
        executor = get_task_executor()

        executor.submit(task)
        time.sleep(0.05)
        executor.cancel(task_id)

        time.sleep(1.0)

        with _cancelled_lock:
            still_in_set = task_id in _cancelled_tasks

        assert not still_in_set, (
            "BUG-006: 任务完成/取消后，_cancelled_tasks 中的条目应被清理。"
            "如果任务在排队阶段被取消，可能存在泄漏风险。"
        )


# ============================================================================
# 【中严重程度】BUG-007: TaskExecutor.cancel 中 state_change from_status 为空
# ============================================================================
class TestBug007_CancelStateChangeFromStatus:
    """
    严重程度: 中
    描述: TaskExecutor.cancel() 中调用 tracer.record_state_change() 时，
          from_status 参数是空字符串 ""，而不是任务的当前真实状态。
          这导致状态追踪链不完整，无法准确知道是从哪个状态转为 cancelled。
    位置: backend/services/task_executor.py:100
    复现步骤:
      1. 创建并提交一个任务
      2. 取消该任务
      3. 检查 trace 中状态变更的 from_status 是否有意义
    """

    def test_cancel_state_change_has_valid_from_status(self, fresh_env):
        from database import create_task
        from services.task_executor import get_task_executor
        from services.observability import get_task_tracer
        from services.task_manager import RepairTask

        task_id = "bug007-from-status"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash007")

        task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
        executor = get_task_executor()
        executor.submit(task)

        time.sleep(0.1)
        executor.cancel(task_id)

        time.sleep(0.5)

        tracer = get_task_tracer()
        history = tracer.get_task_history(task_type="repair")
        task_trace = None
        for t in history:
            if t.task_id == task_id:
                task_trace = t
                break

        assert task_trace is not None, "应该能在历史中找到任务 trace"

        cancel_changes = [sc for sc in task_trace.state_changes if sc.to_status == "cancelled"]
        assert len(cancel_changes) > 0, "应该有 cancelled 状态变更"

        from_status = cancel_changes[0].from_status
        assert from_status != "", (
            f"BUG-007: 取消时 state_change 的 from_status 是空字符串，"
            f"无法知道任务是从什么状态转为 cancelled 的。"
        )
        assert from_status in ("pending", "repairing", "processing"), (
            f"from_status 应该是有效的状态名，而不是 '{from_status}'"
        )


# ============================================================================
# 【中严重程度】BUG-008: RenderTask 缺少 stuck monitor 线程
# ============================================================================
class TestBug008_RenderTaskMissingStuckMonitor:
    """
    严重程度: 中
    描述: RepairTask 和 DetectTask 都有 stuck monitor 线程用于检测任务是否卡住，
          但 RenderTask 完全没有这个机制。如果渲染任务卡住，用户将永远等待，
          没有任何提示。
    位置: backend/services/task_manager.py:853-1065
    复现步骤:
      1. 检查 RenderTask 类的属性和方法
      2. 确认没有 stuck monitor 相关的属性（_stop_monitor, _monitor_thread 等）
    """

    def test_render_task_has_stuck_monitor(self):
        from services.task_manager import RenderTask

        task = RenderTask(
            task_id="bug008-stuck-monitor",
            input_path="/tmp/fake.wav",
            output_path="/tmp/out.wav",
            target_sr=44100,
            bit_depth=16,
            render_filename="out.wav",
        )

        has_stop_monitor = hasattr(task, "_stop_monitor")
        has_monitor_thread = hasattr(task, "_monitor_thread")
        has_start_stuck_monitor = hasattr(task, "_start_stuck_monitor")

        assert has_stop_monitor and has_monitor_thread and has_start_stuck_monitor, (
            "BUG-008: RenderTask 缺少 stuck monitor 机制。"
            "RepairTask 和 DetectTask 都有检测任务卡住的监控线程，"
            "但 RenderTask 没有，导致渲染卡住时用户无感知。"
        )


# ============================================================================
# 【中严重程度】BUG-009: 两套取消机制行为不一致
# ============================================================================
class TestBug009_DualCancelMechanisms:
    """
    严重程度: 中
    描述: 系统中存在两套取消机制：
          1. task_manager.cancel_task() - 旧函数
          2. TaskExecutor.cancel() - 新方法
          两者行为不一致：cancel_task 会调用 _track_task_end()，
          而 TaskExecutor.cancel 不会。cancel_task 不更新 tracer/metrics，
          而 TaskExecutor.cancel 会更新。两套机制并存容易导致混淆和不一致。
    位置: backend/services/task_manager.py:182-191, backend/services/task_executor.py:87-105
    复现步骤:
      1. 比较 cancel_task 和 TaskExecutor.cancel 的行为
      2. 确认它们对 _active_tasks 的处理不一致
    """

    def test_cancel_task_removes_from_active_tasks(self, fresh_env):
        from database import create_task
        from services.task_executor import get_task_executor
        from services.task_manager import (
            RepairTask, cancel_task,
            _active_tasks, _active_tasks_lock,
        )

        task_id = "bug009-dual-cancel"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash009")

        task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
        executor = get_task_executor()
        executor.submit(task)

        time.sleep(0.1)

        with _active_tasks_lock:
            assert task_id in _active_tasks

        cancel_task(task_id)

        with _active_tasks_lock:
            after_old_cancel = task_id in _active_tasks

        assert not after_old_cancel, (
            "旧的 cancel_task 会调用 _track_task_end，正确移除活跃任务"
        )


# ============================================================================
# 【中严重程度】BUG-010: 两套活跃任务计数可能不一致
# ============================================================================
class TestBug010_DualActiveTaskCounters:
    """
    严重程度: 中
    描述: 系统中有两套独立的活跃任务计数：
          1. task_manager._active_tasks 集合
          2. observability.SystemMetrics._active_tasks 数字
          两者通过不同路径更新，可能不一致。例如 TaskExecutor.cancel 会更新
          metrics 但不更新 _active_tasks 集合（BUG-001），导致两者偏差。
    位置: backend/services/observability.py:270-289
    复现步骤:
      1. 提交并取消一个任务
      2. 比较两套计数是否一致
    """

    def test_two_active_counters_are_consistent(self, fresh_env):
        from database import create_task
        from services.task_executor import get_task_executor
        from services.task_manager import RepairTask, get_active_task_count
        from services.observability import get_system_metrics

        task_id = "bug010-dual-counter"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v2.4"}, file_hash="hash010")

        metrics = get_system_metrics()
        count_before_set = get_active_task_count()
        count_before_metrics = metrics.get_task_stats()["active_tasks"]

        task = RepairTask(task_id, audio_path, {"algorithm_version": "v2.4"}, mobile_mode=False)
        executor = get_task_executor()
        executor.submit(task)

        time.sleep(0.1)
        executor.cancel(task_id)
        time.sleep(0.5)

        count_after_set = get_active_task_count()
        count_after_metrics = metrics.get_task_stats()["active_tasks"]

        assert count_after_set == count_after_metrics, (
            f"BUG-010: 两套活跃任务计数不一致。"
            f"task_manager 集合计数={count_after_set}, "
            f"SystemMetrics 计数={count_after_metrics}。"
            f"（提交前: set={count_before_set}, metrics={count_before_metrics}）"
        )


# ============================================================================
# 【中严重程度】BUG-011: get_queue_status 和 mark_stuck_tasks 缺 rendering
# ============================================================================
class TestBug011_MissingRenderingInStatusChecks:
    """
    严重程度: 中
    描述: get_queue_status() 和 mark_stuck_tasks() 只检查 'detecting' 和
          'repairing' 状态的运行中任务，但遗漏了 'rendering' 状态。
          这导致渲染任务不会出现在运行队列状态中，也不会被超时检测覆盖。
    位置: backend/database.py:370-376, 404-417
    复现步骤:
      1. 创建一个状态为 'rendering' 的任务
      2. 调用 get_queue_status()，检查 running 列表是否包含该任务
    """

    def test_rendering_tasks_appear_in_queue_status(self, fresh_env):
        from database import create_task, update_task, get_queue_status

        task_id = "bug011-rendering-queue"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {}, file_hash="hash011")
        update_task(task_id, status="rendering", progress=0.5, step="渲染中...")

        queue_status = get_queue_status()
        running_ids = [t["id"] for t in queue_status["running"]]

        assert task_id in running_ids, (
            "BUG-011: get_queue_status 的 running 列表未包含 'rendering' 状态的任务。"
            "渲染任务在运行队列中不可见。"
        )

    def test_mark_stuck_tasks_covers_rendering(self, fresh_env):
        from database import init_db, create_task, update_task, get_task, get_db

        task_id = "bug011-rendering-stuck"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {}, file_hash="hash011b")
        update_task(task_id, status="rendering", progress=0.5, step="渲染中...")

        conn = get_db()
        conn.execute(
            "UPDATE tasks SET updated_at = datetime('now', '-10 minutes') WHERE id = ?",
            (task_id,),
        )
        conn.commit()
        conn.close()

        from database import mark_stuck_tasks
        mark_stuck_tasks(timeout_seconds=60)

        task = get_task(task_id)
        assert task["status"] == "timeout", (
            "BUG-011: mark_stuck_tasks 未覆盖 'rendering' 状态，"
            "渲染任务永远不会被标记为超时。"
        )


# ============================================================================
# 【中严重程度】BUG-012: RenderTask.cleanup 用错事件循环获取方式
# ============================================================================
class TestBug012_RenderTaskCleanupEventLoop:
    """
    严重程度: 中
    描述: RenderTask.cleanup() 中使用 asyncio.get_event_loop() 获取事件循环，
          但任务在 ThreadPoolExecutor 的后台线程中执行。在后台线程中调用
          get_event_loop() 会创建新的事件循环（或在 Python 3.10+ 中报错），
          而不是使用主线程的运行中事件循环。应该使用 task_manager._get_loop()。
    位置: backend/services/task_manager.py:1059
    复现步骤:
      1. 检查 RenderTask.cleanup 的源码
      2. 确认使用了 asyncio.get_event_loop() 而非 _get_loop()
    """

    def test_render_task_cleanup_uses_proper_event_loop(self):
        import inspect
        from services.task_manager import RenderTask

        cleanup_source = inspect.getsource(RenderTask.cleanup)

        uses_get_event_loop = "asyncio.get_event_loop()" in cleanup_source
        uses_get_loop_helper = "_get_loop(" in cleanup_source or "set_event_loop" in cleanup_source

        assert not uses_get_event_loop or uses_get_loop_helper, (
            "BUG-012: RenderTask.cleanup 使用 asyncio.get_event_loop() 获取事件循环。"
            "在后台线程中调用会创建新的未运行事件循环，导致 WebSocket 广播失败。"
            "应该使用 task_manager._get_loop() 来获取主线程的运行中事件循环。"
        )


# ============================================================================
# 【低严重程度】BUG-013: RenderTask._execute_dual 未校验 track_type
# ============================================================================
class TestBug013_RenderTaskTrackTypeValidation:
    """
    严重程度: 低
    描述: RenderTask._execute_dual() 中 track_type 参数只检查了 "vocal" 和
          "accompaniment"，其他值都会静默走 "both" 路径。没有参数校验，
          传入无效值时不会报错，行为不明确。
    位置: backend/services/task_manager.py:942-1035
    复现步骤:
      1. 创建 RenderTask 时传入无效的 track_type
      2. 检查是否会报错还是静默走 both 路径
    """

    def test_invalid_track_type_raises_error(self):
        from services.task_manager import RenderTask

        task = RenderTask(
            task_id="bug013-track-type",
            input_path="/tmp/in.wav",
            output_path="/tmp/out.wav",
            target_sr=44100,
            bit_depth=16,
            render_filename="out.wav",
            vocal_path="/tmp/vocal.wav",
            accompaniment_path="/tmp/acc.wav",
            track_type="invalid_type",
        )

        assert task.track_type in ("vocal", "accompaniment", "both"), (
            f"BUG-013: RenderTask 允许无效的 track_type='{task.track_type}'。"
            "应该在初始化时校验参数，无效值应抛出异常。"
        )


# ============================================================================
# 【低严重程度】BUG-014: DetectTask 缺少 on_error 实现
# ============================================================================
class TestBug014_DetectTaskMissingOnError:
    """
    严重程度: 低
    描述: RepairTask 实现了 on_error() 方法来特殊处理 MemoryError（自定义
          错误消息和步骤文案），但 DetectTask 没有重写 on_error()。
          两者行为不一致，DetectTask 遇到内存错误时没有特殊处理。
    位置: backend/services/task_manager.py:677-683 (RepairTask.on_error)
          vs DetectTask (无 on_error)
    复现步骤:
      1. 检查 DetectTask 是否有 on_error 方法
      2. 与 RepairTask 对比
    """

    def test_detect_task_has_on_error(self):
        from services.task_manager import DetectTask, RepairTask

        repair_has_on_error = "on_error" in RepairTask.__dict__
        detect_has_on_error = "on_error" in DetectTask.__dict__

        assert detect_has_on_error == repair_has_on_error, (
            "BUG-014: DetectTask 缺少 on_error 实现，与 RepairTask 不一致。"
            "RepairTask 有特殊的 MemoryError 处理，DetectTask 应该保持一致。"
        )


# ============================================================================
# 【低严重程度】BUG-015: stuck monitor 线程不 join，可能短暂残留
# ============================================================================
class TestBug015_StuckMonitorThreadJoin:
    """
    严重程度: 低
    描述: RepairTask 和 DetectTask 的 stuck monitor 线程在 cleanup 中
          只设置了 stop 标志，但没有 join 等待线程退出。虽然线程是 daemon=True，
          不会阻止进程退出，但任务结束后 monitor 线程可能还存活一小段时间
          （最多 2 秒，即 sleep 间隔），造成资源短暂泄漏。
    位置: backend/services/task_manager.py:707-713, 849-850
    复现步骤:
      1. 检查 cleanup 方法中是否调用了 monitor_thread.join()
    """

    def test_repair_task_cleanup_joins_monitor_thread(self):
        import inspect
        from services.task_manager import RepairTask

        cleanup_source = inspect.getsource(RepairTask.cleanup)

        joins_thread = "join(" in cleanup_source
        sets_stop = "_stop_monitor" in cleanup_source

        assert sets_stop and joins_thread, (
            "BUG-015: RepairTask.cleanup 只设置了 _stop_monitor 标志但没有 join 线程。"
            "虽然是 daemon 线程不会阻止进程退出，但任务结束后 monitor 线程可能"
            "还存活最多 2 秒（sleep 间隔），造成短暂的线程泄漏。"
        )

    def test_detect_task_cleanup_joins_monitor_thread(self):
        import inspect
        from services.task_manager import DetectTask

        cleanup_source = inspect.getsource(DetectTask.cleanup)

        joins_thread = "join(" in cleanup_source
        sets_stop = "_stop_monitor" in cleanup_source

        assert sets_stop and joins_thread, (
            "BUG-015: DetectTask.cleanup 只设置了 _stop_monitor 标志但没有 join 线程。"
            "虽然是 daemon 线程不会阻止进程退出，但任务结束后 monitor 线程可能"
            "还存活最多 2 秒（sleep 间隔），造成短暂的线程泄漏。"
        )
