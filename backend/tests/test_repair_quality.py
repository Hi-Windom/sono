import numpy as np
import pytest
from pathlib import Path

from backend.tests.conftest import (
    generate_pure_sine,
    generate_multi_tone,
    generate_speech_like,
    generate_with_pops,
    generate_with_clipping,
    write_temp_wav,
    compute_thd,
    compute_scale_adjusted_snr,
    compute_hf_noise,
    count_flat_top_samples,
    compute_per_step_snr,
    benchmark_step,
    SR,
)


def _run_repair_and_read(repair_fn, input_signal, default_params, tmp_wav_dir):
    input_path = write_temp_wav(input_signal, SR, tmp_wav_dir)
    output_path = str(tmp_wav_dir / "output.wav")

    try:
        import soundfile as sf
    except ImportError:
        from scipy.io import wavfile

    repair_fn(input_path, output_path, default_params)

    try:
        y_out, sr_out = sf.read(output_path)
    except (ImportError, NameError):
        from scipy.io import wavfile as _wv
        sr_out, y_out = _wv.read(output_path)
        y_out = y_out.astype(np.float64) / 32768.0

    if y_out.ndim > 1:
        y_out = y_out[:, 0]

    return y_out, sr_out


class TestRepairQualityBaseline:

    def test_pure_sine_no_artifacts(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_pure_sine(sr=SR, freq=440.0, duration=2.0, amplitude=0.5)
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        thd = compute_thd(y_out, sr_out, 440.0)
        assert thd < -20.0, (
            f"[{repair_version}] THD too high: {thd:.1f} dB (threshold: -20 dB)"
        )

    def test_no_hard_clipping(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_multi_tone(sr=SR, duration=2.0)
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        flat_count = count_flat_top_samples(y_out, threshold=1e-6)
        flat_ratio = flat_count / len(y_out)
        assert flat_ratio < 0.01, (
            f"[{repair_version}] Flat-top ratio: {flat_ratio:.4f} ({flat_count}/{len(y_out)})"
        )

    def test_no_high_frequency_noise(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_speech_like(sr=SR, duration=2.0)
        input_hf = compute_hf_noise(y, SR, 5000, 16000)
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        output_hf = compute_hf_noise(y_out, sr_out, 5000, 16000)
        if input_hf > 1e-10:
            hf_ratio = output_hf / input_hf
        else:
            hf_ratio = output_hf / 1e-10
        assert hf_ratio < 10.0, (
            f"[{repair_version}] HF noise ratio: {hf_ratio:.1f}x (in: {input_hf:.2e}, out: {output_hf:.2e})"
        )

    def test_scale_adjusted_snr(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_speech_like(sr=SR, duration=2.0)
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        if sr_out != SR:
            from scipy.signal import resample_poly
            y_out = resample_poly(y_out, SR, sr_out)
        min_len = min(len(y), len(y_out))
        snr = compute_scale_adjusted_snr(y[:min_len], y_out[:min_len])
        assert snr > 5.0, (
            f"[{repair_version}] SNR too low: {snr:.1f} dB"
        )

    def test_output_finite(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_multi_tone(sr=SR, duration=2.0)
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        assert np.all(np.isfinite(y_out)), (
            f"[{repair_version}] Output contains NaN or Inf"
        )

    def test_peak_level_valid(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_speech_like(sr=SR, duration=2.0) * 0.9
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        peak = np.max(np.abs(y_out))
        assert peak <= 1.0, (
            f"[{repair_version}] Peak exceeds 1.0: {peak:.4f}"
        )

    def test_dc_offset_small(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_speech_like(sr=SR, duration=2.0)
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        dc = np.abs(np.mean(y_out))
        assert dc < 0.01, (
            f"[{repair_version}] DC offset too large: {dc:.4f}"
        )

    def test_output_length_preserved(self, repair_fn, default_params, tmp_wav_dir, repair_version):
        y = generate_speech_like(sr=SR, duration=2.0)
        y_out, sr_out = _run_repair_and_read(repair_fn, y, default_params, tmp_wav_dir)
        duration_in = len(y) / SR
        duration_out = len(y_out) / sr_out
        ratio = duration_out / duration_in
        assert 0.95 < ratio < 1.05, (
            f"[{repair_version}] Duration ratio: {ratio:.3f} (in: {duration_in:.2f}s, out: {duration_out:.2f}s)"
        )


class TestV22aPerStepQuality:

    @pytest.fixture(autouse=True)
    def import_v22a_functions(self):
        from services.repair.repair_v2_2a.core import (
            _simple_declip,
            _simple_depop,
            _simple_depop_1d,
            _transparent_compress,
            _soft_peak_limit,
            _loudness_normalize,
            _remove_dc,
        )
        self._simple_declip = _simple_declip
        self._simple_depop = _simple_depop
        self._simple_depop_1d = _simple_depop_1d
        self._transparent_compress = _transparent_compress
        self._soft_peak_limit = _soft_peak_limit
        self._loudness_normalize = _loudness_normalize
        self._remove_dc = _remove_dc

    def test_declip_snr(self):
        y = generate_with_clipping(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._simple_declip, 0.5)
        assert snr > 20.0, f"declip SNR too low: {snr:.1f} dB"

    def test_depop_snr(self):
        y = generate_with_pops(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._simple_depop, SR, 0.5)
        assert snr > 10.0, f"depop SNR too low: {snr:.1f} dB"

    def test_compress_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._transparent_compress, SR, 0.5)
        assert snr > 40.0, (
            f"compress SNR too low: {snr:.1f} dB. "
            f"Global constant gain should be near-lossless."
        )

    def test_peak_limit_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0) * 0.8
        snr = compute_per_step_snr(y, self._soft_peak_limit, 0.9)
        assert snr > 30.0, f"peak_limit SNR too low: {snr:.1f} dB"

    def test_loudness_norm_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._loudness_normalize, SR, -16.0)
        assert snr > 60.0, (
            f"loudness_normalize SNR too low: {snr:.1f} dB. "
            f"Pure gain operation should have SNR > 80 dB."
        )

    def test_dc_remove_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._remove_dc, SR)
        assert snr > 60.0, f"dc_remove SNR too low: {snr:.1f} dB"

    def test_depop_no_large_window_replacement(self):
        y = generate_with_pops(sr=SR, duration=2.0)
        y_out = self._simple_depop(y, SR, 0.5)
        y_out = y_out.astype(np.float64).flatten()
        y_in = y.astype(np.float64).flatten()
        min_len = min(len(y_in), len(y_out))
        diff = np.abs(y_out[:min_len] - y_in[:min_len])
        changed = diff > 1e-8
        if not np.any(changed):
            pytest.skip("No pops detected in test signal")

        changed_indices = np.where(changed)[0]
        if len(changed_indices) == 0:
            return

        gaps = np.diff(changed_indices)
        max_run = 1
        current_run = 1
        for g in gaps:
            if g == 1:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1

        assert max_run <= 5, (
            f"depop replaced {max_run} consecutive samples. "
            f"Large-window replacement indicates cosine/linear interpolation."
        )

    def test_compress_is_global_gain(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        y_out = self._transparent_compress(y, SR, 0.5)

        y_64 = y.astype(np.float64).flatten()
        y_out_64 = y_out.astype(np.float64).flatten()
        min_len = min(len(y_64), len(y_out_64))
        y_64 = y_64[:min_len]
        y_out_64 = y_out_64[:min_len]

        nonzero = np.abs(y_64) > 1e-10
        if not np.any(nonzero):
            pytest.skip("Signal too quiet for gain ratio test")

        ratios = y_out_64[nonzero] / y_64[nonzero]
        ratio_std = np.std(ratios)
        ratio_mean = np.mean(ratios)

        assert ratio_std / (abs(ratio_mean) + 1e-10) < 0.01, (
            f"compress gain varies: mean={ratio_mean:.6f}, std={ratio_std:.6f}. "
            f"Time-varying gain = AM modulation = audible noise."
        )

    def test_declip_uses_soft_clipping(self):
        y = generate_with_clipping(sr=SR, duration=2.0)
        y_out = self._simple_declip(y, 0.5).astype(np.float64).flatten()
        y_in = y.astype(np.float64).flatten()
        flat_before = count_flat_top_samples(y_in, threshold=1e-6) / len(y_in)
        flat_after = count_flat_top_samples(y_out, threshold=1e-6) / len(y_out)
        assert flat_after <= flat_before, (
            f"declip increased flat-top ratio: before={flat_before:.4f}, after={flat_after:.4f}. "
            f"Declip should reduce flat-top samples, not increase them."
        )

    def test_peak_limit_uses_soft_clipping(self):
        y = generate_speech_like(sr=SR, duration=2.0) * 1.2
        y_out = self._soft_peak_limit(y, 0.9).astype(np.float64).flatten()
        y_in = y.astype(np.float64).flatten()
        flat_before = count_flat_top_samples(y_in, threshold=1e-6) / len(y_in)
        flat_after = count_flat_top_samples(y_out, threshold=1e-6) / len(y_out)
        assert flat_after <= flat_before + 0.001, (
            f"peak_limit increased flat-top ratio: before={flat_before:.4f}, after={flat_after:.4f}. "
            f"Soft peak limit should not introduce new flat-top samples."
        )

    def test_loudness_norm_is_constant_gain(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        y_out = self._loudness_normalize(y, SR, -16.0)

        y_64 = y.astype(np.float64).flatten()
        y_out_64 = y_out.astype(np.float64).flatten()
        min_len = min(len(y_64), len(y_out_64))
        y_64 = y_64[:min_len]
        y_out_64 = y_out_64[:min_len]

        nonzero = np.abs(y_64) > 1e-10
        if not np.any(nonzero):
            pytest.skip("Signal too quiet")

        ratios = y_out_64[nonzero] / y_64[nonzero]
        ratio_std = np.std(ratios)
        ratio_mean = np.mean(ratios)
        cv = ratio_std / (abs(ratio_mean) + 1e-10)

        assert cv < 0.001, (
            f"loudness_norm gain varies: cv={cv:.6f}. "
            f"Should be pure constant gain."
        )

    def test_dc_remove_reduces_dc(self):
        y = generate_speech_like(sr=SR, duration=2.0) + 0.05
        y_out = self._remove_dc(y, SR)
        dc_before = np.abs(np.mean(y.astype(np.float64).flatten()))
        dc_after = np.abs(np.mean(y_out.astype(np.float64).flatten()))
        assert dc_after < dc_before, (
            f"dc_remove did not reduce DC: before={dc_before:.6f}, after={dc_after:.6f}"
        )


class TestV23PerStepQuality:

    @pytest.fixture(autouse=True)
    def import_v23_functions(self):
        from services.repair.repair_v2_3.core import (
            _tanh_declip,
            _diff_clamp_depop,
            _global_loudness_normalize,
            _transparent_multiband_compress,
            _soft_peak_limit,
            _soft_transient_limit,
        )
        self._tanh_declip = _tanh_declip
        self._diff_clamp_depop = _diff_clamp_depop
        self._global_loudness_normalize = _global_loudness_normalize
        self._transparent_multiband_compress = _transparent_multiband_compress
        self._soft_peak_limit = _soft_peak_limit
        self._soft_transient_limit = _soft_transient_limit

    def test_declip_snr(self):
        y = generate_with_clipping(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._tanh_declip, 0.5)
        assert snr > 20.0, f"declip SNR too low: {snr:.1f} dB"

    def test_depop_snr(self):
        y = generate_with_pops(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._diff_clamp_depop, SR, 0.5)
        assert snr > 10.0, f"depop SNR too low: {snr:.1f} dB"

    def test_transient_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        snr = compute_per_step_snr(y, self._soft_transient_limit, SR, 0.5)
        assert snr > 15.0, f"transient SNR too low: {snr:.1f} dB"

    def test_loudness_norm_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        snr = compute_per_step_snr(y, self._global_loudness_normalize, SR, -16.0)
        assert snr > 60.0, (
            f"loudness_normalize SNR too low: {snr:.1f} dB. "
            f"Pure gain operation should have SNR > 80 dB."
        )

    def test_compress_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        snr = compute_per_step_snr(y, self._transparent_multiband_compress, SR, 0.5, "generic")
        assert snr > 30.0, f"compress SNR too low: {snr:.1f} dB"

    def test_peak_limit_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0) * 0.8
        snr = compute_per_step_snr(y, self._soft_peak_limit, 0.9)
        assert snr > 30.0, f"peak_limit SNR too low: {snr:.1f} dB"

    def test_declip_uses_soft_clipping(self):
        y = generate_with_clipping(sr=SR, duration=2.0)
        y_out = self._tanh_declip(y, 0.5).astype(np.float64).flatten()
        y_in = y.astype(np.float64).flatten()
        flat_before = count_flat_top_samples(y_in, threshold=1e-6) / len(y_in)
        flat_after = count_flat_top_samples(y_out, threshold=1e-6) / len(y_out)
        assert flat_after <= flat_before, (
            f"declip increased flat-top ratio: before={flat_before:.4f}, after={flat_after:.4f}"
        )

    def test_depop_no_large_window_replacement(self):
        y = generate_with_pops(sr=SR, duration=2.0)
        y_out = self._diff_clamp_depop(y, SR, 0.5)
        y_out = y_out.astype(np.float64).flatten()
        y_in = y.astype(np.float64).flatten()
        min_len = min(len(y_in), len(y_out))
        diff = np.abs(y_out[:min_len] - y_in[:min_len])
        changed = diff > 1e-8
        if not np.any(changed):
            pytest.skip("No pops detected in test signal")
        changed_indices = np.where(changed)[0]
        if len(changed_indices) == 0:
            return
        gaps = np.diff(changed_indices)
        max_run = 1
        current_run = 1
        for g in gaps:
            if g == 1:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1
        assert max_run <= 2, (
            f"depop replaced {max_run} consecutive samples. "
            f"Iron law 3: max 2 consecutive samples allowed."
        )

    def test_transient_uses_constant_gain(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        y_out = self._soft_transient_limit(y, SR, 0.5)
        y_64 = y.astype(np.float64).flatten()
        y_out_64 = y_out.astype(np.float64).flatten()
        min_len = min(len(y_64), len(y_out_64))
        y_64 = y_64[:min_len]
        y_out_64 = y_out_64[:min_len]
        nonzero = np.abs(y_64) > 1e-10
        if not np.any(nonzero):
            pytest.skip("Signal too quiet for gain ratio test")
        ratios = y_out_64[nonzero] / y_64[nonzero]
        ratio_std = np.std(ratios)
        ratio_mean = np.mean(ratios)
        assert ratio_std / (abs(ratio_mean) + 1e-10) < 0.05, (
            f"transient gain varies: mean={ratio_mean:.6f}, std={ratio_std:.6f}. "
            f"Time-varying gain = AM modulation."
        )

    def test_loudness_norm_is_constant_gain(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        y_out = self._global_loudness_normalize(y, SR, -16.0)
        y_64 = y.astype(np.float64).flatten()
        y_out_64 = y_out.astype(np.float64).flatten()
        min_len = min(len(y_64), len(y_out_64))
        y_64 = y_64[:min_len]
        y_out_64 = y_out_64[:min_len]
        nonzero = np.abs(y_64) > 1e-10
        if not np.any(nonzero):
            pytest.skip("Signal too quiet")
        ratios = y_out_64[nonzero] / y_64[nonzero]
        ratio_std = np.std(ratios)
        ratio_mean = np.mean(ratios)
        cv = ratio_std / (abs(ratio_mean) + 1e-10)
        assert cv < 0.001, (
            f"loudness_norm gain varies: cv={cv:.6f}. "
            f"Should be pure constant gain."
        )

    def test_compress_is_global_gain(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        y_out = self._transparent_multiband_compress(y, SR, 0.5, "generic")
        y_64 = y.astype(np.float64).flatten()
        y_out_64 = y_out.astype(np.float64).flatten()
        min_len = min(len(y_64), len(y_out_64))
        y_64 = y_64[:min_len]
        y_out_64 = y_out_64[:min_len]
        nonzero = np.abs(y_64) > 1e-10
        if not np.any(nonzero):
            pytest.skip("Signal too quiet for gain ratio test")
        ratios = y_out_64[nonzero] / y_64[nonzero]
        ratio_std = np.std(ratios)
        ratio_mean = np.mean(ratios)
        assert ratio_std / (abs(ratio_mean) + 1e-10) < 0.05, (
            f"compress gain varies: mean={ratio_mean:.6f}, std={ratio_std:.6f}. "
            f"Multiband compress CV should be < 5%."
        )

    def test_peak_limit_uses_soft_clipping(self):
        y = generate_speech_like(sr=SR, duration=2.0) * 1.2
        y_out = self._soft_peak_limit(y, 0.9).astype(np.float64).flatten()
        y_in = y.astype(np.float64).flatten()
        flat_before = count_flat_top_samples(y_in, threshold=1e-6) / len(y_in)
        flat_after = count_flat_top_samples(y_out, threshold=1e-6) / len(y_out)
        assert flat_after <= flat_before + 0.001, (
            f"peak_limit increased flat-top ratio: before={flat_before:.4f}, after={flat_after:.4f}"
        )


class TestV23aPerStepQuality:

    @pytest.fixture(autouse=True)
    def import_v23a_functions(self):
        from services.repair.repair_v2_3a.core import (
            _spectral_denoise,
            _de_ess,
        )
        self._spectral_denoise = _spectral_denoise
        self._de_ess = _de_ess

    def test_spectral_denoise_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._spectral_denoise, SR, 0.3)
        assert snr > 10.0, f"spectral_denoise SNR too low: {snr:.1f} dB"

    def test_de_ess_snr(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        snr = compute_per_step_snr(y, self._de_ess, SR, 0.3)
        assert snr > 15.0, f"de_ess SNR too low: {snr:.1f} dB"

    def test_de_ess_is_constant_gain(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        y_out = self._de_ess(y, SR, 0.3)
        y_64 = y.astype(np.float64).flatten()
        y_out_64 = y_out.astype(np.float64).flatten()
        min_len = min(len(y_64), len(y_out_64))
        y_64 = y_64[:min_len]
        y_out_64 = y_out_64[:min_len]
        nonzero = np.abs(y_64) > 1e-10
        if not np.any(nonzero):
            pytest.skip("Signal too quiet")
        ratios = y_out_64[nonzero] / y_64[nonzero]
        ratio_std = np.std(ratios)
        ratio_mean = np.mean(ratios)
        assert ratio_std / (abs(ratio_mean) + 1e-10) < 0.05, (
            f"de_ess gain varies: mean={ratio_mean:.6f}, std={ratio_std:.6f}. "
            f"Should use global constant attenuation."
        )


class TestV23aResample:

    def test_v23a_upsample_to_48k(self, tmp_wav_dir):
        from services.repair.repair_v2_3a import repair_audio
        from services.audio_repair import ALGORITHM_VERSIONS
        y = generate_speech_like(sr=22050, duration=1.0)
        input_path = write_temp_wav(y, 22050, tmp_wav_dir)
        output_path = str(tmp_wav_dir / "output_v23a.wav")
        params = dict(ALGORITHM_VERSIONS["v2.3a"]["default_params"])
        repair_audio(input_path, output_path, params)
        import soundfile as sf
        y_out, sr_out = sf.read(output_path)
        assert sr_out == 48000, f"v2.3a output sr should be 48000, got {sr_out}"

    def test_v23a_output_ignores_sample_rate(self, tmp_wav_dir):
        from services.repair.repair_v2_3a import repair_audio
        from services.audio_repair import ALGORITHM_VERSIONS
        y = generate_speech_like(sr=44100, duration=1.0)
        input_path = write_temp_wav(y, 44100, tmp_wav_dir)
        output_path = str(tmp_wav_dir / "output_v23a_48k.wav")
        params = dict(ALGORITHM_VERSIONS["v2.3a"]["default_params"])
        params["sample_rate"] = 22050
        repair_audio(input_path, output_path, params)
        import soundfile as sf
        y_out, sr_out = sf.read(output_path)
        assert sr_out == 48000, f"v2.3a output sr should be working_sr=48000, got {sr_out}"

    def test_v23a_no_resample_when_same(self, tmp_wav_dir):
        from services.repair.repair_v2_3a import repair_audio
        from services.audio_repair import ALGORITHM_VERSIONS
        y = generate_speech_like(sr=48000, duration=1.0)
        input_path = write_temp_wav(y, 48000, tmp_wav_dir)
        output_path = str(tmp_wav_dir / "output_v23a_native.wav")
        params = dict(ALGORITHM_VERSIONS["v2.3a"]["default_params"])
        repair_audio(input_path, output_path, params)
        import soundfile as sf
        y_out, sr_out = sf.read(output_path)
        assert sr_out == 48000, f"v2.3a output sr should stay 48000, got {sr_out}"

    def test_v23_upsample_to_48k(self, tmp_wav_dir):
        import unittest.mock as mock
        import os
        from services.repair.repair_v2_3 import repair_audio
        from services.audio_repair import ALGORITHM_VERSIONS
        y = generate_speech_like(sr=44100, duration=1.0)
        input_path = write_temp_wav(y, 44100, tmp_wav_dir)
        output_path = str(tmp_wav_dir / "output_v23.wav")
        params = dict(ALGORITHM_VERSIONS["v2.3"]["default_params"])
        with mock.patch.dict(os.environ, {"MOBILE_MODE": "0"}):
            with mock.patch("config.MOBILE_MODE", False):
                repair_audio(input_path, output_path, params)
        import soundfile as sf
        y_out, sr_out = sf.read(output_path)
        assert sr_out == 48000, f"v2.3 output sr should be 48000, got {sr_out}"


class TestV23Performance:

    @pytest.fixture(autouse=True)
    def import_v23_functions(self):
        from services.repair.repair_v2_3.core import (
            _tanh_declip,
            _diff_clamp_depop,
            _global_loudness_normalize,
            _transparent_multiband_compress,
            _soft_peak_limit,
            _soft_transient_limit,
        )
        self._tanh_declip = _tanh_declip
        self._diff_clamp_depop = _diff_clamp_depop
        self._global_loudness_normalize = _global_loudness_normalize
        self._transparent_multiband_compress = _transparent_multiband_compress
        self._soft_peak_limit = _soft_peak_limit
        self._soft_transient_limit = _soft_transient_limit

    def test_declip_performance(self):
        y = generate_with_clipping(sr=SR, duration=2.0).reshape(1, -1)
        elapsed = benchmark_step(self._tanh_declip, y, 0.5)
        assert elapsed < 2.0, f"declip too slow: {elapsed:.3f}s"

    def test_depop_performance(self):
        y = generate_with_pops(sr=SR, duration=2.0).reshape(1, -1)
        elapsed = benchmark_step(self._diff_clamp_depop, y, SR, 0.5)
        assert elapsed < 2.0, f"depop too slow: {elapsed:.3f}s"

    def test_loudness_norm_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        elapsed = benchmark_step(self._global_loudness_normalize, y, SR, -16.0)
        assert elapsed < 2.0, f"loudness_norm too slow: {elapsed:.3f}s"

    def test_compress_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        elapsed = benchmark_step(self._transparent_multiband_compress, y, SR, 0.5, "generic")
        assert elapsed < 2.0, f"compress too slow: {elapsed:.3f}s"

    def test_peak_limit_performance(self):
        y = (generate_speech_like(sr=SR, duration=2.0) * 0.8).reshape(1, -1)
        elapsed = benchmark_step(self._soft_peak_limit, y, 0.9)
        assert elapsed < 2.0, f"peak_limit too slow: {elapsed:.3f}s"

    def test_transient_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0).reshape(1, -1)
        elapsed = benchmark_step(self._soft_transient_limit, y, SR, 0.5)
        assert elapsed < 2.0, f"transient too slow: {elapsed:.3f}s"


class TestV23aPerformance:

    @pytest.fixture(autouse=True)
    def import_v23a_functions(self):
        from services.repair.repair_v2_3a.core import (
            _simple_declip,
            _simple_depop,
            _spectral_denoise,
            _de_ess,
            _loudness_normalize,
            _transparent_compress,
            _soft_peak_limit,
        )
        self._simple_declip = _simple_declip
        self._simple_depop = _simple_depop
        self._spectral_denoise = _spectral_denoise
        self._de_ess = _de_ess
        self._loudness_normalize = _loudness_normalize
        self._transparent_compress = _transparent_compress
        self._soft_peak_limit = _soft_peak_limit

    def test_declip_performance(self):
        y = generate_with_clipping(sr=SR, duration=2.0)
        elapsed = benchmark_step(self._simple_declip, y, 0.5)
        assert elapsed < 2.0, f"declip too slow: {elapsed:.3f}s"

    def test_depop_performance(self):
        y = generate_with_pops(sr=SR, duration=2.0)
        elapsed = benchmark_step(self._simple_depop, y, SR, 0.5)
        assert elapsed < 2.0, f"depop too slow: {elapsed:.3f}s"

    def test_spectral_denoise_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        elapsed = benchmark_step(self._spectral_denoise, y, SR, 0.3)
        assert elapsed < 5.0, f"spectral_denoise too slow: {elapsed:.3f}s"

    def test_de_ess_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        elapsed = benchmark_step(self._de_ess, y, SR, 0.3)
        assert elapsed < 2.0, f"de_ess too slow: {elapsed:.3f}s"

    def test_loudness_norm_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        elapsed = benchmark_step(self._loudness_normalize, y, SR, -16.0)
        assert elapsed < 2.0, f"loudness_norm too slow: {elapsed:.3f}s"

    def test_compress_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0)
        elapsed = benchmark_step(self._transparent_compress, y, SR, 0.5)
        assert elapsed < 2.0, f"compress too slow: {elapsed:.3f}s"

    def test_peak_limit_performance(self):
        y = generate_speech_like(sr=SR, duration=2.0) * 0.8
        elapsed = benchmark_step(self._soft_peak_limit, y, 0.9)
        assert elapsed < 2.0, f"peak_limit too slow: {elapsed:.3f}s"


class TestIstftPerformance:

    def test_istft_performance(self):
        from services.dsp_utils import stft, istft
        y = generate_speech_like(sr=SR, duration=5.0)
        S = stft(y, n_fft=2048, hop_length=512)
        elapsed = benchmark_step(istft, S, 512, len(y))
        assert elapsed < 1.0, f"istft too slow: {elapsed:.3f}s"


class TestMemoryGuard:

    def test_estimate_memory(self):
        from services.memory_guard import estimate_repair_memory_bytes
        estimated = estimate_repair_memory_bytes(
            n_samples=48000 * 60,
            n_channels=2,
            sr=44100,
            working_sr=48000,
        )
        assert estimated > 0, "estimated memory should be positive"

    def test_check_memory_passes(self):
        from services.memory_guard import check_memory_before_repair
        result = check_memory_before_repair(
            n_samples=48000,
            n_channels=2,
            sr=44100,
            working_sr=48000,
        )
        assert result == 48000, f"short audio should pass at full working_sr, got {result}"

    def test_check_memory_raises_on_low_memory(self):
        from unittest.mock import patch
        from services.memory_guard import check_memory_before_repair
        with patch("services.memory_guard.get_available_memory_bytes", return_value=100 * 1024 * 1024):
            with pytest.raises(MemoryError):
                check_memory_before_repair(
                    n_samples=48000 * 300,
                    n_channels=2,
                    sr=44100,
                    working_sr=48000,
                )

    def test_check_memory_raises_on_insufficient(self):
        from unittest.mock import patch
        from services.memory_guard import check_memory_before_repair
        with patch("services.memory_guard.get_available_memory_bytes", return_value=10 * 1024 * 1024):
            with pytest.raises(MemoryError):
                check_memory_before_repair(
                    n_samples=48000 * 600,
                    n_channels=2,
                    sr=44100,
                    working_sr=48000,
                )

    def test_stft_chunked_matches_stft(self):
        from services.dsp_utils import stft, stft_chunked
        y = generate_speech_like(sr=SR, duration=2.0)
        S_full = stft(y, n_fft=2048, hop_length=512)
        S_chunked = stft_chunked(y, n_fft=2048, hop_length=512, chunk_frames=256)
        np.testing.assert_allclose(S_full, S_chunked, rtol=1e-10, atol=1e-12)

    def test_istft_chunked_matches_istft(self):
        from services.dsp_utils import stft, istft, istft_chunked
        y = generate_speech_like(sr=SR, duration=2.0)
        S = stft(y, n_fft=2048, hop_length=512)
        y_full = istft(S, hop_length=512, length=len(y))
        y_chunked = istft_chunked(S, hop_length=512, length=len(y), chunk_frames=256)
        np.testing.assert_allclose(y_full, y_chunked, rtol=1e-10, atol=1e-12)

    def test_streaming_spectral_process_matches_full(self):
        from services.dsp_utils import stft, istft, streaming_spectral_process
        y = generate_speech_like(sr=SR, duration=5.0)
        def process_fn(S, sr, n_fft, hop_length):
            mag = np.abs(S)
            mask = np.ones_like(mag)
            threshold = np.median(mag) * 2
            below = mag < threshold
            mask[below] = mag[below] / (threshold + 1e-10)
            return S * mask
        S = stft(y, n_fft=2048, hop_length=512)
        S_processed = process_fn(S, SR, 2048, 512)
        y_full = istft(S_processed, hop_length=512, length=len(y))
        y_streaming = streaming_spectral_process(
            y, SR, process_fn, n_fft=2048, hop_length=512, chunk_seconds=2
        )
        min_len = min(len(y_full), len(y_streaming))
        np.testing.assert_allclose(y_full[:min_len], y_streaming[:min_len], rtol=0.01, atol=0.01)

    def test_streaming_with_analyze_fn(self):
        from services.dsp_utils import streaming_spectral_process
        y = generate_speech_like(sr=SR, duration=5.0)
        def analyze_fn(y, sr):
            from services.dsp_utils import stft
            S = stft(y[:sr*2], n_fft=2048, hop_length=512)
            return {"global_median": float(np.median(np.abs(S)))}
        def process_fn(S, sr, n_fft, hop_length, global_stats):
            threshold = global_stats["global_median"] * 2
            mag = np.abs(S)
            mask = np.ones_like(mag)
            below = mag < threshold
            mask[below] = mag[below] / (threshold + 1e-10)
            return S * mask
        result = streaming_spectral_process(
            y, SR, process_fn, n_fft=2048, hop_length=512,
            chunk_seconds=2, analyze_fn=analyze_fn
        )
        assert result.shape == y.shape
        assert not np.allclose(result, y)

    def test_should_use_float32(self):
        from services.memory_guard import should_use_float32
        assert not should_use_float32(48000 * 60, 2)
        assert should_use_float32(48000 * 3600, 2)

    def test_estimate_memory_float32_for_long_audio(self):
        from services.memory_guard import estimate_repair_memory_bytes
        est_short = estimate_repair_memory_bytes(48000 * 300, 2, 44100, 48000, algorithm_version="v2.3")
        est_long = estimate_repair_memory_bytes(48000 * 3600, 2, 44100, 48000, algorithm_version="v2.3")
        assert est_short < 1000 * 1024 * 1024
        assert est_long < 4000 * 1024 * 1024

    def test_streaming_uses_less_memory_than_non_streaming(self):
        from services.memory_guard import estimate_repair_memory_bytes
        n = 48000 * 300
        est_streaming = estimate_repair_memory_bytes(n, 2, 44100, 48000, algorithm_version="v2.3")
        est_non_streaming = estimate_repair_memory_bytes(n, 2, 44100, 48000, algorithm_version="v1.1")
        assert est_streaming < est_non_streaming
