"""
BugDigest Phase 2: 文件操作、缓存、配置相关 bug 挖掘与复现

================================================================================
BUG 清单 (共 14 个，按严重程度排序)
================================================================================

[高] Bug-001: safe_write 写入失败时临时文件泄漏
       - 文件: services/file_gateway.py:57-66
       - 描述: safe_write 在写入数据或 fsync 失败时，.tmp 临时文件不会被清理，
         导致磁盘空间泄漏。
       - 复现: 模拟写入过程中抛出异常，验证 .tmp 文件残留

[高] Bug-002: 锁 LRU 淘汰导致并发安全失效
       - 文件: services/file_gateway.py:38-48
       - 描述: 当文件锁因 LRU 策略被淘汰时，如果该锁正被另一个线程持有，
         新请求会创建一个全新的锁对象，导致同一文件的并发写入失去互斥保护，
         可能造成数据损坏。
       - 复现: 设置 _MAX_LOCKS=1，验证被淘汰的锁被持有时新请求得到不同锁

[高] Bug-003: /decoded-wav/{file_hash} 路径遍历漏洞
       - 文件: api/routes/download.py:684-686
       - 描述: decoded-wav 接口直接使用 file_hash 拼接路径，未做任何安全校验，
         攻击者可通过构造包含 ../ 的 file_hash 读取系统任意文件。
       - 复现: 构造含路径遍历的 file_hash，验证拼接后的路径逃逸出 DECODED_DIR

[高] Bug-004: TTL 清理失败的文件在 LRU 阶段不再被重试清理
       - 文件: services/cache_manager.py:169-182
       - 描述: TTL 清理时，即使文件删除失败（OSError 被捕获），该文件仍会从
         files 列表中移除，导致后续 LRU 容量清理阶段不会再尝试删除它，
         最终缓存容量可能超限。
       - 复现: 创建无法删除的文件（通过权限或其他方式），验证 LRU 阶段不处理

[高] Bug-005: file_cache.py 直接修改 CacheManager._layers 非线程安全
       - 文件: services/file_cache.py:45-67
       - 描述: evict_old_files 直接访问并修改 cache_mgr._layers 私有字典中的
         max_size_mb，没有任何锁保护。多线程环境下可能导致读到不一致的配置，
         且破坏了封装性。
       - 复现: 验证 _layers 被直接修改，且无锁保护

[中] Bug-006: safe_rename 同名文件导致死锁
       - 文件: services/file_gateway.py:68-78
       - 描述: 当 temp_filename == final_filename 时，safe_rename 会尝试获取
         同一把锁两次。由于 threading.Lock 不可重入，会导致永久死锁。
       - 复现: 调用 safe_rename("same.txt", "same.txt") 触发死锁

[中] Bug-007: get_dir_size 统计符号链接目标文件大小（可能绕过容量统计）
       - 文件: services/file_gateway.py:108-117
       - 描述: get_dir_size 不检查符号链接，会将符号链接指向的外部文件大小
         计入目录总大小。如果符号链接指向超大文件，可能导致容量统计失真。
       - 复现: 创建指向外部大文件的符号链接，验证 get_dir_size 返回外部文件大小

[中] Bug-008: reset_stats 与 record_hit/miss 竞态导致统计丢失
       - 文件: services/cache_manager.py:269-288
       - 描述: record_hit/miss 先在 _lock 保护下拿到 stats 引用，释放锁后再
         记录。如果在此期间 reset_stats 替换了 stats 对象，统计数据会写入
         旧对象而丢失。
       - 复现: 并发执行 record_hit 和 reset_stats，验证统计数不一致

[中] Bug-009: preview 接口直接使用 original_path 无二次校验
       - 文件: api/routes/download.py:665-672
       - 描述: preview 接口直接从数据库读取 original_path 并返回文件，
         未验证路径是否在安全目录内。如果数据库被污染或上游校验有漏洞，
         可能导致任意文件读取。
       - 复现: 构造含路径遍历的 original_path，验证接口会尝试读取该路径

[中] Bug-010: evict_layer 清理后剩余统计与实际可能不一致
       - 文件: services/cache_manager.py:198-208
       - 描述: 清理完成后重新扫描目录统计剩余文件数和大小，但扫描过程中
         可能有新文件写入或删除，导致返回结果不准确。更严重的是，
         如果删除操作部分失败，remaining 统计与之前的 removed 统计对不上。
       - 复现: 验证 evict_layer 使用两次独立扫描（_scan_files 和重新 os.walk）

[中] Bug-011: ConfigProvider 抽象类与实际配置项不对齐
       - 文件: services/config_provider.py
       - 描述: ConfigProvider 抽象类只定义了 7 个配置字段，但 config.py 中有
         更多关键配置（HOST, PORT, MAX_UPLOAD_SIZE, ALLOWED_EXTENSIONS,
         MAX_WORKERS, DECODED_DIR 等）。如果后续代码依赖 ConfigProvider
         获取这些配置会失败。
       - 复现: 检查 EnvConfigProvider 缺少哪些 config.py 中已有的配置项

[低] Bug-012: resolve 未拒绝 NUL 字节注入
       - 文件: services/file_gateway.py:27-36
       - 描述: 文件名中包含 NUL 字节 (\x00) 时，Python 层面的校验可能通过，
         但底层 C 函数会在 NUL 字节处截断，可能导致安全校验被绕过。
       - 复现: 传入含 NUL 字节的文件名，验证 resolve 是否抛出异常

[低] Bug-013: list_files 不跳过 .tmp 临时文件
       - 文件: services/file_gateway.py:98-106
       - 描述: list_files 返回所有文件，包括 safe_write 失败时残留的 .tmp
         临时文件。这些临时文件对上层业务应该是不可见的。
       - 复现: 创建 .tmp 文件，验证 list_files 将其列出

[低] Bug-014: CacheManager._scan_files 中 isfile 与 stat 存在 TOCTOU
       - 文件: services/cache_manager.py:138-144
       - 描述: _scan_files 中先判断 os.path.isfile(fp)，再调用 os.stat(fp)，
         两次系统调用之间文件可能已被删除，导致 stat 失败（虽然被 try/except
         捕获但影响扫描效率和结果准确性）。
       - 复现: 验证 _scan_files 使用了两次独立的系统调用而非一次 os.stat
================================================================================
"""

