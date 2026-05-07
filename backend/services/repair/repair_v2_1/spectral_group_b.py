import numpy as np
import librosa


def apply_spectral_group_b(y, sr, params, n_fft, hop_length, issues_found):
    result = y.copy()
    harmonic_enhance = params.get("harmonic_enhance", 0)
    harmonic_richness = params.get("harmonic_richness", 0)

    enhance_added = "谐波增强v5" in issues_found
    richness_added = "谐波丰富度v2" in issues_found

    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)

        if harmonic_enhance > 0:
            _apply_harmonic_enhance_v5_inplace(S, mag, sr, n_fft, hop_length, harmonic_enhance)
            if not enhance_added:
                issues_found.append("谐波增强v5")
                enhance_added = True
            mag = np.abs(S)

        if harmonic_richness > 0:
            _apply_harmonic_richness_v2_inplace(S, mag, sr, n_fft, hop_length, harmonic_richness)
            if not richness_added:
                issues_found.append("谐波丰富度v2")
                richness_added = True

        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_harmonic_enhance_v5_inplace(S, mag, sr, n_fft, hop_length, intensity):
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2

    base_mask = (freqs >= 80) & (freqs <= 4000)
    base_indices = np.where(base_mask)[0]

    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain in [(2, 0.08), (3, 0.04), (4, 0.02)]:
        target_freqs = freqs[base_indices] * h_num
        valid = target_freqs < (nyquist - 100)
        if not np.any(valid):
            continue
        valid_base = base_indices[valid]
        valid_target_freqs = target_freqs[valid]
        target_indices = np.argmin(np.abs(freqs[:, np.newaxis] - valid_target_freqs[np.newaxis, :]), axis=0)

        gains = np.sqrt(mag[valid_base, :]) * h_gain * intensity
        for i, t_idx in enumerate(target_indices):
            harmonic_content[t_idx, :] += gains[i, :]

    phase = np.exp(1j * np.angle(S))
    enhanced_mag = mag + harmonic_content * intensity * 0.5
    S[:] = enhanced_mag * phase


def _apply_harmonic_richness_v2_inplace(S, mag, sr, n_fft, hop_length, intensity):
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2

    base_mask = (freqs >= 100) & (freqs <= 5000)
    base_indices = np.where(base_mask)[0]

    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain in [(2, 0.06), (3, 0.03)]:
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
