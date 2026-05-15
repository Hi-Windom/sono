import numpy as np
import soundfile as sf
import gc
import os
from scipy.signal import resample_poly, lfilter

from services.audio_loader import load_audio_with_fallback
from services.repair.repair_v3_3.vocal import process_vocal_v33
from services.repair.repair_v3_3.inst import process_inst_v33
from services.repair.repair_v3_3.mixback import mixback
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
    processing_mode = params.get("processing_mode", "single")
    if processing_mode == "single":
        return _repair_single_track(input_path, output_path, params, progress_callback)
    return _repair_dual_track(input_path, output_path, params, progress_callback)


def _repair_single_track(input_path, output_path, params, progress_callback=None):
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


def _repair_dual_track(input_path, output_path, params, progress_callback=None):
    if progress_callback:
        progress_callback(0.05, "v3.3a+ 加载双轨音频...")

    vocal_path = params.get("vocal_path", input_path)
    accompaniment_path = params.get("accompaniment_path", input_path)
    output_dir = os.path.dirname(output_path)
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    vocal_output = os.path.join(output_dir, f"{base_name}_vocal.wav")
    inst_output = os.path.join(output_dir, f"{base_name}_accompaniment.wav")

    v_y, v_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    a_y, a_sr = load_audio_with_fallback(accompaniment_path, sr=None, mono=False)
    if v_y.ndim == 1:
        v_y = v_y.reshape(1, -1)
    if a_y.ndim == 1:
        a_y = a_y.reshape(1, -1)

    working_sr = DESKTOP_WORKING_SR
    from services.memory_guard import check_memory_before_repair, should_use_float32
    max_len = max(v_y.shape[1], a_y.shape[1])
    working_sr = check_memory_before_repair(
        n_samples=max_len,
        n_channels=max(v_y.shape[0], a_y.shape[0]) * 2,
        sr=max(v_sr, a_sr),
        working_sr=working_sr,
        algorithm_version="v3.3a+",
    )
    for audio_data in [(v_y, v_sr), (a_y, a_sr)]:
        y_arr, sr_arr = audio_data
        if should_use_float32(y_arr.shape[1], y_arr.shape[0]):
            y_arr = y_arr.astype(np.float32)

    if v_sr != working_sr:
        target_len = int(v_y.shape[1] * working_sr / v_sr)
        new_y = np.zeros((v_y.shape[0], target_len), dtype=v_y.dtype)
        for ch in range(v_y.shape[0]):
            resampled = resample_poly(v_y[ch], working_sr, v_sr)
            copy_len = min(target_len, len(resampled))
            new_y[ch, :copy_len] = resampled[:copy_len]
        v_y = new_y
    if a_sr != working_sr:
        target_len = int(a_y.shape[1] * working_sr / a_sr)
        new_y = np.zeros((a_y.shape[0], target_len), dtype=a_y.dtype)
        for ch in range(a_y.shape[0]):
            resampled = resample_poly(a_y[ch], working_sr, a_sr)
            copy_len = min(target_len, len(resampled))
            new_y[ch, :copy_len] = resampled[:copy_len]
        a_y = new_y
    sr = working_sr
    gc.collect()

    if progress_callback:
        progress_callback(0.15, "v3.3a+ 双轨预分析...")

    vocal_params = params.get("vocal_params", {})
    inst_params = params.get("inst_params", {})
    mix_params = params.get("mix_params", {})

    vp = {
        "spectral_naturalize": 0.0,
        "noise_floor_shape": 0.0,
        "harmonic_deregularize": 0.0,
        "phase_naturalize": 0.0,
        "transient_protect": 0.5,
        "dynamic_naturalize": 0.0,
        "f0_harmonic": 0.5,
        "microtremor_breath": 0.3,
        "de_shimmer": 0.3,
        "phase_diffuse": 0.2,
        "noise_floor": 0.1,
    }
    for k, v in vocal_params.items():
        if k in vp or k == "strength":
            vp[k] = v
    vp["strength"] = vocal_params.get("strength", params.get("strength", 1.0))

    ip = {
        "spectral_naturalize": 0.6,
        "noise_floor_shape": 0.0,
        "harmonic_deregularize": 0.4,
        "phase_naturalize": 0.0,
        "transient_protect": 0.5,
        "dynamic_naturalize": 0.2,
    }
    for k, v in inst_params.items():
        if k in ip or k == "strength":
            ip[k] = v
    ip["strength"] = inst_params.get("strength", params.get("strength", 1.0))

    if progress_callback:
        progress_callback(0.25, "v3.3a+ 处理人声轨...")

    v_processed = process_vocal_v33(v_y, sr, vp, progress_callback=progress_callback, progress_start=0.25, progress_end=0.50)

    a_processed = process_inst_v33(a_y, sr, ip, progress_callback=progress_callback, progress_start=0.50, progress_end=0.70)

    mix_p = {
        "strength": params.get("strength", 1.0),
        "vocal_ratio": params.get("vocal_ratio", 1.0),
        "accompaniment_ratio": params.get("accompaniment_ratio", 1.0),
        "cross_bleed": mix_params.get("cross_bleed", 0.2),
        "target_lufs": mix_params.get("target_lufs", -14.0),
        "residual_refine": mix_params.get("residual_refine", 0.2),
    }
    merged = mixback(v_processed, a_processed, sr, mix_p, progress_callback=progress_callback, progress_start=0.70, progress_end=0.85)

    if progress_callback:
        progress_callback(0.85, "v3.3a+ 导出...")

    y = merged
    channels = y.shape[0] if y.ndim > 1 else 1
    if y.dtype == np.float32:
        y = y.astype(np.float64)
    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")
    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)

    v_export = v_processed.astype(np.float64) if v_processed.dtype == np.float32 else v_processed
    a_export = a_processed.astype(np.float64) if a_processed.dtype == np.float32 else a_processed
    sf.write(vocal_output, v_export.T if v_export.ndim > 1 else v_export, sr, subtype=subtype)
    sf.write(inst_output, a_export.T if a_export.ndim > 1 else a_export, sr, subtype=subtype)

    original_duration = round(max(v_y.shape[1], a_y.shape[1]) / sr, 2)

    if progress_callback:
        progress_callback(1.0, "v3.3a+ 双轨修复完成")
    return {
        "issues_found": [],
        "original_sample_rate": max(v_sr, a_sr),
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.3a+",
        "processing_mode": "dual",
    }