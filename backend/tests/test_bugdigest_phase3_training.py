"""
Bug Digest Phase 3 - 训练模块与性能采集深度扫描
================================================

发现的 15 个潜在问题清单：

【严重程度：高】
BUG-001: 训练目录含子目录时 process_all_files 崩溃 — os.listdir 遍历 TRAINING_DIR，
         只按后缀名过滤，若子目录名恰好以 .wav/.mp3 等结尾会被当作文件处理导致崩溃
BUG-002: 取消后任务仍可完成并覆盖 cancelled 状态 — TaskExecutor.cancel 标记取消后，
         若任务已过取消检查点，会继续执行到完成并把状态改为 completed
BUG-003: 特征提取器数据库连接泄漏 — is_file_processed 每次新建连接，操作异常时
         连接未关闭；process_single_file 异常路径同理
BUG-004: 检测任务缺少 perf start/end — _run_detect 和 DetectTask 均未调用
         perf_collector.start_detect/end_detect，导致检测性能数据完全缺失
BUG-005: process_all_files 重复哈希计算 — 先遍历一次全部文件算哈希统计数量，
         process_single_file 里又重新读文件算一次，大文件下 IO 翻倍
BUG-006: 空音频下流式与非流式内存估算差异巨大且无基准开销 — n_samples=0 时，
         流式版本有固定 STFT 窗口开销，非流式极低，且都未考虑 Python 对象基础开销

【严重程度：中】
BUG-007: PerfTimer 异常时仍记录 step — __exit__ 不区分是否异常，失败操作也
         被记入性能统计，污染均值/P95 等指标
BUG-008: end_repair 未校验 task_id 匹配 — start_repair 存在 thread_local 里的
         task_id 与 end_repair 入参不一致时数据会串扰
BUG-009: safety_margin 参数完全未使用 — check_memory_before_repair 签名有
         safety_margin 但函数体里根本没用到
BUG-010: 算法版本列表不一致 — has_streaming 中的版本集合与 peak_temp 额外开销
         的版本集合不匹配，部分版本漏算或多算
BUG-011: 训练数据路径无符号链接安全校验 — feature_extractor 直接 os.listdir
         遍历 TRAINING_DIR，若其中存在指向系统文件的 symlink 会被读取处理
BUG-012: P95 百分位计算不准确 — calc_stats 用 int(n*0.95) 索引，小样本下偏差大
         （如 n=20 时取到 P100 而非 P95）

【严重程度：低】
BUG-013: _schedule_cancel_cleanup 每次创建新线程 — 高并发取消场景下线程数激增，
         应改用定时器或线程池
BUG-014: 特征缓存文件写入中途异常残留不完整 JSON — 先写文件再写 DB，写文件
         过程中崩溃留下损坏的 JSON，下次读取时会失败
BUG-015: 空音频 xRTF 计算边界不明确 — size_samples=0 时 audio_duration_seconds=0，
         xRTF 恒为 0，但未区分「真的 0 秒」和「获取失败」两种情况
"""

import sys
import os
import json
import time
import threading
import tempfile
import sqlite3
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


