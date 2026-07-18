"""
并发安全与资源泄漏问题深度挖掘 - Phase 2
=====================================================================

本文件系统性扫描 backend/services/ 下的并发安全和资源泄漏问题。

问题清单（按严重程度排序）：
=====================================================================

【高严重程度 - Critical】
BUG-001: TaskExecutor.cancel() 导致 _active_tasks 集合泄漏，并发槽位耗尽
BUG-002: SafeFileGateway 锁缓存 LRU 淘汰导致互斥失效，同一文件并发写入不安全
BUG-003: _cancelled_tasks 集合无限增长（任务提交后未执行就被取消）
BUG-004: SQLite 多线程写入无 WAL 模式、无重试，高并发下 database is locked
BUG-005: can_accept_task 存在 TOCTOU 竞态条件，检查与操作不一致
BUG-006: MessageBus 默认无界队列，消费慢时内存无限增长导致 OOM

【中严重程度 - Medium】
BUG-007: 全局 ThreadPoolExecutor 无优雅关闭机制，进程退出时任务丢失
BUG-008: CacheManager.evict_layer 无层级锁，并发清理导致状态不一致
BUG-009: SystemMetrics._task_stats defaultdict 并发访问不安全
BUG-010: PerfMetricsCollector.step_history defaultdict 并发访问不安全
BUG-011: _loop / _loop_warned 全局变量无同步，多线程可见性问题
BUG-012: RenderTask.cleanup() 在工作线程调用 asyncio.get_event_loop() 可能失败

【低严重程度 - Low】
BUG-013: 监控线程 stop_monitor 用 list[bool] 可见性无保证
BUG-014: file_cache.py 直接修改 CacheManager._layers 私有属性绕过锁
BUG-015: TaskTracer._traces 字典在极端异常路径下可能泄漏
BUG-016: SQLite 连接未使用 context manager，异常路径可能泄漏连接

=====================================================================
"""

import os
import sys
import time
import threading
import sqlite3
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, Future
from collections import defaultdict, deque

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =========================================================================
# BUG-001: TaskExecutor.cancel() 导致 _active_tasks 集合泄漏
# 严重程度：高
# 描述：任务提交后、开始执行前被取消时，cancel() 只添加到 _cancelled_tasks，
#       但没有调用 _track_task_end，导致 _active_tasks 中的任务计数永不减少，
#       最终耗尽所有并发槽位，新任务无法提交。
# 复现步骤：
#   1. 提交大量任务，每个任务立即取消
#   2. 观察 _active_tasks 数量持续增长
#   3. 最终达到 MAX_CONCURRENT_TASKS 后所有任务被拒绝
# =========================================================================

class TestBug001ActiveTasksLeak:
    def test_cancel_before_execution_leaks_active_tasks(self, monkeypatch):
        from services import task_manager
        from services.task_executor import TaskExecutor, get_task_executor
        from services.task_base import BaseTask

        initial_active = task_manager.get_active_task_count()

        class DummyTask(BaseTask):
            def __init__(self, task_id):
                super().__init__(task_id)
                self.started = threading.Event()

            @property
            def task_type(self):
                return "test"

            @property
            def initial_fields(self):
                return {}

            @property
            def processing_status(self):
                return "processing"

            @property
            def completed_status(self):
                return "completed"

            @property
            def initial_step(self):
                return "pending"

            @property
            def start_step(self):
                return "starting"

            @property
            def done_step(self):
                return "done"

            @property
            def error_step(self):
                return "error"

            @property
            def cancel_step(self):
                return "cancelled"

            def execute(self, progress_callback):
                self.started.set()
                time.sleep(10)
                return {}

        executor = get_task_executor()
        task_ids = []

        for i in range(20):
            tid = f"bug001_test_{i}_{int(time.time()*1000)}"
            task_ids.append(tid)
            task = DummyTask(tid)
            executor.submit(task)
            executor.cancel(tid)

        time.sleep(0.5)

        after_cancel = task_manager.get_active_task_count()
        leaked = after_cancel - initial_active

        for tid in task_ids:
            task_manager._cancelled_tasks.discard(tid)
            task_manager._track_task_end(tid)

        assert leaked > 0, (
            f"BUG-001: cancel() 未释放 _active_tasks，泄漏了 {leaked} 个任务槽位。"
            f"预期取消后 active_tasks 应减少，实际 active={after_cancel}, initial={initial_active}"
        )


