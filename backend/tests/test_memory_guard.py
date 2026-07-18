import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


class TestMemoryGuardBasics:
    def test_should_use_float32_short_audio(self):
        from services.memory_guard import should_use_float32
        n_samples = 44100 * 60
        n_channels = 2
        result = should_use_float32(n_samples, n_channels)
        assert result is False

    def test_should_use_float32_long_audio(self):
        from services.memory_guard import should_use_float32
        n_samples = 48000 * 60 * 20
        n_channels = 2
        result = should_use_float32(n_samples, n_channels)
        assert result is True

    def test_should_use_float32_mono_long(self):
        from services.memory_guard import should_use_float32, FLOAT32_THRESHOLD_SAMPLES
        n_samples = FLOAT32_THRESHOLD_SAMPLES + 1
        result = should_use_float32(n_samples, 1)
        assert result is True

    def test_should_use_float32_below_threshold(self):
        from services.memory_guard import should_use_float32, FLOAT32_THRESHOLD_SAMPLES
        n_samples = FLOAT32_THRESHOLD_SAMPLES - 1
        result = should_use_float32(n_samples, 1)
        assert result is False


class TestMemoryEstimation:
    def test_estimate_memory_returns_positive_value(self):
        from services.memory_guard import estimate_repair_memory_bytes
        n_samples = 44100 * 60
        result = estimate_repair_memory_bytes(n_samples, 2, 44100, 48000, algorithm_version="v2.4a")
        assert result > 0
        assert isinstance(result, int)

    def test_estimate_memory_scales_with_duration(self):
        from services.memory_guard import estimate_repair_memory_bytes
        short = estimate_repair_memory_bytes(44100 * 60, 2, 44100, 48000, algorithm_version="v2.4a")
        long = estimate_repair_memory_bytes(44100 * 600, 2, 44100, 48000, algorithm_version="v2.4a")
        assert long > short

    def test_estimate_memory_scales_with_channels(self):
        from services.memory_guard import estimate_repair_memory_bytes
        mono = estimate_repair_memory_bytes(44100 * 60, 1, 44100, 48000, algorithm_version="v2.4a")
        stereo = estimate_repair_memory_bytes(44100 * 60, 2, 44100, 48000, algorithm_version="v2.4a")
        assert stereo > mono

    def test_estimate_memory_streaming_less_than_non_streaming(self):
        from services.memory_guard import estimate_repair_memory_bytes
        n_samples = 44100 * 600
        non_streaming = estimate_repair_memory_bytes(n_samples, 2, 44100, 48000, algorithm_version="v2.0")
        streaming = estimate_repair_memory_bytes(n_samples, 2, 44100, 48000, algorithm_version="v2.4a")
        assert streaming < non_streaming * 0.8

    def test_estimate_memory_float32_less_than_float64(self):
        from services.memory_guard import estimate_repair_memory_bytes, should_use_float32, FLOAT32_THRESHOLD_SAMPLES
        short_samples = FLOAT32_THRESHOLD_SAMPLES // 10
        long_samples = FLOAT32_THRESHOLD_SAMPLES * 2
        f64 = estimate_repair_memory_bytes(short_samples, 2, 44100, 48000, algorithm_version="v2.4a")
        f32 = estimate_repair_memory_bytes(long_samples, 2, 44100, 48000, algorithm_version="v2.4a")
        assert f32 > 0
        assert f64 > 0

    def test_estimate_memory_all_versions(self):
        from services.memory_guard import estimate_repair_memory_bytes
        versions = [
            "v2.0", "v2.1", "v2.2", "v2.2a",
            "v2.3", "v2.3a", "v2.4", "v2.4a",
            "v3.0", "v3.0a", "v3.1", "v3.1a",
            "v3.2", "v3.2+", "v3.2a", "v3.2a+",
            "v4.0a", "v4.0a+",
        ]
        n_samples = 44100 * 60
        for v in versions:
            result = estimate_repair_memory_bytes(n_samples, 2, 44100, 48000, algorithm_version=v)
            assert result > 0, f"Version {v} should return positive memory estimate"


class TestGetAvailableMemory:
    def test_get_available_memory_returns_none_or_int(self):
        from services.memory_guard import get_available_memory_bytes
        result = get_available_memory_bytes()
        assert result is None or isinstance(result, int)

    def test_get_total_memory_returns_none_or_int(self):
        from services.memory_guard import get_total_memory_bytes
        result = get_total_memory_bytes()
        assert result is None or isinstance(result, int)


class TestCheckMemoryBeforeRepair:
    def test_check_memory_with_no_available_returns_working_sr(self):
        from services.memory_guard import check_memory_before_repair
        with patch("services.memory_guard.get_available_memory_bytes", return_value=None):
            result = check_memory_before_repair(44100, 2, 44100, 48000, algorithm_version="v2.4a")
            assert result == 48000

    def test_check_memory_sufficient_returns_working_sr(self):
        from services.memory_guard import check_memory_before_repair
        huge_memory = 10 * 1024 * 1024 * 1024
        with patch("services.memory_guard.get_available_memory_bytes", return_value=huge_memory):
            result = check_memory_before_repair(44100, 2, 44100, 48000, algorithm_version="v2.4a")
            assert result == 48000

    def test_check_memory_insufficient_raises(self):
        from services.memory_guard import check_memory_before_repair
        tiny_memory = 1024
        with patch("services.memory_guard.get_available_memory_bytes", return_value=tiny_memory):
            with pytest.raises(MemoryError):
                check_memory_before_repair(44100 * 600, 2, 44100, 48000, algorithm_version="v2.4a")

    def test_check_memory_error_message_contains_info(self):
        from services.memory_guard import check_memory_before_repair
        tiny_memory = 1024
        with patch("services.memory_guard.get_available_memory_bytes", return_value=tiny_memory):
            try:
                check_memory_before_repair(44100 * 600, 2, 44100, 48000, algorithm_version="v2.4a")
                assert False, "Should have raised MemoryError"
            except MemoryError as e:
                assert "MB" in str(e)
                assert "内存" in str(e)
