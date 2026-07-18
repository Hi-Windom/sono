from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class BaseTask(ABC):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    @property
    @abstractmethod
    def task_type(self) -> str:
        ...

    @property
    def processing_status(self) -> str:
        return "processing"

    @property
    def completed_status(self) -> str:
        return "completed"

    @property
    def initial_step(self) -> str:
        return "任务已提交..."

    @property
    def start_step(self) -> str:
        return "开始执行..."

    @property
    def done_step(self) -> str:
        return "执行完成"

    @property
    def error_step(self) -> str:
        return "执行失败"

    @property
    def cancel_step(self) -> str:
        return "已取消"

    @property
    def initial_fields(self) -> dict[str, Any]:
        return {
            "error": "",
        }

    @abstractmethod
    def execute(self, progress_callback: Callable[[float, str], None]) -> dict[str, Any]:
        ...

    def on_success(self, result: dict[str, Any]) -> dict[str, Any]:
        return {}

    def on_error(self, error: Exception) -> dict[str, Any] | None:
        return None

    def on_cancel(self) -> None:
        pass

    def cancel(self) -> None:
        pass

    def cleanup(self) -> None:
        pass
