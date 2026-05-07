import numpy as np
import librosa
from scipy.signal import medfilt


def apply_spectral_group_a(y, sr, params, n_fft, hop_length, issues_found):
    result = y.copy()
    de_crackle = params.get("de_crackle", 0)
    de_essing = params.get("de_essing", 0)
    noise_red = params.get("noise_reduction", 0)

    crackle_added = "毛刺修复v4" in issues_found
    essing_added = "齿音抑制v4" in issues_found
    noise_added = "智能降噪v4" in issues_found

    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)

        if de_crackle > 0:
            _apply_de_crackle_v4_inplace(S, mag, sr, n_fft, hop_length, de_crackle)
            if not crackle_added:
                issues_found.append("毛刺修复v4")
                crackle_added = True
            mag = np.abs(S)

        if de_essing > 0:
            _apply_de_essing_v4_inplace(S, mag, sr, n_fft, hop_length, de_essing)
            if not essing_added:
                issues_found.append("齿音抑制v4")
                essing_added = True
            mag = np.abs(S)

        if noise_red > 0:
            _apply_noise_reduction_v4_inplace(S, mag, sr, n_fft, hop_length, noise_red)
            if not noise_added:
                issues_found.append("智能降噪v4")
                noise_added = True

        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_de_crackle_v4_inplace(S, mag, sr, n_fft, hop_length, intensity):
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    frame_energy = np.sum(mag ** 2, axis=0)
    med_energy = medfilt(frame_energy, kernel_size=5)
    energy_ratio = frame_energy / (med_energy + 1e-10)

    geo_mean = np.exp(np.mean(np.log(mag + 1e-10), axis=0))
    arith_mean = np.mean(mag, axis=0) + 1e-10
    spectral_flatness = geo_mean / arith_mean

    energy_threshold = np.mean(energy_ratio) + np.std(energy_ratio) * 0.8
    flatness_threshold = np.mean(spectral_flatness) + np.std(spectral_flatness) * 0.5

    crackle_frames = (energy_ratio > energy_threshold) & (spectral_flatness > flatness_threshold)

    if np.any(crackle_frames):
        for j in np.where(crackle_frames)[0]:
            left_j = max(0, j - 2)
            right_j = min(mag.shape[1], j + 3)
            local_avg = np.mean(mag[:, left_j:right_j], axis=1)
            blend = intensity * 0.7
            phase = np.exp(1j * np.angle(S[:, j]))
            S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase


def _apply_de_essing_v4_inplace(S, mag, sr, n_fft, hop_length, intensity):
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    n_frames = mag.shape[1]

    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)

    kernel_size = min(7, n_frames | 1)
    if kernel_size % 2 == 0:
        kernel_size += 1
    smooth_centroid = medfilt(centroid, kernel_size=kernel_size)

    centroid_ratio = centroid / (smooth_centroid + 1e-10)
    centroid_threshold = 1.0 + np.std(centroid_ratio) * 1.0
    sibilant_frames = centroid_ratio > centroid_threshold

    if not np.any(sibilant_frames):
        return

    sibilant_bands = [
        (2000, 4000, 1.0),
        (4000, 8000, 0.8),
        (8000, 12000, 0.6),
    ]

    for low, high, weight in sibilant_bands:
        band_mask = (freqs >= low) & (freqs <= high)
        if not np.any(band_mask):
            continue

        for j in np.where(sibilant_frames)[0]:
            excess = (centroid_ratio[j] - centroid_threshold) / (centroid_threshold + 1e-10)
            reduction = 1.0 - intensity * 0.35 * weight * min(1.0, excess)
            reduction = max(reduction, 0.25)
            S[band_mask, j] *= reduction


def _apply_noise_reduction_v4_inplace(S, mag, sr, n_fft, hop_length, intensity):
    n_frames = mag.shape[1]
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    alpha = 1 + intensity * 5
    floor = 0.05 + (1 - intensity) * 0.2

    G = np.maximum((mag ** 2 - alpha * noise_profile ** 2) / (mag ** 2 + 1e-10), floor)

    for i in range(1, G.shape[1] - 1):
        G[:, i] = G[:, i] * 0.5 + (G[:, i - 1] + G[:, i + 1]) * 0.25

    S *= G
