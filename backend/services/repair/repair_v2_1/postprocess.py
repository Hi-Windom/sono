import numpy as np
from scipy.signal import butter, filtfilt, lfilter


def apply_loudness_normalize_v3(y, sr, target_lufs):
    result = y.copy()

    try:
        for ch in range(y.shape[0]):
            data = result[ch].copy()

            if 60 < sr / 2:
                b_hp, a_hp = butter(2, 60 / (sr / 2), btype='high')
                data = filtfilt(b_hp, a_hp, data)

            shelf_low = 800 / (sr / 2)
            shelf_high = 1200 / (sr / 2)
            if shelf_high < 1.0 and shelf_high > shelf_low:
                b_shelf, a_shelf = butter(2, [shelf_low, shelf_high], btype='band')
                shelf_signal = filtfilt(b_shelf, a_shelf, data)
                data = data + shelf_signal * (10 ** (4.0 / 20) - 1)

            rms = np.sqrt(np.mean(data ** 2))
            if rms < 1e-8:
                continue
            current_lufs = 20 * np.log10(rms) - 0.691
            gain_db = np.clip(target_lufs - current_lufs, -12, 12)
            result[ch] *= 10 ** (gain_db / 20)
    except Exception:
        for ch in range(y.shape[0]):
            rms = np.sqrt(np.mean(result[ch] ** 2))
            if rms < 1e-8:
                continue
            current_lufs = 20 * np.log10(rms) - 0.691
            gain_db = np.clip(target_lufs - current_lufs, -12, 12)
            result[ch] *= 10 ** (gain_db / 20)

    return result


def apply_peak_limit_v3(y, sr, threshold_db=-0.5):
    threshold = 10 ** (threshold_db / 20)
    attack_ms = 5.0
    release_ms = 50.0
    attack_coeff = np.exp(-1 / (attack_ms * 0.001 * sr))
    release_coeff = np.exp(-1 / (release_ms * 0.001 * sr))

    result = y.copy()

    for ch in range(y.shape[0]):
        data = result[ch]
        abs_data = np.abs(data)

        b_env = np.array([1.0 - attack_coeff])
        a_env = np.array([1.0, -attack_coeff])
        attack_env = lfilter(b_env, a_env, abs_data)

        b_rel = np.array([1.0 - release_coeff])
        a_rel = np.array([1.0, -release_coeff])
        release_env = lfilter(b_rel, a_rel, abs_data)

        envelope = np.maximum(attack_env, release_env)

        over = envelope > threshold
        if not np.any(over):
            max_val = np.max(np.abs(result[ch]))
            if max_val > 1.0:
                result[ch] /= max_val
            continue

        gain_reduction = np.ones(len(data))
        gain_reduction[over] = threshold / envelope[over]

        b_atk = np.array([1.0 - attack_coeff])
        a_atk = np.array([1.0, -attack_coeff])
        smooth_atk = lfilter(b_atk, a_atk, gain_reduction)

        b_rel2 = np.array([1.0 - release_coeff])
        a_rel2 = np.array([1.0, -release_coeff])
        smooth_rel = lfilter(b_rel2, a_rel2, gain_reduction)

        smooth_gain = np.minimum(smooth_atk, smooth_rel)
        smooth_gain = np.clip(smooth_gain, 0, 1)
        result[ch] = data * smooth_gain

        max_val = np.max(np.abs(result[ch]))
        if max_val > threshold:
            soft_clip = threshold * np.tanh(result[ch] / threshold)
            blend = np.clip((np.abs(result[ch]) - threshold) / (max_val - threshold + 1e-10), 0, 1)
            result[ch] = result[ch] * (1 - blend) + soft_clip * blend

    return result
