import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from scipy.signal import lfilter
from .type_params import TYPE_PARAMS_MAP


def apply_spectral_combined(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    """
    合并频谱处理 - 单次 STFT/ISTFT 完成所有频谱操作
    比分开调用 group_a 和 group_b 提速 2-3x
    """
    result = y.copy()

    # 检查是否需要处理
    de_crackle = params.get("de_crackle", 0)
    de_essing = params.get("de_essing", 0)
    noise_red = params.get("noise_reduction", 0)
    harmonic_enhance = params.get("harmonic_enhance", 0)
    harmonic_richness = params.get("harmonic_richness", 0)

    need_processing = (de_crackle > 0 or de_essing > 0 or noise_red > 0 or
                       harmonic_enhance > 0 or harmonic_richness > 0)

    if not need_processing:
        return result

    # 追踪已添加的问题
    crackle_added = "毛刺修复v11" in issues_found
    essing_added = "齿音抑制v11" in issues_found
    noise_added = "智能降噪v11" in issues_found
    enhance_added = "谐波增强v8" in issues_found
    richness_added = "谐波丰富度v5" in issues_found

    type_params = TYPE_PARAMS_MAP.get(music_type, TYPE_PARAMS_MAP["generic"])
    n_channels = y.shape[0]

    # 预计算频率
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)

    # 处理每个通道
    for ch in range(n_channels):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        n_frames = mag.shape[1]

        if n_frames < 3:
            result[ch] = istft(S, hop_length=hop_length, length=len(data))
            continue

        # 预计算帧能量
        frame_energy = np.sum(mag ** 2, axis=0)

        # ===== Group A 处理 =====

        # 1. 降噪处理
        if noise_red > 0:
            _fast_noise_reduction(mag, n_frames, noise_red, music_type)
            if not noise_added:
                issues_found.append("智能降噪v11")
                noise_added = True

        # 2. 去齿音
        if de_essing > 0:
            _fast_de_essing(S, mag, freqs, frame_energy, de_essing, music_type, n_frames)
            if not essing_added:
                issues_found.append("齿音抑制v11")
                essing_added = True

        # 3. 毛刺修复
        if de_crackle > 0:
            _fast_de_crackle(S, mag, frame_energy, de_crackle, n_frames)
            if not crackle_added:
                issues_found.append("毛刺修复v11")
                crackle_added = True

        # ===== Group B 处理 =====

        # 4. 谐波增强
        if harmonic_enhance > 0:
            _fast_harmonic_enhance(S, mag, freqs, sr, n_fft, harmonic_enhance, music_type, n_frames)
            if not enhance_added:
                issues_found.append("谐波增强v8")
                enhance_added = True

        # 5. 谐波丰富度
        if harmonic_richness > 0:
            _fast_harmonic_richness(S, mag, freqs, sr, n_fft, harmonic_richness, music_type, n_frames)
            if not richness_added:
                issues_found.append("谐波丰富度v5")
                richness_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(data))

    return result


def _fast_noise_reduction(mag, n_frames, intensity, music_type):
    """快速降噪 - 向量化 Wiener 滤波"""
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    if music_type == "classical":
        floor = 0.25
    elif music_type == "vocal":
        floor = 0.18
    else:
        floor = 0.15

    snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
    gain = snr / (snr + 1)
    gain = np.maximum(gain, floor)

    # 向量化平滑
    alpha = 0.8
    gain = lfilter([1 - alpha], [1, -alpha], gain, axis=1)
    mag *= gain


def _fast_de_essing(S, mag, freqs, frame_energy, intensity, music_type, n_frames):
    """快速去齿音 - 向量化"""
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

    if n_frames >= 3:
        centroid = lfilter([0.25, 0.5, 0.25], [1], centroid)

    mean_centroid = np.mean(centroid)
    thr = mean_centroid * (1.2 + intensity * 0.3)
    sibilant = centroid > thr

    if not np.any(sibilant):
        return

    if music_type == "vocal":
        mask = (freqs >= 3000) & (freqs <= 8000)
        weight = 0.6
    else:
        mask = (freqs >= 2500) & (freqs <= 7000)
        weight = 0.5

    if not np.any(mask):
        return

    reduction = 1.0 - intensity * weight
    attenuation = np.ones(n_frames)
    attenuation[sibilant] = reduction
    S[mask, :] *= attenuation[np.newaxis, :]


