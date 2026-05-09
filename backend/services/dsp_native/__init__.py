"""
DSP Native Library Python Interface
C 原生库加速的 Python 封装（含 ctypes 绑定）
"""

import os
import ctypes
import numpy as np
from typing import Optional, Tuple

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_PATH = os.path.join(_LIB_DIR, "libdsp_native.so")

_lib = None
_lib_loaded = False


def _load_library() -> Optional[ctypes.CDLL]:
    global _lib, _lib_loaded
    if _lib_loaded:
        return _lib
    _lib_loaded = True
    try:
        if os.path.exists(_LIB_PATH):
            _lib = ctypes.CDLL(_LIB_PATH)
            _setup_argtypes(_lib)
            return _lib
    except Exception as e:
        print(f"Warning: Could not load native DSP library: {e}")
        _lib = None
    return None


def _setup_argtypes(lib: ctypes.CDLL):
    lib.stft_execute.argtypes = [
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        ctypes.c_int,
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        ctypes.c_int,
        ctypes.c_int,
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
    ]
    lib.stft_execute.restype = ctypes.c_int

    lib.istft_execute.argtypes = [
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
    ]
    lib.istft_execute.restype = ctypes.c_int

    lib.compressor_process.argtypes = [
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
    ]
    lib.compressor_process.restype = None

    lib.peak_limiter.argtypes = [
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS'),
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int,
    ]
    lib.peak_limiter.restype = None


def is_native_available() -> bool:
    return _load_library() is not None


def stft_native(input_signal: np.ndarray, n_fft: int = 2048, hop_length: int = 512,
                window: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    lib = _load_library()
    if lib is None:
        return stft_python(input_signal, n_fft, hop_length, window)

    input_f32 = np.ascontiguousarray(input_signal, dtype=np.float32)
    input_len = len(input_f32)

    n_frames = (input_len - n_fft) // hop_length + 1
    if n_frames <= 0:
        fft_bins = n_fft // 2 + 1
        return np.zeros((fft_bins, 0), dtype=np.float32), np.zeros((fft_bins, 0), dtype=np.float32)

    fft_bins = n_fft // 2 + 1

    if window is None:
        window = np.hanning(n_fft).astype(np.float32)
    else:
        window = np.ascontiguousarray(window, dtype=np.float32)

    output_real = np.zeros((n_frames * fft_bins), dtype=np.float32)
    output_imag = np.zeros((n_frames * fft_bins), dtype=np.float32)

    actual_frames = lib.stft_execute(
        input_f32, input_len,
        output_real, output_imag,
        n_fft, hop_length,
        window,
    )

    if actual_frames != n_frames:
        n_frames = actual_frames

    output_real = output_real[:n_frames * fft_bins].reshape(n_frames, fft_bins).T
    output_imag = output_imag[:n_frames * fft_bins].reshape(n_frames, fft_bins).T

    return output_real, output_imag


def istft_native(input_real: np.ndarray, input_imag: np.ndarray,
                 n_fft: int = 2048, hop_length: int = 512,
                 window: Optional[np.ndarray] = None) -> np.ndarray:
    lib = _load_library()
    if lib is None:
        return istft_python(input_real, input_imag, n_fft, hop_length, window)

    fft_bins = input_real.shape[0]
    n_frames = input_real.shape[1]

    real_flat = np.ascontiguousarray(input_real.T, dtype=np.float32).flatten()
    imag_flat = np.ascontiguousarray(input_imag.T, dtype=np.float32).flatten()

    output_len = n_fft + (n_frames - 1) * hop_length
    output = np.zeros(output_len, dtype=np.float32)

    if window is None:
        window = np.hanning(n_fft).astype(np.float32)
    else:
        window = np.ascontiguousarray(window, dtype=np.float32)

    lib.istft_execute(
        real_flat, imag_flat,
        output, output_len,
        n_fft, hop_length,
        window,
    )

    return output


def compressor_native(input_signal: np.ndarray, threshold_db: float = -20.0,
                      ratio: float = 4.0, attack_ms: float = 10.0,
                      release_ms: float = 100.0, sample_rate: int = 48000) -> np.ndarray:
    lib = _load_library()
    if lib is None:
        return compressor_python(input_signal, threshold_db, ratio, attack_ms, release_ms, sample_rate)

    input_f32 = np.ascontiguousarray(input_signal, dtype=np.float32)
    output = np.zeros_like(input_f32)
    length = len(input_f32)

    lib.compressor_process(
        input_f32, output, length,
        ctypes.c_float(threshold_db),
        ctypes.c_float(ratio),
        ctypes.c_float(attack_ms),
        ctypes.c_float(release_ms),
        sample_rate,
    )

    return output


def peak_limiter_native(input_signal: np.ndarray, threshold_db: float = -0.5,
                        attack_ms: float = 5.0, release_ms: float = 50.0,
                        sample_rate: int = 48000) -> np.ndarray:
    lib = _load_library()
    if lib is None:
        return peak_limiter_python(input_signal, threshold_db, attack_ms, release_ms, sample_rate)

    input_f32 = np.ascontiguousarray(input_signal, dtype=np.float32)
    output = np.zeros_like(input_f32)
    length = len(input_f32)

    lib.peak_limiter(
        input_f32, output, length,
        ctypes.c_float(threshold_db),
        ctypes.c_float(attack_ms),
        ctypes.c_float(release_ms),
        sample_rate,
    )

    return output


def stft_python(input_signal: np.ndarray, n_fft: int = 2048, hop_length: int = 512,
                window: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
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

    mask = window_sum > 1e-10
    output[mask] /= window_sum[mask]

    return output


def compressor_python(input_signal: np.ndarray, threshold_db: float = -20.0,
                      ratio: float = 4.0, attack_ms: float = 10.0,
                      release_ms: float = 100.0, sample_rate: int = 48000) -> np.ndarray:
    attack_coeff = np.exp(-1.0 / (attack_ms * 0.001 * sample_rate))
    release_coeff = np.exp(-1.0 / (release_ms * 0.001 * sample_rate))

    threshold_lin = 10 ** (threshold_db / 20)
    envelope = 0.0
    output = np.zeros_like(input_signal)

    for i in range(len(input_signal)):
        abs_sample = abs(input_signal[i])

        if abs_sample > envelope:
            envelope = attack_coeff * envelope + (1 - attack_coeff) * abs_sample
        else:
            envelope = release_coeff * envelope + (1 - release_coeff) * abs_sample

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
    threshold = 10 ** (threshold_db / 20)
    attack_coeff = np.exp(-1.0 / (attack_ms * 0.001 * sample_rate))
    release_coeff = np.exp(-1.0 / (release_ms * 0.001 * sample_rate))

    envelope = 0.0
    output = np.zeros_like(input_signal)

    for i in range(len(input_signal)):
        abs_sample = abs(input_signal[i])

        if abs_sample > envelope:
            envelope = attack_coeff * envelope + (1 - attack_coeff) * abs_sample
        else:
            envelope = release_coeff * envelope + (1 - release_coeff) * abs_sample

        gain = 1.0
        if envelope > threshold:
            gain = threshold / envelope

        output[i] = input_signal[i] * gain

    return output


__all__ = [
    "is_native_available",
    "stft_python", "istft_python",
    "compressor_python", "peak_limiter_python",
    "stft_native", "istft_native",
    "compressor_native", "peak_limiter_native",
]
