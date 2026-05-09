import numpy as np
import gc
from functools import lru_cache

from scipy.signal import butter, sosfiltfilt, resample_poly

from services.audio_loader import load_audio_with_fallback
from services.dsp_utils import stft, istft

MOBILE_WORKING_SR = 48000


def _detect_music_type_fast(y, sr):
    if y.ndim > 1:
        y_mono = y.mean(axis=0)
    else:
        y_mono = y

    frame_len = int(sr * 0.05)
    hop_len = int(sr * 0.025)
    frames = np.lib.stride_tricks.sliding_window_view(y_mono, frame_len)[::hop_len]
    if frames.shape[0] == 0:
        return "unknown", 0.5

    frame_energy = np.mean(frames ** 2, axis=1)
    frame_energy = np.maximum(frame_energy, 1e-10)

    low_cut = int(len(y_mono) * 0.1)
    high_start = int(len(y_mono) * 0.5)
    low_energy = np.mean(y_mono[:low_cut] ** 2) if low_cut > 0 else 1e-10
    high_energy = np.mean(y_mono[high_start:] ** 2) if high_start < len(y_mono) else 1e-10

    db_energy = 10 * np.log10(frame_energy)
    dynamic_range = np.max(db_energy) - np.min(db_energy)

    zcr = np.mean(np.abs(np.diff(np.sign(y_mono))) > 0)
    transient_density = zcr / len(y_mono) * sr

    if dynamic_range < 8 and transient_density < 5:
        music_type = "electronic"
        confidence = 0.75
    elif low_energy > high_energy * 3 and dynamic_range > 12:
        music_type = "bass_heavy"
        confidence = 0.7
    elif transient_density > 15 and dynamic_range > 10:
        music_type = "acoustic"
        confidence = 0.7
    elif high_energy > low_energy * 1.5 and dynamic_range > 10:
        music_type = "vocal"
        confidence = 0.65
    else:
        music_type = "general"
        confidence = 0.6

    return music_type, confidence


def _transparent_compress(y, sr, amount, threshold_db=-18.0, ratio=2.0):
    if amount <= 0:
        return y

    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _transparent_compress(y[ch], sr, amount, threshold_db, ratio)
        return ch_out

    n = len(y)
    if n < 1024:
        return y

    y_64 = y.astype(np.float64)
    input_rms = np.sqrt(np.mean(y_64 ** 2))
    if input_rms < 1e-10:
        return y

    threshold_lin = 10 ** (threshold_db / 20.0)
    effective_ratio = 1.0 + (ratio - 1.0) * min(amount, 1.0)

    global_rms = np.sqrt(np.mean(y_64 ** 2))
    if global_rms <= threshold_lin:
        return y

    target_rms = threshold_lin + (global_rms - threshold_lin) / effective_ratio
    global_gain = target_rms / global_rms

    out = y_64 * global_gain

    return out.astype(y.dtype)


def _simple_declip(y, amount):
    if amount <= 0:
        return y
    threshold = 0.90
    mask = np.abs(y) > threshold
    if not np.any(mask):
        return y

    y_out = y.copy().astype(np.float64)
    abs_y = np.abs(y_out[mask])
    over = abs_y - threshold
    headroom = 1.0 - threshold
    y_out[mask] = np.sign(y_out[mask]) * (threshold + headroom * np.tanh(over / headroom))
    return y_out.astype(y.dtype)


def _simple_depop(y, sr, amount):
    if amount <= 0:
        return y
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _simple_depop_1d(y[ch], sr, amount)
        return ch_out

    data = y.flatten() if y.ndim > 1 else y
    return _simple_depop_1d(data, sr, amount).reshape(y.shape)


