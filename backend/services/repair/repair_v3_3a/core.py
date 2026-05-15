import numpy as np
import soundfile as sf
import gc
import os
from scipy.signal import resample_poly

from services.audio_loader import load_audio_with_fallback
from services.dsp_utils import stft, istft
from services.repair.repair_v3_3.vocal import process_vocal_v33
from services.repair.repair_v3_3.inst import process_inst_v33
from services.repair.repair_v3_3.mixback import mixback
from .config import DESKTOP_WORKING_SR, N_FFT, HOP_LENGTH, DEFAULT_PARAMS, ERB_N_BANDS


def _f0_track_lite(y, sr):
    fmin = 65.0
    fmax = 2093.0
    frame_length = 1024
    hop_length = 512
    n_frames = 1 + (len(y) - frame_length) // hop_length
    f0 = np.full(n_frames, np.nan)
    min_lag = max(2, int(sr / fmax))
    max_lag = min(frame_length // 2, int(sr / fmin))
    if n_frames <= 0 or min_lag >= max_lag:
        return np.array([])
    frame_len = frame_length
    n_fft = 1
    while n_fft < 2 * frame_len:
        n_fft *= 2
    lags = np.arange(min_lag, max_lag + 1)
    for i in range(n_frames):
        start = i * hop_length
        end = start + frame_length
        frame = y[start:end]
        frame_centered = frame - np.mean(frame)
        energy = np.sum(frame_centered ** 2)
        if energy < 1e-10:
            continue
        fft_frame = np.fft.rfft(frame_centered, n=n_fft)
        corr_full = np.fft.irfft(fft_frame * np.conj(fft_frame), n=n_fft)
        corr = corr_full[:frame_length]
        corr_norm = corr / energy
        valid_corr = corr_norm[lags]
        best_idx = np.argmax(valid_corr)
        best_corr = valid_corr[best_idx]
        best_lag = lags[best_idx]
        if best_corr > 0.3 and best_lag > 0:
            f0[i] = sr / best_lag
    valid = ~np.isnan(f0)
    if not np.any(valid):
        return np.array([])
    return f0[valid]


def _spectral_naturalize_lite(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim > 1:
        result = np.zeros_like(y)
        for ch in range(y.shape[0]):
            result[ch] = _spectral_naturalize_lite(y[ch], sr, strength)
        return result
    S = stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)
    mag = np.abs(S)
    phase = np.angle(S)
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    noise_target = 1.0 / (freqs + 1e-6)
    noise_target = noise_target / np.max(noise_target)
    current_spectrum = np.mean(mag, axis=1)
    current_spectrum = current_spectrum / (np.max(current_spectrum) + 1e-10)
    shape_strength = DEFAULT_PARAMS.get("noise_floor_shape", 0.0) * strength
    if shape_strength > 0:
        target_spec = (1 - shape_strength) * current_spectrum + shape_strength * noise_target
        ratio = target_spec / (current_spectrum + 1e-10)
        ratio = ratio[:, np.newaxis]
        mag = mag * ratio
    harm_strength = DEFAULT_PARAMS.get("harmonic_deregularize", 0.0) * strength
    if harm_strength > 0:
        rng = np.random.RandomState(42)
        noise_amp = harm_strength * 0.02 * np.max(mag)
        mag += noise_amp * rng.randn(*mag.shape)
        mag = np.maximum(mag, 0)
    S_new = mag * np.exp(1j * phase)
    y_out = istft(S_new, hop_length=HOP_LENGTH, length=len(y))
    y_out = y_out.astype(y.dtype)
    return y_out


def _transient_protect_lite(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim > 1:
        result = np.zeros_like(y)
        for ch in range(y.shape[0]):
            result[ch] = _transient_protect_lite(y[ch], sr, strength)
        return result
    frame_len = 1024
    hop_len = 512
    n_frames = 1 + (len(y) - frame_len) // hop_len
    if n_frames < 2:
        return y
    energy = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_len
        end = start + frame_len
        frame = y[start:end]
        energy[i] = np.mean(frame ** 2)
    energy_ratio = energy / (np.mean(energy) + 1e-10)
    gain_target = 1.0 + (energy_ratio - 1.0) * strength * 0.5
    result = np.zeros_like(y)
    overlap = np.zeros_like(y)
    for i in range(n_frames):
        start = i * hop_len
        end = min(start + frame_len, len(y))
        gain = gain_target[i] if i < len(gain_target) else 1.0
        gain = np.clip(gain, 0.5, 2.0)
        result[start:end] += y[start:end] * gain
        overlap[start:end] += 1.0
    overlap[overlap < 1] = 1.0
    y_out = result / overlap
    return y_out.astype(y.dtype)


def _safe_postprocess_lite(y, sr, params):
    dyn_strength = params.get("dynamic_naturalize", 0.0) * params.get("strength", 1.0)
    if dyn_strength > 0:
        peak = np.max(np.abs(y))
        if peak > 1e-6:
            x = y * 4.0 / peak
            y = np.tanh(x) * peak / 4.0 * (1.0 + 0.1 * dyn_strength)
    max_peak = 0.98
    current_peak = np.max(np.abs(y))
    if current_peak > max_peak:
        y = y * max_peak / current_peak
    return y


def process_v3_3a(y, sr, params):
    strength = params.get("strength", 1.0)
    if y.ndim == 1:
        y = y.reshape(1, -1)
    if params.get("spectral_naturalize", 0) > 0:
        s = params["spectral_naturalize"] * strength
        for ch in range(y.shape[0]):
            y[ch] = _spectral_naturalize_lite(y[ch], sr, s)
        gc.collect()
    if params.get("transient_protect", 0) > 0:
        s = params["transient_protect"] * strength
        for ch in range(y.shape[0]):
            y[ch] = _transient_protect_lite(y[ch], sr, s)
        gc.collect()
    y = _safe_postprocess_lite(y, sr, params)
    if y.shape[0] == 1:
        y = y[0]
    return y


def repair_audio(input_path, output_path, params, progress_callback=None):
    processing_mode = params.get("processing_mode", "single")
    if processing_mode == "single":
        return _repair_single_track(input_path, output_path, params, progress_callback)
    return _repair_dual_track(input_path, output_path, params, progress_callback)


def _repair_single_track(input_path, output_path, params, progress_callback=None):
    if progress_callback:
        progress_callback(0.05, "v3.3a 加载音频...")
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
        algorithm_version="v3.3a",
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
    merged_params = dict(DEFAULT_PARAMS)
    for k, v in params.items():
        if k in merged_params or k == "strength":
            merged_params[k] = v
    merged_params["_issues"] = issues_found
    preset = params.get("preset", "none")
    if progress_callback:
        progress_callback(0.15, "v3.3a 处理音频...")
    audio_len = y.shape[1]
    y = process_v3_3a(y, sr, merged_params)
    if progress_callback:
        progress_callback(0.80, "v3.3a 导出...")
    if y.ndim == 1:
        channels = 1
    else:
        channels = y.shape[0]
    if y.dtype == np.float32:
        y = y.astype(np.float64)
    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")
    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)
    if progress_callback:
        progress_callback(1.0, "v3.3a 修复完成")
    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.3a",
        "processing_mode": "single",
    }


