import numpy as np
from scipy.signal import butter, filtfilt
from .type_params import TYPE_PARAMS_MAP


def apply_spatial_enhance_v6(y, sr, intensity, music_type="generic"):
    if y.shape[0] != 2:
        return y

    mid = (y[0] + y[1]) * 0.5
    side = (y[0] - y[1]) * 0.5

    correlation = np.sum(y[0] * y[1]) / (np.sqrt(np.sum(y[0] ** 2) * np.sum(y[1] ** 2)) + 1e-10)

    if music_type == "vocal":
        side_gain = 1 + intensity * 0.3
    elif music_type == "instrumental":
        side_gain = 1 + intensity * 0.5
    elif music_type == "electronic":
        side_gain = 1 + intensity * 0.4
    elif music_type == "classical":
        side_gain = 1 + intensity * 0.2
    else:
        if correlation > 0.8:
            side_gain = 1 + intensity * 0.45
        elif correlation > 0.5:
            side_gain = 1 + intensity * 0.35
        else:
            side_gain = 1 + intensity * 0.25

    low_cutoff = 150
    if sr > low_cutoff * 2:
        b, a = butter(4, low_cutoff / (sr / 2), btype='low')
        side_low = filtfilt(b, a, side)
        side = side_low * 0.3 + (side - side_low)

    high_cutoff = 4000
    if sr > high_cutoff * 2:
        b_h, a_h = butter(4, high_cutoff / (sr / 2), btype='high')
        side_high = filtfilt(b_h, a_h, side)
        high_boost = 1 + intensity * 0.12
        side = side_high * high_boost + (side - side_high)

    enhanced_mid = mid * (1 - intensity * 0.02)
    enhanced_side = side * side_gain

    result = np.zeros_like(y)
    result[0] = enhanced_mid + enhanced_side
    result[1] = enhanced_mid - enhanced_side

    return result


def apply_stereo_width_v3(y, sr, intensity):
    if y.shape[0] != 2:
        return y

    mid = (y[0] + y[1]) * 0.5
    side = (y[0] - y[1]) * 0.5

    width = 1 + intensity * 0.5
    result = np.zeros_like(y)
    result[0] = mid + side * width
    result[1] = mid - side * width

    max_val = np.max(np.abs(result))
    if max_val > 1.0:
        result /= max_val

    return result
