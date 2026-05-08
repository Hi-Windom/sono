import numpy as np
from scipy.signal import butter, filtfilt, lfilter
from scipy.ndimage import gaussian_filter1d
from .type_params import get_compression_config


def apply_multiband_compression_v4(y, sr, intensity, music_type="generic"):
    """
    改进的多段压缩 - 更平滑的包络检测，保护动态
    """
    if intensity < 0.03:
        return y

    # 获取音乐类型特定的压缩配置
    config = get_compression_config(music_type)

    # 频段分割频率
    if music_type == "vocal":
        low_crossover = 250
        high_crossover = 4000
    elif music_type == "electronic":
        low_crossover = 200
        high_crossover = 5000
    elif music_type == "classical":
        low_crossover = 300
        high_crossover = 3500
    else:
        low_crossover = 250
        high_crossover = 4000

    result = np.zeros_like(y)

    for ch in range(y.shape[0]):
        data = y[ch]

        # 分割频段
        b_low, a_low = butter(4, low_crossover / (sr / 2), btype='low')
        low_band = filtfilt(b_low, a_low, data)

        b_mid_low, a_mid_low = butter(4, low_crossover / (sr / 2), btype='high')
        b_mid_high, a_mid_high = butter(4, high_crossover / (sr / 2), btype='low')
        mid_band = filtfilt(b_mid_low, a_mid_low, data)
        mid_band = filtfilt(b_mid_high, a_mid_high, mid_band)

        b_high, a_high = butter(4, high_crossover / (sr / 2), btype='high')
        high_band = filtfilt(b_high, a_high, data)

        # 应用压缩
        low_compressed = _smooth_compress(
            low_band, 
            config["low"]["threshold"],
            config["low"]["ratio"],
            config["low"]["attack"],
            config["low"]["release"],
            sr,
            intensity
        )
        
        mid_compressed = _smooth_compress(
            mid_band,
            config["mid"]["threshold"],
            config["mid"]["ratio"],
            config["mid"]["attack"],
            config["mid"]["release"],
            sr,
            intensity
        )
        
        high_compressed = _smooth_compress(
            high_band,
            config["high"]["threshold"],
            config["high"]["ratio"],
            config["high"]["attack"],
            config["high"]["release"],
            sr,
            intensity
        )

        # 混合频段 - 使用并行压缩概念
        result[ch] = low_compressed + mid_compressed + high_compressed

    # 应用 makeup gain
    makeup_gain = config["makeup_gain"] * intensity
    result *= 10 ** (makeup_gain / 20)

    return result


def _smooth_compress(band, threshold_db, ratio, attack_ms, release_ms, sr, intensity):
    """
    平滑压缩器 - 使用 RMS 检测和更平滑的包络
    """
    threshold_lin = 10 ** (threshold_db / 20)
    
    # 根据强度调整参数
    adjusted_ratio = 1 + (ratio - 1) * intensity * 0.8
    adjusted_attack = attack_ms * (1.5 - intensity * 0.3)  # 强度越高，attack 越短
    adjusted_release = release_ms * (1.2 - intensity * 0.2)
    
    # 计算 RMS 包络（比峰值更平滑）
    window_size = int(adjusted_attack * 0.001 * sr / 10)  # 约 1/10 的 attack 时间
    if window_size < 2:
        window_size = 2
    
    # 使用滑动窗口 RMS
    rms_envelope = np.sqrt(
        np.convolve(band ** 2, np.ones(window_size) / window_size, mode='same')
    )
    
    # 平滑包络
    rms_envelope = gaussian_filter1d(rms_envelope, sigma=window_size / 2)
    
    # 计算增益
    gain = np.ones(len(band))
    over = rms_envelope > threshold_lin
    
    if np.any(over):
        # 转换为 dB 计算
        over_db = 20 * np.log10(rms_envelope[over] / threshold_lin)
        compressed_db = over_db / adjusted_ratio
        gain_db = compressed_db - over_db
        gain[over] = 10 ** (gain_db / 20)
    
    # 平滑增益变化（减少抽吸效应）
    attack_coeff = np.exp(-1 / (adjusted_attack * 0.001 * sr))
    release_coeff = np.exp(-1 / (adjusted_release * 0.001 * sr))
    
    # 分别处理 attack 和 release
    smoothed_gain = np.ones(len(band))
    current_gain = 1.0
    
    for i in range(len(band)):
        target_gain = gain[i]
        if target_gain < current_gain:
            # Attack - 快速响应
            current_gain = attack_coeff * current_gain + (1 - attack_coeff) * target_gain
        else:
            # Release - 缓慢恢复
            current_gain = release_coeff * current_gain + (1 - release_coeff) * target_gain
        smoothed_gain[i] = current_gain
    
    # 额外的平滑
    smoothed_gain = gaussian_filter1d(smoothed_gain, sigma=window_size / 3)
    
    return band * smoothed_gain


def apply_parallel_compression(y, sr, intensity, music_type="generic"):
    """
    并行压缩（New York Compression）- 保留动态的同时增加密度
    """
    if intensity < 0.05:
        return y
    
    # 获取配置
    config = get_compression_config(music_type)
    
    # 使用整体压缩配置
    thresh = config["mid"]["threshold"]
    ratio = config["mid"]["ratio"] * 1.5  # 并行压缩使用更高比例
    attack = config["mid"]["attack"] * 0.5
    release = config["mid"]["release"] * 0.8
    
    result = np.zeros_like(y)
    
    for ch in range(y.shape[0]):
        data = y[ch]
        
        # 压缩信号
        compressed = _smooth_compress(data, thresh, ratio, attack, release, sr, intensity)
        
        # 并行混合：原始信号 + 压缩信号
        blend = intensity * 0.4  # 压缩信号占比
        result[ch] = data * (1 - blend) + compressed * blend
    
    return result


def apply_softness_v4(y, sr, intensity):
    """
    改进的柔化处理 - 更温和的高频衰减
    """
    if intensity < 0.01:
        return y
    
    result = y.copy()
    
    # 更保守的截止频率
    cutoff = max(10000, 20000 - intensity * 8000)
    cutoff = min(cutoff, sr / 2 - 200)
    nyq = sr / 2
    normalized_cutoff = cutoff / nyq
    
    if normalized_cutoff <= 0 or normalized_cutoff >= 1:
        return result
    
    b, a = butter(2, normalized_cutoff, btype='low')  # 2阶 instead of 4阶，更温和
    blend = intensity * 0.15  # 降低混合比例
    
    for ch in range(y.shape[0]):
        filtered = filtfilt(b, a, result[ch])
        result[ch] = filtered * blend + result[ch] * (1 - blend)
    
    return result
