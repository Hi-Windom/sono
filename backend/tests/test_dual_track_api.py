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


class TestDualUploadEndpoint:
    def test_upload_dual_returns_three_task_ids(self, api_client):
        wav_bytes = _make_wav_bytes()
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert res.status_code == 200
        data = res.json()
        assert "task_id" in data, f"Missing task_id in response: {data}"
        assert "vocal_task_id" in data, f"Missing vocal_task_id in response: {data}"
        assert "accompaniment_task_id" in data, f"Missing accompaniment_task_id in response: {data}"
        assert data["task_id"] != data["vocal_task_id"], "Main task_id should differ from vocal_task_id"
        assert data["task_id"] != data["accompaniment_task_id"], "Main task_id should differ from accompaniment_task_id"
        assert data["vocal_task_id"] != data["accompaniment_task_id"], "vocal_task_id should differ from accompaniment_task_id"

    def test_upload_dual_creates_three_db_tasks(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert res.status_code == 200
        data = res.json()

        main_task = fresh_db["get_task"](data["task_id"])
        assert main_task is not None, "Main task should exist in DB"
        vocal_task = fresh_db["get_task"](data["vocal_task_id"])
        assert vocal_task is not None, "Vocal task should exist in DB"
        acc_task = fresh_db["get_task"](data["accompaniment_task_id"])
        assert acc_task is not None, "Accompaniment task should exist in DB"

    def test_upload_dual_main_task_stores_sub_task_ids(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert res.status_code == 200
        data = res.json()

        main_task = fresh_db["get_task"](data["task_id"])
        assert main_task is not None
        params = main_task.get("params", {})
        if isinstance(params, str):
            params = json.loads(params)
        assert params.get("vocal_task_id") == data["vocal_task_id"], \
            f"Main task params should contain vocal_task_id, got: {params}"
        assert params.get("accompaniment_task_id") == data["accompaniment_task_id"], \
            f"Main task params should contain accompaniment_task_id, got: {params}"

    def test_upload_dual_returns_filenames(self, api_client):
        wav_bytes = _make_wav_bytes()
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("my_vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("my_acc.wav", wav_bytes, "audio/wav"),
        })
        assert res.status_code == 200
        data = res.json()
        assert data["vocal_filename"] == "my_vocal.wav"
        assert data["accompaniment_filename"] == "my_acc.wav"

    def test_upload_dual_returns_sizes(self, api_client):
        wav_bytes = _make_wav_bytes()
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert res.status_code == 200
        data = res.json()
        assert data["vocal_size"] > 0
        assert data["accompaniment_size"] > 0

    def test_upload_dual_rejects_invalid_vocal_format(self, api_client):
        wav_bytes = _make_wav_bytes()
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.txt", b"not audio", "text/plain"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert res.status_code == 400

    def test_upload_dual_rejects_invalid_accompaniment_format(self, api_client):
        wav_bytes = _make_wav_bytes()
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.txt", b"not audio", "text/plain"),
        })
        assert res.status_code == 400


