import sys
import os
import json
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_db, create_task, update_task, find_repair_cache, find_dual_repair_cache


SR = 44100
DURATION = 2.0


def _make_wav(path: str, sr=SR, duration=DURATION):
    import numpy as np
    import soundfile as sf
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    y = 0.5 * np.sin(2 * np.pi * 440 * t)
    sf.write(path, y, sr, subtype='PCM_16')


def _make_dual_params(**overrides):
    base = {
        "vocal_declip": 0.3, "vocal_depop": 0.18, "vocal_formant_repair": 0.5,
        "vocal_de_ess": 0.25, "vocal_breath_enhance": 0.3, "vocal_ai_repair": 0.2,
        "vocal_bass_enhance": 0.1, "vocal_air_texture": 0.2, "vocal_loudness": 0.5,
        "vocal_exciter": 0.2, "vocal_compressor": 0.3, "vocal_clarity": 0.4,
        "inst_declip": 0.3, "inst_depop": 0.18, "inst_noise_reduction": 0.15,
        "inst_dynamic": 0.2, "inst_spatial": 0.15, "inst_warmth": 0.25,
        "inst_timbre_protect": 0.5, "inst_stereo_enhance": 0.2, "inst_loudness": 0.5,
        "vocal_ratio": 1.0, "accompaniment_ratio": 1.0,
        "mastering_style": "standard", "processing_mode": "dual",
    }
    base.update(overrides)
    return base


def _make_single_params(**overrides):
    base = {
        "de_clipping": 0.3, "noise_reduction": 0.15, "de_essing": 0.25,
        "de_crackle": 0.2, "de_pop": 0.18, "harmonic_enhance": 0.2,
        "dynamic_range": 0.3, "softness": 0.2, "presence_boost": 0.15,
        "bass_enhance": 0.1, "spatial_enhance": 0.15, "transient_repair": 0.2,
        "warmth": 0.25, "clarity": 0.4,
        "algorithm_version": "v3.1",
    }
    base.update(overrides)
    return base


