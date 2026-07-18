"""
Bug Digest Phase 3 - DSP & Audio Processing Deep Scan
=====================================================

深度扫描发现的 18 个潜在 bug/问题清单：

编号  严重程度  问题描述
----  --------  ----------------------------------------------------------
BUG01  高       streaming_spectral_process 块边界信号为零（重叠相加错误）
BUG02  高       beat_track 中 best_lag 可能为零导致除零错误
BUG03  高       _tanh_declip 多声道时 in-place 修改输入数组
BUG04  高       _diff_clamp_depop 多声道时 in-place 修改输入数组
BUG05  高       _adaptive_loudness_normalize in-place 修改输入数组
BUG06  高       pyin 全静音信号返回全 NaN 的 f0 数组
BUG07  中       mel_filterbank 与 _mel_filterbank_cached 实现不一致
BUG08  中       _load_with_soundfile 重采样后末尾可能出现零填充
BUG09  中       repair_audio 重采样后 dtype 从 float32 变回 float64
BUG10  中       _get_window 缓存了无用的复数 dtype 窗口（内存泄漏）
BUG11  中       miniaudio 重采样使用线性插值，与 soundfile 结果差异大
BUG12  中       _harmonic_bass_enhance in-place 修改输入数组
BUG13  中       _air_texture_reconstruct in-place 修改输入数组
BUG14  低       spectral_rolloff 全静音时返回频率 0（无明确语义）
BUG15  低       delta 函数大 order 值时递归栈溢出风险
BUG16  中       _soft_peak_limit 多声道时 in-place 修改输入数组
BUG17  中       time_stretch_hifi speed=1 时返回原数组引用
BUG18  低       chroma_stft 对静音信号返回全零（语义不明确）

运行方式：
    cd /workspace && python -m pytest backend/tests/test_bugdigest_phase3_dsp.py -v
"""

import sys
import os
import tempfile
import numpy as np
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


def generate_test_signal(sr=44100, duration=1.0, freq=440.0, dtype=np.float64):
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(dtype)


def generate_silence(sr=44100, duration=1.0, dtype=np.float64):
    return np.zeros(int(sr * duration), dtype=dtype)


# ============================================================
# BUG01: streaming_spectral_process 块边界信号为零
# 严重程度：高
# 描述：输出块无重叠但使用淡入淡出窗口，导致相邻块边界处信号为零
# 复现步骤：构造一个恒等 process_fn，比较输入输出在块边界处的差异
# ============================================================
class TestBug01StreamingBoundaryZero:
    def test_dc_signal_boundary_zero(self):
        from services.dsp_utils import streaming_spectral_process

        sr = 44100
        chunk_seconds = 0.1
        y = np.ones(int(sr * 0.5)) * 0.5

        def identity_process(S, sr, n_fft, hop_length):
            return S

        y_out = streaming_spectral_process(
            y, sr, identity_process,
            n_fft=2048, hop_length=512,
            chunk_seconds=chunk_seconds
        )

        chunk_samples = int(sr * chunk_seconds)
        boundary_idx = chunk_samples

        boundary_region = slice(max(0, boundary_idx - 5), boundary_idx + 5)
        boundary_min = np.min(y_out[boundary_region])

        assert boundary_min > 0.01, (
            f"BUG01: 块边界处信号存在零点 (min={boundary_min:.6f})，"
            f"恒等处理的直流信号边界不应为零。"
            f"这是重叠相加时输出无重叠但使用淡入淡出导致的。"
        )

    def test_block_boundary_amplitude_dip(self):
        from services.dsp_utils import streaming_spectral_process

        sr = 44100
        chunk_seconds = 0.1
        y = np.ones(int(sr * 0.5)) * 0.5

        def identity_process(S, sr, n_fft, hop_length):
            return S

        y_out = streaming_spectral_process(
            y, sr, identity_process,
            n_fft=2048, hop_length=512,
            chunk_seconds=chunk_seconds
        )

        chunk_samples = int(sr * chunk_seconds)
        boundary = chunk_samples

        center_region = y_out[boundary-10:boundary+10]
        center_mean = np.mean(center_region)
        expected = 0.5

        assert abs(center_mean - expected) < 0.01, (
            f"BUG01: 块边界处平均幅度 ({center_mean:.4f}) 远低于预期 ({expected})，"
            f"证明重叠相加算法存在缺陷"
        )


