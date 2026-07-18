import sys
import os
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"

from services.cache_manager import CacheLayer, CacheManager


@pytest.fixture
def fresh_manager(tmp_path):
    CacheManager._instance = None
    manager = CacheManager()
    manager._layers.clear()
    manager._stats.clear()
    return manager


def _create_file(dir_path: Path, size_bytes: int, mtime_offset: float = 0):
    dir_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dir_path, "wb") as f:
        f.write(b"x" * size_bytes)
    if mtime_offset != 0:
        new_mtime = time.time() + mtime_offset
        os.utime(dir_path, (new_mtime, new_mtime))


class TestCacheLayer:
    def test_cache_layer_creation(self):
        layer = CacheLayer(
            name="test",
            base_dir="/tmp/test",
            ttl_seconds=3600,
            max_size_mb=100,
        )
        assert layer.name == "test"
        assert layer.base_dir == "/tmp/test"
        assert layer.ttl_seconds == 3600
        assert layer.max_size_mb == 100

    def test_cache_layer_defaults(self):
        layer = CacheLayer(name="test", base_dir="/tmp/test")
        assert layer.ttl_seconds == 0.0
        assert layer.max_size_mb == 0.0


class TestCacheManagerSingleton:
    def test_singleton_instance(self):
        CacheManager._instance = None
        m1 = CacheManager()
        m2 = CacheManager()
        assert m1 is m2

    def test_singleton_reset(self):
        CacheManager._instance = None
        m1 = CacheManager()
        CacheManager._instance = None
        m2 = CacheManager()
        assert m1 is not m2


