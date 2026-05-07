import numpy as np
from scipy.signal import butter, filtfilt


def apply_presence_boost_v4(y, sr, intensity):
    result = y.copy()
    nyq = sr / 2
    low = 2000 / nyq
    high = 6000 / nyq
    if high >= 1.0 or high <= low:
        return result
    b, a = butter(2, [low, high], btype='band')
    for ch in range(y.shape[0]):
        presence = filtfilt(b, a, result[ch])
        result[ch] += presence * intensity * 0.3
    return result


def apply_bass_enhance_v4(y, sr, intensity):
    result = y.copy()
    nyq = sr / 2
    cutoff = 120 / nyq
    if cutoff >= 1.0:
        return result
    b, a = butter(2, cutoff, btype='low')
    for ch in range(y.shape[0]):
        bass = filtfilt(b, a, result[ch])
        result[ch] += bass * intensity * 0.25
    return result


def apply_warmth(y, sr, intensity):
    result = y.copy()
    nyq = sr / 2
    low_cutoff = 500 / nyq
    if low_cutoff >= 1.0:
        return result
    b_low, a_low = butter(2, low_cutoff, btype='low')
    rect_cutoff = 1000 / nyq
    if rect_cutoff >= 1.0:
        rect_cutoff = 0.99
    b_rect, a_rect = butter(2, rect_cutoff, btype='low')

    for ch in range(y.shape[0]):
        low_signal = filtfilt(b_low, a_low, result[ch])
        rectified = np.abs(low_signal)
        even_harmonics = filtfilt(b_rect, a_rect, rectified)
        result[ch] += even_harmonics * intensity * 0.15
    return result


def apply_clarity(y, sr, intensity):
    result = y.copy()
    nyq = sr / 2
    cutoff = 4000 / nyq
    if cutoff >= 1.0:
        return result
    boost_db = intensity * 3.0
    gain = 10 ** (boost_db / 20) - 1
    b, a = butter(2, cutoff, btype='high')
    for ch in range(y.shape[0]):
        high_freq = filtfilt(b, a, result[ch])
        result[ch] += high_freq * gain
    return result
