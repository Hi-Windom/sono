import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from scipy.signal import medfilt
from scipy.ndimage import gaussian_filter1d
from .type_params import TYPE_PARAMS_MAP


def apply_spectral_group_a(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    result = y.copy()
    de_crackle = params.get("de_crackle", 0)
    de_essing = params.get("de_essing", 0)
    noise_red = params.get("noise_reduction", 0)

    crackle_added = "毛刺修复v6" in issues_found
    essing_added = "齿音抑制v6" in issues_found
    noise_added = "智能降噪v6" in issues_found

    type_params = TYPE_PARAMS_MAP.get(music_type, TYPE_PARAMS_MAP["generic"])

    for ch in range(y.shape[0]):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)

        if de_crackle > 0:
            _apply_de_crackle_v6_inplace(S, mag, sr, n_fft, hop_length, de_crackle)
            if not crackle_added:
                issues_found.append("毛刺修复v6")
                crackle_added = True
            mag = np.abs(S)

        if de_essing > 0:
            _apply_de_essing_v6_inplace(S, mag, sr, n_fft, hop_length, de_essing, music_type, type_params)
            if not essing_added:
                issues_found.append("齿音抑制v6")
                essing_added = True
            mag = np.abs(S)

        if noise_red > 0:
            _apply_noise_reduction_v6_inplace(S, mag, sr, n_fft, hop_length, noise_red, music_type, type_params)
            if not noise_added:
                issues_found.append("智能降噪v6")
                noise_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_de_crackle_v6_inplace(S, mag, sr, n_fft, hop_length, intensity):
    """改进的毛刺修复 - 使用更平滑的检测和修复"""
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)

    # 计算帧能量
    frame_energy = np.sum(mag ** 2, axis=0)
    
    # 使用更大的中值滤波窗口，更平滑
    kernel_size = min(9, len(frame_energy) | 1)
    if kernel_size < 3:
        kernel_size = 3
    med_energy = medfilt(frame_energy, kernel_size=kernel_size)
    
    # 使用高斯平滑进一步减少噪声
    med_energy_smooth = gaussian_filter1d(med_energy, sigma=1.0)
    
    energy_ratio = frame_energy / (med_energy_smooth + 1e-10)

    # 计算频谱平坦度
    geo_mean = np.exp(np.mean(np.log(mag + 1e-10), axis=0))
    arith_mean = np.mean(mag, axis=0) + 1e-10
    spectral_flatness = geo_mean / arith_mean
    
    # 平滑平坦度
    spectral_flatness = gaussian_filter1d(spectral_flatness, sigma=1.0)

    # 更保守的阈值
    energy_threshold = np.mean(energy_ratio) + np.std(energy_ratio) * 1.2
    flatness_threshold = np.mean(spectral_flatness) + np.std(spectral_flatness) * 0.7

    crackle_frames = (energy_ratio > energy_threshold) & (spectral_flatness > flatness_threshold)

    if np.any(crackle_frames):
        for j in np.where(crackle_frames)[0]:
            # 更大的邻域平均
            left_j = max(0, j - 3)
            right_j = min(mag.shape[1], j + 4)
            local_avg = np.mean(mag[:, left_j:right_j], axis=1)
            
            # 更保守的混合比例
            blend = intensity * 0.45
            phase = np.exp(1j * np.angle(S[:, j]))
            S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase


def _apply_de_essing_v6_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type, type_params):
    """改进的去齿音 - 更自然的频段处理"""
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    n_frames = mag.shape[1]

    # 计算频谱质心
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)
    
    # 平滑质心
    kernel_size = min(7, n_frames | 1)
    if kernel_size % 2 == 0:
        kernel_size += 1
    smooth_centroid = medfilt(centroid, kernel_size=kernel_size)
    smooth_centroid = gaussian_filter1d(smooth_centroid, sigma=0.8)

    centroid_ratio = centroid / (smooth_centroid + 1e-10)
    
    # 更保守的阈值
    centroid_threshold = 1.0 + np.std(centroid_ratio) * 1.1
    sibilant_frames = centroid_ratio > centroid_threshold

    if not np.any(sibilant_frames):
        return

    # 根据音乐类型调整频段
    if music_type == "vocal":
        sibilant_bands = [
            (2500, 4500, 0.9),   # 降低权重
            (4500, 8000, 0.7),
            (8000, 12000, 0.4),
        ]
    elif music_type == "classical":
        sibilant_bands = [
            (2500, 4000, 0.6),
            (4000, 7000, 0.4),
            (7000, 10000, 0.2),
        ]
    else:
        sibilant_bands = [
            (2500, 4500, 0.8),
            (4500, 8000, 0.6),
            (8000, 12000, 0.3),
        ]

    for low, high, weight in sibilant_bands:
        band_mask = (freqs >= low) & (freqs <= high)
        if not np.any(band_mask):
            continue

        for j in np.where(sibilant_frames)[0]:
            excess = (centroid_ratio[j] - centroid_threshold) / (centroid_threshold + 1e-10)
            # 更保守的衰减
            reduction = 1.0 - intensity * 0.25 * weight * min(1.0, excess * 0.8)
            reduction = max(reduction, 0.5)  # 最小保留 50%
            S[band_mask, j] *= reduction


