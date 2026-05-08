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

    crackle_added = "毛刺修复v7" in issues_found
    essing_added = "齿音抑制v7" in issues_found
    noise_added = "智能降噪v7" in issues_found

    type_params = TYPE_PARAMS_MAP.get(music_type, TYPE_PARAMS_MAP["generic"])

    for ch in range(y.shape[0]):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)

        if de_crackle > 0:
            _apply_de_crackle_v7_inplace(S, mag, sr, n_fft, hop_length, de_crackle)
            if not crackle_added:
                issues_found.append("毛刺修复v7")
                crackle_added = True
            mag = np.abs(S)

        if de_essing > 0:
            _apply_de_essing_v7_inplace(S, mag, sr, n_fft, hop_length, de_essing, music_type, type_params)
            if not essing_added:
                issues_found.append("齿音抑制v7")
                essing_added = True
            mag = np.abs(S)

        if noise_red > 0:
            _apply_noise_reduction_v7_inplace(S, mag, sr, n_fft, hop_length, noise_red, music_type, type_params)
            if not noise_added:
                issues_found.append("智能降噪v7")
                noise_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_de_crackle_v7_inplace(S, mag, sr, n_fft, hop_length, intensity):
    """优化毛刺修复 - 简化检测逻辑"""
    n_frames = mag.shape[1]
    if n_frames < 5:
        return

    # 计算帧能量
    frame_energy = np.sum(mag ** 2, axis=0)

    # 中值滤波平滑
    kernel = min(5, n_frames | 1)
    med_energy = medfilt(frame_energy, kernel_size=kernel)

    # 能量比
    energy_ratio = frame_energy / (med_energy + 1e-10)

    # 频谱平坦度
    geo_mean = np.exp(np.mean(np.log(mag + 1e-10), axis=0))
    arith_mean = np.mean(mag, axis=0) + 1e-10
    flatness = geo_mean / arith_mean

    # 阈值
    energy_thr = np.mean(energy_ratio) + np.std(energy_ratio)
    flatness_thr = np.mean(flatness) + np.std(flatness) * 0.5

    crackle = (energy_ratio > energy_thr) & (flatness > flatness_thr)

    if not np.any(crackle):
        return

    # 修复
    for j in np.where(crackle)[0]:
        left = max(0, j - 2)
        right = min(mag.shape[1], j + 3)
        local_avg = np.mean(mag[:, left:right], axis=1)
        blend = intensity * 0.4
        phase = np.exp(1j * np.angle(S[:, j]))
        S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase


def _apply_de_essing_v7_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type, type_params):
    """优化去齿音 - 简化频段处理"""
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    n_frames = mag.shape[1]

    # 频谱质心
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

    # 平滑
    kernel = min(5, n_frames | 1)
    smooth_centroid = medfilt(centroid, kernel_size=kernel)

    ratio = centroid / (smooth_centroid + 1e-10)
    thr = 1.0 + np.std(ratio) * 0.8
    sibilant = ratio > thr

    if not np.any(sibilant):
        return

    # 频段配置
    if music_type == "vocal":
        bands = [(2500, 5000, 0.7), (5000, 10000, 0.5)]
    elif music_type == "classical":
        bands = [(2500, 4000, 0.5), (4000, 8000, 0.3)]
    else:
        bands = [(2500, 5000, 0.6), (5000, 10000, 0.4)]

    for low, high, weight in bands:
        mask = (freqs >= low) & (freqs <= high)
        if not np.any(mask):
            continue

        for j in np.where(sibilant)[0]:
            excess = (ratio[j] - thr) / (thr + 1e-10)
            reduction = 1.0 - intensity * 0.2 * weight * min(1.0, excess)
            reduction = max(reduction, 0.6)
            S[mask, j] *= reduction


def _apply_noise_reduction_v7_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type, type_params):
    """
    优化降噪 - 简化 Wiener 滤波，减少循环
    """
    n_frames = mag.shape[1]
    if n_frames < 3:
        return

    # 噪声估计
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    # 参数
    if music_type == "classical":
        alpha, floor, time_smooth = 1 + intensity * 1.5, 0.2 + (1 - intensity) * 0.25, 0.75
    elif music_type == "vocal":
        alpha, floor, time_smooth = 1 + intensity * 2, 0.15 + (1 - intensity) * 0.2, 0.8
    else:
        alpha, floor, time_smooth = 1 + intensity * 2.5, 0.12 + (1 - intensity) * 0.18, 0.8

    # 信号功率
    signal_power = mag ** 2
    noise_power = noise_profile ** 2

    # 后验 SNR
    post_snr = signal_power / (noise_power + 1e-10)

    # 简化先验 SNR 估计（使用前一帧）
    prior_snr = np.zeros_like(post_snr)
    prior_snr[:, 0] = np.maximum(post_snr[:, 0] - 1, 0)

    # 优化：减少循环，使用向量化
    for i in range(1, n_frames):
        prior_snr[:, i] = 0.95 * prior_snr[:, i-1] + 0.05 * np.maximum(post_snr[:, i] - 1, 0)

    # Wiener 增益
    wiener_gain = prior_snr / (prior_snr + 1)

    # 应用 floor
    G = np.maximum(wiener_gain, floor)

    # 时间平滑 - 向量化
    G_smooth = G.copy()
    for i in range(1, n_frames):
        G_smooth[:, i] = time_smooth * G_smooth[:, i-1] + (1 - time_smooth) * G[:, i]

    # 频率平滑 - 使用更高效的卷积
    for i in range(n_frames):
        G_smooth[:, i] = gaussian_filter1d(G_smooth[:, i], sigma=1.0)

    S *= G_smooth
