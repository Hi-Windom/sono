import numpy as np
from services.librosa_compat import stft, istft, fft_frequencies
from scipy.ndimage import gaussian_filter1d
from .type_params import TYPE_PARAMS_MAP


def apply_spectral_group_b(y, sr, params, n_fft, hop_length, issues_found, music_type="generic"):
    result = y.copy()
    harmonic_enhance = params.get("harmonic_enhance", 0)
    harmonic_richness = params.get("harmonic_richness", 0)

    enhance_added = "谐波增强v7" in issues_found
    richness_added = "谐波丰富度v4" in issues_found

    for ch in range(y.shape[0]):
        data = result[ch]
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

    return result


def _apply_harmonic_enhance_v7_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type):
    """
    改进的谐波增强 - 更自然的谐波生成，避免过度增强
    """
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2
    n_frames = mag.shape[1]

    # 根据音乐类型调整参数
    if music_type == "vocal":
        base_freq_min, base_freq_max = 100, 2000
        harmonics = [(2, 0.06), (3, 0.03)]  # 降低增益
        max_harmonic_freq = 6000
    elif music_type == "instrumental":
        base_freq_min, base_freq_max = 80, 3000
        harmonics = [(2, 0.05), (3, 0.025), (4, 0.015)]
        max_harmonic_freq = 8000
    elif music_type == "classical":
        base_freq_min, base_freq_max = 80, 2000
        harmonics = [(2, 0.025), (3, 0.015)]  # 非常轻微
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
    # 使用频谱质心来动态调整增益
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)
    centroid_smooth = gaussian_filter1d(centroid, sigma=2.0)
    
    # 质心越高，增益越低（避免过度增强已经明亮的信号）
    centroid_factor = np.clip(1 - (centroid_smooth - 1000) / 3000, 0.3, 1.0)

    # 生成谐波内容
    harmonic_content = np.zeros_like(mag)
    
    for h_num, h_gain_base in harmonics:
        for frame_idx in range(n_frames):
            # 时变增益
            h_gain = h_gain_base * intensity * centroid_factor[frame_idx]
            
            for base_idx in base_indices:
                base_freq = freqs[base_idx]
                target_freq = base_freq * h_num
                
                if target_freq >= min(max_harmonic_freq, nyquist - 100):
                    continue
                
                # 找到最接近的目标频率 bin
                target_idx = np.argmin(np.abs(freqs - target_freq))
                
                # 计算谐波幅度（基于基频幅度，但使用更温和的曲线）
                base_mag = mag[base_idx, frame_idx]
                # 使用平方根曲线，避免过度增强强信号
                harmonic_mag = np.sqrt(base_mag) * h_gain * 0.5
                
                # 限制最大谐波幅度
                harmonic_mag = min(harmonic_mag, base_mag * 0.3)
                
                # 添加到谐波内容（带相位随机化）
                harmonic_content[target_idx, frame_idx] += harmonic_mag
    
    # 平滑谐波内容
    for frame_idx in range(n_frames):
        harmonic_content[:, frame_idx] = gaussian_filter1d(
            harmonic_content[:, frame_idx], sigma=1.5
        )
    
    # 应用谐波增强（使用原始相位）
    phase = np.exp(1j * np.angle(S))
    enhanced_mag = mag + harmonic_content * intensity * 0.3
    
    # 限制最大增强量
    max_enhance = 1.15  # 最大 15% 增强
    enhanced_mag = np.clip(enhanced_mag, 0, mag * max_enhance)
    
    S[:] = enhanced_mag * phase


def _apply_harmonic_richness_v4_inplace(S, mag, sr, n_fft, hop_length, intensity, music_type):
    """
    改进的谐波丰富度 - 更自然的谐波混合
    """
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    nyquist = sr / 2
    n_frames = mag.shape[1]

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
    # 能量越高，增益越低（避免过度处理强信号）
    energy_factor = np.clip(1 - (energy_smooth - np.mean(energy_smooth)) / (np.std(energy_smooth) + 1e-10) * 0.2, 0.5, 1.0)

    harmonic_content = np.zeros_like(mag)
    
    for h_num, h_gain_base in harmonics:
        for frame_idx in range(n_frames):
            h_gain = h_gain_base * intensity * energy_factor[frame_idx]
            
            for base_idx in base_indices:
                base_freq = freqs[base_idx]
                target_freq = base_freq * h_num
                
                if target_freq >= min(max_harmonic_freq, nyquist - 100):
                    continue
                
                target_idx = np.argmin(np.abs(freqs - target_freq))
                base_mag = mag[base_idx, frame_idx]
                
                # 使用对数曲线，更自然
                harmonic_mag = np.log1p(base_mag) * h_gain * 0.3
                harmonic_mag = min(harmonic_mag, base_mag * 0.25)
                
                harmonic_content[target_idx, frame_idx] += harmonic_mag
    
    # 平滑
    for frame_idx in range(n_frames):
        harmonic_content[:, frame_idx] = gaussian_filter1d(
            harmonic_content[:, frame_idx], sigma=1.5
        )
    
    phase = np.exp(1j * np.angle(S))
    enhanced_mag = mag + harmonic_content
    
    # 限制增强量
    max_enhance = 1.12
    enhanced_mag = np.clip(enhanced_mag, 0, mag * max_enhance)
    
    S[:] = enhanced_mag * phase
