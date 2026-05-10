import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from services.dsp_utils import streaming_spectral_process
from scipy.ndimage import gaussian_filter1d
from .type_params import TYPE_PARAMS_MAP

_STREAMING_THRESHOLD_SECONDS = 300


def apply_spectral_group_b(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    result = y.copy()
    harmonic_enhance = params.get("harmonic_enhance", 0)
    harmonic_richness = params.get("harmonic_richness", 0)

    enhance_added = "谐波增强v7" in issues_found
    richness_added = "谐波丰富度v4" in issues_found

    use_streaming = y.shape[1] > _STREAMING_THRESHOLD_SECONDS * sr

    for ch in range(y.shape[0]):
        data = result[ch]

        if use_streaming:
            def _chunk_process(S, _sr, _n_fft, _hop_length, _he=harmonic_enhance, _hr=harmonic_richness, _mt=music_type):
                mag = np.abs(S)
                if _he > 0:
                    _apply_harmonic_enhance_v7_inplace(S, mag, _sr, _n_fft, _hop_length, _he, _mt)
                    mag = np.abs(S)
                if _hr > 0:
                    _apply_harmonic_richness_v4_inplace(S, mag, _sr, _n_fft, _hop_length, _hr, _mt)
                return S

            result[ch] = streaming_spectral_process(
                data, sr, _chunk_process, n_fft=n_fft, hop_length=hop_length
            )
        else:
            S = stft(data, n_fft=n_fft, hop_length=hop_length)
            mag = np.abs(S)

            if harmonic_enhance > 0:
                _apply_harmonic_enhance_v7_inplace(S, mag, sr, n_fft, hop_length, harmonic_enhance, music_type)
                if not enhance_added:
                    issues_found.append("谐波增强v7")
                    enhance_added = True
                mag = np.abs(S)

            if harmonic_richness > 0:
                _apply_harmonic_richness_v4_inplace(S, mag, sr, n_fft, hop_length, harmonic_richness, music_type)
                if not richness_added:
                    issues_found.append("谐波丰富度v4")
                    richness_added = True

            result[ch] = istft(S, hop_length=hop_length, length=len(data))

    if use_streaming:
        if harmonic_enhance > 0 and not enhance_added:
            issues_found.append("谐波增强v7")
        if harmonic_richness > 0 and not richness_added:
            issues_found.append("谐波丰富度v4")

    return result


def _apply_harmonic_enhance_v7_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type):
    """
    改进的谐波增强 - 向量化实现，避免三重嵌套循环
    """
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2
    n_frames = mag.shape[1]
    n_bins = mag.shape[0]
    df = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0

    # 根据音乐类型调整参数
    if music_type == "vocal":
        base_freq_min, base_freq_max = 100, 2000
        harmonics = [(2, 0.06), (3, 0.03)]
        max_harmonic_freq = 6000
    elif music_type == "instrumental":
        base_freq_min, base_freq_max = 80, 3000
        harmonics = [(2, 0.05), (3, 0.025), (4, 0.015)]
        max_harmonic_freq = 8000
    elif music_type == "classical":
        base_freq_min, base_freq_max = 80, 2000
        harmonics = [(2, 0.025), (3, 0.015)]
        max_harmonic_freq = 5000
    elif music_type == "electronic":
        base_freq_min, base_freq_max = 60, 1500
        harmonics = [(2, 0.04), (3, 0.02)]
        max_harmonic_freq = 4000
    else:
        base_freq_min, base_freq_max = 100, 2000
        harmonics = [(2, 0.035), (3, 0.02)]
        max_harmonic_freq = 6000

    # 找出基频区域
    base_mask = (freqs >= base_freq_min) & (freqs <= base_freq_max)
    base_indices = np.where(base_mask)[0]

    if len(base_indices) < 3:
        return

    # 计算时变增益包络（避免静态增强）
    frame_energy = np.sum(mag, axis=0) + 1e-10
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / frame_energy
    centroid_smooth = gaussian_filter1d(centroid, sigma=2.0)
    centroid_factor = np.clip(1 - (centroid_smooth - 1000) / 3000, 0.3, 1.0)

    # 预计算每个基频bin对应的谐波目标bin索引
    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain_base in harmonics:
        # 向量化：为所有基频bin预计算目标bin
        base_freqs = freqs[base_indices]
        target_freqs = base_freqs * h_num

        # 过滤超出范围的
        valid_mask = target_freqs < min(max_harmonic_freq, nyquist - 100)
        if not np.any(valid_mask):
            continue

        valid_base_indices = base_indices[valid_mask]
        valid_target_freqs = target_freqs[valid_mask]

        # 向量化查找目标bin
        target_indices = np.clip(np.round(valid_target_freqs / df).astype(int), 0, n_bins - 1)

        # 获取基频幅度（所有帧）
        base_mags = mag[valid_base_indices, :]  # shape: (n_valid_base, n_frames)

        # 计算时变增益: (n_frames,)
        h_gains = h_gain_base * intensity * centroid_factor  # broadcasting

        # 计算谐波幅度：使用平方根曲线
        harmonic_mags = np.sqrt(base_mags) * h_gains * 0.5

        # 限制最大谐波幅度
        np.minimum(harmonic_mags, base_mags * 0.3, out=harmonic_mags)

        # 使用np.add.at进行向量化累加（处理可能的重复target_idx）
        for frame_idx in range(n_frames):
            np.add.at(harmonic_content[:, frame_idx], target_indices, harmonic_mags[:, frame_idx])

    # 平滑谐波内容 - 沿频率轴
    if n_frames > 1:
        harmonic_content = gaussian_filter1d(harmonic_content, sigma=1.5, axis=0)

    # 应用谐波增强
    phase = np.exp(1j * np.angle(S))
    enhanced_mag = mag + harmonic_content * intensity * 0.3

    # 限制最大增强量
    max_enhance = 1.15
    enhanced_mag = np.clip(enhanced_mag, 0, mag * max_enhance)

    S[:] = enhanced_mag * phase


