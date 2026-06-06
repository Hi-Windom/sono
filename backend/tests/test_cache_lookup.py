import sys
import os
import json
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"

from database import init_db, get_db, create_task, update_task, find_repair_cache, find_dual_repair_cache
from services.param_maps import VOCAL_KEY_MAP, INST_KEY_MAP, DUAL_REPAIR_PARAM_KEYS, SINGLE_REPAIR_PARAM_KEYS


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
    init_db()
    yield {"db_path": db_path, "get_db": get_db, "create_task": create_task, "update_task": update_task}
    if old_path is not None:
        try:
            config.DB_PATH = old_path
        except Exception:
            pass
    try:
        os.unlink(db_path)
    except OSError:
        pass


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
    # Cache matching uses intersection comparison on repair_param_keys.
    # algorithm_version IS in repair_param_keys for single-track, so:
    # - Both have same algorithm_version → match (if other keys agree)
    # - Both have different algorithm_version → NO match
    # - One side missing algorithm_version → intersection excludes it, other keys compared
    #
    # WARNING: The intersection comparison allows matches when one side lacks
    # algorithm_version. This is intentional for backward compatibility with
    # old tasks that don't store algorithm_version. However, it means a
    # v3.1 request could match a v2.x cache entry if the old entry has no
    # algorithm_version field. This is acceptable because:
    # 1. Old tasks without algorithm_version are from before v3.x existed
    # 2. The repair result is still valid (just from an older algorithm)
    # 3. The user can choose to re-repair if they want the new algorithm

    @pytest.fixture(autouse=True)
    def setup(self, fresh_db):
        self.db = fresh_db
        self.create_task = fresh_db["create_task"]
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
        self.create_task(task_id, "test.wav", self.wav_path, params, file_hash=self.file_hash)
        if status == "completed" and output_path:
            self.db["update_task"](task_id, status=status, output_path=output_path)
        elif status:
            self.db["update_task"](task_id, status=status)

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

    def test_input_has_algorithm_version_stored_missing(self):
        stored = _make_single_params()
        stored.pop("algorithm_version", None)
        input_params = _make_single_params(algorithm_version="v3.1")
        self._create_task("test_single_007", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is not None, "输入有 algorithm_version 但存储没有，交集比较应命中"

    def test_stored_has_mastering_style_input_missing(self):
        stored = _make_single_params()
        stored["mastering_style"] = "standard"
        input_params = _make_single_params()
        self._create_task("test_single_008", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is not None, "存储有 mastering_style 但输入没有，交集比较应命中"

    def test_both_asymmetric_keys(self):
        stored = _make_single_params()
        stored.pop("algorithm_version", None)
        stored["mastering_style"] = "standard"
        stored["extra_stored"] = "only_stored"
        input_params = _make_single_params(algorithm_version="v3.1")
        input_params["extra_input"] = "only_input"
        self._create_task("test_single_009", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is not None, "双方都有不对称 key，交集比较应命中"

    def test_algorithm_version_mismatch_no_cache(self):
        # CRITICAL: Different algorithm versions must NOT match the same cache.
        # Previously, switching from v3.1a to v2.4a would incorrectly reuse
        # the v3.1a repair result because the front-end renderDownloadUrl was
        # not cleared and algorithmVersionRef was stale. The back-end cache
        # matching correctly rejects this because algorithm_version is in
        # repair_param_keys and the intersection includes it when both sides
        # have it.
        stored = _make_single_params(algorithm_version="v3.1a")
        input_params = _make_single_params(algorithm_version="v2.4a")
        self._create_task("test_single_010", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is None, (
            "algorithm_version 不同（v3.1a vs v2.4a）应不命中缓存。"
            "不同算法版本的修复结果不可互换！"
        )

    def test_algorithm_version_same_match(self):
        stored = _make_single_params(algorithm_version="v3.1")
        input_params = _make_single_params(algorithm_version="v3.1")
        self._create_task("test_single_011", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is not None, "algorithm_version 相同应命中缓存"

    def test_algorithm_version_minor_mismatch(self):
        stored = _make_single_params(algorithm_version="v3.0")
        input_params = _make_single_params(algorithm_version="v3.1")
        self._create_task("test_single_012", stored, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is None, (
            "algorithm_version 不同（v3.0 vs v3.1）应不命中缓存。"
            "即使是同一大版本，小版本差异也意味着不同的算法实现。"
        )


class TestDualTrackCacheLookup:
    # Dual-track cache matching also uses intersection comparison on repair_param_keys.
    # BUG FIX: algorithm_version was previously MISSING from dual-track repair_param_keys,
    # which meant switching from v3.0 to v3.1 would incorrectly hit the v3.0 cache.
    # algorithm_version has now been added to the dual-track repair_param_keys.
    #
    # This is critical because different algorithm versions produce different repair
    # results (e.g., v3.0 uses _hf_protect with 3000Hz cutoff while v3.1 uses 4000Hz).
    # Using a cached result from the wrong algorithm version would give the user
    # audio processed by a different algorithm than what they selected.

    @pytest.fixture(autouse=True)
    def setup(self, fresh_db):
        self.db = fresh_db
        self.create_task = fresh_db["create_task"]
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
        self.create_task(
            task_id, "vocal.wav", self.vocal_path, full_params,
            file_hash=f"dual_{vocal_hash[:8]}_{acc_hash[:8]}"
        )
        if status == "completed":
            self.db["update_task"](task_id, status=status, output_path=self.output_path)
        else:
            self.db["update_task"](task_id, status=status)

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

    def test_input_has_algorithm_version_stored_missing(self):
        stored = _make_dual_params()
        input_params = dict(stored)
        input_params["algorithm_version"] = "v3.1a"
        self._create_dual_task("test_dual_007", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is not None, "输入有 algorithm_version 但存储没有，交集比较应命中"

    def test_stored_has_algorithm_version_input_missing(self):
        stored = _make_dual_params()
        stored["algorithm_version"] = "v3.1a"
        input_params = _make_dual_params()
        self._create_dual_task("test_dual_008", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is not None, "存储有 algorithm_version 但输入没有，交集比较应命中"

    def test_algorithm_version_mismatch_no_cache(self):
        # CRITICAL: Different algorithm versions must NOT match in dual-track cache.
        # Previously, algorithm_version was missing from dual-track repair_param_keys,
        # so switching from v3.0 to v3.1a would incorrectly reuse the v3.0 result.
        # This was a confirmed bug — the same file with same params but different
        # algorithm version would produce different audio, yet the cache would
        # return the old version's result.
        stored = _make_dual_params(algorithm_version="v3.0")
        input_params = _make_dual_params(algorithm_version="v3.1a")
        self._create_dual_task("test_dual_009", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is None, (
            "双轨 algorithm_version 不同（v3.0 vs v3.1a）应不命中缓存。"
            "不同算法版本的修复结果不可互换！"
        )

    def test_algorithm_version_same_match(self):
        stored = _make_dual_params(algorithm_version="v3.1a")
        input_params = _make_dual_params(algorithm_version="v3.1a")
        self._create_dual_task("test_dual_010", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is not None, "双轨 algorithm_version 相同应命中缓存"

    def test_algorithm_version_cross_major_mismatch(self):
        stored = _make_dual_params(algorithm_version="v2.4a")
        input_params = _make_dual_params(algorithm_version="v3.0a")
        self._create_dual_task("test_dual_011", self.vocal_hash, self.acc_hash, stored)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is None, (
            "双轨 algorithm_version 跨大版本不同（v2.4a vs v3.0a）应不命中缓存"
        )


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
                head = f.read(200)
            sync_found = False
            for i in range(len(head) - 1):
                if head[i] == 0xFF and (head[i+1] & 0xE0) == 0xE0:
                    sync_found = True
                    break
            assert sync_found, f"未找到 MP3 帧同步头 (前200字节: {head[:32].hex()})"
        finally:
            try:
                os.unlink(wav_path)
                if os.path.exists(mp3_path):
                    os.unlink(mp3_path)
            except OSError:
                pass


class TestParamMapsSync:
    def test_vocal_key_map_sync(self):
        for value in VOCAL_KEY_MAP.values():
            assert value in DUAL_REPAIR_PARAM_KEYS, f"{value} 不在 DUAL_REPAIR_PARAM_KEYS 中"

    def test_inst_key_map_sync(self):
        for value in INST_KEY_MAP.values():
            assert value in DUAL_REPAIR_PARAM_KEYS, f"{value} 不在 DUAL_REPAIR_PARAM_KEYS 中"


@pytest.mark.parametrize("param_key", sorted(set(VOCAL_KEY_MAP.values()) | set(INST_KEY_MAP.values())))
class TestEveryDualParamAffectsCache:
    @pytest.fixture(autouse=True)
    def setup(self, fresh_db):
        self.db = fresh_db
        self.create_task = fresh_db["create_task"]
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
        self.create_task(
            task_id, "vocal.wav", self.vocal_path, full_params,
            file_hash=f"dual_{vocal_hash[:8]}_{acc_hash[:8]}"
        )
        if status == "completed":
            self.db["update_task"](task_id, status=status, output_path=self.output_path)
        else:
            self.db["update_task"](task_id, status=status)

    def test_param_change_causes_cache_miss(self, param_key):
        stored_params = _make_dual_params(**{param_key: 0.5})
        input_params = _make_dual_params(**{param_key: 0.9})
        self._create_dual_task(f"test_dual_param_{param_key}", self.vocal_hash, self.acc_hash, stored_params)
        result = find_dual_repair_cache(self.vocal_hash, self.acc_hash, input_params)
        assert result is None, f"改变参数 {param_key} 应导致缓存不命中"


@pytest.mark.parametrize("param_key", sorted(SINGLE_REPAIR_PARAM_KEYS))
class TestEverySingleParamAffectsCache:
    @pytest.fixture(autouse=True)
    def setup(self, fresh_db):
        self.db = fresh_db
        self.create_task = fresh_db["create_task"]
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            self.wav_path = f.name
        _make_wav(self.wav_path)
        with open(self.wav_path, 'rb') as f:
            import hashlib
            self.file_hash = hashlib.sha256(f.read()).hexdigest()
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
        self.create_task(task_id, "test.wav", self.wav_path, params, file_hash=self.file_hash)
        if status == "completed" and output_path:
            self.db["update_task"](task_id, status=status, output_path=output_path)
        elif status:
            self.db["update_task"](task_id, status=status)

    def test_param_change_causes_cache_miss(self, param_key):
        if param_key == "algorithm_version":
            stored_params = _make_single_params(algorithm_version="v3.0")
            input_params = _make_single_params(algorithm_version="v3.1")
        elif param_key == "mastering_style":
            stored_params = _make_single_params(mastering_style="standard")
            input_params = _make_single_params(mastering_style="powerful")
        else:
            stored_params = _make_single_params(**{param_key: 0.5})
            input_params = _make_single_params(**{param_key: 0.9})
        self._create_task(f"test_single_param_{param_key}", stored_params, self.output_path)
        result = find_repair_cache(self.file_hash, input_params)
        assert result is None, f"改变参数 {param_key} 应导致缓存不命中"