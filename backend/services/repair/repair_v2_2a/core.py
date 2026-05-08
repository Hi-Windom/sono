import numpy as np
from scipy.signal import butter, filtfilt
import gc
import os

from services.audio_loader import load_audio_with_fallback
from services.librosa_compat import stft, istft, fft_frequencies, rms

N_FFT = 2048
HOP_LENGTH = 512


def _detect_music_type_fast(y, sr):
    """基于能量分布的快速音乐类型检测，避免复杂特征提取"""
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

    # 低频 vs 高频能量比（简单近似）
    low_cut = int(len(y_mono) * 0.1)
    high_start = int(len(y_mono) * 0.5)
    low_energy = np.mean(y_mono[:low_cut] ** 2) if low_cut > 0 else 1e-10
    high_energy = np.mean(y_mono[high_start:] ** 2) if high_start < len(y_mono) else 1e-10

    # 动态范围
    db_energy = 10 * np.log10(frame_energy)
    dynamic_range = np.max(db_energy) - np.min(db_energy)

    # 瞬态密度（过零率近似）
    zcr = np.mean(np.abs(np.diff(np.sign(y_mono))) > 0)
    transient_density = zcr / len(y_mono) * sr

    # 分类逻辑
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


def _single_band_compress(y, sr, amount, threshold_db=-20.0, ratio=4.0, attack_ms=10, release_ms=100):
    """单段压缩替代多段压缩，大幅降低计算量"""
    if amount <= 0:
        return y

    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _single_band_compress(y[ch], sr, amount, threshold_db, ratio, attack_ms, release_ms)
        return ch_out

    attack_samples = max(1, int(sr * attack_ms / 1000))
    release_samples = max(1, int(sr * release_ms / 1000))
    attack_coef = np.exp(-1.0 / attack_samples)
    release_coef = np.exp(-1.0 / release_samples)

    threshold_lin = 10 ** (threshold_db / 20.0)
    ratio = 1.0 + (ratio - 1.0) * amount

    # 向量化包络检测：使用分块处理减少 Python 循环开销
    block_size = max(1, sr // 100)  # 10ms 块
    n_blocks = (len(y) + block_size - 1) // block_size

    envelope = 0.0
    gain_array = np.ones(len(y))

    for b in range(n_blocks):
        start = b * block_size
        end = min(start + block_size, len(y))
        block = y[start:end]
        block_abs = np.abs(block)
        block_max = np.max(block_abs) if len(block) > 0 else 0

        # 基于块最大值的包络更新
        if block_max > envelope:
            envelope = attack_coef * envelope + (1 - attack_coef) * block_max
        else:
            envelope = release_coef * envelope + (1 - release_coef) * block_max

        if envelope > threshold_lin:
            gain = (threshold_lin + (envelope - threshold_lin) / ratio) / (envelope + 1e-10)
        else:
            gain = 1.0

        gain_array[start:end] = gain

    # 简单平滑增益
    if len(gain_array) > 5:
        kernel = np.ones(5) / 5
        gain_array = np.convolve(gain_array, kernel, mode='same')

    out = y * gain_array
    makeup_gain = 1.0 + (1.0 - 1.0 / ratio) * amount * 0.3
    return out * makeup_gain


def _spectral_repair(y, sr, params):
    """单次 STFT/ISTFT 完成降噪+去齿音，避免多次变换"""
    is_stereo = y.ndim > 1 and y.shape[0] == 2
    if is_stereo:
        ch_out = np.zeros_like(y)
        for ch in range(y.shape[0]):
            ch_out[ch] = _spectral_repair(y[ch], sr, params)
        return ch_out

    S = stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)
    mag = np.abs(S)
    phase = np.angle(S)

    freqs = fft_frequencies(sr=sr, n_fft=N_FFT)
    n_freqs, n_frames = mag.shape

    # 噪声门限：基于低能量帧估计噪声底
    nr_amount = params.get("noise_reduction", 0)
    deess_amount = params.get("de_essing", 0)

    if nr_amount > 0:
        # 简化的频谱减法：估计噪声底并应用平滑增益
        noise_frames = max(1, n_frames // 20)
        noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)
        
        # 计算 SNR 并应用增益
        signal_power = mag ** 2
        noise_power = noise_profile ** 2 + 1e-10
        snr = signal_power / noise_power
        
        # 软阈值增益
        gain = snr / (snr + 1.0)
        floor = 0.15 + 0.2 * (1 - nr_amount)  # 根据强度调整底噪保留
        gain = np.maximum(gain, floor)
        
        # 时间维度平滑（避免音乐噪声）
        alpha = 0.7 + 0.2 * nr_amount
        for i in range(1, n_frames):
            gain[:, i] = alpha * gain[:, i-1] + (1 - alpha) * gain[:, i]
        
        mag *= gain

    # 去齿音：衰减 4kHz-8kHz 区域
    if deess_amount > 0:
        sibilance_mask = (freqs >= 4000) & (freqs <= 8000)
        if np.any(sibilance_mask):
            attenuation = 1.0 - 0.5 * deess_amount
            mag[sibilance_mask, :] *= attenuation

    S_repaired = mag * np.exp(1j * phase)
    out = istft(S_repaired, hop_length=HOP_LENGTH, length=len(y))
    return out