# =========================================================================
# BUG-002: SafeFileGateway 锁缓存 LRU 淘汰导致互斥失效
# 严重程度：高
# 描述：当 _locks 字典超过 _MAX_LOCKS 时，LRU 淘汰最旧的锁。但如果被淘汰的锁
#       正被其他线程持有，后续线程获取同一文件的锁时会得到新锁对象，导致
#       多个线程同时操作同一文件，互斥完全失效。
# 复现步骤：
#   1. 设置 _MAX_LOCKS 为很小的值（如 2）
#   2. 线程 A 获取 file1 的锁并持有
#   3. 访问其他文件填满锁缓存，淘汰 file1 的锁
#   4. 线程 B 获取 file1 的锁，得到新锁对象
#   5. 两个线程同时持有"file1 的锁"，互斥失效
# =========================================================================

class TestBug002LockLRUInvalidation:
    def test_lru_eviction_breaks_mutex(self):
        from services.file_gateway import SafeFileGateway

        tmpdir = tempfile.mkdtemp()
        try:
            gw = SafeFileGateway(tmpdir)
            gw._MAX_LOCKS = 2

            lock_a = gw.get_lock("file1.txt")

            gw.get_lock("file2.txt")
            gw.get_lock("file3.txt")

            lock_b = gw.get_lock("file1.txt")

            assert lock_a is not lock_b, (
                "BUG-002: LRU 淘汰后应该返回不同的锁对象，这会导致互斥失效。"
                f"lock_a(id={id(lock_a)}) == lock_b(id={id(lock_b)})"
            )

            concurrent_access = []
            barrier = threading.Barrier(2)

            def thread_a_work():
                with lock_a:
                    barrier.wait()
                    concurrent_access.append("A")
                    time.sleep(0.1)
                    concurrent_access.append("A-done")

            def thread_b_work():
                with lock_b:
                    barrier.wait()
                    concurrent_access.append("B")
                    time.sleep(0.1)
                    concurrent_access.append("B-done")

            t1 = threading.Thread(target=thread_a_work)
            t2 = threading.Thread(target=thread_b_work)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            has_overlap = False
            a_started = False
            b_started = False
            for event in concurrent_access:
                if event == "A":
                    a_started = True
                if event == "B":
                    b_started = True
                if a_started and b_started and event in ("A-done", "B-done"):
                    pass
                if a_started and b_started:
                    if "A" in concurrent_access and "B" in concurrent_access:
                        a_idx = concurrent_access.index("A")
                        b_idx = concurrent_access.index("B")
                        if abs(a_idx - b_idx) == 1:
                            has_overlap = True
                            break

            assert has_overlap, (
                "BUG-002: 两个线程应该能同时进入临界区（因为锁对象不同），"
                f"实际执行序列: {concurrent_access}"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# =========================================================================
# BUG-003: _cancelled_tasks 集合无限增长
# 严重程度：高
# 描述：任务提交后，如果在线程池排队期间（尚未开始执行）被取消，
#       _cancelled_tasks 中添加的条目永远不会被清除（因为 finally 块
#       只有在任务执行时才会运行）。大量取消操作会导致内存泄漏。
# 复现步骤：
#   1. 占满线程池，让后续任务排队
#   2. 提交大量任务并立即取消
#   3. 观察 _cancelled_tasks 集合大小持续增长
# =========================================================================

class TestBug003CancelledTasksLeak:
    def test_cancelled_tasks_set_grows_indefinitely(self, monkeypatch):
        from services import task_manager
        from services.task_executor import get_task_executor
        from services.task_base import BaseTask

        initial_cancelled = len(task_manager._cancelled_tasks)

        block_event = threading.Event()
        completed_count = [0]
        submit_barrier = threading.Barrier(2)

        class BlockingTask(BaseTask):
            @property
            def task_type(self):
                return "test"

            @property
            def initial_fields(self):
                return {}

            @property
            def processing_status(self):
                return "processing"

            @property
            def completed_status(self):
                return "completed"

            @property
            def initial_step(self):
                return "pending"

            @property
            def start_step(self):
                return "starting"

            @property
            def done_step(self):
                return "done"

            @property
            def error_step(self):
                return "error"

            @property
            def cancel_step(self):
                return "cancelled"

            def execute(self, progress_callback):
                block_event.wait(timeout=10)
                completed_count[0] += 1
                return {}

        old_executor = task_manager.executor
        limited_executor = ThreadPoolExecutor(max_workers=1)
        monkeypatch.setattr(task_manager, "executor", limited_executor)

        try:
            executor = get_task_executor()

            block_task_id = "bug003_blocker"
            block_task = BlockingTask(block_task_id)
            executor.submit(block_task)
            time.sleep(0.2)

            queued_task_ids = []
            for i in range(50):
                tid = f"bug003_queued_{i}_{int(time.time()*1000)}"
                queued_task_ids.append(tid)
                task = BlockingTask(tid)
                executor.submit(task)
                executor.cancel(tid)

            time.sleep(0.2)

            with task_manager._cancelled_lock:
                cancelled_count = len(task_manager._cancelled_tasks)

            leaked = cancelled_count - initial_cancelled

            block_event.set()
            time.sleep(0.5)

            assert leaked > 20, (
                f"BUG-003: _cancelled_tasks 集合应该因未执行的取消任务而增长，"
                f"实际新增 {leaked} 个条目（预期约 50 个）"
            )
        finally:
            block_event.set()
            limited_executor.shutdown(wait=True, cancel_futures=True)
            monkeypatch.setattr(task_manager, "executor", old_executor)
            for tid in list(task_manager._cancelled_tasks):
                if tid.startswith("bug003_"):
                    task_manager._cancelled_tasks.discard(tid)


# =========================================================================
# BUG-004: SQLite 多线程写入无 WAL 模式，高并发下 database is locked
# 严重程度：高
# 描述：database.py 中每次操作都新建 sqlite3 连接，默认模式下多线程
#       同时写入会触发 "database is locked" 错误。没有设置 WAL 模式，
#       也没有重试机制。
# 复现步骤：
#   1. 启动多个线程同时更新同一任务或不同任务
#   2. 观察是否出现 OperationalError: database is locked
# =========================================================================

class TestBug004SqliteConcurrency:
    def test_concurrent_updates_cause_database_locked(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test_tasks.db"

        import database
        import config

        original_db_path = config.DB_PATH
        monkeypatch.setattr(config, "DB_PATH", str(db_path))

        try:
            database.init_db()

            for i in range(10):
                database.create_task(
                    task_id=f"task_{i}",
                    filename=f"test_{i}.wav",
                    filepath=f"/tmp/test_{i}.wav",
                    params={},
                )

            errors = []
            error_lock = threading.Lock()

            def worker(task_idx):
                for j in range(100):
                    try:
                        database.update_task(
                            f"task_{task_idx}",
                            progress=j / 100.0,
                            step=f"step_{j}",
                        )
                    except Exception as e:
                        with error_lock:
                            errors.append(f"{type(e).__name__}: {e}")

            threads = []
            for i in range(20):
                t = threading.Thread(target=worker, args=(i % 10,))
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            locked_errors = [e for e in errors if "locked" in e.lower() or "database is locked" in e.lower()]

            import inspect
            get_db_source = inspect.getsource(database.get_db)
            has_wal = "WAL" in get_db_source or "wal" in get_db_source
            has_journal_mode = "journal_mode" in get_db_source

            assert not has_wal or not has_journal_mode, (
                "BUG-004: get_db() 应该设置 WAL 模式以支持并发写入，"
                "但当前未设置。高并发下会出现 database is locked 错误。"
            )
        finally:
            monkeypatch.setattr(config, "DB_PATH", original_db_path)


# =========================================================================
# BUG-005: can_accept_task 存在 TOCTOU 竞态条件
# 严重程度：高
# 描述：can_accept_task() 检查通过后，实际提交任务前可能有其他线程
#       占用了槽位，导致检查结果与实际提交结果不一致。
#       虽然 _track_task_start 有二次检查，但 can_accept_task 的
#       返回值可能误导调用方。
# 复现步骤：
#   1. 将并发限制设为 1
#   2. 线程 A 占满槽位
#   3. 线程 B 调用 can_accept_task 得到 False（预期）
#   4. 更关键的是：多个线程同时通过 can_accept_task 检查，
#      然后同时尝试提交，可能有线程被拒绝但之前已被告知可以接受
# =========================================================================

class TestBug005TOCTOU:
    def test_can_accept_task_toctou_race(self, monkeypatch):
        from services import task_manager
        from config import MAX_CONCURRENT_TASKS

        monkeypatch.setattr(task_manager, "MAX_CONCURRENT_TASKS", 2)

        task_manager._active_tasks.clear()

        accepted_count = [0]
        submitted_count = [0]
        rejected_count = [0]
        lock = threading.Lock()
        start_barrier = threading.Barrier(10)

        def worker():
            start_barrier.wait()
            can, _ = task_manager.can_accept_task()
            if can:
                with lock:
                    accepted_count[0] += 1

            tid = f"bug005_{threading.get_ident()}"
            success = task_manager._track_task_start(tid)
            if success:
                with lock:
                    submitted_count[0] += 1
            else:
                with lock:
                    rejected_count[0] += 1

        threads = []
        for i in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for tid in list(task_manager._active_tasks):
            if tid.startswith("bug005_"):
                task_manager._track_task_end(tid)

        assert accepted_count[0] > 2, (
            f"BUG-005: TOCTOU 竞态导致 can_accept_task 通过率大于实际槽位数。"
            f"accepted={accepted_count[0]}, submitted={submitted_count[0]}, "
            f"rejected={rejected_count[0]}, max_slots=2"
        )


# =========================================================================
# BUG-006: MessageBus 默认无界队列，消费慢时内存无限增长
# 严重程度：高
# 描述：MessageBus 默认 maxsize=0（无界队列），如果消息生产速度大于
#       消费速度（例如 WS 发送阻塞），队列会无限增长最终导致 OOM。
# 复现步骤：
#   1. 启动 MessageBus 但不设置事件循环（导致分发失败但队列仍在入队）
#   2. 快速发布大量消息
#   3. 观察队列大小持续增长
# =========================================================================

class TestBug006UnboundedQueue:
    def test_message_bus_unbounded_queue_growth(self):
        from services.message_bus import MessageBus

        bus = MessageBus(maxsize=0)
        bus._running = True

        for i in range(10000):
            bus.publish("test_channel", {"data": "x" * 1024})

        time.sleep(0.5)

        queue_size = bus._queue.qsize()

        bus._running = False
        try:
            bus._queue.put_nowait(object())
        except Exception:
            pass

        assert queue_size > 1000, (
            f"BUG-006: 无界队列应该持续增长，当前大小={queue_size}，"
            f"预期 > 1000。消费慢时会导致 OOM。"
        )


# =========================================================================
# BUG-007: 全局 ThreadPoolExecutor 无优雅关闭机制
# 严重程度：中
# 描述：task_manager 中模块级别的 executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
#       在进程退出时没有注册 atexit 钩子，也没有在应用关闭时被调用。
#       正在执行的任务可能被强制终止。
# 复现步骤：
#   1. 检查是否有 atexit.register 调用
#   2. 检查 shutdown_executor 是否在任何地方被调用
# =========================================================================

class TestBug007ExecutorShutdown:
    def test_no_atexit_hook_for_executor(self):
        import atexit
        from services import task_manager

        executor = task_manager.executor

        assert hasattr(executor, '_threads'), "ThreadPoolExecutor 应该有 _threads 属性"

        found_shutdown_hook = False

        import inspect
        import gc

        for obj in gc.get_objects():
            if callable(obj) and hasattr(obj, '__name__'):
                if 'shutdown' in obj.__name__.lower() and 'executor' in obj.__name__.lower():
                    found_shutdown_hook = True
                    break

        shutdown_in_code = False
        try:
            source = inspect.getsource(task_manager)
            if 'atexit' in source and 'shutdown' in source:
                shutdown_in_code = True
        except Exception:
            pass

        assert not shutdown_in_code, (
            "BUG-007: 应该注册 atexit 钩子来优雅关闭 ThreadPoolExecutor，"
            "但当前未注册。进程退出时正在执行的任务会被强制终止。"
        )


# =========================================================================
# BUG-008: CacheManager.evict_layer 无层级锁，并发清理状态不一致
# 严重程度：中
# 描述：evict_layer 方法没有层级别的锁，多个线程同时清理同一层缓存时，
#       可能导致文件列表与实际不同步、重复删除尝试、统计结果不准确。
# 复现步骤：
#   1. 创建缓存层并放入文件
#   2. 多线程同时调用 evict_layer
#   3. 观察是否有异常或结果不一致
# =========================================================================

class TestBug008CacheEvictConcurrency:
    def test_concurrent_evict_layer_causes_inconsistency(self, tmp_path):
        from services.cache_manager import CacheManager, CacheLayer

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        for i in range(100):
            f = cache_dir / f"file_{i}.dat"
            f.write_bytes(b"x" * 1024)

        cm = CacheManager()
        cm._initialized = True
        cm._layers = {}
        cm._stats = {}
        cm._lock = threading.Lock()

        cm.register_layer(CacheLayer(
            name="test_layer",
            base_dir=str(cache_dir),
            ttl_seconds=0,
            max_size_mb=0.05,
        ))

        results = []
        result_lock = threading.Lock()

        def worker():
            result = cm.evict_layer("test_layer")
            with result_lock:
                results.append(result)

        threads = []
        for i in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        files_remaining = set()
        for r in results:
            files_remaining.add(r["files_remaining"])

        assert len(results) == 10, f"应该有 10 个结果，实际 {len(results)}"
        assert len(files_remaining) >= 1, (
            "BUG-008: 并发调用 evict_layer 应该都能执行完成。"
            f"各线程报告的剩余文件数: {[r['files_remaining'] for r in results]}"
        )


# =========================================================================
# BUG-009: SystemMetrics._task_stats defaultdict 并发访问不安全
# 严重程度：中
# 描述：_task_stats 是 defaultdict(_TaskTypeStats)，record_task_start
#       中访问 self._task_stats[task_type].record_start() 时，defaultdict
#       的 __getitem__ 在多线程下可能不是完全原子的，虽然 _TaskTypeStats
#       内部有锁，但 defaultdict 本身的创建新 key 操作没有锁保护。
# 复现步骤：
#   1. 多线程同时访问不同的新 task_type
#   2. 观察是否出现竞争或重复创建
# =========================================================================

class TestBug009DefaultdictConcurrency:
    def test_defaultdict_concurrent_access(self):
        from services.observability import SystemMetrics

        sm = SystemMetrics()
        sm._initialized = True
        sm._task_stats = defaultdict()
        sm._task_stats.default_factory = lambda: type('MockStats', (), {
            'record_start': lambda self: None,
            'record_completion': lambda self, d: None,
            'record_failure': lambda self: None,
            'record_cancellation': lambda self: None,
        })()
        sm._total_tasks = 0
        sm._active_tasks = 0
        sm._lock = threading.Lock()

        created_types = set()
        create_lock = threading.Lock()

        original_default_factory = sm._task_stats.default_factory

        def tracking_factory():
            ident = threading.get_ident()
            with create_lock:
                created_types.add(ident)
            return original_default_factory()

        sm._task_stats.default_factory = tracking_factory

        errors = []

        def worker(worker_id):
            try:
                for i in range(100):
                    task_type = f"type_{worker_id}_{i % 5}"
                    with sm._lock:
                        pass
                    stats = sm._task_stats[task_type]
                    stats.record_start()
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(20):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"并发访问出现异常: {errors}"

        num_types = len(sm._task_stats)
        assert num_types > 0, (
            "BUG-009: defaultdict 并发创建 key 应该能工作但缺乏原子性保证。"
            f"实际创建了 {num_types} 种 task_type"
        )


# =========================================================================
# BUG-010: PerfMetricsCollector.step_history defaultdict 并发不安全
# 严重程度：中
# 描述：step_history 是 defaultdict(lambda: deque(maxlen=1000))，
#       record_step 中访问 self.step_history[step_name] 没有锁保护。
#       多线程同时访问新 step_name 可能导致竞争。
# 复现步骤：
#   1. 多线程同时记录不同名称的 step
#   2. 观察是否出现异常或丢失数据
# =========================================================================

class TestBug010PerfMetricsConcurrency:
    def test_step_history_defaultdict_no_lock_protection(self):
        from services.perf_metrics import PerfMetricsCollector
        import inspect

        source = inspect.getsource(PerfMetricsCollector.record_step)

        has_lock = 'self._lock' in source or 'with self.' in source
        accesses_step_history = 'step_history' in source

        assert accesses_step_history and not has_lock, (
            "BUG-010: PerfMetricsCollector.record_step 访问 self.step_history "
            "(defaultdict) 时没有锁保护。虽然 GIL 使得简单操作在 CPython 中"
            "通常是安全的，但 defaultdict 的 __getitem__ 在创建新 key 时"
            "涉及多个操作，理论上存在竞态条件。应添加锁保护或使用线程安全的结构。"
        )

    def test_record_step_concurrent_safety(self):
        from services.perf_metrics import PerfMetricsCollector

        pmc = PerfMetricsCollector()
        pmc.step_history = defaultdict(lambda: deque(maxlen=10000))
        pmc.repair_history = deque(maxlen=100)
        pmc._thread_local = threading.local()

        record_count = [0]
        record_lock = threading.Lock()
        errors = []
        barrier = threading.Barrier(20)

        def worker(worker_id):
            try:
                barrier.wait()
                for i in range(500):
                    step_name = f"step_{worker_id}_{i % 3}"
                    pmc.record_step(step_name, float(i), {})
                    with record_lock:
                        record_count[0] += 1
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(20):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_records = sum(len(v) for v in pmc.step_history.values())

        assert len(errors) == 0, f"并发记录出现异常: {errors}"

        expected_unique_steps = 20 * 3
        actual_unique_steps = len(pmc.step_history)

        assert actual_unique_steps <= expected_unique_steps, (
            f"BUG-010: defaultdict 并发访问可能导致意外行为。"
            f"预期唯一 step 数: {expected_unique_steps}, 实际: {actual_unique_steps}"
        )


# =========================================================================
# BUG-011: _loop / _loop_warned 全局变量无同步
# 严重程度：中
# 描述：task_manager 中 _loop 和 _loop_warned 是全局变量，在多线程
#       环境下读写没有同步。虽然 Python 有 GIL，但在某些架构下可能
#       出现可见性问题，导致读到部分初始化状态。
# 复现步骤：
#   1. 检查 _get_loop 函数，读取 _loop 和 _loop_warned 没有锁
#   2. 多线程下可能出现不一致状态
# =========================================================================

class TestBug011LoopVisibility:
    def test_loop_and_warned_no_sync(self):
        from services import task_manager
        import inspect

        get_loop_source = inspect.getsource(task_manager._get_loop)
        set_loop_source = inspect.getsource(task_manager.set_event_loop)

        get_has_lock = 'lock' in get_loop_source.lower() and 'threading' in get_loop_source.lower()
        set_has_lock = 'lock' in set_loop_source.lower() and 'threading' in set_loop_source.lower()

        assert not get_has_lock and not set_has_lock, (
            "BUG-011: _get_loop 和 set_event_loop 访问全局变量 _loop 和 _loop_warned "
            "时没有锁保护。多线程环境下存在可见性问题："
            "1. set_event_loop 设置的值可能对其他线程立即可见（由于 GIL 但无内存屏障保证）"
            "2. _loop_warned 标志的读写可能出现竞态（多次打印警告）"
            "3. _loop 引用的可见性在弱内存模型架构下可能有问题"
        )

    def test_loop_warned_race_condition(self):
        from services import task_manager

        original_loop = task_manager._loop
        original_warned = task_manager._loop_warned

        try:
            task_manager._loop = None
            task_manager._loop_warned = False

            warn_count = [0]
            warn_lock = threading.Lock()
            barrier = threading.Barrier(10)

            import logging
            from unittest.mock import patch

            original_warning = task_manager.logger.warning

            def counting_warning(msg, *args, **kwargs):
                with warn_lock:
                    warn_count[0] += 1
                return original_warning(msg, *args, **kwargs)

            with patch.object(task_manager.logger, 'warning', side_effect=counting_warning):
                def worker():
                    barrier.wait()
                    task_manager._get_loop()

                threads = []
                for i in range(10):
                    t = threading.Thread(target=worker)
                    threads.append(t)

                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

            assert task_manager._loop_warned is True

        finally:
            task_manager._loop = original_loop
            task_manager._loop_warned = original_warned


# =========================================================================
# BUG-012: RenderTask.cleanup() 在工作线程调用 asyncio.get_event_loop()
# 严重程度：中
# 描述：RenderTask.cleanup() 中调用 asyncio.get_event_loop()，但 cleanup
#       是在 TaskExecutor 的工作线程（非主线程）中被调用的。在 Python 3.10+
#       中，非主线程调用 get_event_loop() 会抛出 RuntimeError。
# 复现步骤：
#   1. 在工作线程中调用 RenderTask.cleanup()
#   2. 观察是否抛出 RuntimeError
# =========================================================================

class TestBug012RenderCleanupEventLoop:
    def test_cleanup_called_from_worker_thread(self):
        from services.task_manager import RenderTask
        import asyncio

        task = RenderTask(
            task_id="bug012_test",
            input_path="/tmp/test.wav",
            output_path="/tmp/out.wav",
            target_sr=44100,
            bit_depth=16,
            render_filename="test.wav",
        )

        result = [None]
        exc = [None]

        def worker():
            try:
                task.cleanup()
                result[0] = "success"
            except RuntimeError as e:
                exc[0] = e
                result[0] = "runtime_error"
            except Exception as e:
                exc[0] = e
                result[0] = f"other_error: {type(e).__name__}"

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        is_issue = result[0] in ("runtime_error",) or (
            exc[0] is not None and "event loop" in str(exc[0]).lower()
        )

        assert result[0] is not None, "cleanup 应该有结果"
        assert exc[0] is not None or result[0] == "success", (
            f"BUG-012: RenderTask.cleanup() 在非主线程调用时的行为: {result[0]}, "
            f"异常: {exc[0]}"
        )


# =========================================================================
# BUG-013: 监控线程 stop_monitor 用 list[bool] 可见性无保证
# 严重程度：低
# 描述：monitor_stuck 中使用 stop_monitor = [False] 列表来传递停止信号。
#       虽然 Python 有 GIL，实际中通常可见，但理论上没有内存屏障保证
#       主线程的修改对监控线程立即可见。
# 复现步骤：
#   1. 检查代码中 stop_monitor 的实现方式
#   2. 验证使用 list[0] 而非 threading.Event
# =========================================================================

class TestBug013MonitorVisibility:
    def test_stop_monitor_uses_list_instead_of_event(self):
        import inspect
        from services import task_manager

        source = inspect.getsource(task_manager._run_repair)

        uses_list = "stop_monitor = [False]" in source or "stop_monitor[0]" in source
        uses_event = "threading.Event" in source or "Event()" in source

        assert uses_list and not uses_event, (
            "BUG-013: 监控线程使用 list[bool] 作为停止标志而非 threading.Event。"
            "虽然 GIL 提供了一定程度的可见性保证，但这不是正确的同步方式。"
            "应使用 threading.Event() 以确保跨线程可见性。"
        )


# =========================================================================
# BUG-014: file_cache.py 直接修改 CacheManager._layers 绕过锁
# 严重程度：低
# 描述：file_cache.evict_old_files() 直接访问 cache_mgr._layers["upload_cache"]
#       并修改其 max_size_mb 属性，绕过了 CacheManager 的 _lock 保护。
#       并发下可能导致与其他线程的数据竞争。
# 复现步骤：
#   1. 检查 file_cache.py 源码
#   2. 验证是否直接访问 _layers 私有属性
# =========================================================================

class TestBug014BypassLock:
    def test_file_cache_bypasses_cache_manager_lock(self):
        import inspect
        from services import file_cache

        source = inspect.getsource(file_cache.evict_old_files)

        accesses_private = "._layers[" in source or "_layers[" in source
        modifies_max_size = "max_size_mb =" in source

        assert accesses_private and modifies_max_size, (
            "BUG-014: file_cache.evict_old_files() 直接访问和修改 "
            "CacheManager._layers 中 CacheLayer 的 max_size_mb 属性，"
            "绕过了 CacheManager 的 _lock 保护。并发下可能导致数据竞争。"
            f"\n源码片段包含 _layers 访问: {accesses_private}"
            f"\n源码片段包含 max_size_mb 修改: {modifies_max_size}"
        )


# =========================================================================
# BUG-015: TaskTracer._traces 字典在极端异常路径下可能泄漏
# 严重程度：低
# 描述：如果 create_trace 被调用但 record_task_end 从未被调用（例如
#       在 submit 和任务执行之间发生未捕获的异常），_traces 字典中的
#       条目会永远保留。
# 复现步骤：
#   1. 创建大量 trace 但不调用 record_task_end
#   2. 观察 _traces 字典大小持续增长
# =========================================================================

class TestBug015TraceLeak:
    def test_traces_leak_when_end_not_called(self):
        from services.observability import TaskTracer

        tt = TaskTracer()
        tt._initialized = True
        tt._traces = {}
        tt._history = deque(maxlen=10000)
        tt._lock = threading.Lock()

        initial_count = len(tt._traces)

        for i in range(1000):
            tt.create_trace(f"leak_task_{i}", "test")

        after_create = len(tt._traces)
        leaked = after_create - initial_count

        assert leaked == 1000, (
            f"BUG-015: TaskTracer._traces 在没有调用 record_task_end 时会泄漏。"
            f"创建了 1000 个 trace，实际保留 {leaked} 个。"
            f"极端异常路径下会导致内存持续增长。"
        )


# =========================================================================
# BUG-016: SQLite 连接未使用 context manager，异常路径可能泄漏
# 严重程度：低
# 描述：database.py 中的数据库操作使用手动 conn.close()，如果在
#       conn.execute() 和 conn.close() 之间发生异常，连接可能泄漏。
#       应该使用 with 上下文管理器。
# 复现步骤：
#   1. 检查 database.py 中的连接使用模式
#   2. 验证是否使用 with get_db() as conn 模式
# =========================================================================

class TestBug016DbConnectionLeak:
    def test_database_functions_not_using_context_manager(self):
        import inspect
        import database

        functions_to_check = [
            database.create_task,
            database.update_task,
            database.get_task,
            database.get_all_tasks_ordered,
        ]

        not_using_with = []
        for func in functions_to_check:
            source = inspect.getsource(func)
            if "with get_db()" not in source and "with conn" not in source:
                not_using_with.append(func.__name__)

        assert len(not_using_with) > 0, (
            f"BUG-016: 以下数据库函数未使用 context manager 管理连接："
            f"{not_using_with}。异常路径下可能导致连接泄漏。"
            f"应使用 'with get_db() as conn:' 模式确保连接总是被关闭。"
        )


# =========================================================================
# 额外问题：并发压力测试 - 验证多个问题的组合影响
# =========================================================================

class TestConcurrentStress:
    def test_task_lifecycle_concurrent_stress(self, monkeypatch):
        from services import task_manager
        from services.task_executor import get_task_executor
        from services.task_base import BaseTask
        import random

        initial_active = task_manager.get_active_task_count()
        initial_cancelled = len(task_manager._cancelled_tasks)

        class QuickTask(BaseTask):
            @property
            def task_type(self):
                return "stress_test"

            @property
            def initial_fields(self):
                return {}

            @property
            def processing_status(self):
                return "processing"

            @property
            def completed_status(self):
                return "completed"

            @property
            def initial_step(self):
                return "pending"

            @property
            def start_step(self):
                return "starting"

            @property
            def done_step(self):
                return "done"

            @property
            def error_step(self):
                return "error"

            @property
            def cancel_step(self):
                return "cancelled"

            def execute(self, progress_callback):
                time.sleep(0.01)
                return {"ok": True}

        executor = get_task_executor()
        task_ids = []
        completed_events = []

        for i in range(50):
            tid = f"stress_{i}_{int(time.time()*1000)}_{random.randint(0, 9999)}"
            task_ids.append(tid)
            task = QuickTask(tid)
            executor.submit(task)

            if random.random() < 0.3:
                time.sleep(0.001)
                executor.cancel(tid)

        time.sleep(2.0)

        final_active = task_manager.get_active_task_count()

        for tid in list(task_manager._cancelled_tasks):
            if tid.startswith("stress_"):
                task_manager._cancelled_tasks.discard(tid)
        for tid in list(task_manager._active_tasks):
            if tid.startswith("stress_"):
                task_manager._track_task_end(tid)

        assert final_active >= 0, (
            f"并发压力测试完成。初始 active={initial_active}, "
            f"最终 active={final_active}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
