import numpy as np
from scipy.signal import butter, filtfilt


def apply_multiband_compression_v2(y, sr, intensity):
    if intensity < 0.05:
        return y

    low_crossover = 250
    high_crossover = 4000

    result = np.zeros_like(y)

    for ch in range(y.shape[0]):
        data = y[ch]

        b_low, a_low = butter(4, low_crossover / (sr / 2), btype='low')
        low_band = filtfilt(b_low, a_low, data)

        b_mid_low, a_mid_low = butter(4, low_crossover / (sr / 2), btype='high')
        b_mid_high, a_mid_high = butter(4, high_crossover / (sr / 2), btype='low')
        mid_band = filtfilt(b_mid_low, a_mid_low, data)
        mid_band = filtfilt(b_mid_high, a_mid_high, mid_band)

        b_high, a_high = butter(4, high_crossover / (sr / 2), btype='high')
        high_band = filtfilt(b_high, a_high, data)

        bands = [
            (low_band, -20, 3.0, 10.0, 100.0),
            (mid_band, -18 + intensity * 2, 2.5 + intensity * 2, 5.0, 80.0),
            (high_band, -16 + intensity * 3, 2.0 + intensity * 3, 3.0, 60.0),
        ]

        compressed_bands = []
        for band, thresh_db, ratio, attack_ms, release_ms in bands:
            compressed_bands.append(_simple_compress(band, thresh_db, ratio, attack_ms, release_ms, sr))

        result[ch] = sum(compressed_bands)

    makeup_gain = intensity * 1.5
    result *= 10 ** (makeup_gain / 20)

    return result


def _simple_compress(band, threshold_db, ratio, attack_ms, release_ms, sr):
    threshold_lin = 10 ** (threshold_db / 20)
    attack_coeff = np.exp(-1 / (attack_ms * 0.001 * sr))
    release_coeff = np.exp(-1 / (release_ms * 0.001 * sr))

    envelope = np.zeros(len(band))
    envelope[0] = np.abs(band[0])
    for i in range(1, len(band)):
        sample_abs = np.abs(band[i])
        coeff = attack_coeff if sample_abs > envelope[i - 1] else release_coeff
        envelope[i] = coeff * envelope[i - 1] + (1 - coeff) * sample_abs

    gain = np.ones(len(band))
    over = envelope > threshold_lin
    if np.any(over):
        over_db = 20 * np.log10(envelope[over] / threshold_lin)
        compressed_db = over_db / ratio
        gain[over] = 10 ** ((compressed_db - over_db) / 20)

    return band * gain


def apply_softness_v2(y, sr, intensity):
    result = y.copy()
    cutoff = max(8000, 18000 - intensity * 8000)
    cutoff = min(cutoff, sr / 2 - 100)
    nyq = sr / 2
    normalized_cutoff = cutoff / nyq

    if normalized_cutoff <= 0 or normalized_cutoff >= 1:
        return result

    b, a = butter(4, normalized_cutoff, btype='low')
    blend = intensity * 0.25
    for ch in range(y.shape[0]):
        filtered = filtfilt(b, a, result[ch])
        result[ch] = filtered * blend + result[ch] * (1 - blend)
    return result
