import sys
import os
import json
import tempfile
import hashlib
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


def _make_test_wav(path: str, sr=44100, duration=2.0):
    import numpy as np
    import soundfile as sf
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    y = 0.5 * np.sin(2 * np.pi * 440 * t)
    sf.write(path, y, sr, subtype='PCM_16')


class TestMp3FileInfo:
    def test_miniaudio_reads_mp3_info(self):
        wav_path = None
        mp3_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                wav_path = f.name
            mp3_path = wav_path.replace('.wav', '.mp3')
            _make_test_wav(wav_path, sr=44100, duration=1.0)
            from api.routes import _wav_to_mp3
            _wav_to_mp3(wav_path, mp3_path, bitrate=128)
            assert os.path.exists(mp3_path), "MP3 文件应被创建"
            import miniaudio
            info = miniaudio.get_file_info(mp3_path)
            assert info.sample_rate == 44100, f"采样率应为 44100，实际 {info.sample_rate}"
            assert info.nchannels in (1, 2), f"通道数应 > 0，实际 {info.nchannels}"
            assert info.duration == pytest.approx(1.0, rel=0.1), f"时长应约为 1.0s，实际 {info.duration}"
        finally:
            for p in [wav_path, mp3_path]:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    def test_miniaudio_decodes_mp3(self):
        wav_path = None
        mp3_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                wav_path = f.name
            mp3_path = wav_path.replace('.wav', '.mp3')
            _make_test_wav(wav_path, sr=44100, duration=1.0)
            from api.routes import _wav_to_mp3
            _wav_to_mp3(wav_path, mp3_path, bitrate=128)
            import miniaudio
            decoded = miniaudio.decode_file(mp3_path)
            assert decoded is not None, "miniaudio 应能解码 MP3"
            assert decoded.sample_rate == 44100, f"解码后采样率应为 44100，实际 {decoded.sample_rate}"
            assert decoded.nchannels > 0, f"解码后应有通道，实际 {decoded.nchannels}"
            assert len(decoded.samples) > 0, "解码后应有样本数据"
        finally:
            for p in [wav_path, mp3_path]:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    def test_upload_mp3_via_endpoint(self):
        from app import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app)
        mp3_path = None
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                wav_path = f.name
            mp3_path = wav_path.replace('.wav', '.mp3')
            _make_test_wav(wav_path, sr=44100, duration=0.5)
            from api.routes import _wav_to_mp3
            _wav_to_mp3(wav_path, mp3_path, bitrate=128)
            with open(mp3_path, 'rb') as f:
                mp3_data = f.read()
            response = client.post(
                "/api/v1/upload",
                files={"file": ("test.mp3", mp3_data, "audio/mpeg")},
            )
            assert response.status_code == 200, f"上传应成功，状态码 {response.status_code}"
            data = response.json()
            assert data.get("task_id"), "响应应包含 task_id"
            assert data.get("filename") == "test.mp3", "响应应包含 filename"
            assert data.get("audio_info"), "响应应包含 audio_info"
            audio_info = data["audio_info"]
            assert audio_info.get("sample_rate") == 44100, f"采样率应为 44100，实际 {audio_info.get('sample_rate')}"
            assert audio_info.get("channels") in (1, 2), f"通道数应 > 0，实际 {audio_info.get('channels')}"
            assert "mp3" in str(audio_info.get("format", "")).lower(), f"格式应为 mp3，实际 {audio_info.get('format')}"
        finally:
            for p in [wav_path, mp3_path]:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass