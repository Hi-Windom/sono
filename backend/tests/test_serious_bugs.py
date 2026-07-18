import sys
import os
import json
import tempfile
import time
import threading
import numpy as np
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


@pytest.fixture()
def fresh_env():
    from database import init_db

    tmpdir = tempfile.mkdtemp()
    old_upload = None
    old_output = None
    old_db = None
    try:
        import config
        old_upload = config.UPLOAD_DIR
        old_output = config.OUTPUT_DIR
        old_db = config.DB_PATH
        config.UPLOAD_DIR = tmpdir
        config.OUTPUT_DIR = tmpdir
        config.DB_PATH = os.path.join(tmpdir, "test.db")
    except Exception:
        pass

    init_db()

    import soundfile as sf
    sr = 44100
    duration = 1.0
    t = np.arange(int(sr * duration)) / sr
    y = 0.3 * np.sin(2 * np.pi * 440 * t)
    audio_path = os.path.join(tmpdir, "test.wav")
    sf.write(audio_path, y, sr)

    yield {"tmpdir": tmpdir, "audio_path": audio_path}

    try:
        import config
        if old_upload is not None:
            config.UPLOAD_DIR = old_upload
        if old_output is not None:
            config.OUTPUT_DIR = old_output
        if old_db is not None:
            config.DB_PATH = old_db
    except Exception:
        pass
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestBug1_RerepairRaceCondition:
    """Bug 1: 重新修复时的竞态条件 - submit_repair_task 未同步重置状态"""

    def test_submit_repair_does_not_reset_state_synchronously(self, fresh_env):
        from database import create_task, get_task, update_task
        from services.task_manager import submit_repair_task, get_active_tasks

        task_id = "bug1-rerepair-race"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v3.2"}, file_hash="hash1")
        update_task(task_id, status="completed", progress=1.0, step="完成",
                    repair_result={"issues_found": []})

        task_before = get_task(task_id)
        assert task_before["status"] == "completed"
        assert task_before["progress"] == 1.0

        submit_repair_task(task_id, audio_path, {"algorithm_version": "v3.2"})

        task_after = get_task(task_id)
        assert task_after["status"] != "completed", (
            "BUG: submit_repair_task 应同步重置任务状态，"
            f"但立即检查时状态仍是 {task_after['status']}"
        )

    def test_ws_would_see_old_completed_state(self, fresh_env):
        from database import create_task, get_task, update_task
        from services.task_manager import submit_repair_task

        task_id = "bug1-ws-old-state"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v3.2"}, file_hash="hash2")
        update_task(task_id, status="completed", progress=1.0, step="完成")

        submit_repair_task(task_id, audio_path, {"algorithm_version": "v3.2"})

        task = get_task(task_id)
        terminal_on_connect = {"completed", "detected", "error", "render_completed"}
        assert task["status"] not in terminal_on_connect, (
            "BUG: WebSocket 连接时会看到旧的终态，直接关闭连接，"
            f"导致前端收不到新任务的进度。当前状态: {task['status']}"
        )


class TestBug2_DuplicateActiveTask:
    """Bug 2: 同一任务重复提交会导致 _active_tasks 计数错误"""

    def test_submit_same_task_twice(self, fresh_env):
        from database import create_task, get_task, update_task
        from services.task_manager import submit_repair_task, get_active_task_count, _active_tasks, _active_tasks_lock

        task_id = "bug2-duplicate-submit"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v3.2"}, file_hash="hash3")
        update_task(task_id, status="completed", progress=1.0, step="完成")

        count_before = get_active_task_count()

        submit_repair_task(task_id, audio_path, {"algorithm_version": "v3.2"})
        submit_repair_task(task_id, audio_path, {"algorithm_version": "v3.2"})

        with _active_tasks_lock:
            count_in_set = 1 if task_id in _active_tasks else 0

        assert count_in_set <= 1, (
            "BUG: 同一任务重复提交会多次加入 _active_tasks，"
            "导致并发计数错误，最终阻塞所有新任务"
        )


class TestBug3_CancelClearsCancelledSet:
    """Bug 3: 取消未开始的任务，_cancelled_tasks 中的记录永远不清理"""

    def test_cancel_before_start_leaks(self, fresh_env):
        from database import create_task
        from services.task_manager import (
            cancel_task, _cancelled_tasks, _cancelled_lock,
            submit_repair_task, get_active_task_count,
        )

        task_id = "bug3-cancel-leak"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v3.2"}, file_hash="hash4")

        cancel_task(task_id)

        with _cancelled_lock:
            count_after_cancel = len(_cancelled_tasks)

        assert count_after_cancel > 0, "取消应该记录到 _cancelled_tasks"

        submit_repair_task(task_id, audio_path, {"algorithm_version": "v3.2"})
        time.sleep(0.05)

        with _cancelled_lock:
            count_after_submit = len(_cancelled_tasks)

        assert count_after_submit < count_after_cancel, (
            "BUG: 任务执行前检查到已取消，应该清理 _cancelled_tasks 中的记录，"
            f"但提交后数量仍为 {count_after_submit}"
        )


