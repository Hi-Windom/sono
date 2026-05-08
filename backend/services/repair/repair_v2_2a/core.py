import numpy as np
from scipy.signal import butter, lfilter
import gc

from services.audio_loader import load_audio_with_fallback
from services.librosa_compat import rms


def _detect_music_type_fast(y, sr):
    """基于能量分布的快速音乐类型检测"""
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


def _smooth_compress(y, sr, amount, threshold_db=-22.0, ratio=3.0, attack_ms=15, release_ms=150):
    """平滑单段压缩，使用向量化操作避免逐样本循环
    使用单向低通滤波避免前振铃"""
    if amount <= 0:
        return y

    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _smooth_compress(y[ch], sr, amount, threshold_db, ratio, attack_ms, release_ms)
        return ch_out

    # 包络检测：使用 scipy 的单向低通滤波，避免 Python 循环
    rectified = np.abs(y).astype(np.float64)

    # 设计包络检测低通滤波器（更低截止频率减少高频调制/电流声）
    nyquist = sr / 2
    envelope_cutoff = min(30.0, nyquist * 0.3)  # 从100Hz降到30Hz
    envelope_cutoff_norm = envelope_cutoff / nyquist
    b, a = butter(2, envelope_cutoff_norm, btype='low')
    envelope = lfilter(b, a, rectified)

    threshold_lin = 10 ** (threshold_db / 20.0)
    ratio = 1.0 + (ratio - 1.0) * amount

    # 计算增益曲线
    gain = np.ones_like(y, dtype=np.float64)
    over_mask = envelope > threshold_lin
    gain[over_mask] = (threshold_lin + (envelope[over_mask] - threshold_lin) / ratio) / (envelope[over_mask] + 1e-10)

    # 对增益曲线做重度平滑，消除任何高频调制
    if len(gain) > 201:
        kernel = np.hanning(201)  # 从101增加到201，更平滑
        kernel = kernel / kernel.sum()
        gain = np.convolve(gain, kernel, mode='same')

    out = y * gain

    # 根据实际压缩量计算 makeup gain，更合理
    compressed_rms = np.sqrt(np.mean(out ** 2))
    input_rms = np.sqrt(np.mean(y ** 2))
    if compressed_rms > 1e-10 and input_rms > 1e-10:
        makeup_gain = min(input_rms / compressed_rms, 1.5)  # 最大 +3.5dB
        out = out * makeup_gain

    # 硬限幅到 0.95，避免任何削波
    out = np.clip(out, -0.95, 0.95)

    return out


def _simple_declip(y, amount):
    """削波修复：使用平滑软限幅避免高频谐波"""
    if amount <= 0:
        return y
    threshold = 0.85
    mask = np.abs(y) > threshold
    if not np.any(mask):
        return y

    y_out = y.copy()
    # 软限幅：使用 sigmoid 曲线平滑过渡
    # 超过阈值的部分逐渐被压缩到 threshold + 0.05
    over = np.abs(y_out[mask]) - threshold
    # soft_clip: threshold + (1 - exp(-over * k)) * max_soft
    # k 控制过渡速度，max_soft 控制最大超过量
    max_soft = 0.10
    k = 5.0
    soft_amount = (1.0 - np.exp(-over * k)) * max_soft
    y_out[mask] = np.sign(y_out[mask]) * (threshold + soft_amount)
    return y_out


def _simple_depop(y, sr, amount):
    """爆音检测：基于幅度突变的脉冲修复"""
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
    threshold = median_diff * (15 + 25 * amount)
    pop_mask = np.concatenate(([False], diff > threshold))
    if not np.any(pop_mask):
        return y

    y_out = y.copy()
    window = int(sr * 0.002)
    indices = np.where(pop_mask)[0]
    for idx in indices:
        left = max(0, idx - window)
        right = min(len(y), idx + window + 1)
        if right - left > 2:
            # 使用余弦插值代替线性插值，更平滑
            t = np.linspace(0, 1, right - left)
            y_out[left:right] = y[left] + (y[right - 1] - y[left]) * 0.5 * (1 - np.cos(t * np.pi))
    return y_out


def _remove_dc(y, sr):
    """去除直流偏移和极低频噪声"""
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        for ch in range(y.shape[0]):
            y[ch] = y[ch] - np.mean(y[ch])
        return y
    return y - np.mean(y)


def _lowpass_final(y, sr, cutoff_hz=17000):
    """最终低通滤波：消除所有处理可能引入的高频 artifacts
    使用单向滤波，避免 filtfilt 的前振铃"""
    nyquist = sr / 2
    if nyquist <= cutoff_hz:
        return y

    cutoff_norm = cutoff_hz / nyquist
    # 2 阶 Butterworth，足够平滑且不会引入过多相位失真
    b, a = butter(2, cutoff_norm, btype='low')
    y_filtered = lfilter(b, a, y)
    return y_filtered


def _loudness_normalize(y, sr, target_lufs=-16.0):
    """基于 RMS 的响度归一化"""
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

    # 限制最大增益为 +6dB，避免过度放大噪声底
    gain = min(gain, 2.0)

    if is_stereo:
        return y * gain
    return y * gain


def _peak_limit(y, threshold=0.95):
    """硬限幅，防止削波"""
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

    # 时域修复：削波修复
    if params.get("de_clipping", 0) > 0:
        y = _simple_declip(y, params["de_clipping"])
        issues_found.append("削波修复")

    # 时域修复：爆音修复
    if params.get("de_pop", 0) > 0:
        y = _simple_depop(y, sr, params["de_pop"])
        issues_found.append("爆音修复")

    gc.collect()

    # 时域压缩：平滑包络检测
    if params.get("dynamic_range", 0) > 0:
        if progress_callback:
            progress_callback(0.40, "v2.2a 动态压缩...")
        y = _smooth_compress(y, sr, params["dynamic_range"])
        issues_found.append("动态压缩")
        gc.collect()

    # v2.2a 移动端：去除直流偏移和极低频噪声
    if params.get("noise_reduction", 0) > 0:
        if progress_callback:
            progress_callback(0.60, "v2.2a 噪声抑制...")
        y = _remove_dc(y, sr)
        issues_found.append("直流抑制")
        gc.collect()

    # 最终低通滤波：消除所有处理步骤可能引入的高频 artifacts
    # 这是彻底消除电流声的关键步骤
    if progress_callback:
        progress_callback(0.75, "v2.2a 平滑处理...")
    y = _lowpass_final(y, sr, cutoff_hz=15000)  # 进一步降低截止频率消除高频artifacts
    issues_found.append("高频平滑")
    gc.collect()

    # 响度归一化
    if progress_callback:
        progress_callback(0.85, "v2.2a 响度归一化...")
    y = _loudness_normalize(y, sr, -16.0)
    y = _peak_limit(y, 0.95)
    issues_found.append("响度归一化")

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.95, "v2.2a 导出...")

    # 导出 WAV
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
