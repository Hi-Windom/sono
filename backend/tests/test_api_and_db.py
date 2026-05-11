import sys
import os
import json
import asyncio
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


@pytest.fixture()
def fresh_db():
    from database import init_db, get_db, create_task, get_task, update_task

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    old_path = None
    try:
        import config
        old_path = getattr(config, "DB_PATH", None)
        config.DB_PATH = db_path
    except Exception:
        pass

    init_db()
    yield {"db_path": db_path, "get_db": get_db, "create_task": create_task, "get_task": get_task, "update_task": update_task}

    if old_path is not None:
        try:
            config.DB_PATH = old_path
        except Exception:
            pass
    os.unlink(db_path)


class TestDatabaseSchema:
    def test_tasks_table_has_render_columns(self, fresh_db):
        conn = fresh_db["get_db"]()
        row = conn.execute("PRAGMA table_info(tasks)").fetchall()
        columns = {r["name"] for r in row}
        assert "render_filename" in columns, f"Missing render_filename column. Existing: {columns}"
        assert "render_result" in columns, f"Missing render_result column. Existing: {columns}"

    def test_tasks_table_has_all_required_columns(self, fresh_db):
        required = {
            "id", "status", "progress", "step",
            "original_filename", "original_path", "file_hash", "file_size",
            "output_path", "params",
            "detection_result", "repaired_detection_result", "repair_result",
            "error", "created_at", "updated_at",
            "render_filename", "render_result",
        }
        conn = fresh_db["get_db"]()
        row = conn.execute("PRAGMA table_info(tasks)").fetchall()
        actual = {r["name"] for r in row}
        missing = required - actual
        assert not missing, f"Missing columns: {missing}"

    def test_init_db_idempotent(self):
        from database import init_db

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            import config
            old = getattr(config, "DB_PATH", None)
            config.DB_PATH = path
            init_db()
            init_db()
            init_db()
        finally:
            if old is not None:
                config.DB_PATH = old
            os.unlink(path)

    def test_update_task_writes_render_fields(self, fresh_db):
        task_id = f"test-render-cols-{os.getpid()}"
        fresh_db["create_task"](task_id, "test.wav", "/tmp/test.wav", {}, "abc123")
        fresh_db["update_task"](task_id,
            status="render_completed",
            render_filename="001_rendered_v2.4a_48000_24.wav",
            render_result=json.dumps({"output_sample_rate": 48000, "output_bit_depth": 24}),
        )
        task = fresh_db["get_task"](task_id)
        assert task is not None
        assert task["status"] == "render_completed"
        assert task["render_filename"] == "001_rendered_v2.4a_48000_24.wav"
        result = json.loads(task["render_result"]) if isinstance(task["render_result"], str) else task["render_result"]
        assert result["output_sample_rate"] == 48000


class TestRenderCacheAPI:
    @pytest.fixture()
    def rendered_task(self, fresh_db):
        tid = f"test-rcache-{os.getpid()}-{id(self)}"
        fresh_db["create_task"](tid, "test.mp3", "/tmp/uploads/test.mp3",
                               {"algorithm_version": "v2.4a"}, "hash123")
        output_dir = Path(f"/tmp/sono_test_output_{tid}")
        output_dir.mkdir(parents=True, exist_ok=True)
        fresh_db["update_task"](tid, output_path=str(output_dir / f"{tid}_repaired.wav"))
        return {"task_id": tid, "output_dir": output_dir}

    def test_render_cache_empty_for_new_task(self, rendered_task):
        from api.routes import get_render_cache
        caches = asyncio.run(get_render_cache(rendered_task["task_id"]))
        assert caches == {"caches": []}

    def test_render_cache_lists_rendered_files(self, rendered_task):
        from config import OUTPUT_DIR
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        fname = f"{rendered_task['task_id']}_rendered_v2.4a_48000_24.wav"
        (Path(OUTPUT_DIR) / fname).write_bytes(b"RIFF" + b"\x00" * 100)

        from api.routes import get_render_cache
        caches = asyncio.run(get_render_cache(rendered_task["task_id"]))
        assert len(caches["caches"]) >= 1
        hit = next((c for c in caches["caches"] if c["filename"] == fname), None)
        assert hit is not None
        assert hit["sample_rate"] == 48000
        assert hit["bit_depth"] == 24

    def test_render_cache_includes_algorithm_version(self, rendered_task):
        from config import OUTPUT_DIR
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        (Path(OUTPUT_DIR) / f"{rendered_task['task_id']}_rendered_v2.4a_44100_16.wav").write_bytes(b"RIFF" + b"\x00" * 50)

        from api.routes import get_render_cache
        caches = asyncio.run(get_render_cache(rendered_task["task_id"]))
        v24a_hits = [c for c in caches["caches"] if c.get("algorithm_version") == "v2.4a"]
        assert len(v24a_hits) >= 1