def _simple_depop_1d(data, sr, amount):
    diff = np.diff(data)
    abs_diff = np.abs(diff)
    median_diff = np.median(abs_diff)
    if median_diff < 1e-10:
        return data
    threshold = median_diff * (80 + 120 * amount)
    pop_mask = np.concatenate(([False], abs_diff > threshold))
    if not np.any(pop_mask):
        return data

    y_out = data.copy()
    indices = np.where(pop_mask)[0]
    valid = (indices > 0) & (indices < len(y_out) - 1)
    indices = indices[valid]
    if len(indices) == 0:
        return y_out

    prev_vals = y_out[indices - 1]
    next_vals = y_out[indices + 1]
    actual_diffs = y_out[indices] - prev_vals
    over_mask = np.abs(actual_diffs) > threshold
    indices = indices[over_mask]
    if len(indices) == 0:
        return y_out

    prev_vals = y_out[indices - 1]
    next_vals = y_out[indices + 1]
    actual_diffs = y_out[indices] - prev_vals
    clamped = prev_vals + np.sign(actual_diffs) * threshold
    y_out[indices] = 0.5 * (clamped + next_vals)
    return y_out


def _remove_dc(y, sr):
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        for ch in range(y.shape[0]):
            y[ch] = y[ch] - np.mean(y[ch])
        return y
    return y - np.mean(y)


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


def _soft_peak_limit_1d(data, threshold):
    abs_data = np.abs(data)
    mask = abs_data > threshold
    if not np.any(mask):
        return data

    headroom = 1.0 - threshold
    over = abs_data[mask] - threshold
    scale = headroom * 0.98
    data[mask] = np.sign(data[mask]) * (threshold + scale * np.tanh(over / scale))
    return data


def _loudness_normalize(y, sr, target_lufs=-16.0):
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        y_mono = y.mean(axis=0)
    else:
        y_mono = y

    rms_val = np.sqrt(np.mean(y_mono ** 2))
    if rms_val < 1e-10:
        return y

    current_lufs = -0.691 + 20 * np.log10(rms_val)
    gain_db = np.clip(target_lufs - current_lufs, -12, 6)
    gain = 10 ** (gain_db / 20.0)

    if is_stereo:
        return y * gain
    return y * gain


def _spectral_denoise(y, sr, amount):
    if amount <= 0:
        return y

    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _spectral_denoise_1d(y[ch], sr, amount)
        return ch_out

    data = y.flatten() if y.ndim > 1 else y
    return _spectral_denoise_1d(data, sr, amount).reshape(y.shape)


def _spectral_denoise_1d(data, sr, amount):
    n_fft = 2048
    hop_length = 512

    S = stft(data, n_fft=n_fft, hop_length=hop_length)
    magnitude = np.abs(S)
    phase = np.angle(S)

    global_median = np.median(magnitude)
    threshold = global_median * (1 + amount * 3)

    mask = np.ones_like(magnitude)
    below = magnitude < threshold
    mask[below] = magnitude[below] / (threshold + 1e-10)

    denoised_magnitude = magnitude * mask
    S_denoised = denoised_magnitude * np.exp(1j * phase)

    y_out = istft(S_denoised, hop_length=hop_length, length=len(data))

    if len(y_out) > len(data):
        y_out = y_out[:len(data)]
    elif len(y_out) < len(data):
        y_out = np.pad(y_out, (0, len(data) - len(y_out)))

    return y_out


def _de_ess(y, sr, amount):
    if amount <= 0:
        return y

    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _de_ess_1d(y[ch], sr, amount)
        return ch_out

    data = y.flatten() if y.ndim > 1 else y
    return _de_ess_1d(data, sr, amount).reshape(y.shape)


@lru_cache(maxsize=32)
def _de_ess_bandpass_sos(sr, low_hz, high_hz):
    nyq = sr / 2
    norm_low = low_hz / nyq
    norm_high = min(high_hz, nyq * 0.95) / nyq
    if norm_low >= norm_high or norm_high >= 1.0:
        return None
    return butter(4, [norm_low, norm_high], btype='band', output='sos')


