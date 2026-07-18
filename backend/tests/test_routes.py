import sys
import os
import json
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


@pytest.fixture()
def api_client(fresh_db):
    from fastapi.testclient import TestClient
    from app import create_app
    app = create_app()
    return TestClient(app)


def _make_wav_bytes(duration=1.0, sr=44100, channels=1):
    import struct
    import math
    n_samples = int(sr * duration)
    data_size = n_samples * channels * 2
    bytes_per_sample = 2
    block_align = channels * bytes_per_sample
    byte_rate = sr * block_align

    header = struct.pack('<4sI4s', b'RIFF', 36 + data_size, b'WAVE')
    fmt_chunk = struct.pack('<4sIHHIIHH',
                            b'fmt ', 16, 1, channels, sr, byte_rate, block_align, bytes_per_sample * 8)
    data_chunk_header = struct.pack('<4sI', b'data', data_size)

    samples = bytearray()
    for i in range(n_samples):
        val = int(0.5 * 32767 * math.sin(2 * math.pi * 440 * i / sr))
        samples.extend(struct.pack('<h', max(-32768, min(32767, val))))
        if channels == 2:
            samples.extend(struct.pack('<h', max(-32768, min(32767, val))))

    return header + fmt_chunk + data_chunk_header + bytes(samples)