class TestCacheLookupAPI:
    @pytest.fixture()
    def repair_task_with_output(self, fresh_db):
        tid = f"test-clookup-{os.getpid()}-{id(self)}"
        out_dir = Path(f"/tmp/sono_test_lookup_{tid}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{tid}_repaired.wav"
        out_file.write_bytes(b"RIFF" + b"\x00" * 12000)

        params = {"de_clipping": 0.5, "noise_reduction": 0.3, "algorithm_version": "v2.4a"}
        fresh_db["create_task"](tid, "song.mp3", str(out_file), params, "filehash_abc")
        fresh_db["update_task"](tid, status="completed", output_path=str(out_file))
        return {"task_id": tid, "out_dir": out_dir}

    def test_cache_lookup_matches_same_params(self, repair_task_with_output):
        from api.routes import lookup_repair_cache
        req = type("Req", (), {"file_hash": "filehash_abc",
                                     "params": {"de_clipping": 0.5, "noise_reduction": 0.3, "algorithm_version": "v2.4a"}})()
        result = asyncio.run(lookup_repair_cache(req))
        assert result["found"] is True
        assert result["task_id"] == repair_task_with_output["task_id"]

    def test_cache_lookup_no_match_different_params(self, repair_task_with_output):
        from api.routes import lookup_repair_cache
        req = type("Req", (), {"file_hash": "filehash_abc",
                                     "params": {"de_clipping": 0.9, "noise_reduction": 0.8, "algorithm_version": "v2.4a"}})()
        result = asyncio.run(lookup_repair_cache(req))
        assert result["found"] is False

    def test_cache_lookup_no_match_different_algo(self, repair_task_with_output):
        from api.routes import lookup_repair_cache
        req = type("Req", (), {"file_hash": "filehash_abc",
                                     "params": {"de_clipping": 0.5, "noise_reduction": 0.3, "algorithm_version": "v2.3"}})()
        result = asyncio.run(lookup_repair_cache(req))
        assert result["found"] is False

    def test_cache_lookup_ignores_deleted_output(self, repair_task_with_output):
        out_file = Path(repair_task_with_output["out_dir"]) / f"{repair_task_with_output['task_id']}_repaired.wav"
        if out_file.exists():
            out_file.unlink()

        from api.routes import lookup_repair_cache
        req = type("Req", (), {"file_hash": "filehash_abc",
                                     "params": {"de_clipping": 0.5, "noise_reduction": 0.3, "algorithm_version": "v2.4a"}})()
        result = asyncio.run(lookup_repair_cache(req))
        assert result["found"] is False


class TestRenderEndpoint:
    @pytest.fixture()
    def client_and_task(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        tid = f"test-rendep-{os.getpid()}-{id(self)}"
        out_dir = Path(f"/tmp/sono_test_rendep_{tid}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{tid}_repaired.wav"
        out_file.write_bytes(b"RIFF" + b"\x00" * 200)

        fresh_db["create_task"](tid, "audio.wav", str(out_file),
                               {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed", output_path=str(out_file))
        app = create_app()
        client = TestClient(app)
        return {"client": client, "task_id": tid, "out_dir": out_dir}

    def test_render_nonexistent_task_returns_404(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app
        app = create_app()
        client = TestClient(app)
        res = client.post("/api/v1/render", json={"task_id": "no-such-task-xyz", "sample_rate": 48000, "bit_depth": 24})
        assert res.status_code == 404

    def test_render_missing_output_returns_400(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app
        app = create_app()
        client = TestClient(app)
        tid = f"test-no-output-{os.getpid()}"
        fresh_db["create_task"](tid, "x.wav", "/nonexistent/path.wav", {})
        res = client.post("/api/v1/render", json={"task_id": tid, "sample_rate": 48000, "bit_depth": 24})
        assert res.status_code == 400

    def test_render_accepts_valid_request(self, client_and_task):
        res = client_and_task["client"].post(
            "/api/v1/render",
            json={"task_id": client_and_task["task_id"], "sample_rate": 48000, "bit_depth": 24},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rendering"


class TestWebSocketEndpoint:
    @pytest.fixture()
    def ws_client(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app
        return TestClient(create_app())

    def test_ws_correct_path_accepted(self, ws_client):
        with ws_client.websocket_connect("/api/v1/ws/test-ws-valid") as ws:
            data = ws.receive_json()
            assert data["error"] == "任务不存在"

    def test_ws_wrong_path_returns_error(self, ws_client):
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with ws_client.websocket_connect("/api/v1/ws/progress/test-ws-wrong") as ws:
                ws.receive_json()

    def test_ws_sends_initial_status_for_existing_task(self, ws_client, fresh_db):
        tid = f"test-ws-init-{os.getpid()}"
        fresh_db["create_task"](tid, "x.wav", "/tmp/x.wav",
                                {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed", progress=100, step="done")
        with ws_client.websocket_connect(f"/api/v1/ws/{tid}") as ws:
            data = ws.receive_json()
            assert data["status"] == "completed"
            assert data["progress"] == 100
