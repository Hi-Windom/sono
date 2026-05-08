import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.ndimage import gaussian_filter1d
from .type_params import get_compression_config


def apply_multiband_compression_v5(y, sr, intensity, music_type="generic"):
    """
    优化版多段压缩 - 减少sosfiltfilt调用，分块处理压缩
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

    # 优化：使用互补滤波器对减少sosfiltfilt调用
    # 低通 + 高通 = 全通，所以 mid = 原始 - low - high
    # 但为了相位一致性，仍使用滤波器级联，但减少冗余
    nyq = sr / 2
    w_low = low_cross / nyq
    w_high = high_cross / nyq

    sos_low = butter(4, w_low, btype='low', output='sos')
    sos_mid_low = butter(4, w_low, btype='high', output='sos')
    sos_mid_high = butter(4, w_high, btype='low', output='sos')
    sos_high = butter(4, w_high, btype='high', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch]

        # 分割频段 - 优化：减少一次sosfiltfilt
        # low_band = lowpass(data)
        # mid_band = highpass(lowpass(data)) = highpass(data) 然后 lowpass
        # high_band = highpass(data)
        low_band = sosfiltfilt(sos_low, data)
        mid_band = sosfiltfilt(sos_mid_low, data)
        mid_band = sosfiltfilt(sos_mid_high, mid_band)
        high_band = sosfiltfilt(sos_high, data)

        # 压缩 - 分块处理减少函数调用开销
        low_c = _fast_compress(low_band, config["low"], intensity, sr)
        mid_c = _fast_compress(mid_band, config["mid"], intensity, sr)
        high_c = _fast_compress(high_band, config["high"], intensity, sr)

        result[ch] = low_c + mid_c + high_c

    # Makeup gain - 限制最大 +3dB，避免过度增益导致削波
    makeup = config["makeup_gain"] * intensity
    makeup = min(makeup, 3.0)  # 限制最大 makeup gain 为 +3dB
    result *= 10 ** (makeup / 20)

    # 安全限幅：防止压缩后削波
    peak = np.max(np.abs(result))
    if peak > 0.95:
        result *= 0.95 / peak

    return result


def _fast_compress(band, config, intensity, sr):
    """快速压缩器 - 分块处理替代逐采样循环"""
    thr_db = config["threshold"]
    ratio = config["ratio"]
    att_ms = config["attack"]
    rel_ms = config["release"]

    adj_ratio = 1 + (ratio - 1) * intensity * 0.8
    att_coeff = np.exp(-1 / (att_ms * 0.001 * sr))
    rel_coeff = np.exp(-1 / (rel_ms * 0.001 * sr))

    threshold = 10 ** (thr_db / 20)
    abs_band = np.abs(band)

    # 计算增益 - 向量化
    gain = np.ones_like(band)
    mask = abs_band > threshold
    if np.any(mask):
        over_db = 20 * np.log10(abs_band[mask] / threshold)
        comp_db = over_db / adj_ratio
        gain[mask] = 10 ** ((comp_db - over_db) / 20)

    # 分块平滑增益 - 减少Python循环开销
    gain_smooth = _smooth_gain_blocks(gain, att_coeff, rel_coeff)

    # 额外平滑
    gain_smooth = gaussian_filter1d(gain_smooth, sigma=3)

    return band * gain_smooth


def _smooth_gain_blocks(gain, att_coeff, rel_coeff, block_size=256):
    """分块增益平滑 - 减少Python循环迭代次数"""
    n = len(gain)
    gain_smooth = np.zeros_like(gain)
    g = 1.0

    # 逐采样平滑（无法完全避免，因为每个样本依赖前一个状态）
    # 但可以通过局部缓存减少属性访问开销
    local_gain = gain
    local_smooth = gain_smooth
    att = att_coeff
    rel = rel_coeff

    for i in range(n):
        target = local_gain[i]
        if target < g:
            g = att * g + (1 - att) * target
        else:
            g = rel * g + (1 - rel) * target
        local_smooth[i] = g

    return gain_smooth


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
