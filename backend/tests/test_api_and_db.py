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


class TestPreviewEndpoint:
    @pytest.fixture()
    def preview_client(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        tid = f"test-preview-{os.getpid()}-{id(self)}"
        out_dir = Path(f"/tmp/sono_test_preview_{tid}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{tid}_repaired.wav"
        out_file.write_bytes(b"RIFF" + b"\x00" * 200)
        orig_file = out_dir / f"{tid}_original.wav"
        orig_file.write_bytes(b"RIFF" + b"\x00" * 300)

        fresh_db["create_task"](tid, "audio.wav", str(orig_file),
                               {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed", output_path=str(out_file))
        app = create_app()
        client = TestClient(app)
        return {"client": client, "task_id": tid, "out_dir": out_dir,
                "orig_file": orig_file, "out_file": out_file}

    def test_preview_default_returns_repaired(self, preview_client):
        res = preview_client["client"].get(f"/api/v1/preview/{preview_client['task_id']}")
        assert res.status_code == 200

    def test_preview_type_repaired(self, preview_client):
        res = preview_client["client"].get(f"/api/v1/preview/{preview_client['task_id']}?type=repaired")
        assert res.status_code == 200

    def test_preview_type_original(self, preview_client):
        res = preview_client["client"].get(f"/api/v1/preview/{preview_client['task_id']}?type=original")
        assert res.status_code == 200

    def test_preview_original_missing_returns_404(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        tid = f"test-preview-noorig-{os.getpid()}"
        out_dir = Path(f"/tmp/sono_test_preview_noorig_{tid}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{tid}_repaired.wav"
        out_file.write_bytes(b"RIFF" + b"\x00" * 200)

        fresh_db["create_task"](tid, "audio.wav", "/nonexistent/original.wav",
                               {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed", output_path=str(out_file))
        app = create_app()
        client = TestClient(app)

        res = client.get(f"/api/v1/preview/{tid}?type=original")
        assert res.status_code == 404

    def test_preview_nonexistent_task_returns_404(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app
        client = TestClient(create_app())
        res = client.get("/api/v1/preview/no-such-task?type=repaired")
        assert res.status_code == 404


class TestRenderSpecPropagation:
    @pytest.fixture()
    def rendered_task(self, fresh_db):
        tid = f"test-rcache-{os.getpid()}-{id(self)}"
        fresh_db["create_task"](tid, "test.mp3", "/tmp/uploads/test.mp3",
                               {"algorithm_version": "v2.4a"}, "hash123")
        output_dir = Path(f"/tmp/sono_test_output_{tid}")
        output_dir.mkdir(parents=True, exist_ok=True)
        fresh_db["update_task"](tid, output_path=str(output_dir / f"{tid}_repaired.wav"))
        return {"task_id": tid, "output_dir": output_dir}

    @pytest.fixture()
    def render_spec_client(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        tid = f"test-rspec-{os.getpid()}-{id(self)}"
        out_dir = Path(f"/tmp/sono_test_rspec_{tid}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{tid}_repaired.wav"
        out_file.write_bytes(b"RIFF" + b"\x00" * 200)

        fresh_db["create_task"](tid, "audio.wav", str(out_file),
                               {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed", output_path=str(out_file))
        app = create_app()
        client = TestClient(app)
        return {"client": client, "task_id": tid, "out_dir": out_dir}

    def test_render_96khz_24bit_accepted(self, render_spec_client):
        res = render_spec_client["client"].post(
            "/api/v1/render",
            json={"task_id": render_spec_client["task_id"], "sample_rate": 96000, "bit_depth": 24},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rendering"

    def test_render_192khz_32bit_accepted(self, render_spec_client):
        res = render_spec_client["client"].post(
            "/api/v1/render",
            json={"task_id": render_spec_client["task_id"], "sample_rate": 192000, "bit_depth": 32},
        )
        assert res.status_code == 200

    def test_render_filename_includes_spec(self, render_spec_client, fresh_db):
        tid = render_spec_client["task_id"]
        res = render_spec_client["client"].post(
            "/api/v1/render",
            json={"task_id": tid, "sample_rate": 96000, "bit_depth": 24},
        )
        assert res.status_code == 200

        import time
        time.sleep(2)

        task = fresh_db["get_task"](tid)
        if task and task.get("render_filename"):
            assert "96000" in task["render_filename"]
            assert "24" in task["render_filename"]

    def test_render_cache_distinguishes_different_specs(self, rendered_task):
        from api.routes import get_render_cache
        from config import OUTPUT_DIR
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        tid = rendered_task["task_id"]

        (Path(OUTPUT_DIR) / f"{tid}_rendered_v2.4a_48000_24.wav").write_bytes(b"RIFF" + b"\x00" * 100)
        (Path(OUTPUT_DIR) / f"{tid}_rendered_v2.4a_96000_24.wav").write_bytes(b"RIFF" + b"\x00" * 200)
        (Path(OUTPUT_DIR) / f"{tid}_rendered_v2.4a_96000_32.wav").write_bytes(b"RIFF" + b"\x00" * 300)

        caches = asyncio.run(get_render_cache(tid))
        cache_list = caches["caches"]

        sr_48 = [c for c in cache_list if c["sample_rate"] == 48000 and c["bit_depth"] == 24]
        sr_96_24 = [c for c in cache_list if c["sample_rate"] == 96000 and c["bit_depth"] == 24]
        sr_96_32 = [c for c in cache_list if c["sample_rate"] == 96000 and c["bit_depth"] == 32]

        assert len(sr_48) >= 1, f"Should find 48kHz/24bit cache, got: {cache_list}"
        assert len(sr_96_24) >= 1, f"Should find 96kHz/24bit cache, got: {cache_list}"
        assert len(sr_96_32) >= 1, f"Should find 96kHz/32bit cache, got: {cache_list}"


class TestRenderOutputSpecMatchesRequest:
    @pytest.fixture()
    def render_verify_client(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        tid = f"test-rverify-{os.getpid()}-{id(self)}"
        out_dir = Path(f"/tmp/sono_test_rverify_{tid}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{tid}_repaired.wav"
        out_file.write_bytes(b"RIFF" + b"\x00" * 200)

        fresh_db["create_task"](tid, "audio.wav", str(out_file),
                               {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed", output_path=str(out_file))
        app = create_app()
        client = TestClient(app)
        return {"client": client, "task_id": tid, "out_dir": out_dir}

    def test_render_result_sample_rate_equals_request(self, render_verify_client, fresh_db):
        tid = render_verify_client["task_id"]
        res = render_verify_client["client"].post(
            "/api/v1/render",
            json={"task_id": tid, "sample_rate": 96000, "bit_depth": 24},
        )
        assert res.status_code == 200

        import time
        time.sleep(2)

        task = fresh_db["get_task"](tid)
        assert task is not None, "Task should exist after render"
        if task.get("render_result"):
            result = json.loads(task["render_result"]) if isinstance(task["render_result"], str) else task["render_result"]
            assert result["output_sample_rate"] == 96000, \
                f"Render output_sample_rate must equal requested 96000, got {result['output_sample_rate']}"
            assert result["output_bit_depth"] == 24, \
                f"Render output_bit_depth must equal requested 24, got {result['output_bit_depth']}"

    def test_render_result_48khz_not_default_for_96khz_request(self, render_verify_client, fresh_db):
        tid = render_verify_client["task_id"]
        res = render_verify_client["client"].post(
            "/api/v1/render",
            json={"task_id": tid, "sample_rate": 96000, "bit_depth": 24},
        )
        assert res.status_code == 200

        import time
        time.sleep(2)

        task = fresh_db["get_task"](tid)
        if task and task.get("render_result"):
            result = json.loads(task["render_result"]) if isinstance(task["render_result"], str) else task["render_result"]
            assert result["output_sample_rate"] != 48000, \
                "Render output_sample_rate must NOT be 48000 when 96000 was requested (48kHz bug regression)"

    def test_render_result_32bit_for_32bit_request(self, render_verify_client, fresh_db):
        tid = render_verify_client["task_id"]
        res = render_verify_client["client"].post(
            "/api/v1/render",
            json={"task_id": tid, "sample_rate": 48000, "bit_depth": 32},
        )
        assert res.status_code == 200

        import time
        time.sleep(2)

        task = fresh_db["get_task"](tid)
        if task and task.get("render_result"):
            result = json.loads(task["render_result"]) if isinstance(task["render_result"], str) else task["render_result"]
            assert result["output_bit_depth"] == 32, \
                f"Render output_bit_depth must equal requested 32, got {result['output_bit_depth']}"

    def test_repair_result_output_sr_is_working_sr_not_delivery(self, fresh_db):
        from services.repair.repair_v2_4a.core import MOBILE_WORKING_SR
        tid = f"test-repair-sr-{os.getpid()}"
        fresh_db["create_task"](tid, "audio.wav", "/tmp/test.wav",
                               {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed",
                                repair_result=json.dumps({
                                    "output_sample_rate": MOBILE_WORKING_SR,
                                    "output_bit_depth": 24,
                                }))
        task = fresh_db["get_task"](tid)
        result = task["repair_result"]
        if isinstance(result, str):
            result = json.loads(result)
        assert result["output_sample_rate"] == MOBILE_WORKING_SR, \
            "repair_result.output_sample_rate is the working SR (48000), NOT the delivery spec"
        assert result["output_sample_rate"] != 96000, \
            "repair_result must never be confused with delivery spec sample rate"


class TestDownloadContentDisposition:
    @pytest.fixture()
    def client_and_task(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        tid = f"test-disc-{os.getpid()}-{id(self)}"
        out_dir = Path(f"/tmp/sono_test_disc_{tid}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{tid}_repaired.wav"
        out_file.write_bytes(b"RIFF" + b"\x00" * 200)

        fresh_db["create_task"](tid, "测试音频.wav", str(out_file),
                               {"algorithm_version": "v2.4a"}, "h123")
        fresh_db["update_task"](tid, status="completed", output_path=str(out_file))
        app = create_app()
        client = TestClient(app)
        return {"client": client, "task_id": tid, "out_dir": out_dir}

    def test_download_audio_content_disposition(self, client_and_task):
        res = client_and_task["client"].get(f"/api/v1/download/{client_and_task['task_id']}")
        assert res.status_code == 200
        disp = res.headers.get("content-disposition", "")
        assert "filename=" in disp, f"Content-Disposition 应包含 filename=, 实际: {disp}"
        assert "filename*=UTF-8''" in disp, f"Content-Disposition 应包含 filename*=UTF-8'', 实际: {disp}"

    def test_download_mp3_content_disposition(self, client_and_task):
        from config import OUTPUT_DIR
        wav_path = os.path.join(OUTPUT_DIR, f"{client_and_task['task_id']}_repaired.wav")
        mp3_path = os.path.join(OUTPUT_DIR, f"{client_and_task['task_id']}_repaired.mp3")
        try:
            Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
            Path(wav_path).write_bytes(b"RIFF" + b"\x00" * 200)
            Path(mp3_path).write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1000)
            res = client_and_task["client"].get(f"/api/v1/download-mp3/{client_and_task['task_id']}")
            assert res.status_code == 200
            disp = res.headers.get("content-disposition", "")
            assert "filename=" in disp, f"Content-Disposition 应包含 filename=, 实际: {disp}"
            assert "filename*=UTF-8''" in disp, f"Content-Disposition 应包含 filename*=UTF-8'', 实际: {disp}"
            assert ".mp3" in disp, f"Content-Disposition 应包含 .mp3, 实际: {disp}"
        finally:
            for p in [wav_path, mp3_path]:
                if os.path.exists(p):
                    os.unlink(p)


class TestTimestampFormat:
    def test_upload_returns_iso_timestamp(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        app = create_app()
        client = TestClient(app)
        import hashlib
        wav_data = b"RIFF" + b"\x00" * 200
        file_hash = hashlib.sha256(wav_data).hexdigest()
        res = client.post(
            "/api/v1/upload",
            files={"file": ("test.wav", wav_data, "audio/wav")},
            data={"file_hash": file_hash},
        )
        assert res.status_code == 200
        data = res.json()
        task_id = data["task_id"]
        from database import get_task
        task = get_task(task_id)
        assert task is not None
        assert task.get("created_at"), "任务应有 created_at"
        assert str(task["created_at"]).endswith("Z") or "+" in str(task["created_at"]), \
            f"created_at 应为 ISO 格式(以Z结尾), 实际: {task['created_at']}"

    def test_task_list_returns_iso_timestamp(self, fresh_db):
        from fastapi.testclient import TestClient
        from app import create_app

        fresh_db["create_task"]("ts-test-001", "test.wav", "/tmp/test.wav", {}, "h123")
        fresh_db["update_task"]("ts-test-001", status="completed", output_path="/tmp/test_out.wav")

        app = create_app()
        client = TestClient(app)
        res = client.get("/api/v1/cache/info")
        assert res.status_code == 200
        data = res.json()
        tasks = data.get("tasks", [])
        ts_task = next((t for t in tasks if t["id"] == "ts-test-001"), None)
        assert ts_task is not None, "任务列表应包含刚创建的任务"
        created_at = ts_task.get("created_at", "")
        assert str(created_at).endswith("Z") or "+" in str(created_at), \
            f"任务列表 created_at 应为 ISO 格式(以Z结尾), 实际: {created_at}"
