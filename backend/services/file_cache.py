import os
import logging
from database import get_all_tasks_ordered, delete_task
from config import UPLOAD_DIR, OUTPUT_DIR, SOURCE_FILE_CACHE_LIMIT

logger = logging.getLogger(__name__)

def get_dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total += os.path.getsize(fp)
    return total

def evict_old_files():
    upload_size = get_dir_size(UPLOAD_DIR)
    output_size = get_dir_size(OUTPUT_DIR)
    total = upload_size + output_size

    if total <= SOURCE_FILE_CACHE_LIMIT:
        return

    logger.info(f"缓存超限: upload={upload_size} output={output_size} total={total} limit={SOURCE_FILE_CACHE_LIMIT}")

    tasks = get_all_tasks_ordered()

    for task in tasks:
        if total <= SOURCE_FILE_CACHE_LIMIT:
            break

        task_id = task["id"]
        original_path = task.get("original_path", "")
        output_path = task.get("output_path", "")

        released = 0
        if output_path and os.path.exists(output_path):
            released += os.path.getsize(output_path)
            os.remove(output_path)
            logger.info(f"释放输出文件: {output_path} ({released} bytes)")

        if original_path and os.path.exists(original_path):
            released += os.path.getsize(original_path)
            os.remove(original_path)
            logger.info(f"释放源文件: {original_path} ({os.path.getsize(original_path)} bytes)")

        delete_task(task_id)
        logger.info(f"删除任务记录: {task_id}")

        total -= released

    logger.info(f"缓存清理完成: total={total}")
