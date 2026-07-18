from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)


def _get_config():
    import config
    return config


@dataclass
class CacheLayer:
    name: str
    base_dir: str
    ttl_seconds: float = 0.0
    max_size_mb: float = 0.0


class _LayerStats:
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self._lock = Lock()

    def record_hit(self):
        with self._lock:
            self.hits += 1

    def record_miss(self):
        with self._lock:
            self.misses += 1

    def get_snapshot(self) -> dict:
        with self._lock:
            hits = self.hits
            misses = self.misses
        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0
        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": hit_rate,
        }


class CacheManager:
    _instance: Optional["CacheManager"] = None
    _instance_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._layers: dict[str, CacheLayer] = {}
        self._stats: dict[str, _LayerStats] = {}
        self._lock = Lock()
        self._initialized = True
        self._register_standard_layers()

    def _register_standard_layers(self):
        config = _get_config()
        base_dir = os.path.dirname(os.path.abspath(config.__file__))
        storage_dir = os.path.join(base_dir, "storage")

        self.register_layer(CacheLayer(
            name="upload_cache",
            base_dir=config.UPLOAD_DIR,
            ttl_seconds=0,
            max_size_mb=0,
        ))

        self.register_layer(CacheLayer(
            name="repair_output",
            base_dir=config.OUTPUT_DIR,
            ttl_seconds=0,
            max_size_mb=0,
        ))

        render_dir = os.path.join(storage_dir, "render")
        self.register_layer(CacheLayer(
            name="render_output",
            base_dir=render_dir,
            ttl_seconds=0,
            max_size_mb=0,
        ))

        mp3_dir = os.path.join(storage_dir, "mp3_cache")
        self.register_layer(CacheLayer(
            name="mp3_cache",
            base_dir=mp3_dir,
            ttl_seconds=0,
            max_size_mb=0,
        ))

    def register_layer(self, layer: CacheLayer) -> None:
        with self._lock:
            self._layers[layer.name] = layer
            if layer.name not in self._stats:
                self._stats[layer.name] = _LayerStats()
            os.makedirs(layer.base_dir, exist_ok=True)
            logger.info(f"注册缓存层: {layer.name} -> {layer.base_dir}")

    def _get_layer(self, layer_name: str) -> CacheLayer:
        with self._lock:
            layer = self._layers.get(layer_name)
        if layer is None:
            raise ValueError(f"缓存层不存在: {layer_name}")
        return layer

    def _is_path_safe(self, file_path: str, base_dir: str) -> bool:
        try:
            real_path = os.path.realpath(file_path)
            real_base = os.path.realpath(base_dir)
            return real_path.startswith(real_base + os.sep) or real_path == real_base
        except OSError:
            return False

    def _scan_files(self, base_dir: str) -> list[tuple[str, int, float]]:
        files = []
        for dirpath, _, filenames in os.walk(base_dir):
            for fname in filenames:
                fp = os.path.join(dirpath, fname)
                try:
                    if not os.path.isfile(fp):
                        continue
                    if not self._is_path_safe(fp, base_dir):
                        logger.warning(f"跳过不安全路径: {fp}")
                        continue
                    stat = os.stat(fp)
                    files.append((fp, stat.st_size, stat.st_mtime))
                except OSError as e:
                    logger.warning(f"扫描文件失败 {fp}: {e}")
        return files

    def evict_layer(self, layer_name: str) -> dict:
        layer = self._get_layer(layer_name)
        base_dir = layer.base_dir
        ttl = layer.ttl_seconds
        max_size_bytes = int(layer.max_size_mb * 1024 * 1024) if layer.max_size_mb > 0 else 0

        if not os.path.isdir(base_dir):
            return {
                "layer": layer_name,
                "files_removed": 0,
                "bytes_removed": 0,
                "files_remaining": 0,
                "bytes_remaining": 0,
            }

        files = self._scan_files(base_dir)
        total_size = sum(f[1] for f in files)
        removed_count = 0
        removed_bytes = 0

        if ttl > 0:
            now = time.time()
            expired = [f for f in files if now - f[2] > ttl]
            expired.sort(key=lambda x: x[2])
            for fp, size, mtime in expired:
                try:
                    os.remove(fp)
                    removed_count += 1
                    removed_bytes += size
                    total_size -= size
                    logger.debug(f"TTL 过期删除: {fp}")
                except OSError as e:
                    logger.warning(f"删除文件失败 {fp}: {e}")
            files = [f for f in files if f[0] not in {e[0] for e in expired}]

        if max_size_bytes > 0 and total_size > max_size_bytes:
            files.sort(key=lambda x: x[2])
            for fp, size, mtime in files:
                if total_size <= max_size_bytes:
                    break
                try:
                    os.remove(fp)
                    removed_count += 1
                    removed_bytes += size
                    total_size -= size
                    logger.debug(f"LRU 淘汰: {fp}")
                except OSError as e:
                    logger.warning(f"删除文件失败 {fp}: {e}")

        remaining_files = 0
        remaining_size = 0
        try:
            for dirpath, _, filenames in os.walk(base_dir):
                for fname in filenames:
                    fp = os.path.join(dirpath, fname)
                    if os.path.isfile(fp):
                        remaining_files += 1
                        remaining_size += os.path.getsize(fp)
        except OSError:
            pass

        result = {
            "layer": layer_name,
            "files_removed": removed_count,
            "bytes_removed": removed_bytes,
            "files_remaining": remaining_files,
            "bytes_remaining": remaining_size,
        }
        logger.info(
            f"缓存清理完成 [{layer_name}]: "
            f"删除 {removed_count} 文件 ({removed_bytes} bytes), "
            f"剩余 {remaining_files} 文件 ({remaining_size} bytes)"
        )
        return result

    def evict_all(self) -> dict[str, dict]:
        results = {}
        with self._lock:
            layer_names = list(self._layers.keys())
        for name in layer_names:
            results[name] = self.evict_layer(name)
        return results

    def get_layer_stats(self, layer_name: str) -> dict:
        layer = self._get_layer(layer_name)
        base_dir = layer.base_dir

        file_count = 0
        total_size = 0
        if os.path.isdir(base_dir):
            try:
                for dirpath, _, filenames in os.walk(base_dir):
                    for fname in filenames:
                        fp = os.path.join(dirpath, fname)
                        if os.path.isfile(fp) and self._is_path_safe(fp, base_dir):
                            file_count += 1
                            total_size += os.path.getsize(fp)
            except OSError:
                pass

        with self._lock:
            stats = self._stats.get(layer_name)
        hit_stats = stats.get_snapshot() if stats else {"hits": 0, "misses": 0, "hit_rate": 0.0}

        return {
            "name": layer.name,
            "base_dir": layer.base_dir,
            "ttl_seconds": layer.ttl_seconds,
            "max_size_mb": layer.max_size_mb,
            "file_count": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            **hit_stats,
        }

    def get_stats(self) -> dict[str, dict]:
        with self._lock:
            layer_names = list(self._layers.keys())
        return {name: self.get_layer_stats(name) for name in layer_names}

    def record_hit(self, layer_name: str) -> None:
        with self._lock:
            stats = self._stats.get(layer_name)
        if stats:
            stats.record_hit()

    def record_miss(self, layer_name: str) -> None:
        with self._lock:
            stats = self._stats.get(layer_name)
        if stats:
            stats.record_miss()

    def reset_stats(self, layer_name: Optional[str] = None) -> None:
        with self._lock:
            if layer_name:
                if layer_name in self._stats:
                    self._stats[layer_name] = _LayerStats()
            else:
                for name in list(self._stats.keys()):
                    self._stats[name] = _LayerStats()
