"""
DSP Native Library Python Interface
C 原生库加速的 Python 封装
"""

import os
import ctypes
import numpy as np
from typing import Optional, Tuple

# Library path
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_PATH = os.path.join(_LIB_DIR, "libdsp_native.so")

# Global library handle
_lib = None


def _load_library() -> Optional[ctypes.CDLL]:
    """Load the native DSP library"""
    global _lib
    if _lib is not None:
        return _lib

    try:
        if os.path.exists(_LIB_PATH):
            _lib = ctypes.CDLL(_LIB_PATH)
            return _lib
    except Exception as e:
        print(f"Warning: Could not load native DSP library: {e}")
        return None


def is_native_available() -> bool:
    """Check if native library is available"""
    return _load_library() is not None


# Python fallback implementations
def stft_python(input_signal: np.ndarray, n_fft: int = 2048, hop_length: int = 512,
                window: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Pure Python STFT implementation (fallback)"""
    if window is None:
        window = np.hanning(n_fft)

    n_frames = (len(input_signal) - n_fft) // hop_length + 1
    fft_bins = n_fft // 2 + 1

    output_real = np.zeros((fft_bins, n_frames), dtype=np.float32)
    output_imag = np.zeros((fft_bins, n_frames), dtype=np.float32)

    for i in range(n_frames):
        start = i * hop_length
        frame = input_signal[start:start + n_fft] * window
        fft_result = np.fft.rfft(frame)
        output_real[:, i] = fft_result.real.astype(np.float32)
        output_imag[:, i] = fft_result.imag.astype(np.float32)

    return output_real, output_imag


def istft_python(input_real: np.ndarray, input_imag: np.ndarray,
                 n_fft: int = 2048, hop_length: int = 512,
                 window: Optional[np.ndarray] = None) -> np.ndarray:
    """Pure Python ISTFT implementation (fallback)"""
    if window is None:
        window = np.hanning(n_fft)

    n_frames = input_real.shape[1]
    output_len = n_fft + (n_frames - 1) * hop_length

    output = np.zeros(output_len, dtype=np.float32)
    window_sum = np.zeros(output_len, dtype=np.float32)

    for i in range(n_frames):
        start = i * hop_length
        spectrum = input_real[:, i] + 1j * input_imag[:, i]
        frame = np.fft.irfft(spectrum, n=n_fft) * window
        output[start:start + n_fft] += frame.astype(np.float32)
        window_sum[start:start + n_fft] += window * window

    # Normalize
    mask = window_sum > 1e-10
    output[mask] /= window_sum[mask]

    return output


def compressor_python(input_signal: np.ndarray, threshold_db: float = -20.0,
                      ratio: float = 4.0, attack_ms: float = 10.0,
                      release_ms: float = 100.0, sample_rate: int = 48000) -> np.ndarray:
    """Pure Python compressor implementation (fallback)"""
    attack_coeff = np.exp(-1.0 / (attack_ms * 0.001 * sample_rate))
    release_coeff = np.exp(-1.0 / (release_ms * 0.001 * sample_rate))

    threshold_lin = 10 ** (threshold_db / 20)
    envelope = 0.0
    output = np.zeros_like(input_signal)

    for i in range(len(input_signal)):
        abs_sample = abs(input_signal[i])

        # Envelope follower
        if abs_sample > envelope:
            envelope = attack_coeff * envelope + (1 - attack_coeff) * abs_sample
        else:
            envelope = release_coeff * envelope + (1 - release_coeff) * abs_sample

        # Gain computation
        gain = 1.0
        if envelope > threshold_lin:
            over_db = 20 * np.log10(envelope / threshold_lin)
            compressed_db = over_db / ratio
            gain = 10 ** ((compressed_db - over_db) / 20)

        output[i] = input_signal[i] * gain

    return output


def peak_limiter_python(input_signal: np.ndarray, threshold_db: float = -0.5,
                        attack_ms: float = 5.0, release_ms: float = 50.0,
                        sample_rate: int = 48000) -> np.ndarray:
    """Pure Python peak limiter implementation (fallback)"""
    threshold = 10 ** (threshold_db / 20)
    attack_coeff = np.exp(-1.0 / (attack_ms * 0.001 * sample_rate))
    release_coeff = np.exp(-1.0 / (release_ms * 0.001 * sample_rate))

    envelope = 0.0
    output = np.zeros_like(input_signal)

    for i in range(len(input_signal)):
        abs_sample = abs(input_signal[i])

        # Envelope follower
        if abs_sample > envelope:
            envelope = attack_coeff * envelope + (1 - attack_coeff) * abs_sample
        else:
            envelope = release_coeff * envelope + (1 - release_coeff) * abs_sample

        # Gain reduction
        gain = 1.0
        if envelope > threshold:
            gain = threshold / envelope

        output[i] = input_signal[i] * gain

    return output


# Native wrapper functions (if library is available)
def stft_native(input_signal: np.ndarray, n_fft: int = 2048, hop_length: int = 512,
                window: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """STFT with native acceleration (falls back to Python)"""
    lib = _load_library()
    if lib is None:
        return stft_python(input_signal, n_fft, hop_length, window)

    # Use Python implementation for now (native binding can be added later)
    return stft_python(input_signal, n_fft, hop_length, window)


def istft_native(input_real: np.ndarray, input_imag: np.ndarray,
                 n_fft: int = 2048, hop_length: int = 512,
                 window: Optional[np.ndarray] = None) -> np.ndarray:
    """ISTFT with native acceleration (falls back to Python)"""
    lib = _load_library()
    if lib is None:
        return istft_python(input_real, input_imag, n_fft, hop_length, window)

    # Use Python implementation for now (native binding can be added later)
    return istft_python(input_real, input_imag, n_fft, hop_length, window)


def compressor_native(input_signal: np.ndarray, threshold_db: float = -20.0,
                      ratio: float = 4.0, attack_ms: float = 10.0,
                      release_ms: float = 100.0, sample_rate: int = 48000) -> np.ndarray:
    """Compressor with native acceleration (falls back to Python)"""
    lib = _load_library()
    if lib is None:
        return compressor_python(input_signal, threshold_db, ratio, attack_ms, release_ms, sample_rate)

    # Use Python implementation for now (native binding can be added later)
    return compressor_python(input_signal, threshold_db, ratio, attack_ms, release_ms, sample_rate)


def peak_limiter_native(input_signal: np.ndarray, threshold_db: float = -0.5,
                        attack_ms: float = 5.0, release_ms: float = 50.0,
                        sample_rate: int = 48000) -> np.ndarray:
    """Peak limiter with native acceleration (falls back to Python)"""
    lib = _load_library()
    if lib is None:
        return peak_limiter_python(input_signal, threshold_db, attack_ms, release_ms, sample_rate)

    # Use Python implementation for now (native binding can be added later)
    return peak_limiter_python(input_signal, threshold_db, attack_ms, release_ms, sample_rate)


# Export functions
__all__ = [
    "is_native_available",
    "stft_python", "istft_python",
    "compressor_python", "peak_limiter_python",
    "stft_native", "istft_native",
    "compressor_native", "peak_limiter_native",
]