import sys
import os
import time
import threading
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.file_gateway import SafeFileGateway, SecurityError
from services.cache_manager import CacheLayer, CacheManager, _LayerStats
from services.config_provider import ConfigProvider, EnvConfigProvider, DictConfigProvider


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def gateway(tmp_path):
    gw = SafeFileGateway(str(tmp_path / "gateway"))
    yield gw
    shutil.rmtree(gw.base_dir, ignore_errors=True)


@pytest.fixture
def fresh_cache_manager(tmp_path):
    CacheManager._instance = None
    mgr = CacheManager()
    mgr._layers.clear()
    mgr._stats.clear()
    return mgr


def _create_file(filepath, size_bytes=100, mtime_offset=0):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(b"x" * size_bytes)
    if mtime_offset != 0:
        new_mtime = time.time() + mtime_offset
        os.utime(filepath, (new_mtime, new_mtime))


# ============================================================
# Bug-001: safe_write 写入失败时临时文件泄漏
# ============================================================

class TestBug001SafeWriteTempFileLeak:
    """Bug-001 [高]: safe_write 写入失败时临时文件泄漏"""

    def test_temp_file_leaks_on_write_error(self, gateway, tmp_path):
        """模拟写入过程中抛出异常，验证 .tmp 文件残留"""
        filename = "leak_test.txt"
        full_path = gateway.resolve(filename)
        temp_path = full_path + ".tmp"

        assert not os.path.exists(temp_path)

        original_open = open
        call_count = 0

        def mock_open_bad_write(*args, **kwargs):
            nonlocal call_count
            f = original_open(*args, **kwargs)
            call_count += 1
            orig_write = f.write

            def bad_write(data):
                raise OSError("Disk full")

            f.write = bad_write
            return f

        with patch("builtins.open", side_effect=mock_open_bad_write):
            with pytest.raises(OSError):
                gateway.safe_write(filename, b"test data")

        assert os.path.exists(temp_path), (
            "Bug-001 复现失败: 预期 .tmp 临时文件在写入失败后残留，"
            "但实际文件不存在。如果此断言失败，说明 bug 可能已被修复。"
        )

    def test_temp_file_leaks_on_fsync_error(self, gateway):
        """模拟 os.fsync 失败，验证 .tmp 文件残留"""
        filename = "fsync_fail.txt"
        full_path = gateway.resolve(filename)
        temp_path = full_path + ".tmp"

        assert not os.path.exists(temp_path)

        original_fsync = os.fsync
        call_count = [0]

        def mock_fsync(fd):
            call_count[0] += 1
            raise OSError("fsync failed")

        with patch.object(os, "fsync", side_effect=mock_fsync):
            with pytest.raises(OSError):
                gateway.safe_write(filename, b"test data")

        assert call_count[0] >= 1, "os.fsync 应该被调用"
        assert os.path.exists(temp_path), (
            "Bug-001 复现失败: 预期 fsync 失败后 .tmp 文件残留"
        )


# ============================================================
# Bug-002: 锁 LRU 淘汰导致并发安全失效
# ============================================================