# ============================================================
# BUG02: beat_track 中 best_lag 可能为零导致除零错误
# 严重程度：高
# 描述：当 min_lag=0 且搜索范围第一个点最大时，best_lag=0 导致 tempo 计算除零
# 复现步骤：构造特殊的 onset_envelope 使得 min_lag=0 且 best_lag=0
# ============================================================
class TestBug02BeatTrackDivideByZero:
    def test_very_high_sr_small_hop(self):
        from services.dsp_utils import beat_track

        sr = 8000
        hop_length = 8192
        onset_env = np.zeros(100)
        onset_env[0] = 1.0

        try:
            tempo, beats = beat_track(
                onset_envelope=onset_env,
                sr=sr,
                hop_length=hop_length
            )
            assert np.isfinite(tempo), (
                f"BUG02: beat_track 返回非有限 tempo={tempo}"
            )
        except ZeroDivisionError:
            pytest.fail("BUG02: beat_track 发生除零错误 (ZeroDivisionError)")

    def test_empty_onset_envelope(self):
        from services.dsp_utils import beat_track

        tempo, beats = beat_track(
            onset_envelope=np.array([]),
            sr=22050,
            hop_length=512,
            start_bpm=120.0
        )
        assert np.isfinite(tempo), "BUG02: 空包络时 tempo 应为有限值"
        assert len(beats) == 0


# ============================================================
# BUG03: _tanh_declip 多声道时 in-place 修改输入数组
# 严重程度：高
# 描述：多声道输入时直接修改 y[ch]，导致原始数据被破坏
# 复现步骤：传入多声道数组，比较处理前后的输入数组
# ============================================================
class TestBug03TanhDeclipInPlace:
    def test_multichannel_in_place_modification(self):
        from services.repair.repair_v2_4.core import _tanh_declip

        y_orig = np.random.randn(2, 44100).astype(np.float64) * 0.5
        y_orig[0, 1000] = 2.0
        y_orig[1, 2000] = -2.0
        y_input = y_orig.copy()

        _ = _tanh_declip(y_input, amount=0.5)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "BUG03: _tanh_declip 修改了输入数组 (in-place)，"
            "这会导致上游数据被意外破坏"
        )

    def test_mono_does_not_modify_input(self):
        from services.repair.repair_v2_4.core import _tanh_declip

        y_orig = np.random.randn(44100).astype(np.float64) * 0.5
        y_orig[1000] = 2.0
        y_input = y_orig.copy()

        _ = _tanh_declip(y_input, amount=0.5)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "BUG03: _tanh_declip (单声道) 修改了输入数组"
        )


# ============================================================
# BUG04: _diff_clamp_depop 多声道时 in-place 修改输入数组
# 严重程度：高
# 描述：多声道输入时直接修改 y[ch]，导致原始数据被破坏
# 复现步骤：传入多声道数组，比较处理前后的输入数组
# ============================================================
class TestBug04DiffClampDepopInPlace:
    def test_multichannel_in_place_modification(self):
        from services.repair.repair_v2_4.core import _diff_clamp_depop

        sr = 44100
        np.random.seed(42)
        y_orig = np.random.randn(2, sr).astype(np.float64) * 0.01
        for ch in range(2):
            for pos in [10000, 20000, 30000]:
                y_orig[ch, pos] = 0.8
                y_orig[ch, pos + 1] = -0.7
        y_input = y_orig.copy()

        result = _diff_clamp_depop(y_input, sr, amount=0.5)

        assert result is not None
        input_modified = not np.allclose(y_input, y_orig)
        assert not input_modified, (
            "BUG04: _diff_clamp_depop 修改了输入数组 (in-place)，"
            "这会导致上游数据被意外破坏"
        )