def _mock_librosa():
    """Mock librosa 模块，因为测试环境可能未安装"""
    if "librosa" not in sys.modules:
        mock_librosa = MagicMock()
        mock_librosa.note_to_hz = lambda x: 261.63
        mock_librosa.pyin = lambda y, fmin, fmax, sr, frame_length=2048, hop_length=512: (
            np.zeros(100), np.zeros(100, dtype=bool), None
        )
        mock_librosa.feature = MagicMock()
        mock_librosa.feature.spectral_centroid = lambda y=None, sr=None, S=None: np.zeros((1, 10))
        mock_librosa.feature.spectral_flatness = lambda S=None: np.zeros((1, 10))
        mock_librosa.feature.spectral_bandwidth = lambda y=None, sr=None, S=None: np.zeros((1, 10))
        mock_librosa.feature.spectral_rolloff = lambda y=None, sr=None, S=None: np.zeros((1, 10))
        mock_librosa.feature.mfcc = lambda y=None, sr=None, S=None, n_mfcc=20: np.zeros((20, 10))
        mock_librosa.feature.delta = lambda data, order=1: np.zeros_like(data)
        mock_librosa.feature.chroma_stft = lambda y=None, sr=None, S=None: np.zeros((12, 10))
        mock_librosa.feature.zero_crossing_rate = lambda y: np.zeros((1, 10))
        mock_librosa.feature.rms = lambda y=None: np.zeros((1, 10))
        mock_librosa.effects = MagicMock()
        mock_librosa.effects.hpss = lambda y: (np.zeros_like(y), np.zeros_like(y))
        mock_librosa.effects.harmonic = lambda y: np.zeros_like(y)
        mock_librosa.onset = MagicMock()
        mock_librosa.onset.onset_strength = lambda y=None, sr=None: np.zeros(10)
        mock_librosa.onset.onset_detect = lambda onset_envelope=None, sr=None: np.array([], dtype=int)
        mock_librosa.stft = lambda y, n_fft=4096, hop_length=1024: np.zeros((2049, 10), dtype=complex)
        mock_librosa.util = MagicMock()
        mock_librosa.util.frame = lambda x, frame_length=4096, hop_length=1024: np.zeros((frame_length, 10))
        sys.modules["librosa"] = mock_librosa
    return sys.modules["librosa"]


# ============================================================
# BUG-001: 训练目录含子目录时 process_all_files 崩溃
# ============================================================
class TestBug001SubdirCrash:
    """高 - 训练目录含子目录时 process_all_files 崩溃"""

    def test_subdir_with_audio_suffix_causes_crash(self):
        """子目录名以 .wav 结尾时，被当作文件处理，open 目录导致 IsADirectoryError"""
        _mock_librosa()
        from training import feature_extractor

        with tempfile.TemporaryDirectory() as tmpdir:
            training_dir = os.path.join(tmpdir, "training")
            os.makedirs(training_dir)

            os.makedirs(os.path.join(training_dir, "fake_song.wav"))

            audio_file = os.path.join(training_dir, "test.wav")
            with open(audio_file, "wb") as f:
                f.write(b"fake wav")

            errors = []

            def safe_is_file_processed(file_hash):
                return True

            with patch.object(feature_extractor, "TRAINING_DIR", training_dir):
                with patch.object(feature_extractor, "init_feature_db", lambda: None):
                    with patch.object(feature_extractor, "is_file_processed",
                                      safe_is_file_processed):
                        try:
                            feature_extractor.process_all_files()
                        except Exception as e:
                            errors.append(type(e).__name__)

            assert len(errors) > 0, (
                f"BUG 确认：训练目录中含以 .wav 结尾的子目录时，"
                f"process_all_files 会崩溃。异常类型: {errors}"
            )


# ============================================================
# BUG-002: 取消后任务仍可完成并覆盖 cancelled 状态
# ============================================================
class TestBug002CancelOverwrite:
    """高 - 取消后任务仍可完成并覆盖 cancelled 状态"""

    def test_cancel_then_complete_overwrites_status(self):
        """任务执行中被取消，但已过取消检查点，继续执行完成后状态被覆盖"""
        from services.task_executor import TaskExecutor
        from services.task_base import BaseTask
        from database import get_task, update_task, create_task

        reached_execute = threading.Event()
        can_continue = threading.Event()
        task_id = "test_cancel_ovrw_" + hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

        class SlowTask(BaseTask):
            @property
            def task_type(self):
                return "test"

            def execute(self, progress_callback):
                reached_execute.set()
                can_continue.wait(timeout=5)
                return {"result": "done"}

        create_task(task_id, "test.wav", "/tmp/test.wav", {})
        update_task(task_id, status="pending")

        executor = TaskExecutor()

        def submit_task():
            task = SlowTask(task_id)
            executor.submit(task)

        t = threading.Thread(target=submit_task, daemon=True)
        t.start()

        assert reached_execute.wait(timeout=3), "任务未进入 execute"

        executor.cancel(task_id)

        task_after_cancel = get_task(task_id)
        assert task_after_cancel["status"] == "cancelled", "取消后状态应为 cancelled"

        can_continue.set()
        time.sleep(0.5)

        task_after_complete = get_task(task_id)
        assert task_after_complete["status"] == "completed", (
            f"BUG 确认：取消后任务继续执行完成，状态被覆盖为 {task_after_complete['status']}，"
            f"而不是保持 cancelled"
        )


