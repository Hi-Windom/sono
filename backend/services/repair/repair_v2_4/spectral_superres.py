import numpy as np
from scipy.signal import medfilt
from typing import Dict, Optional
from services.dsp_utils import stft, istft, streaming_spectral_process


N_FFT = 2048
HOP_LENGTH = 512


def hifi_spectral_superresolution(y: np.ndarray, sr: int, amount: float,
                                   tempo_params: Optional[Dict] = None) -> np.ndarray:
    """
    HiFi 频谱超分/重建 - 增强版（类似 QQ 音乐臻品母带效果）

    核心功能：
    - 基于谐波关系的高频智能重建
    - 更强的频谱细节增强和增益
    - 瞬态保护，避免过度处理
    - 相位相干的超分处理

    Args:
        y: 输入音频 (n_channels, n_samples) 或 (n_samples,)
        sr: 采样率
        amount: 超分强度 0-1
        tempo_params: 节奏参数（可选，用于瞬态保护）

    Returns:
        处理后的音频
    """
    if amount <= 0:
        return y

    tempo_params = tempo_params or {}

    # 处理单声道
    if y.ndim == 1:
        return _hifi_superres_channel(y, sr, amount, tempo_params)

    # 处理立体声/多声道
    result = np.zeros_like(y)
    for ch in range(y.shape[0]):
        result[ch] = _hifi_superres_channel(y[ch], sr, amount, tempo_params)
    return result


def _hifi_superres_channel(y_1d: np.ndarray, sr: int, amount: float,
                           tempo_params: Dict) -> np.ndarray:
    """处理单声道音频"""
    n_samples = len(y_1d)
    if n_samples < N_FFT:
        return y_1d

    # 根据音频长度决定是否使用流式处理
    duration_sec = n_samples / sr
    use_streaming = duration_sec > 300  # 5分钟以上使用流式

    if use_streaming:
        def _process_chunk(S, sr_chunk, n_fft, hop_length):
            return _hifi_superres_spectral(S, sr_chunk, amount, tempo_params)

        result = streaming_spectral_process(
            y_1d.astype(np.float64), sr,
            _process_chunk,
            n_fft=N_FFT, hop_length=HOP_LENGTH,
            chunk_seconds=10
        )
        return result.astype(y_1d.dtype)

    # 非流式处理
    S = stft(y_1d, n_fft=N_FFT, hop_length=HOP_LENGTH)
    S = _hifi_superres_spectral(S, sr, amount, tempo_params)
    y_out = istft(S, hop_length=HOP_LENGTH, length=n_samples)
    return y_out.astype(y_1d.dtype)


def _hifi_superres_spectral(S: np.ndarray, sr: int, amount: float,
                             tempo_params: Dict) -> np.ndarray:
    """
    频域超分处理 - 增强版
    """
    mag = np.abs(S)
    phase = np.angle(S)

    # 1. 检测瞬态帧
    transient_frames = _detect_transients_superres(mag, amount)

    # 2. 计算瞬态保护强度
    transient_preservation = tempo_params.get("transient_preservation", 0.5)

    # 3. 基于谐波关系重建高频（增强版）
    enhanced_mag = _harmonic_spectral_reconstruction(
        mag, sr, amount, transient_frames, transient_preservation
    )

    # 4. 相位相干处理
    enhanced_phase = _phase_coherent_enhancement(phase, mag, sr, amount)

    # 5. 基于节奏参数的频段微调
    enhanced_mag = _tempo_adaptive_band_boost(
        enhanced_mag, sr, amount, tempo_params
    )

    # 6. 重建复数频谱
    S_out = enhanced_mag * np.exp(1j * enhanced_phase)

    return S_out


def _detect_transients_superres(mag: np.ndarray, sensitivity: float) -> np.ndarray:
    """检测瞬态帧（用于超分处理）"""
    # 计算每帧能量
    frame_energy = np.sum(mag ** 2, axis=0)

    # 计算能量变化
    energy_change = np.abs(np.diff(frame_energy, prepend=frame_energy[0]))

    # 计算阈值
    mean_change = np.mean(energy_change)
    std_change = np.std(energy_change)

    # 自适应阈值（超分用更高的灵敏度）
    threshold = mean_change + std_change * (1.2 + sensitivity * 0.3)

    # 检测瞬态
    transient_frames = energy_change > threshold

    # 扩展瞬态保护窗口（前后各2帧）
    if len(transient_frames) > 4:
        extended = transient_frames.copy()
        # 向前扩展
        for i in range(1, len(extended)):
            extended[i] = extended[i] or extended[i - 1]
        # 向后扩展
        for i in range(len(extended) - 2, -1, -1):
            extended[i] = extended[i] or extended[i + 1]
        transient_frames = extended

    return transient_frames