def _repair_dual_track(input_path, output_path, params, progress_callback=None):
    if progress_callback:
        progress_callback(0.05, "v3.3a 加载双轨音频...")

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
        algorithm_version="v3.3a",
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
        progress_callback(0.15, "v3.3a 双轨预分析...")

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
        progress_callback(0.25, "v3.3a 处理人声轨...")

    v_processed = process_vocal_v33(v_y, sr, vp, progress_callback=progress_callback, progress_start=0.25, progress_end=0.50)

    a_processed = process_inst_v33(a_y, sr, ip, progress_callback=progress_callback, progress_start=0.50, progress_end=0.70)

    mix_p = {
        "strength": params.get("strength", 1.0),
        "vocal_ratio": params.get("vocal_ratio", 1.0),
        "accompaniment_ratio": params.get("accompaniment_ratio", 1.0),
        "cross_bleed": mix_params.get("cross_bleed", 0.2),
        "target_lufs": mix_params.get("target_lufs", -14.0),
        "residual_refine": mix_params.get("residual_refine", 0.0),
    }
    merged = mixback(v_processed, a_processed, sr, mix_p, progress_callback=progress_callback, progress_start=0.70, progress_end=0.85)

    if progress_callback:
        progress_callback(0.85, "v3.3a 导出...")

    y = merged
    if y.ndim == 1:
        channels = 1
    else:
        channels = y.shape[0]
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
        progress_callback(1.0, "v3.3a 双轨修复完成")
    return {
        "issues_found": [],
        "original_sample_rate": max(v_sr, a_sr),
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.3a",
        "processing_mode": "dual",
    }