def _apply_noise_reduction_v6_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type, type_params):
    """
    改进的降噪算法 - Wiener滤波 + 心理声学掩蔽
    减少音乐噪声，保留音乐细节
    """
    n_frames = mag.shape[1]
    
    # 噪声估计 - 使用更多帧，更平滑
    noise_frames = max(1, n_frames // 15)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)
    
    # 时间平滑噪声估计
    noise_profile = gaussian_filter1d(noise_profile.flatten(), sigma=2.0).reshape(-1, 1)

    # 根据音乐类型调整参数
    if music_type == "classical":
        alpha = 1 + intensity * 2      # 更温和的降噪
        floor = 0.15 + (1 - intensity) * 0.3
        time_smooth = 0.7              # 更强的时间平滑
    elif music_type == "vocal":
        alpha = 1 + intensity * 2.5
        floor = 0.12 + (1 - intensity) * 0.25
        time_smooth = 0.75
    elif music_type == "electronic":
        alpha = 1 + intensity * 3.5
        floor = 0.08 + (1 - intensity) * 0.2
        time_smooth = 0.8
    else:
        alpha = 1 + intensity * 3
        floor = 0.1 + (1 - intensity) * 0.22
        time_smooth = 0.75

    # Wiener 滤波增益计算
    signal_power = mag ** 2
    noise_power = noise_profile ** 2
    
    # 后验 SNR
    post_snr = signal_power / (noise_power + 1e-10)
    
    # 先验 SNR 估计（使用决策导向方法）
    prior_snr = np.zeros_like(post_snr)
    prior_snr[:, 0] = np.maximum(post_snr[:, 0] - 1, 0)
    
    for i in range(1, n_frames):
        # 决策导向先验 SNR 估计
        smoothed_mag = 0.8 * mag[:, i-1] + 0.2 * mag[:, i]
        prior_snr[:, i] = np.maximum(
            0.98 * (smoothed_mag ** 2) / (noise_power.flatten() + 1e-10) + 
            0.02 * (post_snr[:, i] - 1),
            0
        )
    
    # 心理声学掩蔽 - 简化版
    # 计算听觉掩蔽阈值
    masking_threshold = _compute_masking_threshold(mag, freqs=fft_frequencies(sr=sr, n_fft=n_fft))
    
    # Wiener 增益
    wiener_gain = prior_snr / (prior_snr + 1)
    
    # 应用掩蔽 - 如果信号高于掩蔽阈值，不过度衰减
    signal_above_mask = mag > (masking_threshold * 0.5)
    wiener_gain = np.where(signal_above_mask, 
                           wiener_gain * 0.7 + 0.3,  # 保留更多
                           wiener_gain)
    
    # 应用 floor
    G = np.maximum(wiener_gain, floor)
    
    # 时间平滑 - 减少音乐噪声
    G_smooth = np.zeros_like(G)
    G_smooth[:, 0] = G[:, 0]
    for i in range(1, n_frames):
        G_smooth[:, i] = time_smooth * G_smooth[:, i-1] + (1 - time_smooth) * G[:, i]
    
    # 频率平滑
    for i in range(n_frames):
        G_smooth[:, i] = gaussian_filter1d(G_smooth[:, i], sigma=1.5)

    S *= G_smooth


def _compute_masking_threshold(mag, freqs):
    """
    简化的心理声学掩蔽阈值计算
    基于人耳听觉特性
    """
    n_bins, n_frames = mag.shape
    threshold = np.zeros_like(mag)
    
    # 听觉绝对阈值（简化）
    # 人耳对 2-5kHz 最敏感
    abs_threshold = np.ones(n_bins)
    for i, f in enumerate(freqs):
        if f < 500:
            abs_threshold[i] = 1.5 - f / 1000  # 低频不敏感
        elif f < 4000:
            abs_threshold[i] = 0.3 + (f - 2000) ** 2 / 1e7  # 中频敏感
        else:
            abs_threshold[i] = 0.5 + (f - 4000) / 10000  # 高频逐渐不敏感
    
    # 计算每个频段的掩蔽
    for i in range(n_frames):
        frame = mag[:, i]
        
        # 找出强频率成分
        strong_mask = frame > np.mean(frame) * 0.5
        
        # 强成分产生掩蔽
        for j in np.where(strong_mask)[0]:
            # 简化掩蔽模型：强频率会掩蔽邻近频率
            mask_range = 5  # 掩蔽范围
            for k in range(max(0, j-mask_range), min(n_bins, j+mask_range+1)):
                distance = abs(k - j)
                masking = frame[j] * (1 - distance / (mask_range + 1)) * 0.3
                threshold[k, i] = max(threshold[k, i], masking)
        
        # 结合绝对阈值
        threshold[:, i] = np.maximum(threshold[:, i], np.mean(frame) * abs_threshold * 0.1)
    
    return threshold