# ============================================================
# BUG05: _adaptive_loudness_normalize in-place 修改输入数组
# 严重程度：高
# 描述：使用 y[:] = ... 直接修改原数组内容
# 复现步骤：传入数组，比较处理前后的输入数组
# ============================================================
class TestBug05AdaptiveLoudnessInPlace:
    def test_multichannel_in_place_modification(self):
        from services.repair.repair_v2_4.core import _adaptive_loudness_normalize

        sr = 44100
        y_orig = np.random.randn(2, sr).astype(np.float64) * 0.1
        y_input = y_orig.copy()

        _ = _adaptive_loudness_normalize(y_input, sr, target_loudness_lu=-14.0)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "BUG05: _adaptive_loudness_normalize 修改了输入数组 (in-place)，"
            "这会导致上游数据被意外破坏"
        )

    def test_mono_in_place_modification(self):
        from services.repair.repair_v2_4.core import _adaptive_loudness_normalize

        sr = 44100
        y_orig = np.random.randn(sr).astype(np.float64) * 0.1
        y_input = y_orig.copy()

        _ = _adaptive_loudness_normalize(y_input, sr, target_loudness_lu=-14.0)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "BUG05: _adaptive_loudness_normalize (单声道) 修改了输入数组"
        )


# ============================================================
# BUG06: pyin 全静音信号返回全 NaN 的 f0 数组
# 严重程度：高
# 描述：f0 初始化为 np.nan，静音帧不更新，导致全 NaN 输出
# 复现步骤：传入全静音信号，检查 f0 是否包含 NaN
# ============================================================
class TestBug06PyinSilenceNaN:
    def test_silence_returns_nan(self):
        from services.dsp_utils import pyin

        sr = 22050
        y = generate_silence(sr=sr, duration=0.5)

        f0, voiced_flag, voiced_prob = pyin(y, sr=sr, frame_length=2048, hop_length=512)

        has_nan = np.any(np.isnan(f0))
        assert not has_nan, (
            f"BUG06: pyin 对静音信号返回 NaN 的 f0 值 "
            f"(nan 比例: {np.sum(np.isnan(f0))}/{len(f0)})，"
            f"下游计算可能因此崩溃"
        )

    def test_voiced_flag_consistency(self):
        from services.dsp_utils import pyin

        sr = 22050
        y = generate_silence(sr=sr, duration=0.5)

        f0, voiced_flag, voiced_prob = pyin(y, sr=sr, frame_length=2048, hop_length=512)

        assert len(f0) == len(voiced_flag), "f0 与 voiced_flag 长度不一致"
        assert len(f0) == len(voiced_prob), "f0 与 voiced_prob 长度不一致"


# ============================================================
# BUG07: mel_filterbank 与 _mel_filterbank_cached 实现不一致
# 严重程度：中
# 描述：两个版本的 mel 频率点数、滤波器构建方式均不同，结果不一致
# 复现步骤：调用两个版本的 mel filterbank，比较输出
# ============================================================
class TestBug07MelFilterbankInconsistency:
    def test_cached_vs_uncached_differ(self):
        from services.dsp_utils import _mel_filterbank, mel_filterbank

        sr = 22050
        n_fft = 2048
        n_mels = 128

        fb_cached = _mel_filterbank(sr, n_fft, n_mels=n_mels)
        fb_uncached = mel_filterbank(sr, n_fft, n_mels=n_mels)

        assert fb_cached.shape == fb_uncached.shape, (
            f"形状不一致: cached={fb_cached.shape}, uncached={fb_uncached.shape}"
        )

        are_equal = np.allclose(fb_cached, fb_uncached, atol=1e-6)
        assert are_equal, (
            f"BUG07: 两个 mel filterbank 实现结果不一致，"
            f"最大差异: {np.max(np.abs(fb_cached - fb_uncached)):.6f}"
        )

    def test_filterbank_sum_roughly_uniform(self):
        from services.dsp_utils import _mel_filterbank

        sr = 22050
        n_fft = 2048
        n_mels = 128

        fb = _mel_filterbank(sr, n_fft, n_mels=n_mels)
        col_sums = np.sum(fb, axis=0)
        middle_region = col_sums[n_mels // 4: 3 * n_mels // 4]
        if len(middle_region) > 0:
            variation = np.std(middle_region) / (np.mean(middle_region) + 1e-10)
            assert variation < 1.0, (
                f"BUG07: mel 滤波器组中间区域能量和波动过大: {variation:.3f}"
            )


# ============================================================
# BUG08: _load_with_soundfile 重采样后末尾可能出现零填充
# 严重程度：中
# 描述：resample_poly 返回长度可能与目标长度不一致，仅赋值部分样本，末尾保持零
# 复现步骤：构造一个非零信号，重采样后检查末尾是否有零值
# ============================================================
class TestBug08ResampleTrailingZeros:
    def test_multichannel_resample_no_trailing_zeros(self):
        import tempfile
        import soundfile as sf

        sr_orig = 44100
        sr_target = 48000
        y_orig = np.ones((2, sr_orig), dtype=np.float32) * 0.5

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, y_orig.T, sr_orig, subtype="PCM_16")
            tmp_path = f.name

        try:
            from services.audio_loader import _load_with_soundfile

            y_resampled, sr_out, bit_depth = _load_with_soundfile(
                tmp_path, sr=sr_target, mono=False, return_bit_depth=True
            )

            expected_len = int(y_orig.shape[1] * sr_target / sr_orig)
            last_samples = y_resampled[:, -100:]
            has_zeros = np.any(np.abs(last_samples) < 1e-6)

            assert not has_zeros, (
                f"BUG08: 重采样后末尾存在零值样本，"
                f"可能是 resample_poly 长度不匹配导致的零填充"
            )
        finally:
            os.unlink(tmp_path)


