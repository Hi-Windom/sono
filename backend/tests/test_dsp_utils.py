import sys
import os
import pytest
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


def generate_test_signal(sr=44100, duration=1.0, freq=440.0):
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    return 0.5 * np.sin(2 * np.pi * freq * t)


class TestStft:
    def test_stft_returns_complex_array(self):
        from services.dsp_utils import stft
        y = generate_test_signal()
        S = stft(y)
        assert np.iscomplexobj(S)
        assert S.ndim == 2

    def test_stft_shape_matches_expected(self):
        from services.dsp_utils import stft
        sr = 44100
        y = generate_test_signal(sr=sr, duration=0.1)
        n_fft = 2048
        hop_length = 512
        S = stft(y, n_fft=n_fft, hop_length=hop_length)
        expected_bins = n_fft // 2 + 1
        assert S.shape[0] == expected_bins
        assert S.shape[1] > 0

    def test_stft_with_different_windows(self):
        from services.dsp_utils import stft
        y = generate_test_signal()
        for window in ['hann', 'hamming', 'blackman']:
            S = stft(y, window=window)
            assert np.iscomplexobj(S)
            assert S.shape[0] == 1025

    def test_stft_with_different_n_fft(self):
        from services.dsp_utils import stft
        y = generate_test_signal()
        for n_fft in [512, 1024, 2048, 4096]:
            S = stft(y, n_fft=n_fft)
            assert S.shape[0] == n_fft // 2 + 1


class TestIstft:
    def test_istft_returns_real_array(self):
        from services.dsp_utils import stft, istft
        y = generate_test_signal()
        S = stft(y)
        y_recon = istft(S)
        assert np.isrealobj(y_recon)
        assert y_recon.ndim == 1

    def test_stft_istft_reconstruction(self):
        from services.dsp_utils import stft, istft
        y = generate_test_signal(duration=0.5)
        S = stft(y, n_fft=2048, hop_length=512)
        y_recon = istft(S, hop_length=512, length=len(y))
        min_len = min(len(y), len(y_recon))
        y_trimmed = y[:min_len]
        y_recon_trimmed = y_recon[:min_len]
        correlation = np.corrcoef(y_trimmed, y_recon_trimmed)[0, 1]
        assert correlation > 0.99

    def test_istft_with_length_param(self):
        from services.dsp_utils import stft, istft
        y = generate_test_signal(duration=0.5)
        S = stft(y)
        target_len = len(y) - 100
        y_recon = istft(S, length=target_len)
        assert len(y_recon) == target_len


class TestChunkedStft:
    def test_stft_chunked_matches_full(self):
        from services.dsp_utils import stft, stft_chunked
        y = generate_test_signal(duration=0.5)
        S_full = stft(y, n_fft=2048, hop_length=512)
        S_chunked = stft_chunked(y, n_fft=2048, hop_length=512, chunk_frames=128)
        assert S_full.shape == S_chunked.shape
        assert np.allclose(S_full, S_chunked, atol=1e-10)

    def test_istft_chunked_matches_full(self):
        from services.dsp_utils import stft, istft, istft_chunked
        y = generate_test_signal(duration=0.5)
        S = stft(y, n_fft=2048, hop_length=512)
        y_full = istft(S, hop_length=512, length=len(y))
        y_chunked = istft_chunked(S, hop_length=512, length=len(y), chunk_frames=128)
        assert len(y_full) == len(y_chunked)
        assert np.allclose(y_full, y_chunked, atol=1e-10)


class TestAudioUtils:
    def test_rms_amplitude(self):
        from services.dsp_utils import stft
        y = generate_test_signal()
        rms = np.sqrt(np.mean(y ** 2))
        assert rms > 0
        assert rms < 1.0

    def test_peak_amplitude(self):
        y = generate_test_signal()
        peak = np.max(np.abs(y))
        assert peak > 0
        assert peak <= 0.5 + 1e-10

    def test_silence_signal_stft(self):
        from services.dsp_utils import stft, istft
        y = np.zeros(44100, dtype=np.float64)
        S = stft(y)
        assert np.all(np.abs(S) < 1e-10)
        y_recon = istft(S, length=len(y))
        assert np.all(np.abs(y_recon) < 1e-10)


class TestWindowCache:
    def test_window_caching(self):
        from services.dsp_utils import _get_window
        w1 = _get_window('hann', 2048)
        w2 = _get_window('hann', 2048)
        assert w1 is w2

    def test_different_windows_cached_separately(self):
        from services.dsp_utils import _get_window
        w_hann = _get_window('hann', 2048)
        w_hamming = _get_window('hamming', 2048)
        assert w_hann is not w_hamming

    def test_different_sizes_cached_separately(self):
        from services.dsp_utils import _get_window
        w_1024 = _get_window('hann', 1024)
        w_2048 = _get_window('hann', 2048)
        assert w_1024 is not w_2048
        assert len(w_1024) == 1024
        assert len(w_2048) == 2048
