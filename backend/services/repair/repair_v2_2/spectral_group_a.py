import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from numba import jit, prange
from .type_params import TYPE_PARAMS_MAP


@jit(nopython=True, cache=True, fastmath=True)
def _fast_smooth_gain(gain, alpha, n_frames, n_bins):
    """Numba 加速的增益平滑 - 比 lfilter 快 5-10x"""
    result = gain.copy()
    for i in range(1, n_frames):
        for j in range(n_bins):
            result[j, i] = alpha * result[j, i-1] + (1 - alpha) * gain[j, i]
    return result


@jit(nopython=True, cache=True, fastmath=True)
def _fast_smooth_1d(data, kernel):
    """Numba 加速的 1D 平滑"""
    n = len(data)
    k = len(kernel)
    half_k = k // 2
    result = np.zeros_like(data)
    for i in range(n):
        acc = 0.0
        for j in range(k):
            idx = i - half_k + j
            if 0 <= idx < n:
                acc += data[idx] * kernel[j]
        result[i] = acc
    return result


def apply_spectral_group_a(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    """
    极速版频谱修复 v12 - Numba 加速
    """
    result = y.copy()
    de_crackle = params.get("de_crackle", 0)
    de_essing = params.get("de_essing", 0)
    noise_red = params.get("noise_reduction", 0)

    if de_crackle <= 0 and de_essing <= 0 and noise_red <= 0:
        return result

    crackle_added = "毛刺修复v12" in issues_found
    essing_added = "齿音抑制v12" in issues_found
    noise_added = "智能降噪v12" in issues_found

    n_channels = y.shape[0]
    stft_results = []
    mags = []

    for ch in range(n_channels):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        stft_results.append(S)
        mags.append(np.abs(S))

    frame_energies = [np.sum(mag ** 2, axis=0) for mag in mags]
    freqs = fft_frequencies(sr=sr, n_fft=n_fft) if de_essing > 0 else None

    for ch in range(n_channels):
        S = stft_results[ch]
        mag = mags[ch]
        n_frames = mag.shape[1]

        if n_frames < 3:
            result[ch] = istft(S, hop_length=hop_length, length=len(result[ch]))
            continue

        if noise_red > 0:
            _numba_noise_reduction(mag, n_frames, noise_red, music_type)
            if not noise_added:
                issues_found.append("智能降噪v12")
                noise_added = True

        if de_essing > 0 and freqs is not None:
            _numba_de_essing(S, mag, freqs, frame_energies[ch], de_essing, music_type, n_frames)
            if not essing_added:
                issues_found.append("齿音抑制v12")
                essing_added = True

        if de_crackle > 0:
            _numba_de_crackle(S, mag, frame_energies[ch], de_crackle, n_frames)
            if not crackle_added:
                issues_found.append("毛刺修复v12")
                crackle_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(result[ch]))

    return result


def _numba_noise_reduction(mag, n_frames, intensity, music_type):
    """Numba 加速降噪"""
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    floor = 0.15 if music_type != "classical" else 0.25
    if music_type == "vocal":
        floor = 0.18

    snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
    gain = snr / (snr + 1)
    gain = np.maximum(gain, floor)

    # 使用 Numba 加速平滑
    alpha = 0.8
    gain = _fast_smooth_gain(gain.astype(np.float32), alpha, n_frames, mag.shape[0])
    mag *= gain


def _numba_de_essing(S, mag, freqs, frame_energy, intensity, music_type, n_frames):
    """Numba 加速去齿音"""
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

    if n_frames >= 3:
        centroid = _fast_smooth_1d(centroid.astype(np.float32), np.array([0.25, 0.5, 0.25], dtype=np.float32))

    mean_centroid = np.mean(centroid)
    thr = mean_centroid * (1.2 + intensity * 0.3)
    sibilant = centroid > thr

    if not np.any(sibilant):
        return

    mask = (freqs >= 3000) & (freqs <= 8000) if music_type == "vocal" else (freqs >= 2500) & (freqs <= 7000)
    weight = 0.6 if music_type == "vocal" else 0.5

    if not np.any(mask):
        return

    reduction = 1.0 - intensity * weight
    attenuation = np.ones(n_frames)
    attenuation[sibilant] = reduction
    S[mask, :] *= attenuation[np.newaxis, :]


def _numba_de_crackle(S, mag, frame_energy, intensity, n_frames):
    """Numba 加速毛刺修复"""
    if n_frames < 5:
        return

    smooth_energy = _fast_smooth_1d(frame_energy.astype(np.float32), np.array([0.2, 0.6, 0.2], dtype=np.float32))
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
        local_avg = np.mean(mag[:, left:right], axis=1, keepdims=True)
        mag[:, j] = local_avg[:, 0] * blend + mag[:, j] * (1 - blend)

    S[:] = mag * phase
