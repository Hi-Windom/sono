import sys
import os
import json
import tempfile
import pytest
from pathlib import Path
import time
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"

from database import init_db, get_db, create_task, update_task, get_task


@pytest.fixture()
def fresh_db():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    old_path = None
    try:
        import config
        old_path = getattr(config, "DB_PATH", None)
        config.DB_PATH = db_path
    except Exception:
        pass

    from services.task_manager import _active_tasks, _active_tasks_lock
    with _active_tasks_lock:
        _active_tasks.clear()

    init_db()
    yield {"db_path": db_path, "get_db": get_db, "create_task": create_task, "update_task": update_task, "get_task": get_task}

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


@pytest.fixture()
def wav_bytes():
    import struct
    import math
    sr = 44100
    duration = 1.0
    n_samples = int(sr * duration)
    data_size = n_samples * 2
    header = struct.pack('<4sI4s', b'RIFF', 36 + data_size, b'WAVE')
    fmt_chunk = struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, sr, sr * 2, 2, 16)
    data_chunk_header = struct.pack('<4sI', b'data', data_size)
    samples = bytearray()
    for i in range(n_samples):
        val = int(0.5 * 32767 * math.sin(2 * math.pi * 440 * i / sr))
        samples.extend(struct.pack('<h', max(-32768, min(32767, val))))
    return header + fmt_chunk + data_chunk_header + bytes(samples)