class TestRegisterLayer:
    def test_register_layer(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "test_cache"
        layer = CacheLayer(name="test_layer", base_dir=str(cache_dir))
        fresh_manager.register_layer(layer)
        stats = fresh_manager.get_layer_stats("test_layer")
        assert stats["name"] == "test_layer"
        assert stats["base_dir"] == str(cache_dir)
        assert cache_dir.exists()

    def test_register_layer_creates_dir(self, fresh_manager, tmp_path):
        new_dir = tmp_path / "new_dir" / "subdir"
        assert not new_dir.exists()
        layer = CacheLayer(name="auto_create", base_dir=str(new_dir))
        fresh_manager.register_layer(layer)
        assert new_dir.exists()

    def test_register_duplicate_layer(self, fresh_manager, tmp_path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        layer1 = CacheLayer(name="dup", base_dir=str(dir1))
        layer2 = CacheLayer(name="dup", base_dir=str(dir2))
        fresh_manager.register_layer(layer1)
        fresh_manager.register_layer(layer2)
        stats = fresh_manager.get_layer_stats("dup")
        assert stats["base_dir"] == str(dir2)


class TestTTLEviction:
    def test_ttl_expired_files_removed(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "ttl_cache"
        layer = CacheLayer(name="ttl_test", base_dir=str(cache_dir), ttl_seconds=1)
        fresh_manager.register_layer(layer)

        _create_file(cache_dir / "old_file.bin", 100, mtime_offset=-10)
        _create_file(cache_dir / "new_file.bin", 200, mtime_offset=0)

        result = fresh_manager.evict_layer("ttl_test")

        assert result["files_removed"] == 1
        assert result["files_remaining"] == 1
        assert not (cache_dir / "old_file.bin").exists()
        assert (cache_dir / "new_file.bin").exists()

    def test_ttl_zero_no_expiry(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "no_ttl"
        layer = CacheLayer(name="no_ttl", base_dir=str(cache_dir), ttl_seconds=0)
        fresh_manager.register_layer(layer)

        _create_file(cache_dir / "old.bin", 100, mtime_offset=-99999)

        result = fresh_manager.evict_layer("no_ttl")

        assert result["files_removed"] == 0
        assert result["files_remaining"] == 1
        assert (cache_dir / "old.bin").exists()

    def test_ttl_all_expired(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "all_expired"
        layer = CacheLayer(name="all_expired", base_dir=str(cache_dir), ttl_seconds=1)
        fresh_manager.register_layer(layer)

        for i in range(5):
            _create_file(cache_dir / f"file_{i}.bin", 50, mtime_offset=-10)

        result = fresh_manager.evict_layer("all_expired")

        assert result["files_removed"] == 5
        assert result["files_remaining"] == 0


class TestCapacityLRUEviction:
    def test_lru_eviction_by_size(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "lru_cache"
        layer = CacheLayer(name="lru_test", base_dir=str(cache_dir), max_size_mb=0.001)
        fresh_manager.register_layer(layer)

        _create_file(cache_dir / "old_large.bin", 600, mtime_offset=-100)
        _create_file(cache_dir / "new_small.bin", 300, mtime_offset=-10)
        _create_file(cache_dir / "mid.bin", 200, mtime_offset=-50)

        result = fresh_manager.evict_layer("lru_test")

        assert result["files_remaining"] >= 1
        assert result["bytes_remaining"] <= 1024
        assert (cache_dir / "new_small.bin").exists()

    def test_lru_orders_by_mtime(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "lru_order"
        layer = CacheLayer(name="lru_order", base_dir=str(cache_dir), max_size_mb=0.0003)
        fresh_manager.register_layer(layer)

        _create_file(cache_dir / "a_oldest.bin", 200, mtime_offset=-100)
        _create_file(cache_dir / "b_mid.bin", 200, mtime_offset=-50)
        _create_file(cache_dir / "c_newest.bin", 200, mtime_offset=0)

        result = fresh_manager.evict_layer("lru_order")

        assert not (cache_dir / "a_oldest.bin").exists()
        assert not (cache_dir / "b_mid.bin").exists()
        assert (cache_dir / "c_newest.bin").exists()

    def test_no_capacity_limit(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "no_limit"
        layer = CacheLayer(name="no_limit", base_dir=str(cache_dir), max_size_mb=0)
        fresh_manager.register_layer(layer)

        for i in range(10):
            _create_file(cache_dir / f"f_{i}.bin", 10000, mtime_offset=-i)

        result = fresh_manager.evict_layer("no_limit")

        assert result["files_removed"] == 0
        assert result["files_remaining"] == 10


class TestTTLBeforeLRU:
    def test_ttl_runs_before_lru(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "ttl_then_lru"
        layer = CacheLayer(
            name="ttl_lru",
            base_dir=str(cache_dir),
            ttl_seconds=10,
            max_size_mb=0.001,
        )
        fresh_manager.register_layer(layer)

        _create_file(cache_dir / "expired_large.bin", 800, mtime_offset=-100)
        _create_file(cache_dir / "fresh_large.bin", 800, mtime_offset=0)
        _create_file(cache_dir / "fresh_small.bin", 100, mtime_offset=-1)

        result = fresh_manager.evict_layer("ttl_lru")

        assert not (cache_dir / "expired_large.bin").exists()
        assert (cache_dir / "fresh_large.bin").exists()
        assert (cache_dir / "fresh_small.bin").exists()
        assert result["files_removed"] >= 1


class TestStats:
    def test_stats_file_count_and_size(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "stats_test"
        layer = CacheLayer(name="stats_test", base_dir=str(cache_dir))
        fresh_manager.register_layer(layer)

        _create_file(cache_dir / "a.bin", 100)
        _create_file(cache_dir / "sub" / "b.bin", 200)

        stats = fresh_manager.get_layer_stats("stats_test")

        assert stats["file_count"] == 2
        assert stats["total_size_bytes"] == 300
        assert stats["name"] == "stats_test"

    def test_hit_miss_stats(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "hit_miss"
        layer = CacheLayer(name="hit_miss", base_dir=str(cache_dir))
        fresh_manager.register_layer(layer)

        fresh_manager.record_hit("hit_miss")
        fresh_manager.record_hit("hit_miss")
        fresh_manager.record_hit("hit_miss")
        fresh_manager.record_miss("hit_miss")

        stats = fresh_manager.get_layer_stats("hit_miss")
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert abs(stats["hit_rate"] == pytest.approx(0.75))

    def test_get_stats_all_layers(self, fresh_manager, tmp_path):
        d1 = tmp_path / "l1"
        d2 = tmp_path / "l2"
        fresh_manager.register_layer(CacheLayer(name="l1", base_dir=str(d1)))
        fresh_manager.register_layer(CacheLayer(name="l2", base_dir=str(d2)))

        _create_file(d1 / "a.bin", 100)
        _create_file(d2 / "b.bin", 200)

        all_stats = fresh_manager.get_stats()
        assert "l1" in all_stats
        assert "l2" in all_stats
        assert all_stats["l1"]["file_count"] == 1
        assert all_stats["l2"]["file_count"] == 1

    def test_reset_stats(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "reset"
        layer = CacheLayer(name="reset", base_dir=str(cache_dir))
        fresh_manager.register_layer(layer)

        fresh_manager.record_hit("reset")
        fresh_manager.record_miss("reset")
        fresh_manager.reset_stats("reset")

        stats = fresh_manager.get_layer_stats("reset")
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestMultiLayerIsolation:
    def test_evict_one_layer_does_not_affect_other(self, fresh_manager, tmp_path):
        d1 = tmp_path / "layer1"
        d2 = tmp_path / "layer2"
        fresh_manager.register_layer(CacheLayer(
            name="layer1", base_dir=str(d1), ttl_seconds=1,
        ))
        fresh_manager.register_layer(CacheLayer(
            name="layer2", base_dir=str(d2), ttl_seconds=99999,
        ))

        _create_file(d1 / "f1.bin", 100, mtime_offset=-10)
        _create_file(d2 / "f2.bin", 100, mtime_offset=-10)

        fresh_manager.evict_layer("layer1")

        assert not (d1 / "f1.bin").exists()
        assert (d2 / "f2.bin").exists()

    def test_evict_all(self, fresh_manager, tmp_path):
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        fresh_manager.register_layer(CacheLayer(
            name="a", base_dir=str(d1), ttl_seconds=1,
        ))
        fresh_manager.register_layer(CacheLayer(
            name="b", base_dir=str(d2), ttl_seconds=1,
        ))

        _create_file(d1 / "x.bin", 50, mtime_offset=-10)
        _create_file(d2 / "y.bin", 50, mtime_offset=-10)

        results = fresh_manager.evict_all()

        assert "a" in results
        assert "b" in results
        assert results["a"]["files_removed"] == 1
        assert results["b"]["files_removed"] == 1
        assert not (d1 / "x.bin").exists()
        assert not (d2 / "y.bin").exists()


class TestPathSafety:
    def test_safe_path_inside_base(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "safe"
        layer = CacheLayer(name="safe", base_dir=str(cache_dir))
        fresh_manager.register_layer(layer)

        normal_file = cache_dir / "normal.bin"
        _create_file(normal_file, 100)

        assert fresh_manager._is_path_safe(str(normal_file), str(cache_dir))

    def test_unsafe_path_outside_base(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "safe_dir"
        layer = CacheLayer(name="safe_dir", base_dir=str(cache_dir))
        fresh_manager.register_layer(layer)

        outside_file = tmp_path / "outside.bin"
        _create_file(outside_file, 100)

        assert not fresh_manager._is_path_safe(str(outside_file), str(cache_dir))

    def test_symlink_outside_not_deleted(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "link_test"
        layer = CacheLayer(
            name="link_test",
            base_dir=str(cache_dir),
            ttl_seconds=1,
        )
        fresh_manager.register_layer(layer)

        outside_file = tmp_path / "outside.bin"
        _create_file(outside_file, 100, mtime_offset=-10)

        link_path = cache_dir / "link.bin"
        os.symlink(str(outside_file), str(link_path))

        assert os.path.exists(link_path)
        result = fresh_manager.evict_layer("link_test")

        assert outside_file.exists()

    def test_path_traversal_ignored(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "traversal"
        layer = CacheLayer(name="traversal", base_dir=str(cache_dir))
        fresh_manager.register_layer(layer)

        result = fresh_manager._is_path_safe(
            str(cache_dir / ".." / "etc" / "passwd"),
            str(cache_dir),
        )
        assert not result


class TestStandardLayers:
    def test_standard_layers_exist(self):
        CacheManager._instance = None
        manager = CacheManager()
        stats = manager.get_stats()
        assert "upload_cache" in stats
        assert "repair_output" in stats
        assert "render_output" in stats
        assert "mp3_cache" in stats

    def test_standard_layer_config(self):
        CacheManager._instance = None
        manager = CacheManager()
        upload_stats = manager.get_layer_stats("upload_cache")
        assert upload_stats["ttl_seconds"] == 0
        assert upload_stats["max_size_mb"] == 0


class TestEvictReturnValues:
    def test_evict_nonexistent_layer_raises(self, fresh_manager):
        with pytest.raises(ValueError, match="缓存层不存在"):
            fresh_manager.evict_layer("nonexistent")

    def test_stats_nonexistent_layer_raises(self, fresh_manager):
        with pytest.raises(ValueError, match="缓存层不存在"):
            fresh_manager.get_layer_stats("nonexistent")

    def test_evict_empty_dir(self, fresh_manager, tmp_path):
        cache_dir = tmp_path / "empty"
        layer = CacheLayer(name="empty", base_dir=str(cache_dir), ttl_seconds=1)
        fresh_manager.register_layer(layer)

        result = fresh_manager.evict_layer("empty")
        assert result["files_removed"] == 0
        assert result["files_remaining"] == 0
        assert result["bytes_removed"] == 0
        assert result["bytes_remaining"] == 0