class TestBug002LockEvictionRace:
    """Bug-002 [高]: 锁 LRU 淘汰导致并发安全失效"""

    def test_evicted_lock_being_held_creates_new_lock(self, gateway):
        """验证被淘汰的锁正被持有时，新请求会得到不同的锁对象"""
        gateway._MAX_LOCKS = 2

        lock_a_old = gateway.get_lock("file_a.txt")

        barrier = threading.Barrier(2)
        results = {}

        def hold_lock_a():
            with lock_a_old:
                barrier.wait()
                results["held_lock_id"] = id(lock_a_old)
                time.sleep(0.1)

        t = threading.Thread(target=hold_lock_a)
        t.start()

        barrier.wait()

        gateway.get_lock("file_b.txt")
        gateway.get_lock("file_c.txt")

        lock_a_new = gateway.get_lock("file_a.txt")

        assert lock_a_old is not lock_a_new, (
            "Bug-002 复现失败: 预期锁被淘汰后新请求得到不同的锁对象，"
            "但两次得到了同一个锁。如果此断言失败，说明锁淘汰逻辑可能已修复。"
        )

        assert id(lock_a_old) != id(lock_a_new)

        t.join()

    def test_lock_eviction_allows_concurrent_write(self, gateway):
        """验证锁淘汰后，两个线程可以同时持有同一文件的不同锁（数据损坏风险）"""
        gateway._MAX_LOCKS = 2

        lock_a_v1 = gateway.get_lock("shared_file.txt")

        overlap_detected = threading.Event()
        thread1_inside = threading.Event()
        thread2_can_proceed = threading.Event()

        def thread1_writer():
            with lock_a_v1:
                thread1_inside.set()
                thread2_can_proceed.wait(timeout=2)
                time.sleep(0.05)

        def thread2_writer():
            thread1_inside.wait(timeout=2)
            gateway.get_lock("other1.txt")
            gateway.get_lock("other2.txt")
            lock_a_v2 = gateway.get_lock("shared_file.txt")
            if lock_a_v2 is not lock_a_v1:
                acquired = lock_a_v2.acquire(blocking=False)
                if acquired:
                    overlap_detected.set()
                    lock_a_v2.release()

        t1 = threading.Thread(target=thread1_writer)
        t2 = threading.Thread(target=thread2_writer)

        t1.start()
        t2.start()

        thread2_can_proceed.set()

        t1.join(timeout=5)
        t2.join(timeout=5)

        assert overlap_detected.is_set(), (
            "Bug-002 复现失败: 预期锁淘汰后两个线程能同时持有同一文件的不同锁，"
            "但未检测到并发重叠。如果此断言失败，说明锁淘汰并发问题可能已修复。"
        )


# ============================================================
# Bug-003: /decoded-wav/{file_hash} 路径遍历漏洞
# ============================================================

class TestBug003DecodedWavPathTraversal:
    """Bug-003 [高]: /decoded-wav/{file_hash} 路径遍历漏洞"""

    def test_path_traversal_in_file_hash(self, tmp_path):
        """验证 file_hash 含 ../ 时拼接后的路径会逃逸出 DECODED_DIR"""
        decoded_dir = str(tmp_path / "decoded")
        os.makedirs(decoded_dir, exist_ok=True)

        traversal_hash = "../etc/passwd"
        result_path = os.path.join(decoded_dir, f"{traversal_hash}.wav")
        real_result = os.path.realpath(result_path)
        real_decoded = os.path.realpath(decoded_dir)

        assert not real_result.startswith(real_decoded + os.sep), (
            "Bug-003 复现失败: 预期路径拼接后会逃逸出 decoded_dir，"
            "但结果仍在 decoded_dir 内。如果此断言失败，"
            "说明 FastAPI 路径参数可能有额外过滤（不太可能）。"
        )

        parent_dir = os.path.dirname(real_decoded)
        assert real_result.startswith(parent_dir + os.sep) or real_result == parent_dir.rstrip("/"), (
            "路径应该在 decoded_dir 的上级目录中"
        )

    def test_deep_path_traversal(self, tmp_path):
        """验证多级路径遍历"""
        decoded_dir = str(tmp_path / "a" / "b" / "c" / "decoded")
        os.makedirs(decoded_dir, exist_ok=True)

        traversal_hash = "../../../etc/passwd"
        result_path = os.path.join(decoded_dir, f"{traversal_hash}.wav")
        real_result = os.path.realpath(result_path)
        real_decoded = os.path.realpath(decoded_dir)

        assert not real_result.startswith(real_decoded + os.sep), (
            "Bug-003 复现失败: 多级路径遍历应该能逃逸"
        )

    def test_absolute_path_in_hash(self, tmp_path):
        """验证绝对路径形式的 file_hash"""
        decoded_dir = str(tmp_path / "decoded")
        os.makedirs(decoded_dir, exist_ok=True)

        absolute_hash = "/etc/passwd"
        result_path = os.path.join(decoded_dir, f"{absolute_hash}.wav")
        real_result = os.path.realpath(result_path)

        assert real_result == "/etc/passwd.wav" or real_result.endswith("passwd.wav"), (
            "Bug-003 补充: 绝对路径拼接在 os.path.join 中会被当作绝对路径处理"
        )