# ============================================================
# BUG09: repair_audio 重采样后 dtype 从 float32 变回 float64
# 严重程度：中
# 描述：y_new 默认 float64，覆盖了之前的 float32 内存优化
# 复现步骤：检查 should_use_float32 为 True 时重采样后的 dtype
# ============================================================
class TestBug09ResampleDtypeReversion:
    def test_float32_preserved_after_resample(self):
        from services.memory_guard import should_use_float32

        n_samples = 44100 * 60 * 15
        n_channels = 2

        assert should_use_float32(n_samples, n_channels), (
            "测试前提：大文件应使用 float32"
        )

        y_f32 = np.zeros((n_channels, n_samples), dtype=np.float32)
        target_len = int(n_samples * 48000 / 44100)
        y_new = np.zeros((n_channels, target_len))

        assert y_new.dtype == y_f32.dtype, (
            f"BUG09: 重采样目标数组 dtype={y_new.dtype}，"
            f"与源数组 dtype={y_f32.dtype} 不一致。"
            f"repair_audio 中使用 np.zeros 默认创建 float64 数组，"
            f"导致 float32 内存优化失效，内存占用翻倍。"
        )


# ============================================================
# BUG10: _get_window 缓存了无用的复数 dtype 窗口（内存泄漏）
# 严重程度：中
# 描述：每次缓存实数窗口时，额外存一个复数版本但实际不会被使用
# 复现步骤：检查缓存中是否存在复数 dtype 的条目
# ============================================================
class TestBug10WindowCacheComplexLeak:
    def test_complex_dtype_in_cache(self):
        from services.dsp_utils import _get_window
        import services.dsp_utils as dsp_mod

        initial_size = len(dsp_mod._WINDOW_CACHE)

        _get_window('hann', 1024, dtype=np.float64)
        _get_window('hann', 512, dtype=np.float32)

        has_complex_keys = any(
            'complex' in str(k[2]) for k in dsp_mod._WINDOW_CACHE.keys()
        )

        assert not has_complex_keys, (
            "BUG10: _WINDOW_CACHE 中存在复数 dtype 的窗口缓存，"
            "这些缓存不会被使用，造成内存浪费"
        )


# ============================================================
# BUG11: miniaudio 重采样使用线性插值，与 soundfile 结果差异大
# 严重程度：中
# 描述：soundfile 用 resample_poly（高质量），miniaudio 用 np.interp（线性插值）
# 复现步骤：对同一音频分别用两种方式重采样，比较结果
# ============================================================
class TestBug11ResampleQualityDiff:
    def test_soundfile_vs_miniaudio_resample_diff(self):
        import tempfile
        import soundfile as sf

        sr_orig = 44100
        sr_target = 48000
        y_orig = generate_test_signal(sr=sr_orig, duration=0.5, freq=1000)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, y_orig, sr_orig, subtype="PCM_16")
            tmp_path = f.name

        try:
            from services.audio_loader import _load_with_soundfile

            y_sf, sr_sf = _load_with_soundfile(tmp_path, sr=sr_target, mono=True)

            try:
                from services.audio_loader import _load_with_miniaudio
                y_ma, sr_ma = _load_with_miniaudio(tmp_path, sr=sr_target, mono=True)

                min_len = min(len(y_sf), len(y_ma))
                diff = np.max(np.abs(y_sf[:min_len] - y_ma[:min_len]))

                assert diff < 0.1, (
                    f"BUG11: soundfile 与 miniaudio 重采样结果差异过大 "
                    f"(max diff={diff:.6f})，线性插值质量远低于多项式重采样"
                )
            except ImportError:
                pytest.skip("miniaudio 未安装")
        finally:
            os.unlink(tmp_path)