def _harmonic_spectral_reconstruction(mag: np.ndarray, sr: int, amount: float,
                                        transient_frames: np.ndarray,
                                        preservation: float) -> np.ndarray:
    """
    基于谐波关系的高频重建 - 增强版（类似 QQ 音乐臻品母带效果）

    方法：
    1. 分析全频段能量分布
    2. 基于低频谐波模式智能外推高频
    3. 更强的高频增益和细节增强
    """
    enhanced = mag.copy()
    freqs = np.arange(mag.shape[0]) * sr / N_FFT

    # 定义频段（更宽的覆盖范围）
    low_mid_cut = 1000
    mid_high_cut = 4000
    high_start = 7000  # 提前开始超分
    very_high_start = 10000  # 更早开始空气感重建

    # 找到频率索引
    low_mid_idx = np.searchsorted(freqs, low_mid_cut)
    mid_high_idx = np.searchsorted(freqs, mid_high_cut)
    high_start_idx = np.searchsorted(freqs, high_start)
    very_high_idx = np.searchsorted(freqs, very_high_start)

    # 计算非瞬态帧掩码
    non_transient = ~transient_frames
    transient_boost = 1.0 - preservation * 0.7

    # 1. 从 4-7kHz 分析谐波模式，重建 7kHz+（更宽范围）
    if mid_high_idx < high_start_idx:
        source_band = mag[mid_high_idx:high_start_idx, :]
        target_band = enhanced[high_start_idx:, :]

        for j in range(mag.shape[1]):
            if not non_transient[j]:
                # 瞬态帧：直接增强
                transient_scale = 1.0 + amount * 0.3
                enhanced[high_start_idx:, j] *= transient_scale
                continue

            source_frame = source_band[:, j]
            target_len = target_band.shape[0]
            source_len = source_frame.shape[0]

            if source_len > 0 and target_len > 0:
                harmonic_reconstructed = np.zeros(target_len)
                harmonic_scaling = 1.15  # 更强的谐波幅度

                # 计算源能量
                source_energy = np.sqrt(np.mean(source_frame ** 2) + 1e-10)

                for i in range(target_len):
                    # 使用多个源频率的谐波关系，而非单一频率
                    # 寻找最佳匹配的谐波倍频
                    best_matches = []
                    for harmonic_order in range(1, 5):
                        freq_harmonic = freqs[high_start_idx + i] / harmonic_order
                        nearest_idx = int(freq_harmonic * N_FFT / sr)
                        nearest_idx = np.clip(nearest_idx, 0, mag.shape[0] - 1)
                        if nearest_idx < len(mag):
                            # 加权：越高频权重越高（衰减自然趋势）
                            weight = 1.0 / harmonic_order
                            best_matches.append((mag[nearest_idx, j] * harmonic_order * (1.0 / harmonic_order), weight))

                    if best_matches:
                        # 加权平均
                        total_weight = sum(w for _, w in best_matches)
                        if total_weight > 0:
                            harmonic_reconstructed[i] = sum(v * w for v, w in best_matches) / total_weight

                # 应用频谱包络增强（模仿自然频谱衰减但更平缓）
                for i in range(target_len):
                    freq = freqs[high_start_idx + i]
                    # 高频衰减更慢，保持高频亮度
                    freq_decay = 1.0 / (1.0 + (freq / 18000) ** 1.5)
                    harmonic_reconstructed[i] *= freq_decay

                # 与原始混合，新重建内容更高的比例
                blend_factor = amount * 0.65  # 更强的混合
                blend = blend_factor * harmonic_reconstructed + (1.0 - blend_factor) * target_band[:, j]
                # 额外的整体增益
                overall_gain = 1.0 + amount * 0.35
                blend *= overall_gain
                enhanced[high_start_idx:, j] = blend

    # 2. 对 10kHz+ 进行更强的空气感重建
    if very_high_idx < mag.shape[0]:
        envelope_source = mag[high_start_idx:very_high_idx, :]

        for j in range(mag.shape[1]):
            if not non_transient[j]:
                continue

            # 计算源能量
            source_energy = np.sqrt(np.mean(envelope_source[:, j] ** 2) + 1e-10)

            very_high_len = mag.shape[0] - very_high_idx
            # 增加噪声强度
            air_noise = np.random.randn(very_high_len) * 0.025 * amount
            # 添加频谱结构 - 更慢的衰减
            freq_indices = np.arange(very_high_idx, mag.shape[0])
            decay = 1.0 / (1.0 + (freqs[freq_indices] / 20000) ** 1.2)
            air_noise *= decay * source_energy

            # 混合到原始
            blend = air_noise * amount * 0.45 + enhanced[very_high_idx:, j]
            enhanced[very_high_idx:, j] = blend

    # 3. 2-7kHz 频段细节增强（更宽的临场感提升）
    presence_low = 1800
    presence_high = 7500
    pres_low_idx = np.searchsorted(freqs, presence_low)
    pres_high_idx = np.searchsorted(freqs, presence_high)

    if pres_low_idx < pres_high_idx:
        for j in range(mag.shape[1]):
            if non_transient[j]:
                freq_line = enhanced[pres_low_idx:pres_high_idx, j]
                # 使用更细的中值滤波提取细节
                smoothed = medfilt(freq_line, kernel_size=3)
                details = freq_line - smoothed
                # 更强的细节增强
                enhanced_details = smoothed + details * (1.0 + amount * 0.6)
                # 小的整体增益
                enhanced_details *= (1.0 + amount * 0.15)
                enhanced[pres_low_idx:pres_high_idx, j] = enhanced_details
            else:
                # 瞬态帧保持原样或轻微增强
                enhanced[pres_low_idx:pres_high_idx, j] *= (1.0 + amount * 0.12)

    # 4. 低频和中低频的谐波增强（提升整体亮度和冲击力）
    low_presence_low = 100
    low_presence_high = 2000
    low_pres_low_idx = np.searchsorted(freqs, low_presence_low)
    low_pres_high_idx = np.searchsorted(freqs, low_presence_high)

    if low_pres_low_idx < low_pres_high_idx:
        for j in range(mag.shape[1]):
            # 对非瞬态帧进行谐波增强
            if non_transient[j]:
                freq_line = enhanced[low_pres_low_idx:low_pres_high_idx, j]
                # 轻微增强低频谐波
                line_avg = np.mean(freq_line)
                # 增加低频能量的轻微抬升
                for i in range(len(freq_line)):
                    freq = freqs[low_pres_low_idx + i]
                    # 只在低频增加谐波
                    if freq < 500:
                        harmonic_boost = 1.0 + amount * 0.25
                        freq_line[i] *= harmonic_boost
                enhanced[low_pres_low_idx:low_pres_high_idx, j] = freq_line

    return enhanced


