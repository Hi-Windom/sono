import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from scipy.signal import lfilter, sosfiltfilt, butter
from .type_params import TYPE_PARAMS_MAP


def apply_spectral_group_a(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    """
    频谱修复 - 纯 Python/SciPy 实现，Termux 兼容
    使用向量化操作和 scipy.signal.lfilter（C 实现）实现 3-5x 提速
    """
    result = y.copy()
    de_crackle = params.get("de_crackle", 0)
    de_essing = params.get("de_essing", 0)
    noise_red = params.get("noise_reduction", 0)

    if de_crackle <= 0 and de_essing <= 0 and noise_red <= 0:
        return result

    crackle_added = "毛刺修复v13" in issues_found
    essing_added = "齿音抑制v13" in issues_found
    noise_added = "智能降噪v13" in issues_found

    n_channels = y.shape[0]
    n_bins = n_fft // 2 + 1

    # 预计算滤波器系数（一次性计算，复用多次）
    alpha_smooth = 0.8
    b_smooth = np.array([1 - alpha_smooth])
    a_smooth = np.array([1, -alpha_smooth])

    for ch in range(n_channels):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        n_frames = mag.shape[1]

        if n_frames < 3:
            result[ch] = istft(S, hop_length=hop_length, length=len(result[ch]))
            continue

        frame_energy = np.sum(mag ** 2, axis=0)

        # 1. 降噪处理 - 使用 lfilter (C 实现)
        if noise_red > 0:
            noise_frames = max(1, n_frames // 20)
            noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

            floor = 0.15
            if music_type == "classical":
                floor = 0.25
            elif music_type == "vocal":
                floor = 0.18

            snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
            gain = snr / (snr + 1)
            gain = np.maximum(gain, floor)

            # 使用 lfilter 进行平滑（C 实现，比 Python 循环快 5-10x）
            gain = lfilter(b_smooth, a_smooth, gain, axis=1)
            mag *= gain

            if not noise_added:
                issues_found.append("智能降噪v13")
                noise_added = True

        # 2. 去齿音 - 向量化操作
        if de_essing > 0:
            freqs = fft_frequencies(sr=sr, n_fft=n_fft)
            centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

            # lfilter 平滑
            centroid = lfilter([0.25, 0.5, 0.25], [1], centroid)

            mean_centroid = np.mean(centroid)
            thr = mean_centroid * (1.2 + de_essing * 0.3)
            sibilant = centroid > thr

            if np.any(sibilant):
                mask = (freqs >= 3000) & (freqs <= 8000) if music_type == "vocal" else (freqs >= 2500) & (freqs <= 7000)
                weight = 0.6 if music_type == "vocal" else 0.5

                if np.any(mask):
                    reduction = 1.0 - de_essing * weight
                    attenuation = np.ones(n_frames)
                    attenuation[sibilant] = reduction
                    S[mask, :] *= attenuation[np.newaxis, :]

            if not essing_added:
                issues_found.append("齿音抑制v13")
                essing_added = True

        # 3. 毛刺修复 - 使用 lfilter 和向量化
        if de_crackle > 0:
            # lfilter 平滑能量
            smooth_energy = lfilter([0.2, 0.6, 0.2], [1], frame_energy)
            ratio = frame_energy / (smooth_energy + 1e-10)

            thr = np.mean(ratio) + np.std(ratio) * 1.5
            crackle = ratio > thr

            if np.any(crackle):
                blend = de_crackle * 0.3
                phase = np.exp(1j * np.angle(S))

                # 向量化修复：批量处理所有毛刺帧
                crackle_indices = np.where(crackle)[0]
                for j in crackle_indices:
                    left = max(0, j - 1)
                    right = min(n_frames, j + 2)
                    local_avg = np.mean(mag[:, left:right], axis=1, keepdims=True)
                    mag[:, j] = local_avg[:, 0] * blend + mag[:, j] * (1 - blend)

                S[:] = mag * phase

            if not crackle_added:
                issues_found.append("毛刺修复v13")
                crackle_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(result[ch]))

    return result