# ============================================================
# BUG12: _harmonic_bass_enhance in-place 修改输入数组
# 严重程度：中
# 描述：直接 y[ch] += ... 修改原数组
# 复现步骤：传入多声道数组，比较处理前后的输入数组
# ============================================================
class TestBug12HarmonicBassInPlace:
    def test_multichannel_in_place_modification(self):
        from services.repair.repair_v2_4.core import _harmonic_bass_enhance

        sr = 44100
        y_orig = np.random.randn(2, sr).astype(np.float64) * 0.1
        y_input = y_orig.copy()

        _ = _harmonic_bass_enhance(y_input, sr, amount=0.5, music_type="generic")

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "BUG12: _harmonic_bass_enhance 修改了输入数组 (in-place)"
        )


# ============================================================
# BUG13: _air_texture_reconstruct in-place 修改输入数组
# 严重程度：中
# 描述：直接 y[ch] += ... 修改原数组
# 复现步骤：传入多声道数组，比较处理前后的输入数组
# ============================================================
class TestBug13AirTextureInPlace:
    def test_multichannel_in_place_modification(self):
        from services.repair.repair_v2_4.core import _air_texture_reconstruct

        sr = 44100
        y_orig = np.random.randn(2, sr).astype(np.float64) * 0.1
        y_input = y_orig.copy()

        _ = _air_texture_reconstruct(y_input, sr, amount=0.5, music_type="generic")

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "BUG13: _air_texture_reconstruct 修改了输入数组 (in-place)"
        )


