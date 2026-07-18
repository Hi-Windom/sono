from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

SLOW_TASK_THRESHOLD = 300.0
MAX_HISTORY_PER_TYPE = 1000
MAX_TASK_TRACE_HISTORY = 10000


@dataclass
class TaskStateChange:
    timestamp: float
    from_status: str
    to_status: str
    step: str = ""
    note: str = ""


@dataclass
class TaskTrace:
    task_id: str
    task_type: str
    created_at: float
    state_changes: list[TaskStateChange] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    total_duration: Optional[float] = None
    final_status: Optional[str] = None
    error: Optional[str] = None

    def record_state_change(self, from_status: str, to_status: str, step: str = "", note: str = "") -> None:
        self.state_changes.append(TaskStateChange(
            timestamp=time.time(),
            from_status=from_status,
            to_status=to_status,
            step=step,
            note=note,
        ))

    def get_phase_durations(self) -> dict[str, float]:
        durations: dict[str, float] = {}
        for i in range(len(self.state_changes) - 1):
            phase = self.state_changes[i].to_status
            start = self.state_changes[i].timestamp
            end = self.state_changes[i + 1].timestamp
            durations[phase] = end - start
        return durations

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "created_at": self.created_at,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration": self.total_duration,
            "final_status": self.final_status,
            "error": self.error,
            "state_changes": [
                {
                    "timestamp": sc.timestamp,
                    "from_status": sc.from_status,
                    "to_status": sc.to_status,
                    "step": sc.step,
                    "note": sc.note,
                }
                for sc in self.state_changes
            ],
            "phase_durations": self.get_phase_durations(),
        }


class TaskTracer:
    _instance: Optional["TaskTracer"] = None
    _instance_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "TaskTracer":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._traces: dict[str, TaskTrace] = {}
        self._history: deque[TaskTrace] = deque(maxlen=MAX_TASK_TRACE_HISTORY)
        self._lock = threading.Lock()
        self._slow_task_threshold = SLOW_TASK_THRESHOLD
        self._trace_timeout = 3600  # 1小时超时，防止极端异常泄漏
        self._initialized = True

    def set_slow_task_threshold(self, threshold: float) -> None:
        self._slow_task_threshold = threshold

    def create_trace(self, task_id: str, task_type: str) -> TaskTrace:
        trace = TaskTrace(
            task_id=task_id,
            task_type=task_type,
            created_at=time.time(),
        )
        with self._lock:
            self._traces[task_id] = trace
        return trace

    def get_trace(self, task_id: str) -> Optional[TaskTrace]:
        with self._lock:
            return self._traces.get(task_id)

    def record_state_change(
        self,
        task_id: str,
        from_status: str,
        to_status: str,
        step: str = "",
        note: str = "",
    ) -> None:
        with self._lock:
            trace = self._traces.get(task_id)
        if trace is None:
            logger.warning(f"[TaskTracer] 未找到任务 trace: {task_id}")
            return
        trace.record_state_change(from_status, to_status, step, note)
        if trace.start_time is None and to_status in ("processing", "repairing", "detecting", "rendering"):
            trace.start_time = time.time()

    def record_task_start(self, task_id: str, task_type: str) -> None:
        with self._lock:
            trace = self._traces.get(task_id)
            if trace is None:
                trace = TaskTrace(
                    task_id=task_id,
                    task_type=task_type,
                    created_at=time.time(),
                )
                self._traces[task_id] = trace
        trace.start_time = time.time()

    def record_task_end(
        self,
        task_id: str,
        final_status: str,
        error: Optional[str] = None,
    ) -> Optional[float]:
        with self._lock:
            trace = self._traces.get(task_id)
        if trace is None:
            logger.warning(f"[TaskTracer] 任务结束时未找到 trace: {task_id}")
            return None

        trace.end_time = time.time()
        if trace.start_time is not None:
            trace.total_duration = trace.end_time - trace.start_time
        trace.final_status = final_status
        trace.error = error

        if trace.total_duration is not None and trace.total_duration > self._slow_task_threshold:
            logger.warning(
                f"[TaskTracer] 慢任务告警 task_id={task_id} type={trace.task_type} "
                f"duration={trace.total_duration:.2f}s threshold={self._slow_task_threshold}s"
            )

        with self._lock:
            self._history.append(trace)
            self._traces.pop(task_id, None)

        return trace.total_duration

    def get_task_history(self, task_type: Optional[str] = None, limit: int = 100) -> list[TaskTrace]:
        with self._lock:
            history = list(self._history)
        if task_type:
            history = [t for t in history if t.task_type == task_type]
        return history[-limit:]

    def get_active_traces(self) -> list[TaskTrace]:
        with self._lock:
            self._cleanup_expired_traces_locked()
            return list(self._traces.values())

    def _cleanup_expired_traces_locked(self) -> None:
        """清理超时的活跃 trace（必须在持有 _lock 的情况下调用）。"""
        now = time.time()
        expired_ids = [
            tid for tid, trace in self._traces.items()
            if now - trace.created_at > self._trace_timeout
        ]
        for tid in expired_ids:
            trace = self._traces.pop(tid, None)
            if trace is not None:
                trace.end_time = now
                trace.final_status = "expired"
                trace.error = "任务 trace 超时自动清理"
                self._history.append(trace)
                logger.warning(f"[TaskTracer] 清理超时 trace: task_id={tid} age={now - trace.created_at:.0f}s")

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
            self._traces.clear()


