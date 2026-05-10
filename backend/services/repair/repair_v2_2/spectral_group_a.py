import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from services.dsp_utils import streaming_spectral_process
from scipy.signal import medfilt
from .type_params import TYPE_PARAMS_MAP

_STREAMING_THRESHOLD_SECONDS = 5 * 60


def apply_spectral_group_a(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    """
    极速版频谱修复 - 合并处理步骤，减少 STFT/ISTFT 次数
    长音频(>5分钟)使用流式分块处理，避免完整 STFT 矩阵占用过多内存
    """
    result = y.copy()
    de_crackle = params.get("de_crackle", 0)
    de_essing = params.get("de_essing", 0)
    noise_red = params.get("noise_reduction", 0)

    if de_crackle <= 0 and de_essing <= 0 and noise_red <= 0:
        return result

    crackle_added = "毛刺修复v9" in issues_found
    essing_added = "齿音抑制v9" in issues_found
    noise_added = "智能降噪v9" in issues_found

    type_params = TYPE_PARAMS_MAP.get(music_type, TYPE_PARAMS_MAP["generic"])

    n_samples = y.shape[1] if y.ndim > 1 else len(y)
    use_streaming = n_samples > _STREAMING_THRESHOLD_SECONDS * sr

    if use_streaming:
        def _analyze_fn(y_ch, sr_ch):
            return _analyze_spectral_group_a(y_ch, sr_ch, n_fft, hop_length)

        def _process_fn(S, sr_p, n_fft_p, hop_length_p, global_stats):
            return _process_spectral_group_a_chunk(
                S, sr_p, n_fft_p, hop_length_p, global_stats,
                noise_red, de_essing, de_crackle, music_type
            )

    for ch in range(y.shape[0]):
        data = result[ch]

        if use_streaming:
            result[ch] = streaming_spectral_process(
                data, sr, _process_fn,
                n_fft=n_fft, hop_length=hop_length,
                analyze_fn=_analyze_fn
            )
        else:
            S = stft(data, n_fft=n_fft, hop_length=hop_length)
            mag = np.abs(S)
            n_frames = mag.shape[1]

            if n_frames < 3:
                result[ch] = istft(S, hop_length=hop_length, length=len(data))
                continue

            freqs = fft_frequencies(sr=sr, n_fft=n_fft)
            frame_energy = np.sum(mag ** 2, axis=0) if (de_crackle > 0 or de_essing > 0) else None

            if noise_red > 0:
                _fast_noise_reduction(mag, n_frames, noise_red, music_type)
                if not noise_added:
                    issues_found.append("智能降噪v9")
                    noise_added = True

            if de_essing > 0 and frame_energy is not None:
                _fast_de_essing(S, mag, freqs, frame_energy, de_essing, music_type, n_frames)
                if not essing_added:
                    issues_found.append("齿音抑制v9")
                    essing_added = True

            if de_crackle > 0 and frame_energy is not None:
                _fast_de_crackle(S, mag, frame_energy, de_crackle, n_frames)
                if not crackle_added:
                    issues_found.append("毛刺修复v9")
                    crackle_added = True

            result[ch] = istft(S, hop_length=hop_length, length=len(data))

    if use_streaming:
        if noise_red > 0 and not noise_added:
            issues_found.append("智能降噪v9")
        if de_essing > 0 and not essing_added:
            issues_found.append("齿音抑制v9")
        if de_crackle > 0 and not crackle_added:
            issues_found.append("毛刺修复v9")

    return result


def _analyze_spectral_group_a(y, sr, n_fft, hop_length):
    """
    流式处理前的一次快速遍历，计算全局统计量：
    - noise_profile: 前 n_frames//20 帧的平均幅度谱
    - mean_centroid: 全局平均频谱质心
    - ratio_mean/ratio_std: 帧能量比的均值和标准差（用于毛刺检测阈值）
    - gain_state: 初始为 None，处理时逐块传递
    """
    n_samples = len(y)
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    n_bins = len(freqs)

    pad_length = n_fft // 2
    total_n_frames = 1 + (n_samples + 2 * pad_length - n_fft) // hop_length
    noise_frames_target = max(1, total_n_frames // 20)

    noise_profile_sum = np.zeros(n_bins)
    noise_frame_count = 0
    frame_energy_list = []
    centroid_sum = 0.0
    centroid_count = 0

    chunk_samples = int(sr * 30)
    pos = 0

    while pos < n_samples:
        end = min(n_samples, pos + chunk_samples + n_fft)
        chunk = y[pos:end]

        S = stft(chunk, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        n_frames = mag.shape[1]

        if n_frames > 0 and noise_frame_count < noise_frames_target:
            frames_to_take = min(n_frames, noise_frames_target - noise_frame_count)
            noise_profile_sum += np.sum(mag[:, :frames_to_take], axis=1)
            noise_frame_count += frames_to_take

        if n_frames > 0:
            fe = np.sum(mag ** 2, axis=0)
            frame_energy_list.append(fe)

            c = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)
            centroid_sum += np.sum(c)
            centroid_count += len(c)

        del S, mag
        pos += chunk_samples

    noise_profile = (noise_profile_sum / max(1, noise_frame_count)).reshape(-1, 1)
    mean_centroid = centroid_sum / max(1, centroid_count)

    if len(frame_energy_list) > 0:
        frame_energy = np.concatenate(frame_energy_list)
        if len(frame_energy) >= 3:
            smooth_energy = np.convolve(frame_energy, [0.2, 0.6, 0.2], mode='same')
            ratio = frame_energy / (smooth_energy + 1e-10)
            ratio_mean = np.mean(ratio)
            ratio_std = np.std(ratio)
        else:
            ratio_mean = 1.0
            ratio_std = 0.0
    else:
        ratio_mean = 1.0
        ratio_std = 0.0

    return {
        'noise_profile': noise_profile,
        'mean_centroid': mean_centroid,
        'ratio_mean': ratio_mean,
        'ratio_std': ratio_std,
        'gain_state': None,
    }


def _process_spectral_group_a_chunk(S, sr, n_fft, hop_length, global_stats,
                                     noise_red, de_essing, de_crackle, music_type):
    """
    流式处理的单块处理函数，使用预计算的全局统计量
    """
    mag = np.abs(S)
    n_frames = mag.shape[1]

    if n_frames < 3:
        return S

    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    frame_energy = np.sum(mag ** 2, axis=0) if (de_crackle > 0 or de_essing > 0) else None

    if noise_red > 0:
        _streaming_noise_reduction(mag, n_frames, noise_red, music_type, global_stats)

    if de_essing > 0 and frame_energy is not None:
        _streaming_de_essing(S, mag, freqs, de_essing, music_type, n_frames, global_stats)

    if de_crackle > 0 and frame_energy is not None:
        _streaming_de_crackle(S, mag, frame_energy, de_crackle, n_frames, global_stats)

    return S


def _streaming_noise_reduction(mag, n_frames, intensity, music_type, global_stats):
    """流式降噪 - 使用全局噪声轮廓和跨块增益状态传递"""
    noise_profile = global_stats['noise_profile']

    if music_type == "classical":
        floor = 0.25
    elif music_type == "vocal":
        floor = 0.18
    else:
        floor = 0.15

    snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
    gain = snr / (snr + 1)
    gain = np.maximum(gain, floor)

    alpha = 0.8
    gain_state = global_stats.get('gain_state')
    if gain_state is not None:
        gain[:, 0] = alpha * gain_state + (1 - alpha) * gain[:, 0]

    for i in range(1, n_frames):
        gain[:, i] = alpha * gain[:, i-1] + (1 - alpha) * gain[:, i]

    global_stats['gain_state'] = gain[:, -1].copy()

    mag *= gain


def _streaming_de_essing(S, mag, freqs, intensity, music_type, n_frames, global_stats):
    """流式去齿音 - 使用全局平均频谱质心作为阈值基准"""
    mean_centroid = global_stats['mean_centroid']

    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

    if n_frames >= 3:
        centroid = np.convolve(centroid, [0.25, 0.5, 0.25], mode='same')

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
    for j in np.where(sibilant)[0]:
        S[mask, j] *= reduction


def _streaming_de_crackle(S, mag, frame_energy, intensity, n_frames, global_stats):
    """流式毛刺修复 - 使用全局帧能量比统计量作为检测阈值"""
    if n_frames < 5:
        return

    ratio_mean = global_stats['ratio_mean']
    ratio_std = global_stats['ratio_std']

    smooth_energy = np.convolve(frame_energy, [0.2, 0.6, 0.2], mode='same')
    ratio = frame_energy / (smooth_energy + 1e-10)

    thr = ratio_mean + ratio_std * 1.5
    crackle = ratio > thr

    if not np.any(crackle):
        return

    blend = intensity * 0.3
    phase = np.exp(1j * np.angle(S))

    for j in np.where(crackle)[0]:
        left = max(0, j - 1)
        right = min(n_frames, j + 2)
        local_avg = np.mean(mag[:, left:right], axis=1)
        S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase[:, j]


def _fast_noise_reduction(mag, n_frames, intensity, music_type):
    """极速降噪 - 简化算法"""
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

    alpha = 0.8
    for i in range(1, n_frames):
        gain[:, i] = alpha * gain[:, i-1] + (1 - alpha) * gain[:, i]

    mag *= gain


def _fast_de_essing(S, mag, freqs, frame_energy, intensity, music_type, n_frames):
    """极速去齿音 - 简化检测"""
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

    if n_frames >= 3:
        centroid = np.convolve(centroid, [0.25, 0.5, 0.25], mode='same')

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
    for j in np.where(sibilant)[0]:
        S[mask, j] *= reduction


def _fast_de_crackle(S, mag, frame_energy, intensity, n_frames):
    """极速毛刺修复 - 极简检测"""
    if n_frames < 5:
        return

    smooth_energy = np.convolve(frame_energy, [0.2, 0.6, 0.2], mode='same')
    ratio = frame_energy / (smooth_energy + 1e-10)

    thr = np.mean(ratio) + np.std(ratio) * 1.5
    crackle = ratio > thr

    if not np.any(crackle):
        return

    blend = intensity * 0.3
    phase = np.exp(1j * np.angle(S))

    for j in np.where(crackle)[0]:
        left = max(0, j - 1)
        right = min(n_frames, j + 2)
        local_avg = np.mean(mag[:, left:right], axis=1)
        S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase[:, j]
