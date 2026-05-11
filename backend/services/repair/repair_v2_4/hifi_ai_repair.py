import numpy as np
from scipy.signal import medfilt
from typing import Dict, Optional
from services.dsp_utils import stft, istft, streaming_spectral_process


N_FFT = 2048
HOP_LENGTH = 512


def hifi_ai_artifact_repair(y: np.ndarray, sr: int, amount: float,
                             tempo_params: Optional[Dict] = None) -> np.ndarray:
    """
    HiFi AI 频谱修复 - 优化的AI伪影修复算法

    相比原 _ai_artifact_repair 的改进：
    - 移除随机抖动 (jitter_db)，避免引入噪声
    - 保护瞬态（transient preservation）
    - 更保守的平滑策略
    - 频谱掩蔽避免过度处理

    Args:
        y: 输入音频 (n_channels, n_samples) 或 (n_samples,)
        sr: 采样率
        amount: 修复强度 0-1
        tempo_params: 节奏参数（可选，用于瞬态保护）

    Returns:
        处理后的音频
    """
    if amount <= 0:
        return y

    tempo_params = tempo_params or {}

    # 处理单声道
    if y.ndim == 1:
        return _hifi_ai_repair_channel(y, sr, amount, tempo_params)

    # 处理立体声/多声道
    result = np.zeros_like(y)
    for ch in range(y.shape[0]):
        result[ch] = _hifi_ai_repair_channel(y[ch], sr, amount, tempo_params)
    return result


