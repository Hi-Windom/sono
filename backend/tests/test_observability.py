import sys
import os
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"

from services.observability import (
    TaskTracer,
    TaskTrace,
    TaskStateChange,
    SystemMetrics,
    get_task_tracer,
    get_system_metrics,
    _format_uptime,
)


@pytest.fixture
def fresh_tracer():
    TaskTracer._instance = None
    tracer = TaskTracer()
    tracer._traces.clear()
    tracer._history.clear()
    return tracer


@pytest.fixture
def fresh_metrics():
    SystemMetrics._instance = None
    metrics = SystemMetrics()
    metrics.reset()
    return metrics


@pytest.fixture()
def api_client():
    import tempfile
    from fastapi.testclient import TestClient
    from app import create_app

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    old_path = None
    try:
        import config
        old_path = getattr(config, "DB_PATH", None)
        config.DB_PATH = db_path
    except Exception:
        pass

    from database import init_db
    init_db()

    TaskTracer._instance = None
    SystemMetrics._instance = None

    app = create_app()
    client = TestClient(app)

    yield client

    if old_path is not None:
        try:
            import config
            config.DB_PATH = old_path
        except Exception:
            pass
    os.unlink(db_path)


class TestTaskStateChange:
    def test_state_change_creation(self):
        sc = TaskStateChange(
            timestamp=1000.0,
            from_status="pending",
            to_status="processing",
            step="开始执行",
            note="test note",
        )
        assert sc.timestamp == 1000.0
        assert sc.from_status == "pending"
        assert sc.to_status == "processing"
        assert sc.step == "开始执行"
        assert sc.note == "test note"

    def test_state_change_defaults(self):
        sc = TaskStateChange(timestamp=1000.0, from_status="a", to_status="b")
        assert sc.step == ""
        assert sc.note == ""


class TestTaskTrace:
    def test_task_trace_creation(self):
        trace = TaskTrace(task_id="test-123", task_type="repair", created_at=1000.0)
        assert trace.task_id == "test-123"
        assert trace.task_type == "repair"
        assert trace.created_at == 1000.0
        assert trace.state_changes == []
        assert trace.start_time is None
        assert trace.end_time is None
        assert trace.total_duration is None
        assert trace.final_status is None
        assert trace.error is None

    def test_record_state_change(self):
        trace = TaskTrace(task_id="test-123", task_type="repair", created_at=1000.0)
        trace.record_state_change("pending", "processing", step="开始修复")
        assert len(trace.state_changes) == 1
        assert trace.state_changes[0].from_status == "pending"
        assert trace.state_changes[0].to_status == "processing"
        assert trace.state_changes[0].step == "开始修复"

    def test_get_phase_durations(self):
        trace = TaskTrace(task_id="test-123", task_type="repair", created_at=1000.0)
        trace.state_changes = [
            TaskStateChange(timestamp=0.0, from_status="", to_status="pending"),
            TaskStateChange(timestamp=1.0, from_status="pending", to_status="processing"),
            TaskStateChange(timestamp=5.0, from_status="processing", to_status="completed"),
        ]
        durations = trace.get_phase_durations()
        assert durations["pending"] == 1.0
        assert durations["processing"] == 4.0

    def test_to_dict(self):
        trace = TaskTrace(task_id="test-123", task_type="repair", created_at=1000.0)
        trace.start_time = 1001.0
        trace.end_time = 1005.0
        trace.total_duration = 4.0
        trace.final_status = "completed"
        trace.record_state_change("pending", "processing")
        d = trace.to_dict()
        assert d["task_id"] == "test-123"
        assert d["task_type"] == "repair"
        assert d["created_at"] == 1000.0
        assert d["start_time"] == 1001.0
        assert d["end_time"] == 1005.0
        assert d["total_duration"] == 4.0
        assert d["final_status"] == "completed"
        assert len(d["state_changes"]) == 1
        assert "phase_durations" in d


