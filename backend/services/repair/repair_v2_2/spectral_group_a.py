import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from scipy.signal import medfilt
from .type_params import TYPE_PARAMS_MAP


def apply_spectral_group_a(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    """
    极速版频谱修复 - 合并处理步骤，减少 STFT/ISTFT 次数
    """
    result = y.copy()
    de_crackle = params.get("de_crackle", 0)
    de_essing = params.get("de_essing", 0)
    noise_red = params.get("noise_reduction", 0)

    # 如果都不需要处理，直接返回
    if de_crackle <= 0 and de_essing <= 0 and noise_red <= 0:
        return result

    crackle_added = "毛刺修复v9" in issues_found
    essing_added = "齿音抑制v9" in issues_found
    noise_added = "智能降噪v9" in issues_found

    type_params = TYPE_PARAMS_MAP.get(music_type, TYPE_PARAMS_MAP["generic"])

    for ch in range(y.shape[0]):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        n_frames = mag.shape[1]

        if n_frames < 3:
            result[ch] = istft(S, hop_length=hop_length, length=len(data))
            continue

        # 合并处理：只进行一次遍历
        freqs = fft_frequencies(sr=sr, n_fft=n_fft)

        # 预计算：帧能量和频谱质心（如果需要）
        frame_energy = np.sum(mag ** 2, axis=0) if (de_crackle > 0 or de_essing > 0) else None

        # 1. 降噪处理（最高优先级）
        if noise_red > 0:
            _fast_noise_reduction(mag, n_frames, noise_red, music_type)
            if not noise_added:
                issues_found.append("智能降噪v9")
                noise_added = True

        # 2. 去齿音
        if de_essing > 0 and frame_energy is not None:
            _fast_de_essing(S, mag, freqs, frame_energy, de_essing, music_type, n_frames)
            if not essing_added:
                issues_found.append("齿音抑制v9")
                essing_added = True

        # 3. 毛刺修复（最低优先级，可跳过）
        if de_crackle > 0 and frame_energy is not None:
            _fast_de_crackle(S, mag, frame_energy, de_crackle, n_frames)
            if not crackle_added:
                issues_found.append("毛刺修复v9")
                crackle_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(data))

    return result


def _fast_noise_reduction(mag, n_frames, intensity, music_type):
    """极速降噪 - 简化算法"""
    # 噪声估计
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    # 参数
    if music_type == "classical":
        floor = 0.25
    elif music_type == "vocal":
        floor = 0.18
    else:
        floor = 0.15

    # 简化 Wiener 增益
    snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
    gain = snr / (snr + 1)
    gain = np.maximum(gain, floor)

    # 极简平滑 - 时间维度一次遍历
    alpha = 0.8
    for i in range(1, n_frames):
        gain[:, i] = alpha * gain[:, i-1] + (1 - alpha) * gain[:, i]

    # 应用增益
    mag *= gain


def _fast_de_essing(S, mag, freqs, frame_energy, intensity, music_type, n_frames):
    """极速去齿音 - 简化检测"""
    # 简化频谱质心计算
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

    # 简单平滑
    if n_frames >= 3:
        centroid = np.convolve(centroid, [0.25, 0.5, 0.25], mode='same')

    # 检测齿音帧
    mean_centroid = np.mean(centroid)
    thr = mean_centroid * (1.2 + intensity * 0.3)
    sibilant = centroid > thr

    if not np.any(sibilant):
        return

    # 频段掩码
    if music_type == "vocal":
        mask = (freqs >= 3000) & (freqs <= 8000)
        weight = 0.6
    else:
        mask = (freqs >= 2500) & (freqs <= 7000)
        weight = 0.5

    if not np.any(mask):
        return

    # 应用衰减
    reduction = 1.0 - intensity * weight
    for j in np.where(sibilant)[0]:
        S[mask, j] *= reduction


def _fast_de_crackle(S, mag, frame_energy, intensity, n_frames):
    """极速毛刺修复 - 极简检测"""
    # 简化检测：能量突变
    if n_frames < 5:
        return

    # 简单平滑
    smooth_energy = np.convolve(frame_energy, [0.2, 0.6, 0.2], mode='same')
    ratio = frame_energy / (smooth_energy + 1e-10)

    # 检测异常
    thr = np.mean(ratio) + np.std(ratio) * 1.5
    crackle = ratio > thr

    if not np.any(crackle):
        return

    # 简单修复：邻域平均
    blend = intensity * 0.3
    phase = np.exp(1j * np.angle(S))

    for j in np.where(crackle)[0]:
        left = max(0, j - 1)
        right = min(n_frames, j + 2)
        local_avg = np.mean(mag[:, left:right], axis=1)
        S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase[:, j]