class TestBug4_RenderCacheNotEvicted:
    """Bug 4: LRU缓存清理不删除渲染缓存文件"""

    def test_evict_does_not_remove_rendered_files(self, fresh_env):
        from database import create_task, update_task
        from services.file_cache import evict_old_files, get_dir_size
        from services.task_manager import OUTPUT_DIR

        task_id = "bug4-render-cache"
        tmpdir = fresh_env["tmpdir"]
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v3.2"}, file_hash="hash5")
        update_task(task_id, status="completed", progress=1.0,
                    output_path=os.path.join(tmpdir, f"{task_id}_repaired.wav"))

        output_wav = os.path.join(tmpdir, f"{task_id}_repaired.wav")
        with open(output_wav, "wb") as f:
            f.write(b"x" * 10000)

        render_file = os.path.join(tmpdir, f"{task_id}_rendered_v3.2_48000_24.wav")
        with open(render_file, "wb") as f:
            f.write(b"y" * 20000)

        assert os.path.exists(render_file), "渲染缓存文件应该存在"

        import config
        old_limit = getattr(config, "SOURCE_FILE_CACHE_LIMIT", None)
        config.SOURCE_FILE_CACHE_LIMIT = 5000
        try:
            evict_old_files()
        finally:
            if old_limit is not None:
                config.SOURCE_FILE_CACHE_LIMIT = old_limit

        assert not os.path.exists(render_file), (
            "BUG: LRU清理时应该同时删除渲染缓存文件，"
            f"但 {render_file} 仍然存在"
        )


class TestBug5_UpdateTaskNoColumnValidation:
    """Bug 5: update_task 允许更新任意列（之前修复过，这里验证）"""

    def test_update_task_rejects_unknown_columns(self, fresh_env):
        from database import create_task, update_task

        task_id = "bug5-column-validation"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {}, file_hash="hash6")

        with pytest.raises(ValueError, match="不允许更新的字段"):
            update_task(task_id, id="hacked-id", status="completed")


class TestBug6_PathTraversalDownload:
    """Bug 6: 下载接口路径遍历（之前修复过，这里验证）"""

    def test_download_file_rejects_path_traversal(self, fresh_env):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        response = client.get("/api/v1/download-file/../etc/passwd")
        assert response.status_code in (400, 404, 422), (
            f"BUG: 下载接口存在路径遍历风险，返回状态码 {response.status_code}"
        )


class TestBug7_DualUploadNoDiskCheck:
    """Bug 7: 双轨上传无磁盘空间检查（之前修复过，这里验证）"""

    def test_dual_upload_disk_check_exists(self, fresh_env):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        files = {
            "vocal_file": ("vocal.wav", b"fake audio data", "audio/wav"),
            "accompaniment_file": ("accompaniment.wav", b"fake audio data", "audio/wav"),
        }
        response = client.post("/api/v1/upload-dual", files=files)
        assert response.status_code != 500, "双轨上传不应该500"


class TestBug8_CacheDeletePathTraversal:
    """Bug 8: 缓存删除接口路径遍历（之前修复过，这里验证）"""

    def test_delete_delivery_rejects_path_traversal(self, fresh_env):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        response = client.delete("/api/v1/cache/delivery-files/../../../etc/passwd")
        assert response.status_code in (400, 404, 422), (
            f"BUG: 交付文件删除接口存在路径遍历风险，返回状态码 {response.status_code}"
        )


class TestBug9_TaskStatusAfterCancel:
    """Bug 9: 取消任务后状态不明确，重新提交会怎样"""

    def test_cancel_then_rerepair(self, fresh_env):
        from database import create_task, get_task, update_task
        from services.task_manager import submit_repair_task, cancel_task, get_active_task_count

        task_id = "bug9-cancel-rerepair"
        audio_path = fresh_env["audio_path"]

        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v3.2"}, file_hash="hash7")
        update_task(task_id, status="completed", progress=1.0, step="完成")

        cancel_task(task_id)
        time.sleep(0.01)

        submit_repair_task(task_id, audio_path, {"algorithm_version": "v3.2"})
        time.sleep(0.2)

        task = get_task(task_id)
        assert task["status"] != "completed", (
            "BUG: 取消后重新提交，任务应该正常执行，而不是保持旧的completed状态"
        )


class TestBug10_WSManagerThreadSafety:
    """Bug 10: ws_manager 并发安全问题（之前修复过，这里验证）"""

    def test_ws_manager_has_lock(self, fresh_env):
        from services.ws_manager import ProgressWSManager

        mgr = ProgressWSManager()
        assert hasattr(mgr, "_lock"), "ws_manager 应该有 _lock 属性保护并发访问"


class TestBug11_SessionIDValidation:
    """Bug 11: 分块上传 session_id 无格式校验（之前修复过，这里验证）"""

    def test_upload_chunk_rejects_invalid_session(self, fresh_env):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/upload-chunk",
            data={"session_id": "../../etc/passwd", "chunk_index": "0"},
            files={"chunk": ("chunk.bin", b"data", "application/octet-stream")},
        )
        assert response.status_code == 400, (
            f"BUG: 分块上传 session_id 应该校验格式，返回状态码 {response.status_code}"
        )


class TestBug12_RepairDuplicateProgress:
    """Bug 12: 重新修复时旧的repair_result不清理，可能混淆"""

    def test_rerepair_clears_old_result(self, fresh_env):
        from database import create_task, get_task, update_task
        from services.task_manager import submit_repair_task

        task_id = "bug12-old-result"
        audio_path = fresh_env["audio_path"]

        old_result = {"issues_found": ["noise"], "duration": 100}
        create_task(task_id, "test.wav", audio_path, {"algorithm_version": "v3.2"}, file_hash="hash8")
        update_task(task_id, status="completed", progress=1.0, step="完成",
                    repair_result=old_result)

        submit_repair_task(task_id, audio_path, {"algorithm_version": "v3.2"})
        time.sleep(0.05)

        task = get_task(task_id)
        if task["status"] != "completed":
            current_result = task.get("repair_result")
            if isinstance(current_result, str) and current_result:
                parsed = json.loads(current_result)
                assert parsed != old_result, (
                    "BUG: 重新修复时应该清理旧的修复结果，避免混淆"
                )
