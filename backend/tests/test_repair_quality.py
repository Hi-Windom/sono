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
        ratio = len(y_out) / len(y)
        assert 0.95 < ratio < 1.05, (
            f"[{repair_version}] Length ratio: {ratio:.3f} (in: {len(y)}, out: {len(y_out)})"
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