# ============================================================
# BUG-003: 特征提取器数据库连接泄漏
# ============================================================
class TestBug003DbConnectionLeak:
    """高 - 特征提取器数据库连接泄漏"""

    def test_is_file_processed_leaks_on_error(self):
        """is_file_processed 中数据库操作异常时连接未关闭"""
        _mock_librosa()
        import sqlite3
        from training import feature_extractor

        original_connect = sqlite3.connect
        connections_opened = []
        connections_closed = []

        class TrackingConn:
            def __init__(self, real_conn):
                self._real = real_conn
                self._closed = False
                self.row_factory = None
                connections_opened.append(self)

            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("simulated db error")

            def fetchone(self):
                return None

            def close(self):
                self._closed = True
                connections_closed.append(self)
                try:
                    self._real.close()
                except Exception:
                    pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

            def __getattr__(self, name):
                return getattr(self._real, name)

        def mock_connect(*args, **kwargs):
            real = original_connect(":memory:")
            return TrackingConn(real)

        with patch.object(sqlite3, "connect", mock_connect):
            try:
                feature_extractor.is_file_processed("fake_hash")
            except sqlite3.OperationalError:
                pass

        leaked = [c for c in connections_opened if not c._closed]
        assert len(leaked) > 0, (
            f"预期存在未关闭的连接（泄漏），但所有连接都已关闭。"
            f"打开={len(connections_opened)}, 关闭={len(connections_closed)}"
        )

    def test_process_single_file_db_insert_error_leaks_conn(self):
        """process_single_file 中数据库 INSERT 异常时，conn 未关闭"""
        _mock_librosa()
        import sqlite3
        from training import feature_extractor

        original_connect = sqlite3.connect
        connections_closed = []
        connections_opened_count = [0]
        insert_called = [False]

        class LeakTrackingConn:
            def __init__(self, real_conn):
                self._real = real_conn
                connections_opened_count[0] += 1
                self._row_factory = None

            @property
            def row_factory(self):
                return self._row_factory

            @row_factory.setter
            def row_factory(self, value):
                self._row_factory = value

            def execute(self, *args, **kwargs):
                sql = args[0] if args else ""
                if "INSERT" in sql.upper():
                    insert_called[0] = True
                    raise sqlite3.OperationalError("simulated insert error")
                return MagicMock()

            def commit(self):
                pass

            def close(self):
                connections_closed.append(id(self))
                try:
                    self._real.close()
                except Exception:
                    pass

            def __getattr__(self, name):
                return getattr(self._real, name)

        def mock_connect(*args, **kwargs):
            real = original_connect(":memory:")
            return LeakTrackingConn(real)

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_file = os.path.join(tmpdir, "test.wav")
            with open(fake_file, "wb") as f:
                f.write(b"fake wav data")

            with patch.object(sqlite3, "connect", mock_connect):
                with patch.object(feature_extractor, "is_file_processed", return_value=False):
                    with patch.object(feature_extractor, "load_audio_with_fallback",
                                      return_value=(np.zeros(44100), 44100)):
                        with patch.object(feature_extractor, "detect_vocal_vs_instrumental",
                                          return_value="vocal"):
                            with patch.object(feature_extractor, "extract_all_features",
                                              return_value={"feat": 1.0}):
                                result = feature_extractor.process_single_file(fake_file)
                                assert result is None

        assert insert_called[0], "INSERT 语句未被调用（测试逻辑有误）"
        assert connections_opened_count[0] > len(connections_closed), (
            f"BUG 确认：process_single_file 数据库 INSERT 异常时连接泄漏。"
            f"打开连接数={connections_opened_count[0]}, 关闭数={len(connections_closed)}"
        )


