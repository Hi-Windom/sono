import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.ndimage import gaussian_filter1d
from .type_params import get_compression_config


def apply_multiband_compression_v5(y, sr, intensity, music_type="generic"):
    """
    优化版多段压缩 - 使用 SOS 滤波，更高效
    """
    if intensity < 0.03:
        return y

    config = get_compression_config(music_type)

    if music_type == "vocal":
        low_cross = 250
        high_cross = 4000
    elif music_type == "electronic":
        low_cross = 200
        high_cross = 5000
    elif music_type == "classical":
        low_cross = 300
        high_cross = 3500
    else:
        low_cross = 250
        high_cross = 4000

    result = np.zeros_like(y)

    # 优化：使用 SOS 格式滤波，比 TF 格式快
    sos_low = butter(4, low_cross / (sr / 2), btype='low', output='sos')
    sos_mid_low = butter(4, low_cross / (sr / 2), btype='high', output='sos')
    sos_mid_high = butter(4, high_cross / (sr / 2), btype='low', output='sos')
    sos_high = butter(4, high_cross / (sr / 2), btype='high', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch]

        # 分割频段
        low_band = sosfiltfilt(sos_low, data)
        mid_band = sosfiltfilt(sos_mid_low, data)
        mid_band = sosfiltfilt(sos_mid_high, mid_band)
        high_band = sosfiltfilt(sos_high, data)

        # 压缩
        low_c = _fast_compress(low_band, config["low"], intensity, sr)
        mid_c = _fast_compress(mid_band, config["mid"], intensity, sr)
        high_c = _fast_compress(high_band, config["high"], intensity, sr)

        result[ch] = low_c + mid_c + high_c

    # Makeup gain
    makeup = config["makeup_gain"] * intensity
    result *= 10 ** (makeup / 20)

    return result


def _fast_compress(band, config, intensity, sr):
    """快速压缩器 - 向量化实现"""
    thr_db = config["threshold"]
    ratio = config["ratio"]
    att_ms = config["attack"]
    rel_ms = config["release"]

    adj_ratio = 1 + (ratio - 1) * intensity * 0.8
    att_coeff = np.exp(-1 / (att_ms * 0.001 * sr))
    rel_coeff = np.exp(-1 / (rel_ms * 0.001 * sr))

    threshold = 10 ** (thr_db / 20)
    abs_band = np.abs(band)

    # 计算增益 - 矢量化
    gain = np.ones_like(band)
    mask = abs_band > threshold
    if np.any(mask):
        over_db = 20 * np.log10(abs_band[mask] / threshold)
        comp_db = over_db / adj_ratio
        gain[mask] = 10 ** ((comp_db - over_db) / 20)

    # 平滑增益
    gain_smooth = np.zeros_like(gain)
    g = 1.0
    for i in range(len(band)):
        if gain[i] < g:
            g = att_coeff * g + (1 - att_coeff) * gain[i]
        else:
            g = rel_coeff * g + (1 - rel_coeff) * gain[i]
        gain_smooth[i] = g

    # 额外平滑
    gain_smooth = gaussian_filter1d(gain_smooth, sigma=3)

    return band * gain_smooth


def apply_softness_v5(y, sr, intensity):
    """优化柔化 - 使用 SOS 滤波"""
    if intensity < 0.01:
        return y

    result = y.copy()

    cutoff = max(10000, 20000 - intensity * 8000)
    cutoff = min(cutoff, sr / 2 - 200)
    nyq = sr / 2
    norm_cutoff = cutoff / nyq

    if norm_cutoff <= 0 or norm_cutoff >= 1:
        return result

    # 使用 SOS 格式，更高效
    sos = butter(2, norm_cutoff, btype='low', output='sos')
    blend = intensity * 0.12

    for ch in range(y.shape[0]):
        filtered = sosfiltfilt(sos, result[ch])
        result[ch] = filtered * blend + result[ch] * (1 - blend)

    return result
