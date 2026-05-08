import numpy as np
from scipy.signal import butter, sosfiltfilt
import gc

from services.audio_loader import load_audio_with_fallback


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
    """透明压缩：使用长窗口帧级增益，避免逐样本增益调制产生AM伪影
    核心思路：在帧级别计算增益，帧间做极重度平滑，确保增益变化极缓慢"""
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

    frame_len = int(sr * 0.04)
    hop_len = int(sr * 0.01)
    n_frames = max(1, (n - frame_len) // hop_len + 1)

    y_64 = y.astype(np.float64)

    frame_rms = np.zeros(n_frames, dtype=np.float64)
    for i in range(n_frames):
        start = i * hop_len
        end = min(start + frame_len, n)
        frame_rms[i] = np.sqrt(np.mean(y_64[start:end] ** 2))

    frame_rms = np.maximum(frame_rms, 1e-10)

    threshold_lin = 10 ** (threshold_db / 20.0)
    effective_ratio = 1.0 + (ratio - 1.0) * min(amount, 1.0)

    frame_gain = np.ones(n_frames, dtype=np.float64)
    over_mask = frame_rms > threshold_lin
    target_output = threshold_lin + (frame_rms[over_mask] - threshold_lin) / effective_ratio
    frame_gain[over_mask] = target_output / frame_rms[over_mask]

    frame_gain = np.minimum(frame_gain, 1.0)

    smooth_kernel_size = min(31, max(5, n_frames // 10))
    if smooth_kernel_size % 2 == 0:
        smooth_kernel_size += 1
    kernel = np.hanning(smooth_kernel_size)
    kernel = kernel / kernel.sum()
    frame_gain = np.convolve(frame_gain, kernel, mode='same')

    for _ in range(3):
        frame_gain = np.convolve(frame_gain, kernel, mode='same')

    gain = np.ones(n, dtype=np.float64)
    for i in range(n_frames):
        start = i * hop_len
        end = min(start + hop_len, n)
        gain[start:end] = frame_gain[i]

    gain[n_frames * hop_len:] = frame_gain[-1]

    out = y_64 * gain

    compressed_rms = np.sqrt(np.mean(out ** 2))
    input_rms = np.sqrt(np.mean(y_64 ** 2))
    if compressed_rms > 1e-10 and input_rms > 1e-10:
        makeup_gain = min(input_rms / compressed_rms, 1.2)
        out = out * makeup_gain

    out = np.clip(out, -0.95, 0.95)
    return out.astype(y.dtype)


def _simple_declip(y, amount):
    if amount <= 0:
        return y
    threshold = 0.85
    mask = np.abs(y) > threshold
    if not np.any(mask):
        return y

    y_out = y.copy()
    over = np.abs(y_out[mask]) - threshold
    max_soft = 0.10
    k = 5.0
    soft_amount = (1.0 - np.exp(-over * k)) * max_soft
    y_out[mask] = np.sign(y_out[mask]) * (threshold + soft_amount)
    return y_out


def _simple_depop(y, sr, amount):
    if amount <= 0:
        return y
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _simple_depop(y[ch], sr, amount)
        return ch_out

    diff = np.abs(np.diff(y))
    median_diff = np.median(diff)
    if median_diff < 1e-10:
        return y
    threshold = median_diff * (20 + 30 * amount)
    pop_mask = np.concatenate(([False], diff > threshold))
    if not np.any(pop_mask):
        return y

    y_out = y.copy()
    window = int(sr * 0.003)
    indices = np.where(pop_mask)[0]
    for idx in indices:
        left = max(0, idx - window)
        right = min(len(y), idx + window + 1)
        if right - left > 2:
            t = np.linspace(0, 1, right - left)
            y_out[left:right] = y[left] + (y[right - 1] - y[left]) * 0.5 * (1 - np.cos(t * np.pi))
    return y_out


def _remove_dc(y, sr):
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        for ch in range(y.shape[0]):
            y[ch] = y[ch] - np.mean(y[ch])
        return y
    return y - np.mean(y)


def _gentle_lowpass(y, sr, cutoff_hz=16000):
    """温和低通滤波：使用 sosfiltfilt 零相位滤波，避免 lfilter 的相位失真
    使用1阶滤波器确保最平滑的过渡带，不产生振铃"""
    nyquist = sr / 2
    if nyquist <= cutoff_hz:
        return y

    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _gentle_lowpass(y[ch], sr, cutoff_hz)
        return ch_out

    cutoff_norm = cutoff_hz / nyquist
    sos = butter(1, cutoff_norm, btype='low', output='sos')
    padlen = min(len(y) - 1, 3 * max(3, int(3 / cutoff_norm)))
    y_filtered = sosfiltfilt(sos, y, padlen=padlen)
    return y_filtered


def _apply_fade(y, sr, fade_ms=5):
    """首尾淡入淡出，消除边界伪影"""
    fade_samples = int(sr * fade_ms / 1000)
    if fade_samples < 2:
        return y

    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        fade_in = np.linspace(0, 1, fade_samples, dtype=np.float64)
        fade_out = np.linspace(1, 0, fade_samples, dtype=np.float64)
        for ch in range(y.shape[0]):
            y[ch, :fade_samples] *= fade_in
            y[ch, -fade_samples:] *= fade_out
        return y

    fade_in = np.linspace(0, 1, fade_samples, dtype=y.dtype)
    fade_out = np.linspace(1, 0, fade_samples, dtype=y.dtype)
    y[:fade_samples] *= fade_in
    y[-fade_samples:] *= fade_out
    return y


def _loudness_normalize(y, sr, target_lufs=-16.0):
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        y_mono = y.mean(axis=0)
    else:
        y_mono = y

    rms_val = np.sqrt(np.mean(y_mono ** 2))
    if rms_val < 1e-10:
        return y

    target_rms = 10 ** (target_lufs / 20.0)
    gain = target_rms / rms_val
    gain = min(gain, 2.0)

    if is_stereo:
        return y * gain
    return y * gain


def _peak_limit(y, threshold=0.95):
    return np.clip(y, -threshold, threshold)


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)

    if progress_callback:
        progress_callback(0.05, "v2.2a 快速分析...")

    music_type, confidence = _detect_music_type_fast(y, sr)
    issues_found = [f"类型检测: {music_type} ({confidence:.0%})"]

    gc.collect()

    if progress_callback:
        progress_callback(0.15, f"v2.2a {music_type} 处理中...")

    if params.get("de_clipping", 0) > 0:
        y = _simple_declip(y, params["de_clipping"])
        issues_found.append("削波修复")

    if params.get("de_pop", 0) > 0:
        y = _simple_depop(y, sr, params["de_pop"])
        issues_found.append("爆音修复")

    gc.collect()

    if params.get("dynamic_range", 0) > 0:
        if progress_callback:
            progress_callback(0.40, "v2.2a 动态压缩...")
        y = _transparent_compress(y, sr, params["dynamic_range"])
        issues_found.append("动态压缩")
        gc.collect()

    if params.get("noise_reduction", 0) > 0:
        if progress_callback:
            progress_callback(0.60, "v2.2a 噪声抑制...")
        y = _remove_dc(y, sr)
        issues_found.append("直流抑制")
        gc.collect()

    if progress_callback:
        progress_callback(0.75, "v2.2a 平滑处理...")
    y = _gentle_lowpass(y, sr, cutoff_hz=16000)
    issues_found.append("高频平滑")
    gc.collect()

    if progress_callback:
        progress_callback(0.85, "v2.2a 响度归一化...")
    y = _loudness_normalize(y, sr, -16.0)
    y = _peak_limit(y, 0.95)
    y = _apply_fade(y, sr, fade_ms=5)
    issues_found.append("响度归一化")

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.95, "v2.2a 导出...")

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

    gc.collect()

    if progress_callback:
        progress_callback(1.0, "v2.2a 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": params.get("bit_depth", 24),
        "duration": original_duration,
        "channels": y.shape[0] if y.ndim > 1 else 1,
        "music_type": music_type,
        "confidence": confidence,
        "quality_mode": params.get("quality", "fast"),
    }
