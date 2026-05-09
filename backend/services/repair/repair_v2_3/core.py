import numpy as np
import soundfile as sf
from functools import lru_cache
from scipy.signal import butter, resample_poly, sosfiltfilt
from config import MOBILE_MODE
import gc
from services.audio_loader import load_audio_with_fallback

from services.repair.repair_v2_2.spectral_group_a import apply_spectral_group_a
from services.repair.repair_v2_2.spectral_group_b import apply_spectral_group_b
from services.repair.repair_v2_2.subband_processing import apply_subband_repair
from services.repair.repair_v2_2.spatial import apply_spatial_enhance_v6, apply_stereo_width_v3
from services.repair.repair_v2_2.filters import apply_presence_boost_v5, apply_bass_enhance_v5, apply_warmth_v2, apply_clarity_v2
from services.repair.repair_v2_2.dynamics import apply_softness_v5
from services.repair.repair_v2_2.music_type_detector import detect_music_type
from services.repair.repair_v2_2.type_params import apply_music_type_params, get_repair_mode_params

DESKTOP_WORKING_SR = 96000
N_FFT = 2048
HOP_LENGTH = 512


def _tanh_declip_1d(data, threshold):
    mask = np.abs(data) > threshold
    if not np.any(mask):
        return data.copy()
    y_out = data.copy().astype(np.float64)
    abs_y = np.abs(y_out[mask])
    over = abs_y - threshold
    headroom = 1.0 - threshold
    y_out[mask] = np.sign(y_out[mask]) * (threshold + headroom * np.tanh(over / headroom))
    return y_out.astype(data.dtype)


def _tanh_declip(y, amount):
    if amount <= 0:
        return y
    threshold = 0.90
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        result = y.copy()
        for ch in range(y.shape[0]):
            result[ch] = _tanh_declip_1d(y[ch], threshold)
        return result
    data = y.flatten() if y.ndim > 1 else y
    out = _tanh_declip_1d(data, threshold)
    if y.ndim > 1:
        return out.reshape(y.shape)
    return out


def _diff_clamp_depop_1d(data, sr, amount):
    diff = np.diff(data)
    abs_diff = np.abs(diff)
    median_diff = np.median(abs_diff)
    if median_diff < 1e-10:
        return data.copy()
    threshold = median_diff * (80 + 120 * amount)
    pop_mask = np.concatenate(([False], abs_diff > threshold))
    if not np.any(pop_mask):
        return data.copy()
    y_out = data.copy()
    indices = np.where(pop_mask)[0]
    i = 0
    while i < len(indices):
        start = indices[i]
        run_end = start
        while i + 1 < len(indices) and indices[i + 1] == run_end + 1:
            i += 1
            run_end = indices[i]
        max_modify = min(2, run_end - start + 1)
        for idx in range(start, start + max_modify):
            if idx > 0 and idx < len(y_out) - 1:
                prev = y_out[idx - 1]
                next_val = y_out[idx + 1]
                actual_diff = y_out[idx] - prev
                if abs(actual_diff) > threshold:
                    clamped = prev + np.sign(actual_diff) * threshold
                    y_out[idx] = 0.5 * (clamped + next_val)
        i += 1
    return y_out


def _diff_clamp_depop(y, sr, amount):
    if amount <= 0:
        return y
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        result = y.copy()
        for ch in range(y.shape[0]):
            result[ch] = _diff_clamp_depop_1d(y[ch], sr, amount)
        return result
    data = y.flatten() if y.ndim > 1 else y
    out = _diff_clamp_depop_1d(data, sr, amount)
    if y.ndim > 1:
        return out.reshape(y.shape)
    return out


