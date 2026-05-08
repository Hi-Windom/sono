import numpy as np
from scipy.signal import firwin, lfilter
from services.librosa_compat import stft, istft, fft_frequencies


# QMF 滤波器组参数
QMF_NUM_BANDS = 4
QMF_FILTER_LEN = 128


def create_qmf_bank(num_bands=4, filter_len=128):
    """创建 QMF 滤波器组实现完美重构"""
    prototype = firwin(filter_len, 1.0 / num_bands)
    filters = []
    for k in range(num_bands):
        modulation = np.cos(np.pi * (k + 0.5) * np.arange(filter_len))
        filters.append(prototype * modulation)
    return filters


# 预创建滤波器组（避免重复创建）
_QMF_FILTERS = None

def get_qmf_filters():
    global _QMF_FILTERS
    if _QMF_FILTERS is None:
        _QMF_FILTERS = create_qmf_bank(QMF_NUM_BANDS, QMF_FILTER_LEN)
    return _QMF_FILTERS


def apply_subband_repair(y, sr, params, music_type="generic", n_fft=2048, hop_length=512):
    """
    子带分离处理（Apollo-inspired）
    - 低频子带 (0-500Hz): 直接保留，最小处理
    - 中频子带 (500-4000Hz): Wiener 滤波 + 动态均衡
    - 高频子带 (4000Hz+): 谐波重建 + 自适应去齿音
    """
    result = y.copy()
    filters = get_qmf_filters()

    for ch in range(y.shape[0]):
        data = result[ch]

        # 子带分离
        subbands = []
        for f in filters:
            sb = lfilter(f, 1, data)
            subbands.append(sb)

        # 低频子带 (0-~500Hz): 直接保留，仅轻微降噪
        low_band = subbands[0]
        if params.get("noise_reduction", 0) > 0:
            low_band = _process_low_band(low_band, sr, params["noise_reduction"])

        # 中频子带 (~500-~4000Hz): Wiener 滤波 + 动态均衡
        mid_band = subbands[1] + subbands[2]
        if params.get("noise_reduction", 0) > 0 or params.get("de_essing", 0) > 0:
            mid_band = _process_mid_band(mid_band, sr, params, music_type, n_fft, hop_length)

        # 高频子带 (~4000Hz+): 谐波重建 + 去齿音
        high_band = subbands[3]
        if params.get("de_essing", 0) > 0 or params.get("harmonic_enhance", 0) > 0:
            high_band = _process_high_band(high_band, sr, params, music_type, n_fft, hop_length)

        # 重建
        result[ch] = low_band + mid_band + high_band

    return result


def _process_low_band(audio, sr, noise_reduction):
    """低频子带处理：轻微降噪，保留低频完整性"""
    if noise_reduction < 0.05:
        return audio

    # 低频子带使用更小的 FFT 和 hop，减少计算
    n_fft = 256
    hop = 64
    S = stft(audio, n_fft=n_fft, hop_length=hop)
    mag = np.abs(S)

    # 简单噪声估计
    noise_floor = np.percentile(mag, 5) * 0.5
    gain = np.where(mag > noise_floor, 1.0, 0.7 + 0.3 * (1 - noise_reduction))
    mag *= gain

    S_repaired = mag * np.exp(1j * np.angle(S))
    return istft(S_repaired, hop_length=hop, length=len(audio))


def _process_mid_band(audio, sr, params, music_type, n_fft, hop_length):
    """中频子带处理：Wiener 滤波 + 动态均衡"""
    # 中频子带使用中等 FFT
    S = stft(audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(S)
    phase = np.angle(S)
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)

    n_frames = mag.shape[1]

    # 1. Wiener 降噪
    noise_red = params.get("noise_reduction", 0)
    if noise_red > 0:
        noise_frames = max(1, n_frames // 20)
        noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)
        snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
        gain = snr / (snr + 1.0)

        # 音乐类型适配
        if music_type == "classical":
            floor = 0.3
        elif music_type == "vocal":
            floor = 0.2
        else:
            floor = 0.15

        gain = np.maximum(gain, floor)

        # 时间平滑 - 向量化
        alpha = 0.75
        if n_frames > 1:
            gain_smooth = gain.copy()
            for i in range(1, n_frames):
                gain_smooth[:, i] = alpha * gain_smooth[:, i-1] + (1 - alpha) * gain[:, i]
            gain = gain_smooth

        mag *= gain

    # 2. 自适应去齿音（中频子带也包含部分齿音）
    deess = params.get("de_essing", 0)
    if deess > 0:
        sibilance_mask = (freqs >= 3000) & (freqs <= 6000)
        if np.any(sibilance_mask):
            attenuation = 1.0 - 0.4 * deess
            mag[sibilance_mask, :] *= attenuation

    S_repaired = mag * np.exp(1j * phase)
    return istft(S_repaired, hop_length=hop_length, length=len(audio))


def _process_high_band(audio, sr, params, music_type, n_fft, hop_length):
    """高频子带处理：去齿音 + 谐波重建"""
    S = stft(audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(S)
    phase = np.angle(S)
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)

    # 1. 去齿音
    deess = params.get("de_essing", 0)
    if deess > 0:
        sibilance_mask = (freqs >= 5000) & (freqs <= 9000)
        if np.any(sibilance_mask):
            attenuation = 1.0 - 0.5 * deess
            mag[sibilance_mask, :] *= attenuation

    # 2. 高频谐波重建（轻微增强空气感）
    harmonic = params.get("harmonic_enhance", 0)
    if harmonic > 0 and music_type in ["vocal", "instrumental"]:
        # 基于现有高频内容生成轻微谐波增强
        air_mask = (freqs >= 8000) & (freqs <= 16000)
        if np.any(air_mask):
            air_energy = np.mean(mag[air_mask, :])
            if air_energy > 0.001:
                # 轻微提升空气频段
                boost = 1.0 + harmonic * 0.1
                mag[air_mask, :] *= boost

    S_repaired = mag * np.exp(1j * phase)
    return istft(S_repaired, hop_length=hop_length, length=len(audio))