class TestTaskTracer:
    def test_singleton(self, fresh_tracer):
        t1 = TaskTracer()
        t2 = TaskTracer()
        assert t1 is t2

    def test_create_trace(self, fresh_tracer):
        trace = fresh_tracer.create_trace("task-1", "repair")
        assert trace.task_id == "task-1"
        assert trace.task_type == "repair"
        assert fresh_tracer.get_trace("task-1") is trace

    def test_get_trace_not_found(self, fresh_tracer):
        assert fresh_tracer.get_trace("nonexistent") is None

    def test_record_state_change(self, fresh_tracer):
        fresh_tracer.create_trace("task-1", "repair")
        fresh_tracer.record_state_change("task-1", "pending", "processing", step="开始")
        trace = fresh_tracer.get_trace("task-1")
        assert len(trace.state_changes) == 1
        assert trace.state_changes[0].to_status == "processing"

    def test_record_state_change_sets_start_time(self, fresh_tracer):
        fresh_tracer.create_trace("task-1", "repair")
        fresh_tracer.record_state_change("task-1", "pending", "processing")
        trace = fresh_tracer.get_trace("task-1")
        assert trace.start_time is not None

    def test_record_task_end_success(self, fresh_tracer):
        fresh_tracer.create_trace("task-1", "repair")
        fresh_tracer.record_state_change("task-1", "pending", "processing")
        time.sleep(0.01)
        duration = fresh_tracer.record_task_end("task-1", "completed")
        assert duration is not None
        assert duration > 0
        trace = fresh_tracer.get_trace("task-1")
        assert trace is None
        history = fresh_tracer.get_task_history()
        assert len(history) == 1
        assert history[0].final_status == "completed"

    def test_record_task_end_failure(self, fresh_tracer):
        fresh_tracer.create_trace("task-1", "repair")
        fresh_tracer.record_task_end("task-1", "error", error="something went wrong")
        history = fresh_tracer.get_task_history()
        assert len(history) == 1
        assert history[0].final_status == "error"
        assert history[0].error == "something went wrong"

    def test_slow_task_warning(self, fresh_tracer, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        fresh_tracer.set_slow_task_threshold(0.001)
        fresh_tracer.create_trace("task-slow", "repair")
        fresh_tracer.record_state_change("task-slow", "pending", "processing")
        time.sleep(0.01)
        fresh_tracer.record_task_end("task-slow", "completed")
        assert any("慢任务告警" in record.message for record in caplog.records)

    def test_get_task_history_by_type(self, fresh_tracer):
        for i in range(5):
            fresh_tracer.create_trace(f"task-r-{i}", "repair")
            fresh_tracer.record_task_end(f"task-r-{i}", "completed")
        for i in range(3):
            fresh_tracer.create_trace(f"task-d-{i}", "detect")
            fresh_tracer.record_task_end(f"task-d-{i}", "completed")

        repair_history = fresh_tracer.get_task_history(task_type="repair")
        detect_history = fresh_tracer.get_task_history(task_type="detect")
        all_history = fresh_tracer.get_task_history()

        assert len(repair_history) == 5
        assert len(detect_history) == 3
        assert len(all_history) == 8

    def test_get_task_history_limit(self, fresh_tracer):
        for i in range(20):
            fresh_tracer.create_trace(f"task-{i}", "repair")
            fresh_tracer.record_task_end(f"task-{i}", "completed")
        history = fresh_tracer.get_task_history(limit=5)
        assert len(history) == 5

    def test_get_active_traces(self, fresh_tracer):
        fresh_tracer.create_trace("task-1", "repair")
        fresh_tracer.create_trace("task-2", "detect")
        fresh_tracer.record_task_end("task-1", "completed")
        active = fresh_tracer.get_active_traces()
        assert len(active) == 1
        assert active[0].task_id == "task-2"

    def test_clear_history(self, fresh_tracer):
        fresh_tracer.create_trace("task-1", "repair")
        fresh_tracer.record_task_end("task-1", "completed")
        fresh_tracer.create_trace("task-2", "detect")
        assert len(fresh_tracer.get_active_traces()) == 1
        assert len(fresh_tracer.get_task_history()) == 1
        fresh_tracer.clear_history()
        assert len(fresh_tracer.get_active_traces()) == 0
        assert len(fresh_tracer.get_task_history()) == 0


class TestSystemMetrics:
    def test_singleton(self, fresh_metrics):
        m1 = SystemMetrics()
        m2 = SystemMetrics()
        assert m1 is m2

    def test_record_task_start(self, fresh_metrics):
        fresh_metrics.record_task_start("repair")
        stats = fresh_metrics.get_task_stats()
        assert stats["active_tasks"] == 1
        assert stats["total_tasks"] == 1
        assert stats["by_type"]["repair"]["total"] == 1

    def test_record_task_completion(self, fresh_metrics):
        fresh_metrics.record_task_start("repair")
        fresh_metrics.record_task_completion("repair", 5.0)
        stats = fresh_metrics.get_task_stats()
        assert stats["active_tasks"] == 0
        assert stats["completed_tasks"] == 1
        assert stats["by_type"]["repair"]["completed"] == 1
        assert stats["by_type"]["repair"]["avg_duration"] == 5.0

    def test_record_task_failure(self, fresh_metrics):
        fresh_metrics.record_task_start("repair")
        fresh_metrics.record_task_failure("repair")
        stats = fresh_metrics.get_task_stats()
        assert stats["active_tasks"] == 0
        assert stats["failed_tasks"] == 1
        assert stats["by_type"]["repair"]["failed"] == 1

    def test_record_task_cancellation(self, fresh_metrics):
        fresh_metrics.record_task_start("repair")
        fresh_metrics.record_task_cancellation("repair")
        stats = fresh_metrics.get_task_stats()
        assert stats["active_tasks"] == 0
        assert stats["cancelled_tasks"] == 1
        assert stats["by_type"]["repair"]["cancelled"] == 1

    def test_success_rate(self, fresh_metrics):
        for _ in range(8):
            fresh_metrics.record_task_start("repair")
            fresh_metrics.record_task_completion("repair", 1.0)
        for _ in range(2):
            fresh_metrics.record_task_start("repair")
            fresh_metrics.record_task_failure("repair")
        stats = fresh_metrics.get_task_stats()
        assert stats["overall_success_rate"] == 80.0

    def test_p95_duration(self, fresh_metrics):
        durations = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
                     11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0]
        for d in durations:
            fresh_metrics.record_task_start("repair")
            fresh_metrics.record_task_completion("repair", d)
        stats = fresh_metrics.get_task_stats()
        p95 = stats["by_type"]["repair"]["p95_duration"]
        assert p95 > 0

    def test_get_cache_stats(self, fresh_metrics):
        cache_stats = fresh_metrics.get_cache_stats()
        assert "total_hits" in cache_stats
        assert "total_misses" in cache_stats
        assert "overall_hit_rate" in cache_stats
        assert "layers" in cache_stats

    def test_get_ws_stats(self, fresh_metrics):
        ws_stats = fresh_metrics.get_ws_stats()
        assert "active_connections" in ws_stats
        assert "active_tasks_with_connections" in ws_stats
        assert "total_messages_sent" in ws_stats

    def test_record_ws_message(self, fresh_metrics):
        for _ in range(10):
            fresh_metrics.record_ws_message()
        ws_stats = fresh_metrics.get_ws_stats()
        assert ws_stats["total_messages_sent"] == 10

    def test_get_summary(self, fresh_metrics):
        fresh_metrics.record_task_start("repair")
        fresh_metrics.record_task_completion("repair", 2.0)
        summary = fresh_metrics.get_summary()
        assert "uptime_seconds" in summary
        assert "uptime_formatted" in summary
        assert "tasks" in summary
        assert "cache" in summary
        assert "websocket" in summary
        assert "timestamp" in summary
        assert summary["tasks"]["total_tasks"] == 1

    def test_reset(self, fresh_metrics):
        fresh_metrics.record_task_start("repair")
        fresh_metrics.record_task_completion("repair", 1.0)
        fresh_metrics.record_ws_message()
        fresh_metrics.reset()
        stats = fresh_metrics.get_task_stats()
        assert stats["total_tasks"] == 0
        assert stats["active_tasks"] == 0