class TestSingleTrackCacheLookup:
    @pytest.fixture(autouse=True)
    def setup(self):
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            self.wav_path = f.name
        _make_wav(self.wav_path)
        with open(self.wav_path, 'rb') as f:
            import hashlib
            self.file_hash = hashlib.sha256(f.read()).hexdigest()
        self.params = _make_single_params()
        self.output_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.output_dir, 'test_repaired.wav')
        _make_wav(self.output_path)
        yield
        try:
            os.unlink(self.wav_path)
            os.unlink(self.output_path)
            os.rmdir(self.output_dir)
        except OSError:
            pass

    def _create_task(self, task_id, params, output_path=None, status="completed"):
        create_task(task_id, "test.wav", self.wav_path, params, file_hash=self.file_hash)
        if status == "completed" and output_path:
            update_task(task_id, status=status, output_path=output_path)
        elif status:
            update_task(task_id, status=status)

    def test_exact_match(self):
        self._create_task("test_single_001", self.params, self.output_path)
        result = find_repair_cache(self.file_hash, self.params)
        assert result is not None, "精确匹配应命中缓存"
        assert result["id"] == "test_single_001"

    def test_extra_input_keys_match(self):
        stored = _make_single_params()
        input_params = dict(stored)
        input_params["extra_key_ignored"] = "should_not_matter"
        input_params["algorithm_version"] = "v3.1"
        self._create_task("test_single_002", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is not None, "输入有额外 key 但 repair_param_keys 相同应命中"

    def test_extra_stored_keys_match(self):
        stored = _make_single_params()
        stored["extra_db_field"] = "some_meta"
        input_params = _make_single_params()
        self._create_task("test_single_003", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is not None, "存储有额外 key 但 repair_param_keys 相同应命中"

    def test_param_value_mismatch(self):
        stored = _make_single_params()
        input_params = _make_single_params(de_clipping=0.9)
        self._create_task("test_single_004", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is None, "de_clipping 不同应不命中"

    def test_no_output_path(self):
        self._create_task("test_single_005", self.params, status="pending")
        result = find_repair_cache(self.file_hash, self.params)
        assert result is None, "无 output_path 应不命中"

    def test_output_file_not_exists(self):
        self._create_task("test_single_006", self.params, "/tmp/nonexistent.wav")
        result = find_repair_cache(self.file_hash, self.params)
        assert result is None, "输出文件不存在应不命中"


class TestDualTrackCacheLookup:
    @pytest.fixture(autouse=True)
    def setup(self):
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            self.vocal_path = f.name
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            self.acc_path = f.name
        _make_wav(self.vocal_path)
        _make_wav(self.acc_path)
        with open(self.vocal_path, 'rb') as f:
            import hashlib
            self.vocal_hash = hashlib.sha256(f.read()).hexdigest()
        with open(self.acc_path, 'rb') as f:
            self.acc_hash = hashlib.sha256(f.read()).hexdigest()
        self.params = _make_dual_params()
        self.output_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.output_dir, 'test_dual_repaired.wav')
        _make_wav(self.output_path)
        yield
        try:
            os.unlink(self.vocal_path)
            os.unlink(self.acc_path)
            os.unlink(self.output_path)
            os.rmdir(self.output_dir)
        except OSError:
            pass

    def _create_dual_task(self, task_id, vocal_hash, acc_hash, params, status="completed"):
        full_params = dict(params)
        full_params["vocal_file_hash"] = vocal_hash
        full_params["accompaniment_file_hash"] = acc_hash
        create_task(
            task_id, "vocal.wav", self.vocal_path, full_params,
            file_hash=f"dual_{vocal_hash[:8]}_{acc_hash[:8]}"
        )
        if status == "completed":
            update_task(task_id, status=status, output_path=self.output_path)
        else:
            update_task(task_id, status=status)

    def test_exact_match(self):
        self._create_dual_task("test_dual_001", self.vocal_hash, self.acc_hash, self.params)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, self.params)
        assert result is not None, "双轨精确匹配应命中"
        assert result["id"] == "test_dual_001"

    def test_input_has_extra_keys(self):
        stored = _make_dual_params()
        input_params = dict(stored)
        input_params["algorithm_version"] = "v3.1a"
        input_params["some_meta"] = "extra"
        self._create_dual_task("test_dual_002", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is not None, "输入有额外 key 应命中"

    def test_stored_has_extra_keys(self):
        stored = _make_dual_params()
        stored["vocal_ai_repair_enhanced"] = 0.15
        stored["inst_custom_field"] = 0.3
        input_params = _make_dual_params()
        self._create_dual_task("test_dual_003", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is not None, "存储有额外 key 应命中"

    def test_both_have_extra_keys(self):
        stored = _make_dual_params(mastering_style="powerful")
        stored["stored_only_field"] = 999
        input_params = _make_dual_params(mastering_style="powerful")
        input_params["input_only_field"] = 888
        self._create_dual_task("test_dual_004", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is not None, "双方都有额外 key 应命中"

    def test_core_param_mismatch(self):
        stored = _make_dual_params(vocal_declip=0.9)
        input_params = _make_dual_params(vocal_declip=0.3)
        self._create_dual_task("test_dual_005", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is None, "核心参数 vocal_declip 不同应不命中"

    def test_hash_mismatch(self):
        wrong_hash = "a" * 64
        self._create_dual_task("test_dual_006", self.vocal_hash, self.acc_hash, self.params)
        result = find_dual_repair_cache(wrong_hash, self.acc_hash, self.params)
        assert result is None, "vocal_hash 不同应不命中"


class TestMp3Encoding:
    def test_wav_to_mp3(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name
        mp3_path = wav_path.replace('.wav', '.mp3')
        try:
            _make_wav(wav_path, sr=44100, duration=1.0)
            from api.routes import _wav_to_mp3
            _wav_to_mp3(wav_path, mp3_path, bitrate=128)
            assert os.path.exists(mp3_path), "MP3 文件应被创建"
            mp3_size = os.path.getsize(mp3_path)
            assert mp3_size > 1000, f"MP3 文件太小: {mp3_size}B"
            with open(mp3_path, 'rb') as f:
                header = f.read(3)
            assert header == b'ID3' or header[:2] == b'\xff\xfb', f"MP3 头部异常: {header.hex()}"
        finally:
            try:
                os.unlink(wav_path)
                if os.path.exists(mp3_path):
                    os.unlink(mp3_path)
            except OSError:
                pass