from __future__ import annotations

import logging
import os
from typing import Any

from database import TaskDict, delete_task, get_all_tasks_ordered
from services.cache_manager import CacheManager

logger = logging.getLogger(__name__)


def _get_config():
    import config
    return config.OUTPUT_DIR, config.SOURCE_FILE_CACHE_LIMIT, config.UPLOAD_DIR

def get_dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total += os.path.getsize(fp)
    return total

def evict_old_files() -> None:
    OUTPUT_DIR, SOURCE_FILE_CACHE_LIMIT, UPLOAD_DIR = _get_config()

    cache_mgr = CacheManager()

    upload_stats = cache_mgr.get_layer_stats("upload_cache")
    output_stats = cache_mgr.get_layer_stats("repair_output")

    upload_size = upload_stats["total_size_bytes"]
    output_size = output_stats["total_size_bytes"]
    total = upload_size + output_size

    if total <= SOURCE_FILE_CACHE_LIMIT:
        return

    logger.info(f"缓存超限: upload={upload_size} output={output_size} total={total} limit={SOURCE_FILE_CACHE_LIMIT}")

    limit_mb = SOURCE_FILE_CACHE_LIMIT / (1024 * 1024)

    upload_layer = cache_mgr._layers["upload_cache"]
    output_layer = cache_mgr._layers["repair_output"]

    old_upload_max = upload_layer.max_size_mb
    old_output_max = output_layer.max_size_mb

    try:
        if upload_size > 0 and output_size > 0:
            ratio = upload_size / total
            upload_layer.max_size_mb = limit_mb * ratio * 0.9
            output_layer.max_size_mb = limit_mb * (1 - ratio) * 0.9
        elif upload_size > 0:
            upload_layer.max_size_mb = limit_mb * 0.9
            output_layer.max_size_mb = 0
        else:
            upload_layer.max_size_mb = 0
            output_layer.max_size_mb = limit_mb * 0.9

        cache_mgr.evict_layer("upload_cache")
        cache_mgr.evict_layer("repair_output")
    finally:
        upload_layer.max_size_mb = old_upload_max
        output_layer.max_size_mb = old_output_max

    tasks: list[TaskDict] = get_all_tasks_ordered()
    for task in tasks:
        task_id: str = task["id"]
        original_path: str = task.get("original_path", "")
        output_path: str = task.get("output_path", "")

        orig_exists = original_path and os.path.exists(original_path)
        out_exists = output_path and os.path.exists(output_path)

        if not orig_exists and not out_exists:
            has_render_cache = False
            if os.path.isdir(OUTPUT_DIR):
                for fname in os.listdir(OUTPUT_DIR):
                    if fname.startswith(f"{task_id}_rendered_") and fname.endswith(".wav"):
                        has_render_cache = True
                        break

            if not has_render_cache:
                delete_task(task_id)
                logger.info(f"删除孤儿任务记录: {task_id}")

    logger.info(f"缓存清理完成")