# ============================================================
# BUG-004: 检测任务缺少 perf start/end
# ============================================================
class TestBug004DetectMissingPerf:
    """高 - 检测任务缺少 perf start/end"""

    def test_detect_task_has_no_perf_start(self):
        """DetectTask.execute 中未调用 perf_collector.start_detect"""
        import inspect
        from services.task_manager import DetectTask

        source = inspect.getsource(DetectTask.execute)
        assert "start_detect" not in source, (
            "BUG 已修复：DetectTask.execute 中已包含 start_detect"
        )
        assert "end_detect" not in source, (
            "BUG 已修复：DetectTask.execute 中已包含 end_detect"
        )

    def test_run_detect_function_has_no_perf(self):
        """_run_detect 函数中未调用 perf start/end"""
        import inspect
        from services import task_manager

        source = inspect.getsource(task_manager._run_detect)
        assert "start_detect" not in source, (
            "BUG 已修复：_run_detect 中已包含 start_detect"
        )
        assert "end_detect" not in source, (
            "BUG 已修复：_run_detect 中已包含 end_detect"
        )

    def test_perf_collector_has_detect_methods(self):
        """确认 PerfMetricsCollector 确实定义了 start_detect/end_detect（但没被调用）"""
        from services.perf_metrics import PerfMetricsCollector

        assert hasattr(PerfMetricsCollector, "start_detect"), "start_detect 方法不存在"
        assert hasattr(PerfMetricsCollector, "end_detect"), "end_detect 方法不存在"