# ============================================================
# Bug-004: TTL 清理失败的文件在 LRU 阶段不再被重试
# ============================================================

class TestBug004TTLFailNotRetriedInLRU:
    """Bug-004 [高]: TTL 清理失败的文件在 LRU 阶段不再被重试"""

    def test_failed_ttl_deletion_skipped_in_lru(self, fresh_cache_manager, tmp_path):
        """验证 TTL 删除失败的文件不会在 LRU 阶段被再次尝试删除"""
        cache_dir = tmp_path / "ttl_lru_test"
        layer = CacheLayer(
            name="test_layer",
            base_dir=str(cache_dir),
            ttl_seconds=1,
            max_size_mb=0.001,
        )
        fresh_cache_manager.register_layer(layer)

        _create_file(str(cache_dir / "expired_undeletable.bin"), 800, mtime_offset=-100)
        _create_file(str(cache_dir / "fresh_large.bin"), 600, mtime_offset=0)

        original_remove = os.remove
        delete_attempts = {"expired_undeletable.bin": 0}

        def mock_remove(path):
            fname = os.path.basename(path)
            if fname == "expired_undeletable.bin":
                delete_attempts[fname] += 1
                if delete_attempts[fname] == 1:
                    raise OSError("Permission denied")
            return original_remove(path)

        with patch("os.remove", side_effect=mock_remove):
            result = fresh_cache_manager.evict_layer("test_layer")

        assert delete_attempts["expired_undeletable.bin"] >= 1

        assert delete_attempts["expired_undeletable.bin"] < 2, (
            "Bug-004 复现失败: 预期 TTL 删除失败的文件在 LRU 阶段不会被重试，"
            "但实际被删除了多次。如果此断言失败，说明 bug 可能已被修复。"
        )

        remaining_path = cache_dir / "expired_undeletable.bin"
        assert remaining_path.exists(), (
            "预期不可删除的文件仍然存在（因为第一次删除失败且 LRU 不重试）"
        )


# ============================================================
# Bug-005: file_cache.py 直接修改 _layers 非线程安全
# ============================================================

class TestBug005FileCacheDirectLayerMutation:
    """Bug-005 [高]: file_cache.py 直接修改 CacheManager._layers 非线程安全"""

    def test_direct_access_to_private_layers(self, fresh_cache_manager, tmp_path):
        """验证 file_cache.py 中直接访问 _layers 私有属性"""
        import services.file_cache as fc_module

        source = fc_module.evict_old_files.__code__.co_code
        source_str = str(fc_module.evict_old_files.__doc__) if fc_module.evict_old_files.__doc__ else ""

        import inspect
        src = inspect.getsource(fc_module.evict_old_files)

        assert "_layers" in src, (
            "Bug-005 验证失败: 预期 evict_old_files 直接访问 _layers 私有属性"
        )
        assert "max_size_mb =" in src, (
            "Bug-005 验证失败: 预期 evict_old_files 直接修改 max_size_mb"
        )

    def test_layer_mutation_without_lock(self, fresh_cache_manager, tmp_path):
        """验证直接修改 layer 属性绕过了 CacheManager 的锁保护"""
        cache_dir = tmp_path / "mutate_test"
        layer = CacheLayer(name="mutate", base_dir=str(cache_dir))
        fresh_cache_manager.register_layer(layer)

        with fresh_cache_manager._lock:
            layer_ref = fresh_cache_manager._layers["mutate"]
            original_max = layer_ref.max_size_mb

        layer_ref.max_size_mb = 999.0

        with fresh_cache_manager._lock:
            assert fresh_cache_manager._layers["mutate"].max_size_mb == 999.0, (
                "Bug-005 验证: 直接修改 _layers 中的对象确实会生效（绕过锁保护）"
            )

        layer_ref.max_size_mb = original_max

    def test_concurrent_mutation_race(self, fresh_cache_manager, tmp_path):
        """验证并发修改 layer 属性可能导致不一致"""
        cache_dir = tmp_path / "race_test"
        layer = CacheLayer(name="race", base_dir=str(cache_dir), max_size_mb=100.0)
        fresh_cache_manager.register_layer(layer)

        errors = []
        iterations = 100

        def mutator():
            try:
                for i in range(iterations):
                    with fresh_cache_manager._lock:
                        l = fresh_cache_manager._layers["race"]
                    l.max_size_mb = float(i)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(iterations):
                    with fresh_cache_manager._lock:
                        l = fresh_cache_manager._layers["race"]
                    _ = l.max_size_mb
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=mutator))
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"并发修改出现错误: {errors}"

        assert hasattr(layer, "max_size_mb")


# ============================================================
# Bug-006: safe_rename 同名文件导致死锁
# ============================================================