class _TaskTypeStats:
    def __init__(self) -> None:
        self.total = 0
        self.completed = 0
        self.failed = 0
        self.cancelled = 0
        self.durations: deque[float] = deque(maxlen=MAX_HISTORY_PER_TYPE)
        self._lock = threading.Lock()

    def record_start(self) -> None:
        with self._lock:
            self.total += 1

    def record_completion(self, duration: float) -> None:
        with self._lock:
            self.completed += 1
            self.durations.append(duration)

    def record_failure(self) -> None:
        with self._lock:
            self.failed += 1

    def record_cancellation(self) -> None:
        with self._lock:
            self.cancelled += 1

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            durations = list(self.durations)
            total = self.total
            completed = self.completed
            failed = self.failed
            cancelled = self.cancelled

        if durations:
            durations_sorted = sorted(durations)
            avg_duration = sum(durations) / len(durations)
            p95_idx = max(0, int(len(durations_sorted) * 0.95) - 1)
            p95_duration = durations_sorted[p95_idx]
        else:
            avg_duration = 0.0
            p95_duration = 0.0

        success_rate = (completed / total * 100) if total > 0 else 0.0

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "success_rate": round(success_rate, 2),
            "avg_duration": round(avg_duration, 3),
            "p95_duration": round(p95_duration, 3),
            "sample_count": len(durations),
        }