def _de_ess_1d(data, sr, amount):
    nyq = sr / 2
    low_hz = 4000
    high_hz = 8000

    if high_hz >= nyq:
        high_hz = nyq * 0.95
    if low_hz >= high_hz:
        return data

    sos = _de_ess_bandpass_sos(sr, low_hz, high_hz)
    if sos is None:
        return data
    high_band = sosfiltfilt(sos, data)
    low_band = data - high_band

    full_rms = np.sqrt(np.mean(data.astype(np.float64) ** 2))
    high_rms = np.sqrt(np.mean(high_band.astype(np.float64) ** 2))

    if full_rms < 1e-10:
        return data

    ratio = high_rms / full_rms
    threshold_ratio = 1 + amount * 0.5

    if ratio <= threshold_ratio:
        return data

    gain = 1 - amount * 0.3
    gain = max(gain, 0.1)

    result = low_band + high_band * gain
    return result.astype(data.dtype)


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    target_sr = params.get("sample_rate", None)
    original_duration = round(y.shape[1] / sr, 2)

    working_sr = MOBILE_WORKING_SR
    if sr != working_sr:
        if progress_callback:
            progress_callback(0.02, f"v2.3a 重采样到 {working_sr//1000}kHz...")
        target_len = int(y.shape[1] * working_sr / sr)
        y_new = np.zeros((y.shape[0], target_len))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            y_new[ch, :len(resampled)] = resampled[:target_len]
        y = y_new
        sr = working_sr
        gc.collect()

    if progress_callback:
        progress_callback(0.05, "v2.3a 快速分析...")

    music_type, confidence = _detect_music_type_fast(y, sr)
    issues_found = [f"类型检测: {music_type} ({confidence:.0%})"]

    if progress_callback:
        progress_callback(0.15, f"v2.3a {music_type} 处理中...")

    if params.get("de_clipping", 0) > 0:
        y = _simple_declip(y, params["de_clipping"])
        issues_found.append("削波修复")

    if params.get("de_pop", 0) > 0:
        y = _simple_depop(y, sr, params["de_pop"])
        issues_found.append("爆音修复")

    if params.get("noise_reduction", 0) > 0:
        if progress_callback:
            progress_callback(0.30, "v2.3a 频谱降噪...")
        y = _spectral_denoise(y, sr, params["noise_reduction"])
        issues_found.append("频谱降噪")
        gc.collect()

    if params.get("de_essing", 0) > 0:
        if progress_callback:
            progress_callback(0.40, "v2.3a 齿音抑制...")
        y = _de_ess(y, sr, params["de_essing"])
        issues_found.append("齿音抑制")

    y = _loudness_normalize(y, sr, -16.0)
    issues_found.append("响度归一化")

    if params.get("dynamic_range", 0) > 0:
        if progress_callback:
            progress_callback(0.55, "v2.3a 动态压缩...")
        y = _transparent_compress(y, sr, params["dynamic_range"])
        issues_found.append("动态压缩")

    y = _remove_dc(y, sr)
    issues_found.append("直流移除")

    if progress_callback:
        progress_callback(0.85, "v2.3a 峰值限制...")
    y = _soft_peak_limit(y, threshold=0.9)
    issues_found.append("峰值限制")

    if target_sr is not None and target_sr != sr:
        if progress_callback:
            progress_callback(0.88, f"v2.3a 重采样到 {target_sr//1000}kHz...")
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

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.95, "v2.3a 导出...")

    try:
        import soundfile as sf
        bit_depth = params.get("bit_depth", 24)
        subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
        subtype = subtype_map.get(bit_depth, "PCM_24")
        sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)
    except Exception:
        from scipy.io import wavfile
        if y.ndim > 1:
            y_out = y.T
        else:
            y_out = y
        if y_out.dtype != np.int16:
            y_out = np.clip(y_out * 32767, -32768, 32767).astype(np.int16)
        wavfile.write(output_path, sr, y_out)

    if progress_callback:
        progress_callback(1.0, "v2.3a 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": params.get("bit_depth", 24),
        "duration": original_duration,
        "channels": y.shape[0] if y.ndim > 1 else 1,
        "music_type": music_type,
        "confidence": confidence,
        "quality_mode": params.get("quality", "standard"),
    }