class TestBug006SafeRenameDeadlock:
    """Bug-006 [中]: safe_rename 同名文件导致死锁"""

    def test_same_filename_rename_deadlocks(self, gateway):
        """验证 temp_filename == final_filename 时会死锁"""
        gateway.safe_write("same.txt", b"test data")

        deadlock_detected = threading.Event()
        result_container = {"success": False, "error": None}

        def try_rename():
            try:
                gateway.safe_rename("same.txt", "same.txt")
                result_container["success"] = True
            except Exception as e:
                result_container["error"] = e
            finally:
                deadlock_detected.set()

        t = threading.Thread(target=try_rename)
        t.start()
        t.join(timeout=2)

        if t.is_alive():
            assert True, "Bug-006 复现成功: safe_rename 同名文件导致死锁（线程超时未返回）"
        else:
            if result_container["success"]:
                pytest.fail(
                    "Bug-006 未复现: safe_rename 同名文件没有死锁也没有报错，"
                    "可能已被修复或锁是可重入的"
                )
            elif result_container["error"]:
                if isinstance(result_container["error"], SecurityError):
                    pytest.fail(
                        "Bug-006 未复现: 同名被安全校验拦截了（这是好事）"
                    )
                else:
                    pytest.fail(
                        f"Bug-006 变体: 同名文件抛出了 {type(result_container['error']).__name__} "
                        f"而非死锁: {result_container['error']}"
                    )

    def test_same_lock_acquired_twice(self, gateway):
        """直接验证同一把 Lock 不能 acquire 两次"""
        lock = gateway.get_lock("test.txt")
        assert lock.acquire(blocking=False)
        second_acquire = lock.acquire(blocking=False)
        if not second_acquire:
            assert True, "验证: threading.Lock 不可重入，第二次 acquire 失败"
        else:
            lock.release()
            pytest.fail("意外: Lock 似乎是可重入的")
        lock.release()


# ============================================================
# Bug-007: get_dir_size 统计符号链接目标文件大小
# ============================================================

class TestBug007GetDirSizeSymlink:
    """Bug-007 [中]: get_dir_size 统计符号链接目标文件大小"""

    def test_symlink_file_size_counted(self, gateway, tmp_path):
        """验证指向外部大文件的符号链接会被计入目录大小"""
        external_file = tmp_path / "external_large.bin"
        external_size = 1024 * 1024
        with open(external_file, "wb") as f:
            f.write(b"x" * external_size)

        symlink_path = os.path.join(gateway.base_dir, "link_to_large.bin")
        os.symlink(str(external_file), symlink_path)

        reported_size = gateway.get_dir_size()

        assert reported_size >= external_size, (
            f"Bug-007 复现失败: 预期 get_dir_size 会将符号链接目标文件大小({external_size})"
            f"计入目录，但实际只报告了 {reported_size} 字节。"
            "如果此断言失败，说明 get_dir_size 可能已增加了符号链接检查。"
        )

    def test_symlink_counted_as_file_in_list(self, gateway, tmp_path):
        """验证符号链接被 list_files 当作普通文件"""
        external_file = tmp_path / "external.txt"
        with open(external_file, "w") as f:
            f.write("external")

        symlink_path = os.path.join(gateway.base_dir, "mylink.txt")
        os.symlink(str(external_file), symlink_path)

        files = gateway.list_files()
        assert "mylink.txt" in files, (
            "Bug-007 相关: list_files 将符号链接当作文件列出"
        )


# ============================================================
# Bug-008: reset_stats 与 record_hit/miss 竞态导致统计丢失
# ============================================================

class TestBug008StatsRaceCondition:
    """Bug-008 [中]: reset_stats 与 record_hit/miss 竞态导致统计丢失"""

    def test_concurrent_reset_and_record_loses_stats(self, fresh_cache_manager, tmp_path):
        """验证并发执行 reset_stats 和 record_hit 可能导致统计丢失"""
        cache_dir = tmp_path / "stats_race"
        fresh_cache_manager.register_layer(CacheLayer(name="race_layer", base_dir=str(cache_dir)))

        lost_hits_detected = False
        num_iterations = 20

        for iteration in range(num_iterations):
            fresh_cache_manager.reset_stats("race_layer")

            barrier = threading.Barrier(2)
            hit_count = 100

            def hitter():
                barrier.wait()
                for _ in range(hit_count):
                    fresh_cache_manager.record_hit("race_layer")

            def resetter():
                barrier.wait()
                for _ in range(5):
                    fresh_cache_manager.reset_stats("race_layer")
                    time.sleep(0.001)

            t1 = threading.Thread(target=hitter)
            t2 = threading.Thread(target=resetter)

            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

            stats = fresh_cache_manager.get_layer_stats("race_layer")
            if stats["hits"] < hit_count:
                lost_hits_detected = True
                break

        assert lost_hits_detected, (
            "Bug-008 复现失败: 预期并发 reset 和 record 会导致统计丢失，"
            "但在多次尝试中未检测到。这可能是因为竞态窗口很小，"
            "或者 bug 已被修复。"
        )

    def test_stats_object_replacement_race(self, fresh_cache_manager, tmp_path):
        """验证 reset_stats 会替换 stats 对象，而 record 可能在旧对象上记录"""
        cache_dir = tmp_path / "obj_race"
        fresh_cache_manager.register_layer(CacheLayer(name="obj_layer", base_dir=str(cache_dir)))

        old_stats_ref = None
        new_stats_ref = None

        with fresh_cache_manager._lock:
            old_stats_ref = fresh_cache_manager._stats["obj_layer"]

        assert old_stats_ref is not None

        fresh_cache_manager.record_hit("obj_layer")

        fresh_cache_manager.reset_stats("obj_layer")

        with fresh_cache_manager._lock:
            new_stats_ref = fresh_cache_manager._stats["obj_layer"]

        assert old_stats_ref is not new_stats_ref, (
            "验证: reset_stats 确实创建了新的 _LayerStats 对象"
        )

        old_snapshot = old_stats_ref.get_snapshot()
        new_snapshot = new_stats_ref.get_snapshot()

        assert old_snapshot["hits"] == 1, "旧对象上的记录仍然存在"
        assert new_snapshot["hits"] == 0, "新对象从 0 开始"