class SystemMetrics:
    _instance: Optional["SystemMetrics"] = None
    _instance_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "SystemMetrics":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._task_stats: dict[str, _TaskTypeStats] = defaultdict(_TaskTypeStats)
        self._total_tasks = 0
        self._active_tasks = 0
        self._ws_connections = 0
        self._ws_messages = 0
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._initialized = True

    def record_task_start(self, task_type: str) -> None:
        with self._lock:
            self._total_tasks += 1
            self._active_tasks += 1
            stats = self._task_stats[task_type]
        stats.record_start()

    def record_task_completion(self, task_type: str, duration: float) -> None:
        with self._lock:
            self._active_tasks = max(0, self._active_tasks - 1)
            stats = self._task_stats[task_type]
        stats.record_completion(duration)

    def record_task_failure(self, task_type: str) -> None:
        with self._lock:
            self._active_tasks = max(0, self._active_tasks - 1)
            stats = self._task_stats[task_type]
        stats.record_failure()

    def record_task_cancellation(self, task_type: str) -> None:
        with self._lock:
            self._active_tasks = max(0, self._active_tasks - 1)
            stats = self._task_stats[task_type]
        stats.record_cancellation()

    def record_ws_connect(self) -> None:
        with self._lock:
            self._ws_connections += 1

    def record_ws_disconnect(self) -> None:
        with self._lock:
            self._ws_connections = max(0, self._ws_connections - 1)

    def record_ws_message(self) -> None:
        with self._lock:
            self._ws_messages += 1

    def get_task_stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._total_tasks
            active = self._active_tasks

        task_types: dict[str, Any] = {}
        all_completed = 0
        all_failed = 0
        all_cancelled = 0

        for task_type, stats in self._task_stats.items():
            s = stats.get_stats()
            task_types[task_type] = s
            all_completed += s["completed"]
            all_failed += s["failed"]
            all_cancelled += s["cancelled"]

        overall_success_rate = (all_completed / total * 100) if total > 0 else 0.0

        return {
            "active_tasks": active,
            "total_tasks": total,
            "completed_tasks": all_completed,
            "failed_tasks": all_failed,
            "cancelled_tasks": all_cancelled,
            "overall_success_rate": round(overall_success_rate, 2),
            "by_type": task_types,
        }

    def get_cache_stats(self) -> dict[str, Any]:
        try:
            from services.cache_manager import CacheManager
            cache_manager = CacheManager()
            layer_stats = cache_manager.get_stats()

            total_hits = 0
            total_misses = 0
            layers = {}

            for name, stats in layer_stats.items():
                layers[name] = {
                    "hits": stats.get("hits", 0),
                    "misses": stats.get("misses", 0),
                    "hit_rate": round(stats.get("hit_rate", 0.0), 4),
                    "file_count": stats.get("file_count", 0),
                    "total_size_mb": round(stats.get("total_size_mb", 0.0), 2),
                }
                total_hits += stats.get("hits", 0)
                total_misses += stats.get("misses", 0)

            total_requests = total_hits + total_misses
            overall_hit_rate = (total_hits / total_requests) if total_requests > 0 else 0.0

            return {
                "total_hits": total_hits,
                "total_misses": total_misses,
                "total_requests": total_requests,
                "overall_hit_rate": round(overall_hit_rate, 4),
                "layers": layers,
            }
        except Exception as e:
            logger.error(f"[SystemMetrics] 获取缓存统计失败: {e}")
            return {
                "total_hits": 0,
                "total_misses": 0,
                "total_requests": 0,
                "overall_hit_rate": 0.0,
                "layers": {},
                "error": str(e),
            }

    def get_ws_stats(self) -> dict[str, Any]:
        try:
            from services.ws_manager import ws_manager
            active_connections = sum(len(conns) for conns in ws_manager._connections.values())
            active_tasks = len(ws_manager._connections)
        except Exception:
            active_connections = 0
            active_tasks = 0

        with self._lock:
            total_messages = self._ws_messages

        return {
            "active_connections": active_connections,
            "active_tasks_with_connections": active_tasks,
            "total_messages_sent": total_messages,
        }

    def get_summary(self) -> dict[str, Any]:
        uptime = time.time() - self._start_time

        return {
            "uptime_seconds": round(uptime, 2),
            "uptime_formatted": _format_uptime(uptime),
            "tasks": self.get_task_stats(),
            "cache": self.get_cache_stats(),
            "websocket": self.get_ws_stats(),
            "timestamp": time.time(),
        }

    def reset(self) -> None:
        with self._lock:
            self._task_stats.clear()
            self._total_tasks = 0
            self._active_tasks = 0
            self._ws_connections = 0
            self._ws_messages = 0
            self._start_time = time.time()


def _format_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    parts.append(f"{secs}秒")

    return "".join(parts)


_task_tracer_instance: Optional[TaskTracer] = None
_task_tracer_lock = threading.Lock()

_system_metrics_instance: Optional[SystemMetrics] = None
_system_metrics_lock = threading.Lock()


def get_task_tracer() -> TaskTracer:
    global _task_tracer_instance
    if _task_tracer_instance is None:
        with _task_tracer_lock:
            if _task_tracer_instance is None:
                _task_tracer_instance = TaskTracer()
    return _task_tracer_instance


def get_system_metrics() -> SystemMetrics:
    global _system_metrics_instance
    if _system_metrics_instance is None:
        with _system_metrics_lock:
            if _system_metrics_instance is None:
                _system_metrics_instance = SystemMetrics()
    return _system_metrics_instance