class TestSystemRoutes:
    def test_health_endpoint(self, api_client):
        res = api_client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "version" in data
        assert "active_tasks" in data

    def test_algorithm_versions(self, api_client):
        res = api_client.get("/api/v1/algorithm-versions")
        assert res.status_code == 200
        data = res.json()
        assert "versions" in data
        assert isinstance(data["versions"], list)
        assert len(data["versions"]) > 0

    def test_detector_versions(self, api_client):
        res = api_client.get("/api/v1/detector-versions")
        assert res.status_code == 200
        data = res.json()
        assert "versions" in data
        assert isinstance(data["versions"], list)

    def test_deploy_info(self, api_client):
        res = api_client.get("/api/v1/deploy-info")
        assert res.status_code == 200
        data = res.json()
        assert "deploy_time" in data
        assert "deploy_days" in data

    def test_system_load(self, api_client):
        res = api_client.get("/api/v1/system/load")
        assert res.status_code == 200
        data = res.json()
        assert "active_tasks" in data
        assert "max_concurrent_tasks" in data
        assert "can_accept" in data
        assert "load_percent" in data

    def test_diagnostics(self, api_client):
        res = api_client.get("/api/v1/diag")
        assert res.status_code == 200
        data = res.json()
        assert data["backend"] is True
        assert "python" in data
        assert "ffmpeg" in data
        assert "system" in data
        assert "runtime" in data

    def test_memory_info(self, api_client):
        res = api_client.post("/api/v1/memory/info", json={
            "duration": 60.0,
            "channels": 2,
            "sample_rate": 44100,
            "algorithm_version": "v2.4a",
        })
        assert res.status_code == 200
        data = res.json()
        assert "estimated_memory_bytes" in data
        assert "is_sufficient" in data
        assert "working_sr" in data
        assert "use_float32" in data
        assert "has_streaming" in data

    def test_memory_info_zero_duration(self, api_client):
        res = api_client.post("/api/v1/memory/info", json={
            "duration": 0,
            "channels": 2,
            "sample_rate": 44100,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["estimated_memory_bytes"] == 0
        assert data["is_sufficient"] is True

    def test_log_endpoint(self, api_client):
        res = api_client.post("/api/v1/log", json={"message": "test log message", "level": "info"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"


class TestUploadRoutes:
    def test_upload_wav(self, api_client):
        wav_bytes = _make_wav_bytes(duration=0.5)
        res = api_client.post(
            "/api/v1/upload",
            files={"file": ("test.wav", wav_bytes, "audio/wav")},
            data={"file_hash": "test_hash_123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "task_id" in data
        assert "filename" in data
        assert "size" in data
        assert data["filename"] == "test.wav"
        assert data["size"] > 0

    def test_upload_invalid_format(self, api_client):
        res = api_client.post(
            "/api/v1/upload",
            files={"file": ("test.txt", b"not audio", "text/plain")},
        )
        assert res.status_code == 400

    def test_check_hash_exists(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes(duration=0.5)
        upload_res = api_client.post(
            "/api/v1/upload",
            files={"file": ("test.wav", wav_bytes, "audio/wav")},
            data={"file_hash": "unique_hash_abc"},
        )
        assert upload_res.status_code == 200

        res = api_client.post("/api/v1/check-hash", json={"file_hash": "unique_hash_abc"})
        assert res.status_code == 200
        data = res.json()
        assert data["exists"] is True
        assert "task_id" in data

    def test_check_hash_not_exists(self, api_client):
        res = api_client.post("/api/v1/check-hash", json={"file_hash": "nonexistent_hash"})
        assert res.status_code == 200
        data = res.json()
        assert data["exists"] is False


class TestCacheRoutes:
    def test_cache_info(self, api_client):
        res = api_client.get("/api/v1/cache/info")
        assert res.status_code == 200
        data = res.json()
        assert "total_size" in data
        assert "upload_size" in data
        assert "output_size" in data
        assert "task_count" in data
        assert "tasks" in data

    def test_lookup_repair_cache_not_found(self, api_client):
        res = api_client.post("/api/v1/cache/lookup", json={
            "file_hash": "no_such_hash",
            "params": {"algorithm_version": "v2.4a", "de_clipping": 0.5},
        })
        assert res.status_code == 200
        data = res.json()
        assert data["found"] is False

    def test_lookup_dual_cache_not_found(self, api_client):
        res = api_client.post("/api/v1/cache/lookup-dual", json={
            "vocal_file_hash": "no_vocal_hash",
            "accompaniment_file_hash": "no_acc_hash",
            "params": {"algorithm_version": "v3.0"},
        })
        assert res.status_code == 200
        data = res.json()
        assert data["found"] is False

    def test_render_cache_empty(self, api_client, fresh_db):
        fresh_db["create_task"]("test-task-123", "test.wav", "/tmp/test.wav", {}, "hash123")
        res = api_client.get("/api/v1/render-cache/test-task-123")
        assert res.status_code == 200
        data = res.json()
        assert "caches" in data
        assert isinstance(data["caches"], list)

    def test_get_audio_info_not_found(self, api_client):
        res = api_client.get("/api/v1/audio-info/nonexistent_hash")
        assert res.status_code == 404

    def test_analysis_cache_not_found(self, api_client):
        res = api_client.get("/api/v1/analysis-cache/nonexistent")
        assert res.status_code == 200
        data = res.json()
        assert data["found"] is False

    def test_save_analysis_cache(self, api_client):
        res = api_client.post("/api/v1/analysis-cache", json={
            "quick_hash": "test_analysis_hash",
            "file_name": "test.wav",
            "file_size": 1024,
            "wav_info": '{"sampleRate":44100}',
            "analysis": '{"issues":[]}',
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"

    def test_list_analysis_cache(self, api_client):
        res = api_client.get("/api/v1/analysis-cache-list")
        assert res.status_code == 200
        data = res.json()
        assert "entries" in data
        assert "count" in data


class TestRepairRoutes:
    def test_repair_nonexistent_task(self, api_client):
        res = api_client.post("/api/v1/repair", json={
            "task_id": "no-such-task",
            "params": {"algorithm_version": "v2.4a"},
        })
        assert res.status_code == 404

    def test_repair_with_valid_task(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes(duration=0.5)
        upload_res = api_client.post(
            "/api/v1/upload",
            files={"file": ("test.wav", wav_bytes, "audio/wav")},
        )
        assert upload_res.status_code == 200
        task_id = upload_res.json()["task_id"]

        res = api_client.post("/api/v1/repair", json={
            "task_id": task_id,
            "params": {"algorithm_version": "v2.4a", "de_clipping": 0.5},
        })
        assert res.status_code == 200
        data = res.json()
        assert data["task_id"] == task_id
        assert data["status"] == "pending"


class TestDownloadRoutes:
    def test_download_nonexistent_task(self, api_client):
        res = api_client.get("/api/v1/download/no-such-task")
        assert res.status_code == 404

    def test_preview_nonexistent_task(self, api_client):
        res = api_client.get("/api/v1/preview/no-such-task")
        assert res.status_code == 404


class TestRenderRoutes:
    def test_render_nonexistent_task(self, api_client):
        res = api_client.post("/api/v1/render", json={
            "task_id": "no-such-task",
            "sample_rate": 48000,
            "bit_depth": 24,
        })
        assert res.status_code == 404