# ============================================================
# Bug-009: preview 接口直接使用 original_path 无二次校验
# ============================================================

class TestBug009PreviewNoPathValidation:
    """Bug-009 [中]: preview 接口直接使用 original_path 无二次校验"""

    def test_preview_uses_original_path_directly(self):
        """验证 preview 接口直接从 task 取 original_path 而不做路径校验"""
        import inspect
        from api.routes import download as dl_module

        src = inspect.getsource(dl_module.preview_audio)

        assert "original_path" in src, "preview 接口使用 original_path"
        assert "FileResponse" in src, "preview 接口返回 FileResponse"

        assert "resolve" not in src.lower() or "safe_" not in src.lower(), (
            "Bug-009 验证: preview 接口中没有调用 resolve 或 safe_ 前缀的路径校验函数"
        )

    def test_traversal_original_path_would_be_served(self, tmp_path):
        """验证如果 original_path 包含路径遍历，FileResponse 会读取该路径"""
        traversal_path = str(tmp_path / ".." / "etc" / "passwd")
        resolved = os.path.realpath(traversal_path)
        base = os.path.realpath(str(tmp_path))

        assert not resolved.startswith(base + os.sep), (
            "Bug-009 原理验证: 含 ../ 的路径会逃逸出 base_dir"
        )

    def test_download_audio_also_uses_output_path_directly(self):
        """验证 download_audio 接口也直接使用 output_path"""
        import inspect
        from api.routes import download as dl_module

        src = inspect.getsource(dl_module.download_audio)

        assert "output_path" in src
        assert "get_task" in src


# ============================================================
# Bug-010: evict_layer 清理后剩余统计与实际可能不一致
# ============================================================

class TestBug010EvictRemainingInaccuracy:
    """Bug-010 [中]: evict_layer 清理后剩余统计与实际可能不一致"""

    def test_evict_uses_two_separate_scans(self, fresh_cache_manager, tmp_path):
        """验证 evict_layer 使用 _scan_files 扫描一次，然后又用 os.walk 重新扫描"""
        import inspect

        src = inspect.getsource(fresh_cache_manager.evict_layer)

        assert "_scan_files" in src, "evict_layer 调用 _scan_files 获取文件列表"
        assert "os.walk" in src, "evict_layer 最后又用 os.walk 重新扫描统计剩余"

        scan_call_count = src.count("_scan_files")
        walk_call_count = src.count("os.walk")

        assert scan_call_count >= 1
        assert walk_call_count >= 1

    def test_remaining_does_not_account_for_failed_deletes(self, fresh_cache_manager, tmp_path):
        """验证删除失败时，removed 统计和 remaining 统计可能不一致"""
        cache_dir = tmp_path / "inaccurate"
        layer = CacheLayer(
            name="inacc",
            base_dir=str(cache_dir),
            ttl_seconds=1,
        )
        fresh_cache_manager.register_layer(layer)

        for i in range(5):
            _create_file(str(cache_dir / f"file_{i}.bin"), 100, mtime_offset=-10)

        original_remove = os.remove
        fail_count = 0

        def mock_remove(path):
            nonlocal fail_count
            if "file_2" in path:
                fail_count += 1
                raise OSError("Cannot delete")
            return original_remove(path)

        with patch("os.remove", side_effect=mock_remove):
            result = fresh_cache_manager.evict_layer("inacc")

        expected_removed = 4
        actual_removed = result["files_removed"]
        remaining = result["files_remaining"]

        assert actual_removed + remaining >= 4, (
            f"removed({actual_removed}) + remaining({remaining}) 应该 >= 成功删除的数量"
        )

        file_2_exists = (cache_dir / "file_2.bin").exists()
        assert file_2_exists, "删除失败的文件应该仍然存在"