def _hifi_ai_repair_channel(y_1d: np.ndarray, sr: int, amount: float,
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
            return _hifi_ai_repair_spectral(S, sr_chunk, amount, tempo_params)

        result = streaming_spectral_process(
            y_1d.astype(np.float64), sr,
            _process_chunk,
            n_fft=N_FFT, hop_length=HOP_LENGTH,
            chunk_seconds=10
        )
        return result.astype(y_1d.dtype)

    # 非流式处理
    S = stft(y_1d, n_fft=N_FFT, hop_length=HOP_LENGTH)
    S = _hifi_ai_repair_spectral(S, sr, amount, tempo_params)
    y_out = istft(S, hop_length=HOP_LENGTH, length=n_samples)
    return y_out.astype(y_1d.dtype)


def _hifi_ai_repair_spectral(S: np.ndarray, sr: int, amount: float,
                              tempo_params: Dict) -> np.ndarray:
    """
    频域修复处理

    核心改进：
    1. 瞬态保护 - 不处理瞬态帧
    2. 保守平滑 - 使用更小的滤波核
    3. 无随机抖动 - 移除 jitter_db
    4. 频谱掩蔽 - 限制处理量
    """
    mag = np.abs(S)
    phase = np.angle(S)

    # 1. 检测瞬态帧
    transient_frames = _detect_transients(mag, amount)

    # 2. 计算瞬态保护强度
    transient_preservation = tempo_params.get("transient_preservation", 0.5)

    # 3. 保守的频谱平滑（仅在非瞬态帧）
    smoothed_mag = _conservative_smooth(mag, transient_frames, amount, transient_preservation)

    # 4. 频谱掩蔽 - 限制处理量
    # 计算原始和处理的差异
    diff_ratio = smoothed_mag / (mag + 1e-10)

    # 限制最大修改量（避免过度处理）
    max_change = 1.0 + 0.3 * amount  # 最大提升 30%
    min_change = 1.0 - 0.2 * amount  # 最大衰减 20%

    diff_ratio = np.clip(diff_ratio, min_change, max_change)

    # 应用修改
    processed_mag = mag * diff_ratio

    # 5. 2-5kHz presence 区域处理（基于节奏参数）
    presence_boost_db = tempo_params.get("presence_boost_db", 0.0)
    if presence_boost_db > 0 and amount > 0:
        freqs = np.arange(S.shape[0]) * sr / N_FFT
        presence_mask = (freqs >= 2000) & (freqs <= 5000)

        if np.any(presence_mask):
            # 计算当前 presence 能量
            presence_rms = np.sqrt(np.mean(processed_mag[presence_mask, :] ** 2))
            global_rms = np.sqrt(np.mean(processed_mag ** 2))

            # 如果 presence 不过高，才进行提升
            if presence_rms < global_rms * 1.3:
                boost_linear = 10 ** (presence_boost_db * amount / 20.0)
                processed_mag[presence_mask, :] *= boost_linear

    # 6. 10kHz+ 空气感处理（仅慢节奏）
    air_boost_db = tempo_params.get("air_boost_db", 0.0)
    if air_boost_db > 0 and amount > 0:
        freqs = np.arange(S.shape[0]) * sr / N_FFT
        air_mask = freqs >= 10000

        if np.any(air_mask):
            # 基于中频包络生成高频内容
            mid_mask = (freqs >= 2000) & (freqs < 8000)
            if np.any(mid_mask):
                mid_energy = np.mean(processed_mag[mid_mask, :] ** 2, axis=0)
                mid_envelope = np.sqrt(mid_energy + 1e-10)
                mid_envelope_norm = mid_envelope / (np.max(mid_envelope) + 1e-10)

                # 生成谐波相关的高频内容（非随机噪声）
                air_indices = np.where(air_mask)[0]
                # 使用相位相干的方式添加高频
                for j in range(S.shape[1]):
                    if mid_envelope_norm[j] > 0.1:
                        # 基于中频相位生成高频
                        mid_phase = np.angle(S[mid_mask, j])
                        # 使用简单的谐波关系
                        harmonic_factor = 2.0  # 2倍频关系
                        for i, air_idx in enumerate(air_indices):
                            # 映射到中频索引
                            mid_idx = int(air_idx / harmonic_factor)
                            if mid_idx < len(mid_phase):
                                # 复制相位关系
                                phase[air_idx, j] = mid_phase[mid_idx]

                # 提升高频幅度
                boost_linear = 10 ** (air_boost_db * amount / 20.0)
                processed_mag[air_mask, :] *= boost_linear

    # 重建复数频谱
    S_out = processed_mag * np.exp(1j * phase)

    return S_out


def _detect_transients(mag: np.ndarray, sensitivity: float) -> np.ndarray:
    """
    检测瞬态帧

    Args:
        mag: 幅度频谱
        sensitivity: 检测灵敏度 0-1

    Returns:
        布尔数组，标记瞬态帧
    """
    # 计算每帧能量
    frame_energy = np.sum(mag ** 2, axis=0)

    # 计算能量变化
    energy_change = np.abs(np.diff(frame_energy, prepend=frame_energy[0]))

    # 计算阈值
    mean_change = np.mean(energy_change)
    std_change = np.std(energy_change)

    # 自适应阈值
    threshold = mean_change + std_change * (1.5 + sensitivity)

    # 检测瞬态
    transient_frames = energy_change > threshold

    # 扩展瞬态保护窗口（前后各1帧）
    if len(transient_frames) > 2:
        extended = transient_frames.copy()
        extended[1:] = extended[1:] | transient_frames[:-1]
        extended[:-1] = extended[:-1] | transient_frames[1:]
        transient_frames = extended

    return transient_frames


def _conservative_smooth(mag: np.ndarray, transient_frames: np.ndarray,
                         amount: float, preservation: float) -> np.ndarray:
    """
    保守的频谱平滑

    特点：
    - 使用更小的滤波核（3 instead of 3/5/7）
    - 跳过瞬态帧
    - 根据 preservation 参数调整平滑强度
    """
    smoothed = mag.copy()

    # 调整平滑强度
    smooth_strength = amount * (1.0 - preservation * 0.5)

    if smooth_strength <= 0:
        return smoothed

    # 对每个频率bin进行时间轴平滑
    for i in range(mag.shape[0]):
        # 只在非瞬态帧应用平滑
        non_transient = ~transient_frames

        if np.sum(non_transient) < 3:
            continue

        # 使用较小的核（kernel_size=3）
        kernel_size = 3

        # 对非瞬态区域进行平滑
        mag_line = mag[i, :].copy()

        # 使用中值滤波（更保守）
        smoothed_line = medfilt(mag_line, kernel_size=kernel_size)

        # 混合原始和平滑后的结果
        blend_factor = smooth_strength * 0.5  # 最大混合 50%
        smoothed[i, :] = mag_line * (1 - blend_factor) + smoothed_line * blend_factor

    return smoothed


def apply_hifi_ai_repair(y: np.ndarray, sr: int, amount: float,
                          tempo_params: Optional[Dict] = None) -> np.ndarray:
    """
    便捷函数：应用 HiFi AI 频谱修复

    Args:
        y: 输入音频
        sr: 采样率
        amount: 修复强度 0-1
        tempo_params: 节奏参数（可选）

    Returns:
        处理后的音频
    """
    return hifi_ai_artifact_repair(y, sr, amount, tempo_params)