class TestDualRepairEndpoint:
    def test_repair_dual_with_valid_task_ids(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        upload_res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()

        repair_res = api_client.post("/api/v1/repair-dual", json={
            "task_id": upload_data["task_id"],
            "vocal_task_id": upload_data["vocal_task_id"],
            "accompaniment_task_id": upload_data["accompaniment_task_id"],
            "params": {"algorithm_version": "v3.0"},
        })
        assert repair_res.status_code == 200
        repair_data = repair_res.json()
        assert repair_data["task_id"] == upload_data["task_id"]
        assert repair_data["status"] == "pending"

    def test_repair_dual_with_separate_params(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        upload_res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()

        repair_res = api_client.post("/api/v1/repair-dual", json={
            "task_id": upload_data["task_id"],
            "vocal_task_id": upload_data["vocal_task_id"],
            "accompaniment_task_id": upload_data["accompaniment_task_id"],
            "params": {"algorithm_version": "v3.0"},
            "vocal_params": {"de_clipping": 0.8, "noise_reduction": 0.5, "algorithm_version": "v3.0"},
            "accompaniment_params": {"de_clipping": 0.3, "noise_reduction": 0.2, "algorithm_version": "v3.0"},
            "mix_ratio": 0.6,
        })
        assert repair_res.status_code == 200

    def test_repair_dual_nonexistent_vocal_task(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        upload_res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()

        repair_res = api_client.post("/api/v1/repair-dual", json={
            "task_id": upload_data["task_id"],
            "vocal_task_id": "nonexistent-vocal-task-id",
            "accompaniment_task_id": upload_data["accompaniment_task_id"],
            "params": {"algorithm_version": "v3.0"},
        })
        assert repair_res.status_code == 404

    def test_repair_dual_nonexistent_accompaniment_task(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        upload_res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()

        repair_res = api_client.post("/api/v1/repair-dual", json={
            "task_id": upload_data["task_id"],
            "vocal_task_id": upload_data["vocal_task_id"],
            "accompaniment_task_id": "nonexistent-acc-task-id",
            "params": {"algorithm_version": "v3.0"},
        })
        assert repair_res.status_code == 404

    def test_repair_dual_missing_required_fields(self, api_client):
        repair_res = api_client.post("/api/v1/repair-dual", json={
            "task_id": "some-task",
            "params": {"algorithm_version": "v3.0"},
        })
        assert repair_res.status_code == 422


class TestTrackStatusEndpoint:
    def test_track_status_returns_sub_task_info(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        upload_res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()

        status_res = api_client.get(f"/api/v1/tracks/{upload_data['task_id']}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["task_id"] == upload_data["task_id"]
        assert "vocal" in status_data, f"Should include vocal sub-task info, got: {status_data}"
        assert "accompaniment" in status_data, f"Should include accompaniment sub-task info, got: {status_data}"
        assert status_data["vocal"]["task_id"] == upload_data["vocal_task_id"]
        assert status_data["accompaniment"]["task_id"] == upload_data["accompaniment_task_id"]

    def test_track_status_nonexistent_task(self, api_client):
        status_res = api_client.get("/api/v1/tracks/nonexistent-task-id")
        assert status_res.status_code == 404

    def test_track_status_without_sub_tasks(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes()
        upload_res = api_client.post("/api/v1/upload", files={
            "file": ("single.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        task_id = upload_res.json()["task_id"]

        status_res = api_client.get(f"/api/v1/tracks/{task_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert "vocal" not in status_data
        assert "accompaniment" not in status_data


class TestDualTrackEndToEnd:
    def test_full_dual_track_flow(self, api_client, fresh_db):
        wav_bytes = _make_wav_bytes(duration=0.5)

        upload_res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()

        assert upload_data["task_id"]
        assert upload_data["vocal_task_id"]
        assert upload_data["accompaniment_task_id"]

        main_task = fresh_db["get_task"](upload_data["task_id"])
        assert main_task is not None
        params = main_task.get("params", {})
        if isinstance(params, str):
            params = json.loads(params)
        assert params.get("vocal_task_id") == upload_data["vocal_task_id"]
        assert params.get("accompaniment_task_id") == upload_data["accompaniment_task_id"]

        status_res = api_client.get(f"/api/v1/tracks/{upload_data['task_id']}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["vocal"]["task_id"] == upload_data["vocal_task_id"]
        assert status_data["accompaniment"]["task_id"] == upload_data["accompaniment_task_id"]

        repair_res = api_client.post("/api/v1/repair-dual", json={
            "task_id": upload_data["task_id"],
            "vocal_task_id": upload_data["vocal_task_id"],
            "accompaniment_task_id": upload_data["accompaniment_task_id"],
            "params": {"algorithm_version": "v3.0"},
            "vocal_params": {"de_clipping": 0.5, "algorithm_version": "v3.0"},
            "accompaniment_params": {"de_clipping": 0.3, "algorithm_version": "v3.0"},
            "mix_ratio": 0.5,
        })
        assert repair_res.status_code == 200
        assert repair_res.json()["status"] == "pending"