def _global_loudness_normalize(y, sr, target_lufs):
    result = y.copy()
    try:
        for ch in range(y.shape[0]):
            data = result[ch].copy()
            if 60 < sr / 2:
                sos_hp = butter(2, 60 / (sr / 2), btype='high', output='sos')
                data = sosfiltfilt(sos_hp, data)
            shelf_low = 1000 / (sr / 2)
            shelf_high = 4000 / (sr / 2)
            if shelf_high < 1.0 and shelf_high > shelf_low:
                sos_shelf = butter(2, [shelf_low, shelf_high], btype='band', output='sos')
                shelf_signal = sosfiltfilt(sos_shelf, data)
                data = data + shelf_signal * (10 ** (4.0 / 20) - 1)
            rms_val = np.sqrt(np.mean(data ** 2))
            if rms_val < 1e-10:
                continue
            current_lufs = -0.691 + 20 * np.log10(rms_val)
            gain_db = np.clip(target_lufs - current_lufs, -12, 6)
            result[ch] *= 10 ** (gain_db / 20)
    except Exception:
        for ch in range(y.shape[0]):
            rms = np.sqrt(np.mean(result[ch] ** 2))
            if rms > 1e-10:
                current_lufs = -0.691 + 20 * np.log10(rms)
                gain_db = np.clip(target_lufs - current_lufs, -12, 6)
                result[ch] *= 10 ** (gain_db / 20)
    return result


@lru_cache(maxsize=32)
def _multiband_sos_cache(sr, low_cross, high_cross):
    nyq = sr / 2
    w_low = low_cross / nyq
    w_high = high_cross / nyq
    if w_low >= 1.0 or w_high >= 1.0 or w_low <= 0 or w_high <= 0:
        return None
    sos_low = butter(4, w_low, btype='low', output='sos')
    sos_mid_low = butter(4, w_low, btype='high', output='sos')
    sos_mid_high = butter(4, w_high, btype='low', output='sos')
    sos_high = butter(4, w_high, btype='high', output='sos')
    return sos_low, sos_mid_low, sos_mid_high, sos_high


def _transparent_multiband_compress(y, sr, amount, music_type):
    if amount <= 0:
        return y
    if music_type == "vocal":
        low_cross = 250
        high_cross = 4000
    elif music_type == "electronic":
        low_cross = 200
        high_cross = 5000
    elif music_type == "classical":
        low_cross = 300
        high_cross = 3500
    else:
        low_cross = 250
        high_cross = 4000
    nyq = sr / 2
    w_low = low_cross / nyq
    w_high = high_cross / nyq
    cached = _multiband_sos_cache(sr, low_cross, high_cross)
    if cached is None:
        return y
    sos_low, sos_mid_low, sos_mid_high, sos_high = cached
    result = np.zeros_like(y)
    for ch in range(y.shape[0]):
        data = y[ch]
        low_band = sosfiltfilt(sos_low, data)
        mid_band = sosfiltfilt(sos_mid_low, data)
        mid_band = sosfiltfilt(sos_mid_high, mid_band)
        high_band = sosfiltfilt(sos_high, data)
        threshold_db = -18.0
        threshold_lin = 10 ** (threshold_db / 20.0)
        effective_ratio = 1.0 + (2.0 - 1.0) * min(amount, 1.0)
        low_rms = np.sqrt(np.mean(low_band ** 2))
        mid_rms = np.sqrt(np.mean(mid_band ** 2))
        high_rms = np.sqrt(np.mean(high_band ** 2))
        low_gain = 1.0
        if low_rms > threshold_lin and low_rms > 1e-10:
            target_rms = threshold_lin + (low_rms - threshold_lin) / effective_ratio
            low_gain = target_rms / low_rms
        mid_gain = 1.0
        if mid_rms > threshold_lin and mid_rms > 1e-10:
            target_rms = threshold_lin + (mid_rms - threshold_lin) / effective_ratio
            mid_gain = target_rms / mid_rms
        high_gain = 1.0
        if high_rms > threshold_lin and high_rms > 1e-10:
            target_rms = threshold_lin + (high_rms - threshold_lin) / effective_ratio
            high_gain = target_rms / high_rms
        result[ch] = low_band * low_gain + mid_band * mid_gain + high_band * high_gain
    makeup_gain_db = min(3.0, 0.8 * amount)
    result *= 10 ** (makeup_gain_db / 20)
    peak = np.max(np.abs(result))
    if peak > 0.95:
        result *= 0.95 / peak
    return result