# ============================================================
# BUG-005: process_all_files 重复哈希计算
# ============================================================
class TestBug005DuplicateHash:
    """高 - process_all_files 重复哈希计算"""

    def test_process_all_files_reads_files_twice(self):
        """process_all_files 先遍历所有文件算一次哈希，process_single_file 又算一次"""
        _mock_librosa()
        from training import feature_extractor

        sha256_call_count = [0]

        original_sha256 = hashlib.sha256

        def counting_sha256(data=None):
            if data is not None:
                sha256_call_count[0] += 1
            return original_sha256(data if data is not None else b"")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = os.path.join(tmpdir, "cache")
            os.makedirs(cache_dir)

            training_dir = os.path.join(tmpdir, "training")
            os.makedirs(training_dir)

            for i in range(3):
                fpath = os.path.join(training_dir, f"file_{i}.wav")
                with open(fpath, "wb") as f:
                    f.write(os.urandom(1024))

            def mock_get_feature_db():
                conn = sqlite3.connect(":memory:")
                conn.execute("""CREATE TABLE IF NOT EXISTS file_features (
                    file_hash TEXT PRIMARY KEY,
                    filename TEXT,
                    file_type TEXT,
                    file_size INTEGER,
                    duration REAL,
                    sample_rate INTEGER,
                    feature_cache_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
                return conn

            with patch.object(feature_extractor, "TRAINING_DIR", training_dir):
                with patch.object(feature_extractor, "FEATURE_CACHE_DIR", cache_dir):
                    with patch.object(feature_extractor, "init_feature_db", lambda: None):
                        with patch.object(feature_extractor, "get_feature_db",
                                          mock_get_feature_db):
                            with patch.object(feature_extractor, "load_audio_with_fallback",
                                              return_value=(np.zeros(44100), 44100)):
                                with patch.object(feature_extractor,
                                                  "detect_vocal_vs_instrumental",
                                                  return_value="vocal"):
                                    with patch.object(feature_extractor,
                                                      "extract_all_features",
                                                      return_value={"feat": 1.0}):
                                        with patch.object(hashlib, "sha256",
                                                          counting_sha256):
                                            feature_extractor.process_all_files()

        assert sha256_call_count[0] >= 6, (
            f"BUG 确认：3 个文件，带 data 的 sha256 调用被调用了 {sha256_call_count[0]} 次。"
            f"如果只读取一次应该是 3 次，现在 >= 6 次说明存在重复哈希计算（2 次读取）"
        )


# ============================================================
# BUG-006: 空音频下流式与非流式内存估算差异巨大且无基准开销
# ============================================================
class TestBug006ZeroSamplesMemory:
    """高 - 空音频下内存估算不一致且无基础开销"""

    def test_zero_samples_streaming_vs_nonstreaming_differs_hugely(self):
        """n_samples=0 时，流式版本有固定 STFT 开销，非流式版本极低"""
        from services.memory_guard import estimate_repair_memory_bytes

        streaming_est = estimate_repair_memory_bytes(0, 2, 44100, 48000, algorithm_version="v2.4a")
        non_streaming_est = estimate_repair_memory_bytes(0, 2, 44100, 48000, algorithm_version="v2.0")

        ratio = streaming_est / max(non_streaming_est, 1)
        assert ratio > 500, (
            f"BUG 确认：0 采样数时，流式与非流式算法的内存估算差异巨大。\n"
            f"  流式(v2.4a): {streaming_est} 字节\n"
            f"  非流式(v2.0): {non_streaming_est} 字节\n"
            f"  差异倍数: {ratio:.1f}x\n"
            f"  同样是空音频，估算却差数百倍"
        )

    def test_zero_samples_both_underestimate_actual_overhead(self):
        """空音频下两种版本都严重低估了 Python 对象的实际基础开销"""
        from services.memory_guard import estimate_repair_memory_bytes

        streaming_est = estimate_repair_memory_bytes(0, 2, 44100, 48000, algorithm_version="v2.4a")
        non_streaming_est = estimate_repair_memory_bytes(0, 2, 44100, 48000, algorithm_version="v2.0")

        min_est = min(streaming_est, non_streaming_est)
        assert min_est < 1024 * 100, (
            f"空音频下最小估算={min_est} 字节，"
            f"远低于实际运行时 numpy/librosa 等库的基础内存开销（数 MB 级）"
        )


# ============================================================
# BUG-007: PerfTimer 异常时仍记录 step
# ============================================================
class TestBug007PerfTimerRecordsOnError:
    """中 - PerfTimer 异常时仍记录 step"""

    def test_perf_timer_records_step_despite_exception(self):
        """PerfTimer 上下文管理器中发生异常时，step 仍被记录"""
        from services.perf_metrics import PerfMetricsCollector, perf_timer

        collector = PerfMetricsCollector.get_instance()
        before_count = len(collector.step_history.get("bug007_test_step", []))

        with pytest.raises(ValueError):
            with perf_timer("bug007_test_step"):
                raise ValueError("test error")

        after_count = len(collector.step_history.get("bug007_test_step", []))

        assert after_count > before_count, (
            f"BUG 确认：异常发生后 step 仍被记录。"
            f"之前={before_count}, 之后={after_count}"
        )


# ============================================================
# BUG-008: end_repair 未校验 task_id 匹配
# ============================================================
class TestBug008EndRepairTaskIdMismatch:
    """中 - end_repair 未校验 task_id 匹配"""

    def test_end_repair_different_task_id(self):
        """start_repair(task_A) 后 end_repair(task_B)，数据被错误关联"""
        from services.perf_metrics import PerfMetricsCollector

        collector = PerfMetricsCollector()
        collector._instance = None
        collector.__init__()

        collector.start_repair("task_A")
        time.sleep(0.01)

        result = collector.end_repair("task_B", 48000, "v2.4a")

        assert result["task_id"] == "task_B", (
            "end_repair 直接使用传入的 task_id，未校验是否与 start_repair 匹配"
        )

        task_ids = [h["task_id"] for h in collector.repair_history]
        assert "task_A" not in task_ids, (
            f"BUG 确认：start_repair 的 task_A 未出现在历史中，"
            f"end_repair 传入的 task_B 却被记录了。历史={task_ids}"
        )


# ============================================================
# BUG-009: safety_margin 参数完全未使用
# ============================================================
class TestBug009UnusedSafetyMargin:
    """中 - safety_margin 参数完全未使用"""

    def test_safety_margin_only_in_signature_not_body(self):
        """check_memory_before_repair 的 safety_margin 仅在签名中出现，函数体未使用"""
        import inspect
        from services.memory_guard import check_memory_before_repair

        sig = inspect.signature(check_memory_before_repair)
        assert "safety_margin" in sig.parameters, (
            "函数签名中没有 safety_margin 参数"
        )

        source = inspect.getsource(check_memory_before_repair)
        lines = source.split("\n")
        margin_line_count = sum(1 for l in lines if "safety_margin" in l)

        assert margin_line_count <= 2, (
            f"BUG 确认：safety_margin 仅出现在函数签名中（{margin_line_count} 行），"
            f"函数体未实际使用该参数"
        )

    def test_estimate_has_no_safety_margin_param(self):
        """estimate_repair_memory_bytes 根本没有 safety_margin 参数"""
        import inspect
        from services.memory_guard import estimate_repair_memory_bytes

        sig = inspect.signature(estimate_repair_memory_bytes)
        assert "safety_margin" not in sig.parameters, (
            "estimate_repair_memory_bytes 已有 safety_margin 参数（BUG 已修复？）"
        )


# ============================================================
# BUG-010: 算法版本列表不一致
# ============================================================
class TestBug010VersionListMismatch:
    """中 - 算法版本列表不一致"""

    def test_streaming_versions_vs_peak_temp_versions(self):
        """has_streaming 版本集合与 peak_temp 分支版本集合不匹配"""
        import inspect
        import re
        from services import memory_guard

        source = inspect.getsource(memory_guard.estimate_repair_memory_bytes)

        streaming_versions = set()
        peak_temp_versions = set()

        streaming_match = re.search(r'has_streaming = algorithm_version in \((.+?)\)', source, re.DOTALL)
        if streaming_match:
            versions_str = streaming_match.group(1)
            streaming_versions = set(v.strip().strip('"').strip("'") for v in versions_str.split(",") if v.strip())

        peak_temp_pattern = r'algorithm_version == "([^"]+)"'
        for match in re.finditer(peak_temp_pattern, source):
            peak_temp_versions.add(match.group(1))

        in_streaming_not_peak = streaming_versions - peak_temp_versions
        in_peak_not_streaming = peak_temp_versions - streaming_versions

        assert len(in_streaming_not_peak) > 0 or len(in_peak_not_streaming) > 0, (
            f"BUG 确认：两个版本列表不一致。\n"
            f"  has_streaming 中有但 peak_temp 中没有: {in_streaming_not_peak}\n"
            f"  peak_temp 中有但 has_streaming 中没有: {in_peak_not_streaming}"
        )


# ============================================================
# BUG-011: 训练数据路径无符号链接安全校验
# ============================================================
class TestBug011SymlinkTraversal:
    """中 - 训练数据路径无符号链接安全校验"""

    def test_feature_extractor_follows_symlinks_outside_dir(self):
        """TRAINING_DIR 中的符号链接指向外部文件时，会跟随 symlink 读取外部内容"""
        _mock_librosa()
        from training import feature_extractor

        with tempfile.TemporaryDirectory() as tmpdir:
            training_dir = os.path.join(tmpdir, "training")
            os.makedirs(training_dir)

            secret_file = os.path.join(tmpdir, "secret.wav")
            secret_content = b"sensitive data outside training dir - should not be read"
            with open(secret_file, "wb") as f:
                f.write(secret_content)

            symlink_path = os.path.join(training_dir, "evil.wav")
            try:
                os.symlink(secret_file, symlink_path)
            except (OSError, AttributeError):
                pytest.skip("系统不支持符号链接")

            read_hashes = []

            def tracking_is_file_processed(file_hash):
                read_hashes.append(file_hash)
                return True

            with patch.object(feature_extractor, "TRAINING_DIR", training_dir):
                with patch.object(feature_extractor, "init_feature_db", lambda: None):
                    with patch.object(feature_extractor, "is_file_processed",
                                      tracking_is_file_processed):
                        feature_extractor.process_all_files()

            real_path = os.path.realpath(symlink_path)
            assert os.path.commonpath([real_path, training_dir]) != training_dir, (
                f"BUG 确认：symlink 解析后的真实路径 {real_path} "
                f"不在训练目录 {training_dir} 内，但文件内容仍被读取并计算了哈希。"
                f"读取的哈希数={len(read_hashes)}"
            )
            assert len(read_hashes) > 0, (
                f"符号链接文件确实被读取了（{len(read_hashes)} 个文件被哈希）"
            )


# ============================================================
# BUG-012: P95 百分位计算不准确
# ============================================================
class TestBug012P95Inaccuracy:
    """中 - P95 百分位计算不准确"""

    def test_p95_n20_index_19_not_18(self):
        """n=20 时 int(20*0.95)=19，取到最大值（P100）而非 P95"""
        from services.perf_metrics import PerfMetricsCollector

        collector = PerfMetricsCollector()
        collector._instance = None
        collector.__init__()

        values = list(range(1, 21))
        for v in values:
            collector.repair_history.append({"total_time_ms": float(v)})

        summary = collector.get_summary()
        actual_p95 = summary["repair"]["overall"]["p95_ms"]
        numpy_p95 = float(np.percentile(values, 95))

        assert actual_p95 != numpy_p95, (
            f"BUG 确认：P95 计算与 numpy.percentile 不一致。\n"
            f"  实际计算值={actual_p95}\n"
            f"  numpy 参考值={numpy_p95}\n"
            f"  差值={abs(actual_p95 - numpy_p95)}"
        )

    def test_p95_small_sample_uses_max_not_percentile(self):
        """小样本下 P95 退化为最大值，失去统计意义"""
        from services.perf_metrics import PerfMetricsCollector

        collector = PerfMetricsCollector()
        collector._instance = None
        collector.__init__()

        values = [10, 20, 30, 40, 50]
        for v in values:
            collector.repair_history.append({"total_time_ms": float(v)})

        summary = collector.get_summary()
        p95 = summary["repair"]["overall"]["p95_ms"]
        max_val = summary["repair"]["overall"]["max_ms"]

        assert p95 == max_val, (
            f"BUG 确认：n=5 时 P95({p95}) 等于最大值({max_val})，"
            f"用简单索引 int(n*0.95)=4 取到了最后一个元素而非真正的 P95"
        )


# ============================================================
# BUG-013: _schedule_cancel_cleanup 每次创建新线程
# ============================================================
class TestBug013CancelCleanupThreadPerCall:
    """低 - _schedule_cancel_cleanup 每次创建新线程"""

    def test_each_cancel_creates_new_thread(self):
        """多次取消任务会创建多个 daemon 线程"""
        from services import task_manager

        original_thread = threading.Thread
        threads_created = []

        class CountingThread(original_thread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                threads_created.append(self)

        with patch.object(threading, "Thread", CountingThread):
            initial_count = len(threads_created)

            for i in range(5):
                task_manager._schedule_cancel_cleanup(f"test_task_{i}")

            time.sleep(0.1)

            new_threads = len(threads_created) - initial_count
            assert new_threads == 5, (
                f"BUG 确认：5 次取消创建了 {new_threads} 个新线程。"
                f"高并发取消场景下线程数会激增。"
            )


# ============================================================
# BUG-014: 特征缓存文件写入中途异常残留不完整 JSON
# ============================================================
class TestBug014PartialCacheFile:
    """低 - 特征缓存文件写入中途异常残留不完整 JSON"""

    def test_partial_json_left_on_write_error(self):
        """写缓存文件过程中异常，留下不完整的 JSON 文件"""
        _mock_librosa()
        from training import feature_extractor
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = os.path.join(tmpdir, "cache")
            os.makedirs(cache_dir)

            fake_file = os.path.join(tmpdir, "test.wav")
            with open(fake_file, "wb") as f:
                f.write(b"fake wav data")

            def mock_json_dump(obj, f, **kwargs):
                f.write('{"partial": true, "incomplete": ')
                raise IOError("disk full simulation")

            with patch.object(feature_extractor, "FEATURE_CACHE_DIR", cache_dir):
                with patch.object(feature_extractor, "is_file_processed", return_value=False):
                    with patch.object(feature_extractor, "load_audio_with_fallback",
                                      return_value=(np.zeros(44100), 44100)):
                        with patch.object(feature_extractor, "detect_vocal_vs_instrumental",
                                          return_value="instrumental"):
                            with patch.object(feature_extractor, "extract_all_features",
                                              return_value={"feat": 1.0}):
                                with patch.object(json, "dump", mock_json_dump):
                                    result = feature_extractor.process_single_file(fake_file)
                                    assert result is None

            cache_files = os.listdir(cache_dir)
            assert len(cache_files) > 0, (
                f"BUG 确认：写缓存失败后仍留下了不完整的文件。"
                f"缓存目录内容: {cache_files}"
            )

            for cf in cache_files:
                cf_path = os.path.join(cache_dir, cf)
                try:
                    with open(cf_path) as f:
                        json.load(f)
                except json.JSONDecodeError:
                    return

            pytest.fail("预期找到不完整的 JSON 文件，但所有文件都能正常解析")


# ============================================================
# BUG-015: 空音频 xRTF 计算边界不明确
# ============================================================
class TestBug015XrtfZeroSamples:
    """低 - 空音频 xRTF 计算边界不明确"""

    def test_zero_samples_xrtf_is_zero_indistinguishable(self):
        """size_samples=0 时 xRTF=0，无法区分 0 秒音频和获取失败"""
        from services.perf_metrics import PerfMetricsCollector

        collector = PerfMetricsCollector()
        collector._instance = None
        collector.__init__()

        collector.start_repair("task_zero")
        time.sleep(0.01)
        result = collector.end_repair("task_zero", 0, "v2.4a")

        assert result["xrtf"] == 0, (
            f"size_samples=0 时 xRTF={result['xrtf']}，无法区分：\n"
            f"  1) 音频确实是 0 秒\n"
            f"  2) size_samples 获取失败（代码中 size_samples 默认 0）"
        )

    def test_size_samples_default_zero_in_repair(self):
        """_run_repair 中 size_samples 初始为 0，加载失败时保持 0"""
        import inspect
        from services import task_manager

        source = inspect.getsource(task_manager._run_repair)
        lines_with_size_samples = [l.strip() for l in source.split("\n")
                                    if "size_samples" in l and "=" in l]

        assert any("size_samples = 0" in l for l in lines_with_size_samples), (
            "BUG 确认：size_samples 初始化为 0，且预加载失败时仅打 warning 不抛出，"
            "导致 xRTF=0 但无法区分是真的 0 秒还是加载失败"
        )


# ============================================================
# 额外验证：record_step 锁范围问题
# ============================================================
class TestExtraRecordStepLockScope:
    """补充验证：record_step 中步骤分步加锁，数据更新非原子"""

    def test_thread_local_steps_outside_data_lock(self):
        """record_step 中 thread_local.steps 更新在 _data_lock 之外"""
        import inspect
        from services.perf_metrics import PerfMetricsCollector

        source = inspect.getsource(PerfMetricsCollector.record_step)

        lines = source.strip().split("\n")
        in_lock = False
        thread_local_outside_lock = False

        for i, line in enumerate(lines):
            stripped = line.strip()
            if "with self._data_lock:" in stripped:
                in_lock = True
                continue
            if in_lock and stripped and not stripped.startswith("#"):
                indent = len(line) - len(line.lstrip())
                if indent <= 8:
                    in_lock = False

            if "_get_thread_steps" in stripped or "steps[step_name]" in stripped:
                if not in_lock:
                    thread_local_outside_lock = True

        assert thread_local_outside_lock, (
            "BUG 确认：record_step 中 step_history 写入在 _data_lock 内，"
            "但 thread_local.steps 的更新在锁外，两步操作非原子"
        )
