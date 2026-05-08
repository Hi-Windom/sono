import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from .type_params import TYPE_PARAMS_MAP


def apply_spectral_group_b(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    result = y.copy()
    harmonic_enhance = params.get("harmonic_enhance", 0)
    harmonic_richness = params.get("harmonic_richness", 0)

    enhance_added = "谐波增强v6" in issues_found
    richness_added = "谐波丰富度v3" in issues_found

    for ch in range(y.shape[0]):
        data = result[ch]
        S = stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)

        if harmonic_enhance > 0:
            _apply_harmonic_enhance_v6_inplace(S, mag, sr, n_fft, hop_length, harmonic_enhance, music_type)
            if not enhance_added:
                issues_found.append("谐波增强v6")
                enhance_added = True
            mag = np.abs(S)

        if harmonic_richness > 0:
            _apply_harmonic_richness_v3_inplace(S, mag, sr, n_fft, hop_length, harmonic_richness, music_type)
            if not richness_added:
                issues_found.append("谐波丰富度v3")
                richness_added = True

        result[ch] = istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_harmonic_enhance_v6_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type):
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2

    if music_type == "vocal":
        base_mask = (freqs >= 80) & (freqs <= 4000)
        harmonics = [(2, 0.12), (3, 0.08)]
    elif music_type == "instrumental":
        base_mask = (freqs >= 60) & (freqs <= 5000)
        harmonics = [(2, 0.1), (3, 0.06), (4, 0.03)]
    elif music_type == "classical":
        base_mask = (freqs >= 60) & (freqs <= 4000)
        harmonics = [(2, 0.05), (3, 0.03)]
    elif music_type == "electronic":
        base_mask = (freqs >= 40) & (freqs <= 2000)
        harmonics = [(2, 0.15), (3, 0.08)]
    else:
        base_mask = (freqs >= 80) & (freqs <= 4000)
        harmonics = [(2, 0.08), (3, 0.04), (4, 0.02)]

    base_indices = np.where(base_mask)[0]
    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain in harmonics:
        target_freqs = freqs[base_indices] * h_num
        valid = target_freqs < (nyquist - 100)
        if not np.any(valid):
            continue
        valid_base = base_indices[valid]
        valid_target_freqs = target_freqs[valid]
        target_indices = np.argmin(np.abs(freqs[:, np.newaxis] - valid_target_freqs[np.newaxis, :]), axis=0)

        crossfade = np.hanning(len(base_indices))
        gains = np.sqrt(mag[valid_base, :]) * h_gain * intensity * crossfade[:, np.newaxis]
        for i, t_idx in enumerate(target_indices):
            harmonic_content[t_idx, :] += gains[i, :]

    phase = np.exp(1j * np.angle(S))
    enhanced_mag = mag + harmonic_content * intensity * 0.5
    S[:] = enhanced_mag * phase


def _apply_harmonic_richness_v3_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type):
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2

    if music_type == "vocal":
        base_mask = (freqs >= 100) & (freqs <= 4000)
        harmonics = [(2, 0.08), (3, 0.04)]
    elif music_type == "instrumental":
        base_mask = (freqs >= 80) & (freqs <= 5000)
        harmonics = [(2, 0.1), (3, 0.05)]
    elif music_type == "classical":
        base_mask = (freqs >= 60) & (freqs <= 4000)
        harmonics = [(2, 0.04), (3, 0.02)]
    else:
        base_mask = (freqs >= 100) & (freqs <= 5000)
        harmonics = [(2, 0.06), (3, 0.03)]

    base_indices = np.where(base_mask)[0]
    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain in harmonics:
        target_freqs = freqs[base_indices] * h_num
        valid = target_freqs < (nyquist - 100)
        if not np.any(valid):
            continue
        valid_base = base_indices[valid]
        valid_target_freqs = target_freqs[valid]
        target_indices = np.argmin(np.abs(freqs[:, np.newaxis] - valid_target_freqs[np.newaxis, :]), axis=0)

        gains = mag[valid_base, :] * h_gain * intensity
        for i, t_idx in enumerate(target_indices):
            harmonic_content[t_idx, :] += gains[i, :]

    phase = np.exp(1j * np.angle(S))
    enhanced_mag = mag + harmonic_content
    S[:] = enhanced_mag * phase