def _loudness_normalize(y, sr, target_lufs=-16.0):
    """基于 RMS 的响度归一化，轻量快速"""
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

    if is_stereo:
        return y * gain
    return y * gain


def _peak_limit(y, threshold=0.99):
    """硬限幅，防止削波"""
    peak = np.max(np.abs(y))
    if peak > threshold:
        return y * (threshold / peak)
    return y


def _simple_declip(y, amount):
    """简单削波检测与修复"""
    if amount <= 0:
        return y
    threshold = 0.95
    mask = np.abs(y) > threshold
    if not np.any(mask):
        return y
    y_out = y.copy()
    y_out[mask] = np.sign(y_out[mask]) * (threshold + (np.abs(y_out[mask]) - threshold) * (1 - amount * 0.5))
    return y_out


def _simple_depop(y, sr, amount):
    """简单爆音检测：基于幅度突变的脉冲修复"""
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
    threshold = median_diff * (10 + 20 * amount)
    pop_mask = np.concatenate(([False], diff > threshold))
    if not np.any(pop_mask):
        return y

    y_out = y.copy()
    window = int(sr * 0.001)
    indices = np.where(pop_mask)[0]
    for idx in indices:
        left = max(0, idx - window)
        right = min(len(y), idx + window + 1)
        if right - left > 2:
            y_out[left:right] = np.linspace(y[left], y[right - 1], right - left)
    return y_out


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

    # 时域修复
    if params.get("de_clipping", 0) > 0:
        y = _simple_declip(y, params["de_clipping"])
        issues_found.append("削波修复")

    if params.get("de_pop", 0) > 0:
        y = _simple_depop(y, sr, params["de_pop"])
        issues_found.append("爆音修复")

    gc.collect()

    # 单段压缩替代多段压缩
    if params.get("dynamic_range", 0) > 0:
        if progress_callback:
            progress_callback(0.35, "v2.2a 动态压缩...")
        y = _single_band_compress(y, sr, params["dynamic_range"])
        issues_found.append("单段压缩")
        gc.collect()

    # 单次 STFT 频谱修复（降噪+去齿音）
    if params.get("noise_reduction", 0) > 0 or params.get("de_essing", 0) > 0:
        if progress_callback:
            progress_callback(0.55, "v2.2a 频谱修复...")
        y = _spectral_repair(y, sr, params)
        issues_found.append("频谱修复")
        gc.collect()

    # 响度归一化
    if progress_callback:
        progress_callback(0.85, "v2.2a 响度归一化...")
    y = _loudness_normalize(y, sr, -16.0)
    y = _peak_limit(y, 0.99)
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
        # fallback: 使用 scipy.io.wavfile
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