class TestHelperFunctions:
    def test_format_uptime_seconds(self):
        assert _format_uptime(30) == "30秒"

    def test_format_uptime_minutes(self):
        assert _format_uptime(90) == "1分钟30秒"

    def test_format_uptime_hours(self):
        result = _format_uptime(3661)
        assert "1小时" in result
        assert "1分钟" in result
        assert "1秒" in result

    def test_format_uptime_days(self):
        result = _format_uptime(90061)
        assert "1天" in result

    def test_get_task_tracer_singleton(self):
        TaskTracer._instance = None
        t1 = get_task_tracer()
        t2 = get_task_tracer()
        assert t1 is t2

    def test_get_system_metrics_singleton(self):
        SystemMetrics._instance = None
        m1 = get_system_metrics()
        m2 = get_system_metrics()
        assert m1 is m2


class TestMetricsApiEndpoints:
    def test_metrics_summary_endpoint(self, api_client):
        res = api_client.get("/api/v1/metrics/summary")
        assert res.status_code == 200
        data = res.json()
        assert "uptime_seconds" in data
        assert "tasks" in data
        assert "cache" in data
        assert "websocket" in data

    def test_metrics_tasks_endpoint(self, api_client):
        res = api_client.get("/api/v1/metrics/tasks")
        assert res.status_code == 200
        data = res.json()
        assert "stats" in data
        assert "active" in data
        assert "history" in data

    def test_metrics_tasks_with_type_filter(self, api_client):
        res = api_client.get("/api/v1/metrics/tasks?task_type=repair&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "stats" in data

    def test_metrics_cache_endpoint(self, api_client):
        res = api_client.get("/api/v1/metrics/cache")
        assert res.status_code == 200
        data = res.json()
        assert "total_hits" in data
        assert "total_misses" in data
        assert "overall_hit_rate" in data
        assert "layers" in data

    def test_metrics_websocket_endpoint(self, api_client):
        res = api_client.get("/api/v1/metrics/websocket")
        assert res.status_code == 200
        data = res.json()
        assert "active_connections" in data
        assert "total_messages_sent" in data

    def test_metrics_reset_endpoint(self, api_client):
        import config as _config
        original = _config.ADMIN_TOKEN
        try:
            _config.ADMIN_TOKEN = "test-admin-token-123"
            res = api_client.post("/api/v1/metrics/reset", headers={"X-Admin-Token": "test-admin-token-123"})
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
        finally:
            _config.ADMIN_TOKEN = original
