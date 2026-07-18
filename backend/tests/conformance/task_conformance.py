from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import config
from services.task_base import BaseTask
from services.task_executor import TaskExecutor, get_task_executor
from services.task_manager import (
    TaskCancelledError,
    _active_tasks,
    _active_tasks_lock,
    _cancelled_lock,
    _cancelled_tasks,
    _track_task_end,
    _track_task_start,
    _ws_send_final,
    _ws_send_progress,
    get_active_task_count,
)


class FakeTask(BaseTask):
    def __init__(self, task_id: str, sleep_time: float = 0.2, fail: bool = False) -> None:
        super().__init__(task_id)
        self._sleep_time = sleep_time
        self._fail = fail

    @property
    def task_type(self) -> str:
        return "fake"

    def execute(self, progress_callback) -> dict[str, Any]:
        steps = 10
        for i in range(steps):
            progress_callback(i / steps, f"step {i + 1}/{steps}")
            time.sleep(self._sleep_time / steps)
        if self._fail:
            raise RuntimeError("fake task failure")
        progress_callback(1.0, "done")
        return {"result": "ok"}


class TaskConformanceTest(ABC):
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        self._tmp_path = tmp_path
        self._progress_calls = []
        self._final_calls = []

        db_path = str(tmp_path / "test_tasks.db")
        monkeypatch.setattr("config.DB_PATH", db_path)

        import database as db_module
        db_module.config.DB_PATH = db_path
        db_module.init_db()

        self._db_module = db_module

        import services.task_manager as task_manager
        import services.task_executor as task_executor

        new_active_tasks = set()
        new_cancelled_tasks = set()

        task_manager._active_tasks = new_active_tasks
        task_manager._cancelled_tasks = new_cancelled_tasks
        task_executor._active_tasks = new_active_tasks
        task_executor._cancelled_tasks = new_cancelled_tasks
        task_executor._cancelled_lock = task_manager._cancelled_lock
        task_executor._active_tasks_lock = task_manager._active_tasks_lock

        def fake_ws_send_progress(task_id: str, data: dict[str, Any]) -> None:
            self._progress_calls.append((task_id, dict(data)))

        def fake_ws_send_final(task_id: str, data: dict[str, Any]) -> None:
            self._final_calls.append((task_id, dict(data)))

        monkeypatch.setattr("services.task_manager._ws_send_progress", fake_ws_send_progress)
        monkeypatch.setattr("services.task_manager._ws_send_final", fake_ws_send_final)
        monkeypatch.setattr("services.task_executor._ws_send_progress", fake_ws_send_progress)
        monkeypatch.setattr("services.task_executor._ws_send_final", fake_ws_send_final)

        monkeypatch.setattr("config.MAX_CONCURRENT_TASKS", 2)
        monkeypatch.setattr("services.task_manager.MAX_CONCURRENT_TASKS", 2)
        monkeypatch.setattr("services.task_executor.MAX_CONCURRENT_TASKS", 2)

        old_instance = TaskExecutor._instance
        old_instance_lock = TaskExecutor._instance_lock
        TaskExecutor._instance = None
        TaskExecutor._instance_lock = threading.Lock()

        self._task_executor = get_task_executor()

        yield

        TaskExecutor._instance = old_instance
        TaskExecutor._instance_lock = old_instance_lock

    @abstractmethod
    def make_task(self, task_id: str) -> BaseTask:
        ...

    def _make_task_id(self) -> str:
        return uuid.uuid4().hex[:16]

    def _create_task_in_db(self, task_id: str) -> None:
        self._db_module.create_task(
            task_id,
            "test.wav",
            f"/tmp/{task_id}.wav",
            {},
            file_hash="",
            file_size=0,
        )

    def _submit_task(self, task: BaseTask) -> None:
        self._create_task_in_db(task.task_id)
        self._task_executor.submit(task)

    def _wait_for_task(self, task_id: str, timeout: float = 10.0) -> None:
        start = time.time()
        while time.time() - start < timeout:
            task = self._db_module.get_task(task_id)
            if task and task["status"] in ("completed", "error", "cancelled"):
                return
            time.sleep(0.05)
        raise TimeoutError(f"Task {task_id} did not finish within {timeout}s")

    def test_submit_and_complete(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)
        self._submit_task(task)
        self._wait_for_task(task_id)

        task_data = self._db_module.get_task(task_id)
        assert task_data is not None
        assert task_data["status"] == "completed"
        assert task_data["progress"] == 1.0

        statuses = []
        for _, data in self._progress_calls:
            if data.get("task_id") == task_id and "status" in data:
                statuses.append(data["status"])
        assert "processing" in statuses

        final_calls = [d for tid, d in self._final_calls if tid == task_id]
        assert len(final_calls) == 1
        assert final_calls[0]["status"] == "completed"

    def test_progress_callback_called(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)
        self._submit_task(task)
        self._wait_for_task(task_id)

        progress_values = []
        for _, data in self._progress_calls:
            if data.get("task_id") == task_id and "progress" in data:
                progress_values.append(data["progress"])

        assert len(progress_values) >= 2
        assert progress_values[0] < progress_values[-1]
        assert progress_values[-1] <= 1.0

    def test_task_failure(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)

        def failing_execute(progress_callback):
            progress_callback(0.5, "halfway")
            raise ValueError("test failure message")

        task.execute = failing_execute

        self._submit_task(task)
        self._wait_for_task(task_id)

        task_data = self._db_module.get_task(task_id)
        assert task_data is not None
        assert task_data["status"] == "error"
        assert "test failure message" in task_data["error"]

        final_calls = [d for tid, d in self._final_calls if tid == task_id]
        assert len(final_calls) == 1
        assert final_calls[0]["status"] == "error"
        assert "test failure message" in final_calls[0].get("error", "")

    def test_cancel_before_start(self):
        from services.task_manager import _cancelled_lock, _cancelled_tasks

        task_id = self._make_task_id()
        task = self.make_task(task_id)
        self._create_task_in_db(task_id)

        with _cancelled_lock:
            _cancelled_tasks.add(task_id)

        self._task_executor.submit(task)
        time.sleep(0.5)

        task_data = self._db_module.get_task(task_id)
        assert task_data is not None
        assert task_data["status"] == "pending"

        with _cancelled_lock:
            assert task_id not in _cancelled_tasks

    def test_cancel_during_execution(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)

        cancel_triggered = False

        def slow_execute(progress_callback):
            nonlocal cancel_triggered
            for i in range(20):
                progress_callback(i / 20, f"step {i}")
                time.sleep(0.05)
                if i == 5 and not cancel_triggered:
                    cancel_triggered = True
                    self._task_executor.cancel(task_id)
            return {"result": "should not reach here"}

        task.execute = slow_execute

        self._submit_task(task)
        self._wait_for_task(task_id, timeout=10.0)

        task_data = self._db_module.get_task(task_id)
        assert task_data is not None
        assert task_data["status"] == "cancelled"

        final_calls = [d for tid, d in self._final_calls if tid == task_id]
        assert len(final_calls) >= 1
        assert final_calls[-1]["status"] == "cancelled"

    def test_concurrency_limit(self):
        from services.task_manager import _active_tasks, _active_tasks_lock

        with _active_tasks_lock:
            _active_tasks.clear()

        task_ids = []
        tasks = []
        for i in range(3):
            tid = self._make_task_id()
            task_ids.append(tid)
            tasks.append(self.make_task(tid))

        for task in tasks:
            self._submit_task(task)

        time.sleep(0.3)

        rejected_task = self._db_module.get_task(task_ids[2])
        assert rejected_task is not None
        assert rejected_task["status"] == "error"
        assert "系统繁忙" in rejected_task["error"]

        for tid in task_ids[:2]:
            self._wait_for_task(tid)

    def test_active_task_count_cleanup_on_success(self):
        from services.task_manager import _active_tasks, _active_tasks_lock

        task_id = self._make_task_id()
        task = self.make_task(task_id)
        self._submit_task(task)
        self._wait_for_task(task_id)

        time.sleep(0.2)

        with _active_tasks_lock:
            assert task_id not in _active_tasks
            assert len(_active_tasks) == 0

    def test_active_task_count_cleanup_on_failure(self):
        from services.task_manager import _active_tasks, _active_tasks_lock

        task_id = self._make_task_id()
        task = self.make_task(task_id)

        def failing_execute(progress_callback):
            raise RuntimeError("cleanup test failure")

        task.execute = failing_execute

        self._submit_task(task)
        self._wait_for_task(task_id)

        time.sleep(0.2)

        with _active_tasks_lock:
            assert task_id not in _active_tasks
            assert len(_active_tasks) == 0

    def test_active_task_count_cleanup_on_cancel(self):
        from services.task_manager import _active_tasks, _active_tasks_lock

        task_id = self._make_task_id()
        task = self.make_task(task_id)

        cancel_done = False

        def slow_execute(progress_callback):
            nonlocal cancel_done
            for i in range(20):
                progress_callback(i / 20, f"step {i}")
                time.sleep(0.05)
                if i == 3 and not cancel_done:
                    cancel_done = True
                    self._task_executor.cancel(task_id)
            return {}

        task.execute = slow_execute

        self._submit_task(task)
        self._wait_for_task(task_id, timeout=10.0)

        time.sleep(0.2)

        with _active_tasks_lock:
            assert task_id not in _active_tasks
            assert len(_active_tasks) == 0

    def test_cancelled_tasks_cleanup(self):
        from services.task_manager import _cancelled_lock, _cancelled_tasks

        task_id = self._make_task_id()
        task = self.make_task(task_id)

        cancel_done = False

        def slow_execute(progress_callback):
            nonlocal cancel_done
            for i in range(10):
                progress_callback(i / 10, f"step {i}")
                time.sleep(0.05)
                if i == 2 and not cancel_done:
                    cancel_done = True
                    self._task_executor.cancel(task_id)
            return {}

        task.execute = slow_execute

        self._submit_task(task)
        self._wait_for_task(task_id, timeout=10.0)

        time.sleep(0.2)

        with _cancelled_lock:
            assert task_id not in _cancelled_tasks

    def test_ws_final_on_success(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)
        self._submit_task(task)
        self._wait_for_task(task_id)

        final_calls = [d for tid, d in self._final_calls if tid == task_id]
        assert len(final_calls) == 1
        data = final_calls[0]
        assert data["status"] == "completed"
        assert data["progress"] == 1.0
        assert "step" in data

    def test_ws_final_on_failure(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)

        def failing_execute(progress_callback):
            raise TypeError("type error test")

        task.execute = failing_execute

        self._submit_task(task)
        self._wait_for_task(task_id)

        final_calls = [d for tid, d in self._final_calls if tid == task_id]
        assert len(final_calls) == 1
        data = final_calls[0]
        assert data["status"] == "error"
        assert "type error test" in data.get("error", "")
        assert "error_type" in data

    def test_ws_final_on_cancel(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)

        cancel_done = False

        def slow_execute(progress_callback):
            nonlocal cancel_done
            for i in range(10):
                progress_callback(i / 10, f"step {i}")
                time.sleep(0.05)
                if i == 2 and not cancel_done:
                    cancel_done = True
                    self._task_executor.cancel(task_id)
            return {}

        task.execute = slow_execute

        self._submit_task(task)
        self._wait_for_task(task_id, timeout=10.0)

        final_calls = [d for tid, d in self._final_calls if tid == task_id]
        assert len(final_calls) >= 1
        data = final_calls[-1]
        assert data["status"] == "cancelled"

    def test_double_cancel(self):
        task_id = self._make_task_id()
        task = self.make_task(task_id)

        def slow_execute(progress_callback):
            for i in range(20):
                progress_callback(i / 20, f"step {i}")
                time.sleep(0.05)
            return {}

        task.execute = slow_execute

        self._submit_task(task)
        time.sleep(0.15)

        first_result = self._task_executor.cancel(task_id)
        assert first_result is True

        second_result = self._task_executor.cancel(task_id)
        assert second_result is False

        self._wait_for_task(task_id, timeout=10.0)

        final_calls = [d for tid, d in self._final_calls if tid == task_id]
        assert len(final_calls) >= 1
        assert final_calls[-1]["status"] == "cancelled"


class TestFakeTaskConformance(TaskConformanceTest):
    def make_task(self, task_id: str) -> FakeTask:
        return FakeTask(task_id, sleep_time=0.2)
