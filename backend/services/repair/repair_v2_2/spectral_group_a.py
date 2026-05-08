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

    crackle_added = "毛刺修复v8" in issues_found
    essing_added = "齿音抑制v8" in issues_found
    noise_added = "智能降噪v8" in issues_found

    type_params = TYPE_PARAMS_MAP.get(music_type, TYPE_PARAMS_MAP["generic"])

    for ch in range(y.shape[0]):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)

        if de_crackle > 0:
            _apply_de_crackle_v8_inplace(S, mag, sr, n_fft, hop_length, de_crackle)
            if not crackle_added:
                issues_found.append("毛刺修复v8")
                crackle_added = True
            mag = np.abs(S)

        if de_essing > 0:
            _apply_de_essing_v8_inplace(S, mag, sr, n_fft, hop_length, de_essing, music_type, type_params)
            if not essing_added:
                issues_found.append("齿音抑制v8")
                essing_added = True
            mag = np.abs(S)

        if noise_red > 0:
            _apply_noise_reduction_v8_inplace(S, mag, sr, n_fft, hop_length, noise_red, music_type, type_params)
            if not noise_added:
                issues_found.append("智能降噪v8")
                noise_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_de_crackle_v8_inplace(S, mag, sr, n_fft, hop_length, intensity):
    """优化毛刺修复 - 向量化邻域平均"""
    n_frames = mag.shape[1]
    if n_frames < 5:
        return

    # 计算帧能量
    frame_energy = np.sum(mag ** 2, axis=0)

    # 中值滤波
    kernel = min(5, n_frames | 1)
    med_energy = medfilt(frame_energy, kernel_size=kernel)
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

    # 向量化修复：使用卷积实现邻域平均
    from scipy.ndimage import uniform_filter1d

    blend = intensity * 0.4
    phase = np.exp(1j * np.angle(S))

    # 对每个频率 bin 进行时间维度的平滑
    for j in np.where(crackle)[0]:
        # 使用 uniform_filter1d 实现邻域平均
        local_avg = uniform_filter1d(mag[:, j], size=5, mode='nearest')
        S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase[:, j]


def _apply_de_essing_v8_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type, type_params):
    """优化去齿音 - 向量化频段处理"""
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

    # 向量化处理
    for low, high, weight in bands:
        mask = (freqs >= low) & (freqs <= high)
        if not np.any(mask):
            continue

        # 计算所有帧的衰减因子
        excess = np.maximum((ratio - thr) / (thr + 1e-10), 0)
        reduction = 1.0 - intensity * 0.2 * weight * np.minimum(excess, 1.0)
        reduction = np.maximum(reduction, 0.6)

        # 应用到所有帧
        for j in np.where(sibilant)[0]:
            S[mask, j] *= reduction[j]


def _apply_noise_reduction_v8_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type, type_params):
    """
    优化降噪 - 简化算法，减少平滑操作
    """
    n_frames = mag.shape[1]
    if n_frames < 3:
        return

    # 噪声估计
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    # 参数
    if music_type == "classical":
        floor, time_smooth = 0.2 + (1 - intensity) * 0.25, 0.75
    elif music_type == "vocal":
        floor, time_smooth = 0.15 + (1 - intensity) * 0.2, 0.8
    else:
        floor, time_smooth = 0.12 + (1 - intensity) * 0.18, 0.8

    # 信号功率
    signal_power = mag ** 2
    noise_power = noise_profile ** 2

    # 简化 SNR 估计
    snr = signal_power / (noise_power + 1e-10)

    # 简化 Wiener 增益（不使用决策导向）
    gain = snr / (snr + 1)
    gain = np.maximum(gain, floor)

    # 优化：使用更高效的指数平滑
    # 使用 scipy.ndimage 的 gaussian_filter1d 替代循环
    for i in range(n_frames):
        # 时间平滑
        if i > 0:
            gain[:, i] = time_smooth * gain[:, i-1] + (1 - time_smooth) * gain[:, i]

    # 频率平滑 - 每帧单独处理
    for i in range(n_frames):
        gain[:, i] = gaussian_filter1d(gain[:, i], sigma=1.0)

    S *= gain
