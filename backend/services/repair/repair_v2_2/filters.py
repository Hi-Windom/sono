import numpy as np
from scipy.signal import butter, filtfilt, lfilter
from .type_params import TYPE_PARAMS_MAP


def apply_presence_boost_v5(y, sr, intensity, music_type="generic"):
    """优化临场增强 - 合并频段处理，减少filtfilt调用"""
    result = y.copy()
    nyq = sr / 2

    if music_type == "vocal":
        bands = [
            (1500, 3000, 1.0),
            (3000, 6000, 0.8),
        ]
    elif music_type == "classical":
        bands = [
            (2000, 4000, 0.6),
            (4000, 6000, 0.4),
        ]
    else:
        bands = [
            (2000, 4000, 1.0),
            (4000, 6000, 0.6),
        ]

    # 优化：为每个通道一次性处理所有频段
    # 预计算所有滤波器系数
    filters = []
    for freq_low, freq_high, weight in bands:
        low = freq_low / nyq
        high = freq_high / nyq
        if high >= 1.0 or high <= low:
            continue
        b, a = butter(2, [low, high], btype='band')
        filters.append((b, a, weight))

    if not filters:
        return result

    for ch in range(y.shape[0]):
        for b, a, weight in filters:
            presence = filtfilt(b, a, result[ch])
            result[ch] += presence * intensity * weight * 0.25

    return result


def apply_bass_enhance_v5(y, sr, intensity, music_type="generic"):
    """优化低音增强 - 减少不必要的复制"""
    nyq = sr / 2

    if music_type == "electronic":
        cutoff = 150 / nyq
        gain = 0.35
    elif music_type == "classical":
        cutoff = 100 / nyq
        gain = 0.15
    else:
        cutoff = 120 / nyq
        gain = 0.25

    if cutoff >= 1.0:
        return y

    b, a = butter(2, cutoff, btype='low')
    result = y.copy()

    for ch in range(y.shape[0]):
        bass = filtfilt(b, a, result[ch])
        result[ch] += bass * intensity * gain

    return result


def apply_warmth_v2(y, sr, intensity, music_type="generic"):
    """优化温暖度 - 减少滤波器创建和filtfilt调用"""
    nyq = sr / 2

    if music_type == "vocal":
        low_cutoff = 600 / nyq
        rect_cutoff = 1200 / nyq
        gain = 0.2
    elif music_type == "classical":
        low_cutoff = 400 / nyq
        rect_cutoff = 800 / nyq
        gain = 0.1
    else:
        low_cutoff = 500 / nyq
        rect_cutoff = 1000 / nyq
        gain = 0.15

    if low_cutoff >= 1.0:
        return y

    b_low, a_low = butter(2, low_cutoff, btype='low')
    if rect_cutoff >= 1.0:
        rect_cutoff = 0.99
    b_rect, a_rect = butter(2, rect_cutoff, btype='low')

    result = y.copy()

    for ch in range(y.shape[0]):
        low_signal = filtfilt(b_low, a_low, result[ch])
        rectified = np.abs(low_signal)
        even_harmonics = filtfilt(b_rect, a_rect, rectified)
        result[ch] += even_harmonics * intensity * gain

    return result


def apply_clarity_v2(y, sr, intensity, music_type="generic"):
    """优化清晰度 - 合并频段处理，减少filtfilt调用"""
    nyq = sr / 2

    if music_type == "vocal":
        bands = [
            (2000, 4000, 0.5),
            (4000, 8000, 1.0),
            (8000, 12000, 0.7),
        ]
    elif music_type == "classical":
        bands = [
            (3000, 6000, 0.6),
            (6000, 10000, 0.4),
        ]
    else:
        bands = [
            (2000, 4000, 0.4),
            (4000, 8000, 1.0),
            (8000, 12000, 0.6),
        ]

    # 预计算所有滤波器系数
    filters = []
    for freq_low, freq_high, weight in bands:
        low = freq_low / nyq
        high = freq_high / nyq
        if high >= 1.0 or high <= low:
            continue
        b, a = butter(2, [low, high], btype='band')
        band_gain = intensity * weight * 0.55
        filters.append((b, a, band_gain))

    if not filters:
        return y

    result = y.copy()

    for ch in range(y.shape[0]):
        for b, a, band_gain in filters:
            band_signal = filtfilt(b, a, result[ch])
            result[ch] += band_signal * band_gain

    return result