def _phase_coherent_enhancement(phase: np.ndarray, mag: np.ndarray, sr: int,
                                  amount: float) -> np.ndarray:
    """相位相干增强（让超分更自然）"""
    # 保持原始相位，但在高频进行轻微平滑
    enhanced_phase = phase.copy()

    freqs = np.arange(mag.shape[0]) * sr / N_FFT
    high_start_idx = np.searchsorted(freqs, 8000)

    if high_start_idx < phase.shape[0]:
        # 对高频相位进行时间轴平滑
        for i in range(high_start_idx, phase.shape[0]):
            phase_line = phase[i, :]
            # 使用小窗口平滑相位
            from scipy.ndimage import uniform_filter1d
            smoothed_phase = uniform_filter1d(phase_line, size=3, mode='wrap')
            # 混合原始和平滑相位
            blend_factor = amount * 0.2
            enhanced_phase[i, :] = (1.0 - blend_factor) * phase_line + blend_factor * smoothed_phase

    return enhanced_phase


def _tempo_adaptive_band_boost(mag: np.ndarray, sr: int, amount: float,
                                tempo_params: Dict) -> np.ndarray:
    """基于节奏参数的频段微调"""
    enhanced = mag.copy()
    freqs = np.arange(mag.shape[0]) * sr / N_FFT

    # 基于节奏类别的增强
    tempo_class = tempo_params.get("tempo_class", "medium")

    if tempo_class == "fast":
        # 快节奏：强调 2-6kHz 临场感 + 更强的高频
        presence_low = 2000
        presence_high = 8000
        pres_low_idx = np.searchsorted(freqs, presence_low)
        pres_high_idx = np.searchsorted(freqs, presence_high)

        if pres_low_idx < pres_high_idx:
            boost_linear = 1.0 + 0.4 * amount
            enhanced[pres_low_idx:pres_high_idx, :] *= boost_linear

    elif tempo_class == "slow":
        # 慢节奏：强调 8-16kHz 空气感 + 低频
        air_low = 6000
        air_high = 18000
        air_low_idx = np.searchsorted(freqs, air_low)
        air_high_idx = np.searchsorted(freqs, air_high)

        if air_low_idx < air_high_idx:
            boost_linear = 1.0 + 0.55 * amount
            enhanced[air_low_idx:air_high_idx, :] *= boost_linear

        # 低频增强
        bass_low = 60
        bass_high = 250
        bass_low_idx = np.searchsorted(freqs, bass_low)
        bass_high_idx = np.searchsorted(freqs, bass_high)
        if bass_low_idx < bass_high_idx:
            bass_boost = 1.0 + 0.2 * amount
            enhanced[bass_low_idx:bass_high_idx, :] *= bass_boost

    else:  # medium
        # 中节奏：均衡提升
        presence_low = 1800
        presence_high = 6000
        pres_low_idx = np.searchsorted(freqs, presence_low)
        pres_high_idx = np.searchsorted(freqs, presence_high)

        if pres_low_idx < pres_high_idx:
            boost_linear = 1.0 + 0.3 * amount
            enhanced[pres_low_idx:pres_high_idx, :] *= boost_linear

    return enhanced


def apply_hifi_superres(y: np.ndarray, sr: int, amount: float,
                         tempo_params: Optional[Dict] = None) -> np.ndarray:
    """
    便捷函数：应用 HiFi 频谱超分/重建（增强版）

    Args:
        y: 输入音频
        sr: 采样率
        amount: 超分强度 0-1
        tempo_params: 节奏参数（可选）

    Returns:
        处理后的音频
    """
    return hifi_spectral_superresolution(y, sr, amount, tempo_params)
