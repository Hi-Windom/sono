import numpy as np
import soundfile as sf
import gc
from scipy.signal import resample_poly, lfilter

from services.audio_loader import load_audio_with_fallback
from ..repair_v3_3a.core import process_v3_3a
from ..repair_v3_3a.config import DEFAULT_PARAMS as BASE_PARAMS
from .config import DESKTOP_WORKING_SR, HOP_LENGTH, N_FFT


def _residual_refine_lite(original, processed, strength):
    if strength <= 0:
        return processed

    orig_f64 = original.astype(np.float64)
    proc_f64 = processed.astype(np.float64)
    residual = orig_f64 - proc_f64

    rms_res = np.sqrt(np.mean(residual ** 2))
    if rms_res < 1e-12:
        return processed

    a = 0.1
    b = np.array([a, 1.0])
    a_coeff = np.array([1.0, a])
    if residual.ndim == 1:
        residual_filt = lfilter(b, a_coeff, residual)
        residual_filt = lfilter(b, a_coeff, residual_filt[::-1])[::-1]
    else:
        residual_filt = np.zeros_like(residual)
        for ch in range(residual.shape[0]):
            residual_filt[ch] = lfilter(b, a_coeff, residual[ch])
            residual_filt[ch] = lfilter(b, a_coeff, residual_filt[ch][::-1])[::-1]

    rng = np.random.RandomState(42)
    if residual.ndim == 1:
        noise = rng.randn(len(residual)).astype(np.float64)
    else:
        noise = rng.randn(*residual.shape).astype(np.float64)
    noise_rms = np.sqrt(np.mean(noise ** 2)) + 1e-12
    noise *= (rms_res * 3.16e-5) / noise_rms

    mix = proc_f64 + (residual_filt + noise) * strength * 0.15

    peak = np.max(np.abs(mix))
    if peak > 0.99:
        mix *= 0.99 / peak

    return mix.astype(processed.dtype)


def process_v3_3ap(y, sr, params):
    y_orig = y.copy()
    y_out = process_v3_3a(y, sr, params)
    if params.get("residual_refine", 0) > 0:
        y_out = _residual_refine_lite(y_orig, y_out, params["residual_refine"])
    return y_out


def repair_audio(input_path, output_path, params, progress_callback=None):
    if progress_callback:
        progress_callback(0.05, "v3.3a+ 加载音频...")

    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)
    issues_found = []

    working_sr = DESKTOP_WORKING_SR

    from services.memory_guard import check_memory_before_repair, should_use_float32
    working_sr = check_memory_before_repair(
        n_samples=y.shape[1],
        n_channels=y.shape[0],
        sr=sr,
        working_sr=working_sr,
        algorithm_version="v3.3a+",
    )

    if should_use_float32(y.shape[1], y.shape[0]):
        y = y.astype(np.float32)

    if sr != working_sr:
        target_len = int(y.shape[1] * working_sr / sr)
        new_y = np.zeros((y.shape[0], target_len), dtype=y.dtype)
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            copy_len = min(target_len, len(resampled))
            new_y[ch, :copy_len] = resampled[:copy_len]
        y = new_y
        sr = working_sr

    gc.collect()

    if progress_callback:
        progress_callback(0.10, "v3.3a+ 处理音频...")

    merged_params = dict(BASE_PARAMS)
    for k, v in params.items():
        if k in merged_params or k == "residual_refine":
            merged_params[k] = v
    merged_params["_issues"] = issues_found

    y = process_v3_3ap(y, sr, merged_params)

    if progress_callback:
        progress_callback(0.85, "v3.3a+ 导出...")

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if y.dtype == np.float32:
        y = y.astype(np.float64)

    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)

    channels = y.shape[0] if y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, "v3.3a+ 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.3a+",
        "processing_mode": "single",
    }