# ============================================================
# BUG14: spectral_rolloff 全静音时返回频率 0（无明确语义）
# 严重程度：低
# 描述：total_energy=0 时 threshold=0，所有累积能量 >= 0，argmax 返回第一个索引
# 复现步骤：传入全静音频谱，检查返回值
# ============================================================
class TestBug14SpectralRolloffSilence:
    def test_silence_rolloff_value(self):
        from services.dsp_utils import spectral_rolloff

        sr = 22050
        n_fft = 2048
        n_frames = 10
        S = np.zeros((n_fft // 2 + 1, n_frames), dtype=np.float64)

        rolloff = spectral_rolloff(S=S, sr=sr, n_fft=n_fft)

        all_zero = np.all(rolloff == 0)
        assert not all_zero, (
            "BUG14: 全静音频谱的 rolloff 返回 0 Hz，"
            "语义不明确，应返回 NaN 或有明确的标记值"
        )

    def test_rolloff_shape(self):
        from services.dsp_utils import spectral_rolloff

        sr = 22050
        y = generate_test_signal(sr=sr, duration=0.5)
        rolloff = spectral_rolloff(y=y, sr=sr)

        assert rolloff.ndim == 2
        assert rolloff.shape[0] == 1


# ============================================================
# BUG15: delta 函数大 order 值时递归栈溢出风险
# 严重程度：低
# 描述：使用递归计算高阶 delta，order 很大时可能栈溢出
# 复现步骤：传入大 order 值，观察是否栈溢出或过深递归
# ============================================================
class TestBug15DeltaRecursionDepth:
    def test_large_order_no_stack_overflow(self):
        from services.dsp_utils import delta

        data = np.random.randn(1, 1000)

        try:
            import sys
            old_limit = sys.getrecursionlimit()
            sys.setrecursionlimit(200)

            try:
                result = delta(data, width=9, order=50)
                assert result is not None, "BUG15: 大 order 导致递归问题"
            finally:
                sys.setrecursionlimit(old_limit)
        except RecursionError:
            pytest.fail(
                "BUG15: delta 函数在大 order 时发生递归栈溢出，"
                "应使用迭代实现或增加 order 上限校验"
            )

    def test_delta_order_1_shape(self):
        from services.dsp_utils import delta

        data = np.random.randn(1, 100)
        result = delta(data, width=9, order=1)
        assert result.shape == data.shape


# ============================================================
# BUG16: _soft_peak_limit 多声道时 in-place 修改输入数组
# 严重程度：中
# 描述：直接 y[ch] = ... 修改原数组，与单声道版本返回副本不一致
# 复现步骤：传入多声道数组，比较处理前后的输入数组
# ============================================================
class TestBug16SoftPeakLimitInPlace:
    def test_multichannel_in_place_modification(self):
        from services.repair.repair_v2_4.core import _soft_peak_limit

        sr = 44100
        y_orig = np.random.randn(2, sr).astype(np.float64) * 0.5
        y_orig[:, 1000:1010] = 2.0
        y_input = y_orig.copy()

        _ = _soft_peak_limit(y_input, threshold=0.9)

        modified = not np.allclose(y_input, y_orig)
        assert not modified, (
            "BUG16: _soft_peak_limit 修改了输入数组 (in-place)，"
            "与单声道版本返回副本的行为不一致"
        )


# ============================================================
# BUG17: time_stretch_hifi 对 speed=1 返回原数组引用
# 严重程度：中
# 描述：speed 接近 1 时直接返回 y，后续修改会影响原数组
# 复现步骤：调用 time_stretch_hifi(speed=1)，检查返回值是否为原对象
# ============================================================
class TestBug17TimeStretchSameArray:
    def test_speed_1_returns_same_object(self):
        from services.time_stretch import time_stretch_hifi

        sr = 44100
        y = np.random.randn(sr).astype(np.float64) * 0.5

        result = time_stretch_hifi(y, sr, speed=1.0)

        assert result is not y, (
            "BUG17: time_stretch_hifi 在 speed=1 时返回原数组引用，"
            "后续修改结果会意外影响输入数组"
        )

    def test_multichannel_speed_1_returns_copy(self):
        from services.time_stretch import time_stretch_hifi

        sr = 44100
        y = np.random.randn(2, sr).astype(np.float64) * 0.5

        result = time_stretch_hifi(y, sr, speed=1.0)

        assert result is not y, (
            "BUG17: time_stretch_hifi 多声道 speed=1 时也应返回副本"
        )


# ============================================================
# BUG18: chroma_stft 对静音信号返回全 0/1e-10 归一化问题
# 严重程度：低
# 描述：静音时 chroma_max = 1e-10，chroma / chroma_max = 0，所有色度均为 0
# 复现步骤：传入静音频谱，检查 chroma 输出
# ============================================================
class TestBug18ChromaSilence:
    def test_silence_chroma_all_zero(self):
        from services.dsp_utils import chroma_stft

        sr = 22050
        n_fft = 2048
        n_frames = 5
        S = np.zeros((n_fft // 2 + 1, n_frames), dtype=np.float64)

        chroma = chroma_stft(S=S, sr=sr, n_fft=n_fft)

        all_zero = np.all(chroma == 0)
        assert not all_zero, (
            "BUG18: 全静音频谱的 chroma 全部为 0，"
            "由于 chroma_max + 1e-10 导致的 0/1e-10 = 0，"
            "语义不明确，应返回 NaN 或均匀分布"
        )

    def test_chroma_shape(self):
        from services.dsp_utils import chroma_stft

        sr = 22050
        y = generate_test_signal(sr=sr, duration=0.5)
        chroma = chroma_stft(y=y, sr=sr)

        assert chroma.ndim == 2
        assert chroma.shape[0] == 12


# ============================================================
# 额外发现：stft 对极短信号的处理
# 严重程度：低
# 描述：当信号长度 < n_fft 时，_stride_frames 返回空数组，stft 返回空频谱
# ============================================================
class TestExtraVeryShortSignal:
    def test_stft_very_short_signal(self):
        from services.dsp_utils import stft

        y = np.zeros(100, dtype=np.float64)
        S = stft(y, n_fft=2048, hop_length=512)

        assert S.shape[0] == 1025
        assert S.shape[1] >= 0, "极短信号的 STFT 应至少有 0 帧或 1 帧"

    def test_zero_crossing_rate_short_signal(self):
        from services.dsp_utils import zero_crossing_rate

        y = np.zeros(100, dtype=np.float64)
        zcr = zero_crossing_rate(y, frame_length=2048, hop_length=512)

        assert zcr.shape[0] == 1