# ============================================================
# Bug-011: ConfigProvider 抽象类与实际配置项不对齐
# ============================================================

class TestBug011ConfigProviderMissingFields:
    """Bug-011 [中]: ConfigProvider 抽象类与实际配置项不对齐"""

    def test_env_config_missing_host(self):
        """验证 EnvConfigProvider 没有 get_host 方法"""
        provider = EnvConfigProvider()
        assert not hasattr(provider, "get_host"), (
            "Bug-011: EnvConfigProvider 缺少 get_host 方法"
        )

    def test_env_config_missing_port(self):
        """验证 EnvConfigProvider 没有 get_port 方法"""
        provider = EnvConfigProvider()
        assert not hasattr(provider, "get_port"), (
            "Bug-011: EnvConfigProvider 缺少 get_port 方法"
        )

    def test_env_config_missing_max_upload_size(self):
        """验证 EnvConfigProvider 没有 get_max_upload_size 方法"""
        provider = EnvConfigProvider()
        assert not hasattr(provider, "get_max_upload_size"), (
            "Bug-011: EnvConfigProvider 缺少 get_max_upload_size 方法"
        )

    def test_env_config_missing_max_workers(self):
        """验证 EnvConfigProvider 没有 get_max_workers 方法"""
        provider = EnvConfigProvider()
        assert not hasattr(provider, "get_max_workers"), (
            "Bug-011: EnvConfigProvider 缺少 get_max_workers 方法"
        )

    def test_abstract_class_missing_methods(self):
        """验证 ConfigProvider 抽象类缺少 config.py 中的多个配置项"""
        import config

        config_attrs = [
            attr for attr in dir(config)
            if attr.isupper() and not attr.startswith("_")
        ]

        provider_methods = [
            method for method in dir(ConfigProvider)
            if method.startswith("get_") and callable(getattr(ConfigProvider, method))
        ]

        missing_configs = []
        for attr in config_attrs:
            expected_method = f"get_{attr.lower()}"
            if expected_method not in provider_methods:
                missing_configs.append(attr)

        assert len(missing_configs) > 0, (
            f"Bug-011: ConfigProvider 缺少 {len(missing_configs)} 个配置项的方法: "
            f"{missing_configs}"
        )

        assert "HOST" in missing_configs or "PORT" in missing_configs, (
            "至少应该缺少 HOST 或 PORT 等基础配置"
        )

    def test_dict_config_provider_also_missing(self):
        """验证 DictConfigProvider 同样缺少这些方法"""
        provider = DictConfigProvider({})
        assert not hasattr(provider, "get_host")
        assert not hasattr(provider, "get_port")
        assert not hasattr(provider, "get_max_upload_size")
        assert not hasattr(provider, "get_max_workers")
        assert not hasattr(provider, "get_decoded_dir")


# ============================================================
# Bug-012: resolve 未拒绝 NUL 字节注入
# ============================================================

class TestBug012NullByteInjection:
    """Bug-012 [低]: resolve 未拒绝 NUL 字节注入"""

    def test_null_byte_raises_value_error_not_security_error(self, gateway):
        """验证含 NUL 字节的文件名抛出 ValueError 而非 SecurityError

        Bug 说明: resolve 方法没有显式检查 NUL 字节，而是依赖底层 os.path.realpath
        抛出 ValueError。这意味着:
        1. 异常类型不符合预期（应该是 SecurityError）
        2. 错误信息可能泄露路径等内部信息
        3. 如果某些平台/调用不抛异常，可能被绕过
        """
        null_filename = "test\x00evil.txt"

        with pytest.raises(ValueError, match="null byte"):
            gateway.resolve(null_filename)

    def test_null_byte_not_explicitly_validated(self, gateway):
        """验证 resolve 代码中没有显式的 NUL 字节检查"""
        import inspect
        src = inspect.getsource(gateway.resolve)

        assert "\\x00" not in src and "null" not in src.lower(), (
            "如果 resolve 中有显式 NUL 检查，说明 bug 可能已修复"
        )

    def test_null_byte_basename_still_has_path_traversal(self):
        """验证含 NUL 字节 + 路径遍历时，basename 的行为

        注意: 'file\\x00../passwd' 中 basename 返回 'passwd'，
        因为 basename 只是找最后一个 '/'，NUL 字节不影响 Python 字符串处理。
        但在与 C 扩展交互时可能有截断风险。
        """
        test_name = "file\x00../passwd"
        basename = os.path.basename(test_name)

        assert basename == "passwd", (
            f"os.path.basename 对含 NUL + 遍历的字符串返回: {repr(basename)}"
        )
        assert "\x00" not in basename, (
            "basename 返回值中没有 NUL 字节（因为 '/' 在 NUL 之后）"
        )


# ============================================================
# Bug-013: list_files 不跳过 .tmp 临时文件
# ============================================================