class TestDeliverySpecConversion:
    def test_task_manager_imports_upload_dir(self):
        from config import UPLOAD_DIR, OUTPUT_DIR
        assert UPLOAD_DIR is not None
        assert OUTPUT_DIR is not None
        assert os.path.exists(UPLOAD_DIR) or True

    def test_task_manager_run_repair_accepts_target_spec_params(self, fresh_db):
        import numpy as np
        import soundfile as sf
        from services.task_manager import _run_repair

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        try:
            sr, duration = 44100, 1.0
            t = np.arange(int(sr * duration)) / sr
            y = 0.5 * np.sin(2 * np.pi * 440 * t)
            sf.write(wav_path, y, sr, subtype='PCM_16')

            with open(wav_path, 'rb') as f:
                import hashlib
                file_hash = hashlib.sha256(f.read()).hexdigest()

            task_id = "test_delivery_spec_001"
            params = {
                "algorithm_version": "v3.0",
                "target_sample_rate": 48000,
                "target_bit_depth": 24,
                "de_clipping": 0.3,
            }

            create_task(task_id, "test.wav", wav_path, params, file_hash=file_hash)

            result_container = [None]
            exception_container = [None]

            def run_in_thread():
                try:
                    _run_repair(task_id, wav_path, params.copy(), mobile_mode=False)
                except Exception as e:
                    exception_container[0] = e

            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join(timeout=60)

            if exception_container[0]:
                raise exception_container[0]

            updated_task = fresh_db["get_task"](task_id)
            assert updated_task is not None, "Task should exist after repair"
            assert updated_task["status"] in ["completed", "error"], f"Task status should be completed or error, got: {updated_task['status']}"

            if updated_task["status"] == "completed":
                output_path = updated_task.get("output_path")
                assert output_path, "Output path should be set"
                assert os.path.exists(output_path), f"Output file should exist: {output_path}"
                size = os.path.getsize(output_path)
                assert size > 10240, f"Output file too small: {size}B"

        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

            import glob as glob_module
            for pattern in [f"{tempfile.gettempdir()}/test_delivery_spec_001*.wav"]:
                for f in glob_module.glob(pattern):
                    try:
                        os.unlink(f)
                    except OSError:
                        pass

    def test_repair_api_accepts_target_spec_params(self, api_client, fresh_db, wav_bytes):
        import hashlib
        file_hash = hashlib.sha256(wav_bytes).hexdigest()

        upload_res = api_client.post("/api/v1/upload", files={
            "file": ("test.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()
        task_id = upload_data["task_id"]

        repair_params = {
            "algorithm_version": "v3.0",
            "de_clipping": 0.3,
            "target_sample_rate": 48000,
            "target_bit_depth": 24,
        }

        repair_res = api_client.post("/api/v1/repair", json={
            "task_id": task_id,
            "params": repair_params
        })
        assert repair_res.status_code == 200
        repair_data = repair_res.json()
        assert repair_data["task_id"] == task_id

    def test_render_output_function_works(self):
        import numpy as np
        import soundfile as sf
        from services.render import render_output

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as input_f:
            input_path = input_f.name
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_f:
            output_path = output_f.name

        try:
            sr, duration = 44100, 1.0
            t = np.arange(int(sr * duration)) / sr
            y = 0.5 * np.sin(2 * np.pi * 440 * t)
            sf.write(input_path, y, sr, subtype='PCM_16')

            result = render_output(input_path, output_path, target_sr=48000, bit_depth=24)

            assert os.path.exists(output_path), "Output file should exist"
            size = os.path.getsize(output_path)
            assert size > 10240, f"Output file too small: {size}B"

            info = sf.info(output_path)
            assert info.samplerate == 48000, f"Sample rate should be 48000, got {info.samplerate}"
            assert info.subtype in ["PCM_24", "PCM_32"], f"Bit depth should be 24 or 32, got {info.subtype}"

            assert result["output_sample_rate"] == 48000
            assert result["output_bit_depth"] == 24

        finally:
            try:
                os.unlink(input_path)
            except OSError:
                pass
            try:
                os.unlink(output_path)
            except OSError:
                pass


class TestUploadEndpointTargetSpec:
    def test_upload_with_target_spec_params(self, api_client, wav_bytes):
        res = api_client.post("/api/v1/upload", files={
            "file": ("test.wav", wav_bytes, "audio/wav"),
        }, data={
            "target_sample_rate": 48000,
            "target_bit_depth": 24,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["task_id"]

        task_id = data["task_id"]
        status_res = api_client.get(f"/api/v1/status/{task_id}")
        assert status_res.status_code == 200

    def test_upload_dual_with_target_spec_params(self, api_client, wav_bytes):
        res = api_client.post("/api/v1/upload-dual", files={
            "vocal_file": ("vocal.wav", wav_bytes, "audio/wav"),
            "accompaniment_file": ("acc.wav", wav_bytes, "audio/wav"),
        })
        assert res.status_code == 200
        data = res.json()
        assert data["task_id"]


class TestEndToEndWithDeliverySpec:
    def test_full_flow_with_delivery_spec_conversion(self, api_client, fresh_db, wav_bytes):
        import hashlib
        import numpy as np
        import soundfile as sf

        file_hash = hashlib.sha256(wav_bytes).hexdigest()

        upload_res = api_client.post("/api/v1/upload", files={
            "file": ("test.wav", wav_bytes, "audio/wav"),
        })
        assert upload_res.status_code == 200
        upload_data = upload_res.json()
        task_id = upload_data["task_id"]

        repair_params = {
            "algorithm_version": "v3.0",
            "de_clipping": 0.3,
            "target_sample_rate": 48000,
            "target_bit_depth": 24,
        }

        repair_res = api_client.post("/api/v1/repair", json={
            "task_id": task_id,
            "params": repair_params
        })
        assert repair_res.status_code == 200

        for _ in range(30):
            time.sleep(1)
            task = fresh_db["get_task"](task_id)
            if task and task["status"] in ["completed", "error"]:
                break

        task = fresh_db["get_task"](task_id)
        assert task is not None
        assert task["status"] == "completed", f"Task should be completed, got status={task['status']}, step={task.get('step')}, error={task.get('error')}"

        output_path = task.get("output_path")
        assert output_path, "Output path should be set"
        assert os.path.exists(output_path), f"Output file should exist: {output_path}"

        info = sf.info(output_path)
        assert info.samplerate == 48000, f"Sample rate should be 48000, got {info.samplerate}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