def _fast_de_crackle(S, mag, frame_energy, intensity, n_frames):
    """快速毛刺修复 - 向量化"""
    if n_frames < 5:
        return

    smooth_energy = lfilter([0.2, 0.6, 0.2], [1], frame_energy)
    ratio = frame_energy / (smooth_energy + 1e-10)

    thr = np.mean(ratio) + np.std(ratio) * 1.5
    crackle = ratio > thr

    if not np.any(crackle):
        return

    blend = intensity * 0.3
    phase = np.exp(1j * np.angle(S))
    crackle_indices = np.where(crackle)[0]

    for j in crackle_indices:
        left = max(0, j - 1)
        right = min(n_frames, j + 2)
        local_avg = np.mean(mag[:, left:right], axis=1, keepdims=True)
        mag[:, j] = local_avg[:, 0] * blend + mag[:, j] * (1 - blend)

    S[:] = mag * phase


def _fast_harmonic_enhance(S, mag, freqs, sr, n_fft, intensity, music_type, n_frames):
    """快速谐波增强 - 简化版"""
    nyquist = sr / 2

    # 根据音乐类型设置参数
    if music_type == "vocal":
        base_freq_min, base_freq_max = 100, 2000
        harmonics = [(2, 0.06), (3, 0.03)]
        max_harmonic_freq = 6000
    elif music_type == "instrumental":
        base_freq_min, base_freq_max = 80, 3000
        harmonics = [(2, 0.05), (3, 0.025)]
        max_harmonic_freq = 8000
    elif music_type == "classical":
        base_freq_min, base_freq_max = 80, 2000
        harmonics = [(2, 0.025), (3, 0.015)]
        max_harmonic_freq = 5000
    else:
        base_freq_min, base_freq_max = 100, 2000
        harmonics = [(2, 0.035), (3, 0.02)]
        max_harmonic_freq = 6000

    base_mask = (freqs >= base_freq_min) & (freqs <= base_freq_max)
    base_indices = np.where(base_mask)[0]

    if len(base_indices) < 3:
        return

    # 简化：使用全局增益因子，避免逐帧计算
    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain_base in harmonics:
        h_gain = h_gain_base * intensity

        for base_idx in base_indices[::2]:  # 每隔一个频率，减少计算
            base_freq = freqs[base_idx]
            target_freq = base_freq * h_num

            if target_freq >= min(max_harmonic_freq, nyquist - 100):
                continue

            target_idx = np.argmin(np.abs(freqs - target_freq))
            base_mag = mag[base_idx, :]

            # 向量化计算谐波幅度
            harmonic_mag = np.sqrt(base_mag) * h_gain * 0.5
            harmonic_mag = np.minimum(harmonic_mag, base_mag * 0.3)
            harmonic_content[target_idx, :] += harmonic_mag

    # 限制最大增强量
    max_enhance = 1.15
    enhanced_mag = np.clip(mag + harmonic_content * intensity * 0.3, 0, mag * max_enhance)

    phase = np.exp(1j * np.angle(S))
    S[:] = enhanced_mag * phase


def _fast_harmonic_richness(S, mag, freqs, sr, n_fft, intensity, music_type, n_frames):
    """快速谐波丰富度 - 简化版"""
    nyquist = sr / 2

    if music_type == "vocal":
        base_freq_min, base_freq_max = 120, 2500
        harmonics = [(2, 0.04), (3, 0.02)]
        max_harmonic_freq = 7000
    elif music_type == "instrumental":
        base_freq_min, base_freq_max = 100, 3500
        harmonics = [(2, 0.05), (3, 0.025)]
        max_harmonic_freq = 9000
    elif music_type == "classical":
        base_freq_min, base_freq_max = 80, 2000
        harmonics = [(2, 0.02), (3, 0.01)]
        max_harmonic_freq = 5000
    else:
        base_freq_min, base_freq_max = 120, 3000
        harmonics = [(2, 0.03), (3, 0.015)]
        max_harmonic_freq = 7000

    base_mask = (freqs >= base_freq_min) & (freqs <= base_freq_max)
    base_indices = np.where(base_mask)[0]

    if len(base_indices) < 3:
        return

    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain_base in harmonics:
        h_gain = h_gain_base * intensity

        for base_idx in base_indices[::2]:
            base_freq = freqs[base_idx]
            target_freq = base_freq * h_num

            if target_freq >= min(max_harmonic_freq, nyquist - 100):
                continue

            target_idx = np.argmin(np.abs(freqs - target_freq))
            base_mag = mag[base_idx, :]

            harmonic_mag = np.log1p(base_mag) * h_gain * 0.3
            harmonic_mag = np.minimum(harmonic_mag, base_mag * 0.25)
            harmonic_content[target_idx, :] += harmonic_mag

    max_enhance = 1.12
    enhanced_mag = np.clip(mag + harmonic_content, 0, mag * max_enhance)

    phase = np.exp(1j * np.angle(S))
    S[:] = enhanced_mag * phase
