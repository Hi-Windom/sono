from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from config import MAX_CONCURRENT_TASKS
from database import update_task
from services.task_base import BaseTask
from services.task_manager import (
    TaskCancelledError,
    _cancelled_lock,
    _cancelled_tasks,
    _track_task_end,
    _track_task_start,
    _ws_send_final,
    _ws_send_progress,
    executor,
    get_active_task_count,
)

logger = logging.getLogger(__name__)


class TaskExecutor:
    _instance: TaskExecutor | None = None
    _instance_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> TaskExecutor:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

    def submit(self, task: BaseTask) -> None:
        task_id = task.task_id
        logger.info(f"[TaskExecutor] submit task_id={task_id} type={task.task_type}")

        update_fields = {
            "status": "pending",
            "progress": 0.0,
            "step": task.initial_step,
        }
        update_fields.update(task.initial_fields)
        update_task(task_id, **update_fields)

        if not _track_task_start(task_id):
            active = get_active_task_count()
            logger.warning(
                f"[TaskExecutor] 拒绝任务 task_id={task_id}: 系统繁忙 ({active}/{MAX_CONCURRENT_TASKS})"
            )
            error_msg = f"系统繁忙（{active}/{MAX_CONCURRENT_TASKS} 任务运行中），请稍后重试"
            update_task(task_id, status="error", error=error_msg, step="系统繁忙")
            _ws_send_final(
                task_id,
                {
                    "task_id": task_id,
                    "status": "error",
                    "progress": 0,
                    "step": "系统繁忙",
                    "error": error_msg,
                },
            )
            _track_task_end(task_id)
            return

        future = executor.submit(self._run_task, task)
        future.add_done_callback(lambda f: self._handle_future_exception(f, task_id))

    def cancel(self, task_id: str) -> bool:
        with _cancelled_lock:
            if task_id in _cancelled_tasks:
                return False
            _cancelled_tasks.add(task_id)

        update_task(task_id, status="cancelled", step="已取消", progress=0)
        _ws_send_final(task_id, {"task_id": task_id, "status": "cancelled"})
        logger.info(f"[TaskExecutor] 任务已取消 task_id={task_id}")
        return True

    def _run_task(self, task: BaseTask) -> None:
        task_id = task.task_id
        task_type = task.task_type
        processing_status = task.processing_status
        completed_status = task.completed_status
        logger.info(f"[TaskExecutor] 开始执行 task_id={task_id} type={task_type}")

        try:
            with _cancelled_lock:
                if task_id in _cancelled_tasks:
                    logger.info(f"[TaskExecutor] 任务已取消，跳过执行 task_id={task_id}")
                    return

            update_task(task_id, status=processing_status, progress=0, step=task.start_step)
            _ws_send_progress(
                task_id,
                {
                    "task_id": task_id,
                    "status": processing_status,
                    "progress": 0,
                    "step": task.start_step,
                },
            )

            def progress_callback(progress: float, step: str) -> None:
                with _cancelled_lock:
                    if task_id in _cancelled_tasks:
                        raise TaskCancelledError(f"任务已取消: {task_id}")
                update_task(task_id, progress=progress, step=step)
                _ws_send_progress(
                    task_id,
                    {
                        "task_id": task_id,
                        "status": processing_status,
                        "progress": progress,
                        "step": step,
                    },
                )

            result = task.execute(progress_callback)

            extra_fields = task.on_success(result) or {}

            update_fields: dict[str, Any] = {
                "status": completed_status,
                "progress": 1,
                "step": task.done_step,
            }
            update_fields.update(extra_fields)

            update_task(task_id, **update_fields)

            final_data: dict[str, Any] = {
                "task_id": task_id,
                "status": completed_status,
                "progress": 1,
                "step": task.done_step,
            }
            final_data.update({k: v for k, v in update_fields.items() if k not in ("status", "progress", "step")})
            _ws_send_final(task_id, final_data)

            logger.info(f"[TaskExecutor] 完成 task_id={task_id} type={task_type}")

        except TaskCancelledError:
            task.on_cancel()
            logger.info(f"[TaskExecutor] 已取消 task_id={task_id}")
            update_task(task_id, status="cancelled", step=task.cancel_step, progress=0)
            _ws_send_final(
                task_id,
                {
                    "task_id": task_id,
                    "status": "cancelled",
                    "progress": 0,
                    "step": task.cancel_step,
                },
            )
        except Exception as e:
            import traceback

            extra_error_fields = task.on_error(e) or {}
            error_msg = f"{type(e).__name__}: {e}"
            full_error = f"{error_msg}\n{traceback.format_exc()}"
            logger.error(f"[TaskExecutor] 失败 task_id={task_id}: {full_error}")
            error_text = extra_error_fields.pop("error", full_error[:500])
            step_text = extra_error_fields.pop("step", task.error_step)
            update_task(task_id, status="error", error=error_text, step=step_text, **extra_error_fields)
            _ws_send_final(
                task_id,
                {
                    "task_id": task_id,
                    "status": "error",
                    "progress": 0,
                    "step": step_text,
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    **extra_error_fields,
                },
            )
            raise
        finally:
            try:
                task.cleanup()
            except Exception as e:
                logger.warning(f"[TaskExecutor] cleanup 失败 task_id={task_id}: {e}")
            _track_task_end(task_id)
            with _cancelled_lock:
                _cancelled_tasks.discard(task_id)

    def _handle_future_exception(self, future: Any, task_id: str) -> None:
        try:
            future.result()
        except Exception:
            pass


def get_task_executor() -> TaskExecutor:
    return TaskExecutor()