def _soft_peak_limit_1d(data, threshold):
    abs_data = np.abs(data)
    mask = abs_data > threshold
    if not np.any(mask):
        return data.copy()
    headroom = 1.0 - threshold
    over = abs_data[mask] - threshold
    scale = headroom * 0.98
    out = data.copy().astype(np.float64)
    out[mask] = np.sign(out[mask]) * (threshold + scale * np.tanh(over / scale))
    return out.astype(data.dtype)


def _soft_peak_limit(y, threshold=0.9):
    abs_max = np.max(np.abs(y))
    if abs_max <= threshold:
        return y
    y_out = y.copy().astype(np.float64)
    is_stereo = y_out.ndim > 1 and y_out.shape[0] == 2
    if is_stereo:
        for ch in range(y_out.shape[0]):
            y_out[ch] = _soft_peak_limit_1d(y_out[ch], threshold)
    else:
        data = y_out.flatten() if y_out.ndim > 1 else y_out
        data = _soft_peak_limit_1d(data, threshold)
        if y_out.ndim > 1:
            y_out = data.reshape(y_out.shape)
        else:
            y_out = data
    return y_out.astype(y.dtype)


def _soft_transient_limit(y, sr, amount):
    if amount < 0.05:
        return y
    result = y.copy()
    frame_size = int(sr * 0.1)
    for ch in range(y.shape[0]):
        data = result[ch]
        n_frames = len(data) // frame_size
        if n_frames < 4:
            continue
        frames = data[:n_frames * frame_size].reshape(n_frames, frame_size)
        frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
        window = 3
        kernel = np.ones(window) / window
        smooth_rms = np.convolve(frame_rms, kernel, mode='same')
        diff = np.abs(np.diff(frame_rms, prepend=frame_rms[0]))
        threshold = np.mean(diff) + np.std(diff) * (1.5 - amount)
        anomaly = diff > threshold
        if not np.any(anomaly):
            continue
        anomaly_indices = np.where(anomaly)[0]
        left_rms = smooth_rms[np.maximum(anomaly_indices - 1, 0)]
        right_rms = smooth_rms[np.minimum(anomaly_indices + 1, n_frames - 1)]
        target_rms_arr = (left_rms + right_rms) / 2
        current_rms_arr = frame_rms[anomaly_indices]
        valid = (current_rms_arr > 0) & (target_rms_arr > 0)
        if not np.any(valid):
            continue
        ratios = target_rms_arr[valid] / current_rms_arr[valid]
        max_ratio = float(np.min(ratios)) if len(ratios) > 0 else 1.0
        global_gain = max_ratio * amount * 0.3 + 1.0 * (1 - amount * 0.3)
        for idx in anomaly_indices:
            start = idx * frame_size
            end = min(len(data), (idx + 1) * frame_size)
            region = result[ch, start:end]
            peak = np.max(np.abs(region))
            if peak > 0:
                target_peak = peak * global_gain
                if target_peak < peak:
                    result[ch, start:end] = _soft_peak_limit_1d(region, target_peak / peak * 0.98)
    return result


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    target_sr = params.get("sample_rate", None)
    original_duration = round(y.shape[1] / sr, 2)

    quality_mode = params.get("quality", "standard")
    is_hifi = quality_mode == "hifi"

    if MOBILE_MODE:
        working_sr = sr
    else:
        working_sr = DESKTOP_WORKING_SR

    if sr != working_sr:
        if progress_callback:
            progress_callback(0.02, f"v2.3 重采样到 {working_sr//1000}kHz...")
        target_len = int(y.shape[1] * working_sr / sr)
        y_new = np.zeros((y.shape[0], target_len))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            y_new[ch, :len(resampled)] = resampled[:target_len]
        y = y_new
        sr = working_sr
        gc.collect()

    issues_found = []

    if progress_callback:
        progress_callback(0.04, "v2.3 检测音乐类型...")

    music_type_override = params.get("music_type", "auto")
    repair_mode = params.get("repair_mode", "smart")

    if music_type_override != "auto":
        music_type = music_type_override
        confidence = 1.0
    else:
        music_type, confidence, features = detect_music_type(y, sr)
        issues_found.append(f"类型检测: {music_type} ({confidence:.0%})")

    if repair_mode != "smart":
        mode_params = get_repair_mode_params(repair_mode)
        params = {**params, **mode_params}
    else:
        params = apply_music_type_params(params, music_type, confidence)

    if is_hifi:
        for key in params:
            if isinstance(params[key], (int, float)) and 0 < params[key] <= 1:
                params[key] *= 0.6

    active_steps = _count_active_steps(params, y.shape[0], is_hifi)
    total_steps = active_steps + 2
    step_idx = 0

    if progress_callback:
        mode_label = "HiFi" if is_hifi else "标准"
        progress_callback(0.05, f"v2.3 {mode_label}模式处理({active_steps}步)...")

    def advance(label):
        nonlocal step_idx
        step_idx += 1
        if progress_callback:
            progress_callback(0.05 + 0.85 * step_idx / total_steps, f"v2.3 {label}...")

    if params.get("de_clipping", 0) > 0:
        y = _tanh_declip(y, params["de_clipping"])
        if "削波修复(tanh)" not in issues_found:
            issues_found.append("削波修复(tanh)")
        advance("削波修复")

    if params.get("de_pop", 0) > 0:
        y = _diff_clamp_depop(y, sr, params["de_pop"])
        if "爆音修复(diff)" not in issues_found:
            issues_found.append("爆音修复(diff)")
        advance("爆音修复")

    if params.get("transient_repair", 0) > 0:
        y = _soft_transient_limit(y, sr, params["transient_repair"])
        if "瞬态修复(soft)" not in issues_found:
            issues_found.append("瞬态修复(soft)")
        advance("瞬态修复")

    y = _global_loudness_normalize(y, sr, -16.0)
    if "响度归一化(global)" not in issues_found:
        issues_found.append("响度归一化(global)")
    advance("响度归一化")

    if params.get("dynamic_range", 0) > 0:
        y = _transparent_multiband_compress(y, sr, params["dynamic_range"], music_type)
        if "多段压缩(transparent)" not in issues_found:
            issues_found.append("多段压缩(transparent)")
        advance("动态处理")

    use_subband = params.get("subband_processing", False)
    if use_subband and not is_hifi:
        need_subband = (params.get("noise_reduction", 0) > 0 or
                       params.get("de_essing", 0) > 0 or
                       params.get("harmonic_enhance", 0) > 0)
        if need_subband:
            y = apply_subband_repair(y, sr, params, music_type, N_FFT, HOP_LENGTH)
            if "子带修复" not in issues_found:
                issues_found.append("子带修复")
            advance("子带修复")
    else:
        need_group_a = (params.get("de_crackle", 0) > 0 or
                        params.get("de_essing", 0) > 0 or
                        params.get("noise_reduction", 0) > 0)
        if need_group_a:
            y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
            advance("频谱修复")

        if not is_hifi:
            need_group_b = (params.get("harmonic_enhance", 0) > 0 or
                            params.get("harmonic_richness", 0) > 0)
            if need_group_b:
                y = apply_spectral_group_b(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
                advance("谐波增强")

    if not use_subband and params.get("spatial_enhance", 0) > 0:
        y = apply_spatial_enhance_v6(y, sr, params["spatial_enhance"], music_type)
        if "空间感增强v6" not in issues_found:
            issues_found.append("空间感增强v6")
        advance("空间感")

    if not is_hifi:
        if params.get("presence_boost", 0) > 0 and not use_subband:
            y = apply_presence_boost_v5(y, sr, params["presence_boost"], music_type)
            if "临场增强v5" not in issues_found:
                issues_found.append("临场增强v5")
            advance("临场增强")

        if params.get("bass_enhance", 0) > 0 and not use_subband:
            y = apply_bass_enhance_v5(y, sr, params["bass_enhance"], music_type)
            if "低音增强v5" not in issues_found:
                issues_found.append("低音增强v5")
            advance("低音增强")

        if params.get("warmth", 0) > 0 and not use_subband:
            y = apply_warmth_v2(y, sr, params["warmth"], music_type)
            if "温暖度v2" not in issues_found:
                issues_found.append("温暖度v2")
            advance("温暖度")

        if params.get("clarity", 0) > 0 and not use_subband:
            y = apply_clarity_v2(y, sr, params["clarity"], music_type)
            if "清晰度v2" not in issues_found:
                issues_found.append("清晰度v2")
            advance("清晰度")

    if params.get("stereo_width", 0) > 0 and y.shape[0] == 2:
        y = apply_stereo_width_v3(y, sr, params["stereo_width"])
        if "立体声宽度v3" not in issues_found:
            issues_found.append("立体声宽度v3")
        advance("立体声宽度")

    if params.get("softness", 0) > 0:
        y = apply_softness_v5(y, sr, params["softness"])
        if "柔化处理v5" not in issues_found:
            issues_found.append("柔化处理v5")
        advance("柔化处理")

    if target_sr is not None and target_sr != sr:
        if progress_callback:
            progress_callback(0.92, f"v2.3 重采样到 {target_sr//1000}kHz...")
        if target_sr < sr:
            nyquist = target_sr / 2
            cutoff = nyquist * 0.95
            sos = butter(6, cutoff / (sr / 2), btype='low', output='sos')
            for ch in range(y.shape[0]):
                y[ch] = sosfiltfilt(sos, y[ch])
        y_resampled = np.zeros((y.shape[0], int(y.shape[1] * target_sr / sr)))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], target_sr, sr)
            y_resampled[ch, :len(resampled)] = resampled[:y_resampled.shape[1]]
        y = y_resampled
        sr = target_sr
        gc.collect()

    if progress_callback:
        progress_callback(0.95, "v2.3 峰值限制...")

    y = _soft_peak_limit(y, threshold=0.9)

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.97, "导出WAV...")

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v2.3 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": y.shape[0] if y.ndim > 1 else 1,
        "music_type": music_type,
        "confidence": confidence,
        "quality_mode": quality_mode,
    }


def _count_active_steps(params, num_channels, is_hifi=False):
    count = 0
    if params.get("de_clipping", 0) > 0: count += 1
    if params.get("de_pop", 0) > 0: count += 1
    if params.get("transient_repair", 0) > 0: count += 1
    if params.get("dynamic_range", 0) > 0: count += 1
    if params.get("de_crackle", 0) > 0 or params.get("de_essing", 0) > 0 or params.get("noise_reduction", 0) > 0: count += 1

    if not is_hifi:
        if params.get("harmonic_enhance", 0) > 0 or params.get("harmonic_richness", 0) > 0: count += 1
        if params.get("presence_boost", 0) > 0: count += 1
        if params.get("bass_enhance", 0) > 0: count += 1
        if params.get("warmth", 0) > 0: count += 1
        if params.get("clarity", 0) > 0: count += 1

    if params.get("spatial_enhance", 0) > 0: count += 1
    if params.get("stereo_width", 0) > 0 and num_channels == 2: count += 1
    if params.get("softness", 0) > 0: count += 1
    return count
