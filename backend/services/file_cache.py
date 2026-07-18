from __future__ import annotations

import logging
import os
from typing import Any

from config import OUTPUT_DIR, SOURCE_FILE_CACHE_LIMIT, UPLOAD_DIR
from database import TaskDict, delete_task, get_all_tasks_ordered

logger = logging.getLogger(__name__)

def get_dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total += os.path.getsize(fp)
    return total

def evict_old_files() -> None:
    upload_size = get_dir_size(UPLOAD_DIR)
    output_size = get_dir_size(OUTPUT_DIR)
    total = upload_size + output_size

    if total <= SOURCE_FILE_CACHE_LIMIT:
        return

    logger.info(f"缓存超限: upload={upload_size} output={output_size} total={total} limit={SOURCE_FILE_CACHE_LIMIT}")

    tasks: list[TaskDict] = get_all_tasks_ordered()

    for task in tasks:
        if total <= SOURCE_FILE_CACHE_LIMIT:
            break

        task_id: str = task["id"]
        original_path: str = task.get("original_path", "")
        output_path: str = task.get("output_path", "")

        released = 0
        if output_path and os.path.exists(output_path):
            released += os.path.getsize(output_path)
            os.remove(output_path)
            logger.info(f"释放输出文件: {output_path} ({released} bytes)")

        if original_path and os.path.exists(original_path):
            orig_size = os.path.getsize(original_path)
            os.remove(original_path)
            released += orig_size
            logger.info(f"释放源文件: {original_path} ({orig_size} bytes)")

        if os.path.isdir(OUTPUT_DIR):
            for fname in os.listdir(OUTPUT_DIR):
                if fname.startswith(f"{task_id}_rendered_") and fname.endswith(".wav"):
                    fp = os.path.join(OUTPUT_DIR, fname)
                    if os.path.isfile(fp):
                        try:
                            fsize = os.path.getsize(fp)
                            os.remove(fp)
                            released += fsize
                            logger.info(f"释放渲染缓存: {fp} ({fsize} bytes)")
                        except OSError as e:
                            logger.warning(f"删除渲染缓存失败: {fp}, {e}")

        delete_task(task_id)
        logger.info(f"删除任务记录: {task_id}")

        total -= released

    logger.info(f"缓存清理完成: total={total}")