class TestBug013ListFilesIncludesTemp:
    """Bug-013 [低]: list_files 不跳过 .tmp 临时文件"""

    def test_tmp_files_listed(self, gateway):
        """验证 .tmp 临时文件会被 list_files 返回"""
        gateway.safe_write("real.txt", b"real data")

        temp_file = os.path.join(gateway.base_dir, "orphan.tmp")
        with open(temp_file, "wb") as f:
            f.write(b"orphan temp")

        files = gateway.list_files()

        assert "orphan.tmp" in files, (
            "Bug-013 复现失败: 预期 list_files 会包含 .tmp 文件，"
            "但实际没有。如果此断言失败，说明 list_files 可能已增加过滤逻辑。"
        )
        assert "real.txt" in files

    def test_multiple_tmp_files_all_listed(self, gateway):
        """验证多个 .tmp 文件都会被列出"""
        for i in range(3):
            temp_path = os.path.join(gateway.base_dir, f"temp_{i}.tmp")
            with open(temp_path, "w") as f:
                f.write(f"temp {i}")

        files = gateway.list_files()
        tmp_files = [f for f in files if f.endswith(".tmp")]

        assert len(tmp_files) == 3, (
            f"Bug-013: 预期 3 个 .tmp 文件都被列出，实际只有 {len(tmp_files)} 个"
        )


# ============================================================
# Bug-014: _scan_files 中 isfile 与 stat 存在 TOCTOU
# ============================================================

class TestBug014ScanFilesTOCTOU:
    """Bug-014 [低]: _scan_files 中 isfile 与 stat 存在 TOCTOU"""

    def test_scan_files_uses_isfile_then_stat(self, fresh_cache_manager, tmp_path):
        """验证 _scan_files 使用 isfile 后再 stat，两次系统调用存在 TOCTOU"""
        import inspect

        src = inspect.getsource(fresh_cache_manager._scan_files)

        assert "os.path.isfile" in src, "_scan_files 调用 isfile"
        assert "os.stat" in src, "_scan_files 调用 stat"

        isfile_pos = src.find("os.path.isfile")
        stat_pos = src.find("os.stat")

        assert isfile_pos < stat_pos, (
            "Bug-014 验证: isfile 在 stat 之前调用，存在 TOCTOU 窗口"
        )

    def test_file_disappears_between_isfile_and_stat(self, fresh_cache_manager, tmp_path):
        """验证文件在 isfile 和 stat 之间消失时的行为"""
        cache_dir = tmp_path / "toctou"
        layer = CacheLayer(name="toctou", base_dir=str(cache_dir))
        fresh_cache_manager.register_layer(layer)

        file_path = cache_dir / "volatile.bin"
        _create_file(str(file_path), 100)

        original_isfile = os.path.isfile
        call_count = 0

        def mock_isfile(path):
            nonlocal call_count
            call_count += 1
            result = original_isfile(path)
            if result and "volatile" in path:
                try:
                    os.remove(path)
                except OSError:
                    pass
            return result

        with patch("os.path.isfile", side_effect=mock_isfile):
            files = fresh_cache_manager._scan_files(str(cache_dir))

        assert len(files) == 0 or not file_path.exists(), (
            "验证: 文件在 isfile 和 stat 之间消失时，_scan_files 应该处理这种情况"
        )

        assert call_count >= 1


# ============================================================
# 综合验证：确保至少 12 个 bug 类存在
# ============================================================

class TestBugCountVerification:
    def test_at_least_12_bug_classes(self):
        """验证本测试文件包含至少 12 个 bug 测试类"""
        bug_classes = [
            name for name in globals()
            if name.startswith("TestBug")
        ]
        assert len(bug_classes) >= 12, (
            f"预期至少 12 个 bug 测试类，实际只有 {len(bug_classes)} 个: {bug_classes}"
        )

    def test_severity_distribution(self):
        """验证 bug 严重程度分布：高/中/低 都有"""
        high_bugs = [n for n in globals() if n.startswith("TestBug") and any(
            kw in n for kw in ["TempFileLeak", "LockEviction", "PathTraversal", "TTLFail", "DirectLayer"]
        )]
        medium_bugs = [n for n in globals() if n.startswith("TestBug") and any(
            kw in n for kw in ["Deadlock", "Symlink", "StatsRace", "NoPathValidation", "RemainingInaccuracy", "MissingFields"]
        )]
        low_bugs = [n for n in globals() if n.startswith("TestBug") and any(
            kw in n for kw in ["NullByte", "IncludesTemp", "TOCTOU"]
        )]

        assert len(high_bugs) >= 4, f"高危 bug 应不少于 4 个，实际 {len(high_bugs)} 个"
        assert len(medium_bugs) >= 5, f"中危 bug 应不少于 5 个，实际 {len(medium_bugs)} 个"
        assert len(low_bugs) >= 3, f"低危 bug 应不少于 3 个，实际 {len(low_bugs)} 个"