def _apply_harmonic_richness_v4_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type):
    """
    改进的谐波丰富度 - 向量化实现
    """
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2
    n_frames = mag.shape[1]
    n_bins = mag.shape[0]
    df = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0

    if music_type == "vocal":
        base_freq_min, base_freq_max = 120, 2500
        harmonics = [(2, 0.04), (3, 0.02)]
        max_harmonic_freq = 7000
    elif music_type == "instrumental":
        base_freq_min, base_freq_max = 100, 3500
        harmonics = [(2, 0.05), (3, 0.025)]
        max_harmonic_freq = 9000
    elif music_type == "classical":
        base_freq_min, base_freq_max = 80, 2000
        harmonics = [(2, 0.02), (3, 0.01)]
        max_harmonic_freq = 5000
    else:
        base_freq_min, base_freq_max = 120, 3000
        harmonics = [(2, 0.03), (3, 0.015)]
        max_harmonic_freq = 7000

    base_mask = (freqs >= base_freq_min) & (freqs <= base_freq_max)
    base_indices = np.where(base_mask)[0]

    if len(base_indices) < 3:
        return

    # 计算动态增益因子
    frame_energy = np.sum(mag ** 2, axis=0)
    energy_smooth = gaussian_filter1d(frame_energy, sigma=2.0)
    energy_mean = np.mean(energy_smooth)
    energy_std = np.std(energy_smooth) + 1e-10
    energy_factor = np.clip(1 - (energy_smooth - energy_mean) / energy_std * 0.2, 0.5, 1.0)

    harmonic_content = np.zeros_like(mag)

    for h_num, h_gain_base in harmonics:
        base_freqs = freqs[base_indices]
        target_freqs = base_freqs * h_num

        valid_mask = target_freqs < min(max_harmonic_freq, nyquist - 100)
        if not np.any(valid_mask):
            continue

        valid_base_indices = base_indices[valid_mask]
        valid_target_freqs = target_freqs[valid_mask]
        target_indices = np.clip(np.round(valid_target_freqs / df).astype(int), 0, n_bins - 1)

        base_mags = mag[valid_base_indices, :]
        h_gains = h_gain_base * intensity * energy_factor

        # 使用对数曲线
        harmonic_mags = np.log1p(base_mags) * h_gains * 0.3
        np.minimum(harmonic_mags, base_mags * 0.25, out=harmonic_mags)

        for frame_idx in range(n_frames):
            np.add.at(harmonic_content[:, frame_idx], target_indices, harmonic_mags[:, frame_idx])

    # 平滑
    if n_frames > 1:
        harmonic_content = gaussian_filter1d(harmonic_content, sigma=1.5, axis=0)

    phase = np.exp(1j * np.angle(S))
    enhanced_mag = mag + harmonic_content

    max_enhance = 1.12
    enhanced_mag = np.clip(enhanced_mag, 0, mag * max_enhance)

    S[:] = enhanced_mag * phase
