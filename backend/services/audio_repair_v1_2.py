import numpy as np
import librosa
import soundfile as sf
try:
    from pedalboard import Pedalboard, Compressor, Gain, LowShelfFilter, HighShelfFilter, PeakFilter, Reverb, Limiter, HighpassFilter, LowpassFilter, Chorus
    HAS_PEDALBOARD = True
except ImportError:
    HAS_PEDALBOARD = False
from scipy.signal import medfilt, butter, filtfilt, resample_poly
from scipy.fftpack import fft, ifft
import gc


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    """v1.2 修复算法 - 96kHz全频带处理，流式分块优化"""
    y, sr = librosa.load(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    target_sr = params.get("sample_rate", sr)
    original_duration = round(y.shape[1] / sr, 2)

    # v1.2 核心：始终升采样到 96kHz 进行全频带处理
    WORKING_SR = 96000

    if progress_callback:
        progress_callback(0.02, f"v1.2 升采样到 {WORKING_SR//1000}kHz...")

    # 升采样到 96kHz
    if sr != WORKING_SR:
        target_len = int(y.shape[1] * WORKING_SR / sr)
        y_96k = np.zeros((y.shape[0], target_len))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], WORKING_SR, sr)
            y_96k[ch, :len(resampled)] = resampled[:target_len]
        y = y_96k
        sr = WORKING_SR
        gc.collect()  # 释放内存

    # 分块处理配置
    BLOCK_SIZE = 4 * WORKING_SR  # 4秒一块，平衡内存和性能
    n_blocks = int(np.ceil(y.shape[1] / BLOCK_SIZE))

    n_fft = 4096
    hop_length = 1024

    if progress_callback:
        progress_callback(0.05, f"v1.2 分块处理({n_blocks}块)...")

    issues_found = []
    processed_blocks = []

    for block_idx in range(n_blocks):
        start = block_idx * BLOCK_SIZE
        end = min(start + BLOCK_SIZE, y.shape[1])
        block = y[:, start:end].copy()

        # 处理当前块
        block = _process_block(block, sr, params, n_fft, hop_length, issues_found)
        processed_blocks.append(block)

        # 每处理完一块就释放内存
        del block
        gc.collect()

        # 进度更新
        if progress_callback:
            progress = 0.05 + 0.89 * (block_idx + 1) / n_blocks
            progress_callback(progress, f"v1.2 处理块 {block_idx+1}/{n_blocks}...")

    # 合并所有块
    y = np.concatenate(processed_blocks, axis=1)
    del processed_blocks
    gc.collect()

    # 降采样到目标采样率
    if target_sr != WORKING_SR:
        if progress_callback:
            progress_callback(0.95, f"v1.2 降采样到 {target_sr//1000}kHz...")

        if target_sr < WORKING_SR:
            nyquist = target_sr / 2
            cutoff = nyquist * 0.95
            b, a = butter(6, cutoff / (WORKING_SR / 2), btype='low')
            for ch in range(y.shape[0]):
                y[ch] = filtfilt(b, a, y[ch])

        y_resampled = np.zeros((y.shape[0], int(y.shape[1] * target_sr / WORKING_SR)))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], target_sr, WORKING_SR)
            y_resampled[ch, :len(resampled)] = resampled[:y_resampled.shape[1]]
        y = y_resampled
        sr = target_sr
        gc.collect()

    # 最终处理
    if progress_callback:
        progress_callback(0.97, "v1.2 峰值限制...")

    y = _apply_loudness_normalize_v2(y, sr, -16.0)
    y = _apply_peak_limit_v2(y, sr)

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.99, "导出WAV...")

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v1.2 修复完成")

    return {
        "issues_found": issues_found,
        "original_duration": original_duration,
        "output_duration": round(y.shape[1] / sr if y.ndim > 1 else len(y) / sr, 2),
        "sample_rate": sr,
        "channels": y.shape[0] if y.ndim > 1 else 1,
    }


def _process_block(block, sr, params, n_fft, hop_length, issues_found):
    """处理单个音频块"""
    if params.get("de_clipping", 0) > 0:
        block = _apply_de_clipping_v3(block, sr, params["de_clipping"])

    if params.get("de_crackle", 0) > 0:
        block = _apply_de_crackle_v3(block, sr, params["de_crackle"], n_fft, hop_length)

    if params.get("de_pop", 0) > 0:
        block = _apply_de_pop_v3(block, sr, params["de_pop"])

    if params.get("de_essing", 0) > 0:
        block = _apply_de_essing_v3(block, sr, params["de_essing"], n_fft, hop_length)

    if params.get("noise_reduction", 0) > 0:
        block = _apply_noise_reduction_v3(block, sr, params["noise_reduction"])

    if params.get("transient_repair", 0) > 0:
        block = _apply_transient_repair_v3(block, sr, params["transient_repair"])

    if params.get("harmonic_enhance", 0) > 0:
        block = _apply_harmonic_enhance_v4(block, sr, params["harmonic_enhance"], n_fft, hop_length)

    if params.get("spatial_enhance", 0) > 0:
        block = _apply_spatial_enhance_v4(block, sr, params["spatial_enhance"])

    if params.get("presence_boost", 0) > 0:
        block = _apply_presence_boost_v3(block, sr, params["presence_boost"])

    if params.get("bass_enhance", 0) > 0:
        block = _apply_bass_enhance_v3(block, sr, params["bass_enhance"])

    if params.get("stereo_width", 0) > 0 and block.shape[0] == 2:
        block = _apply_stereo_width(block, sr, params["stereo_width"])

    if params.get("harmonic_richness", 0) > 0:
        block = _apply_harmonic_richness(block, sr, params["harmonic_richness"], n_fft, hop_length)

    return block


def _apply_de_clipping_v3(y, sr, intensity):
    """去削波 v3"""
    result = y.copy()
    threshold = 0.95 - intensity * 0.15
    for ch in range(y.shape[0]):
        data = result[ch]
        clipped = np.abs(data) > threshold
        if np.any(clipped):
            result[ch] = np.clip(data, -threshold, threshold) * (1 + intensity * 0.1)
    return result


def _apply_de_crackle_v3(y, sr, intensity, n_fft, hop_length):
    """频谱注意力去毛刺 v3 - 优化版"""
    result = y.copy()

    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        phase = np.exp(1j * np.angle(S))

        # 简化：只检测帧能量异常
        frame_energy = np.sum(mag ** 2, axis=0)
        med_energy = medfilt(frame_energy, kernel_size=5)
        energy_ratio = frame_energy / (med_energy + 1e-10)

        mean_ratio = np.mean(energy_ratio)
        std_ratio = np.std(energy_ratio)
        threshold = mean_ratio + std_ratio * 0.8
        crackle_frames = energy_ratio > threshold

        if np.any(crackle_frames):
            # 只对异常帧进行简单中值滤波
            for j in np.where(crackle_frames)[0]:
                left_j = max(0, j - 2)
                right_j = min(mag.shape[1], j + 3)
                local_avg = np.mean(mag[:, left_j:right_j], axis=1)
                blend = intensity * 0.7
                S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase[:, j]

        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_de_pop_v3(y, sr, intensity):
    """去爆音 v3"""
    result = y.copy()
    window_size = int(0.005 * sr)

    for ch in range(y.shape[0]):
        data = result[ch]
        envelope = np.abs(data)
        threshold = np.mean(envelope) + np.std(envelope) * (2.5 - intensity)
        pops = envelope > threshold

        if np.any(pops):
            for i in np.where(pops)[0]:
                left = max(0, i - window_size)
                right = min(len(data), i + window_size)
                data[left:right] *= 0.3

    return result


def _apply_de_essing_v3(y, sr, intensity, n_fft, hop_length):
    """智能齿音抑制 v3 - 优化版"""
    result = y.copy()

    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        # 简化频段
        sibilant_bands = [
            (4000, 8000, 1.0),
            (8000, 16000, 0.6),
        ]

        for low, high, weight in sibilant_bands:
            band_mask = (freqs >= low) & (freqs <= high)
            if not np.any(band_mask):
                continue

            band_energy = np.mean(mag[band_mask, :], axis=0)
            total_energy = np.mean(mag, axis=0) + 1e-10
            sibilant_ratio = band_energy / total_energy

            mean_ratio = np.mean(sibilant_ratio)
            threshold = mean_ratio + np.std(sibilant_ratio) * 1.2
            sibilant_frames = sibilant_ratio > threshold

            if np.any(sibilant_frames):
                reduction = 1.0 - intensity * 0.35 * weight
                mag[band_mask, :] *= np.where(sibilant_frames, reduction, 1.0)

        S = mag * np.exp(1j * np.angle(S))
        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))

    return result


def _apply_noise_reduction_v3(y, sr, intensity):
    """自适应降噪 v3 - 修复电流声问题"""
    result = y.copy()
    # 使用相对阈值而非绝对阈值，避免截断正常信号
    # 基于信号 RMS 计算噪声门限

    for ch in range(y.shape[0]):
        data = result[ch]
        rms = np.sqrt(np.mean(data ** 2))
        # 噪声门限设为 RMS 的一个比例，随 intensity 调整
        noise_gate = rms * 0.01 * (1 - intensity * 0.5)
        # 使用平滑衰减而非硬截断
        mask = np.abs(data) < noise_gate
        # 平滑过渡：在门限附近使用渐变
        attenuation = np.ones_like(data)
        attenuation[mask] = 0.3 + 0.7 * (np.abs(data[mask]) / (noise_gate + 1e-10)) ** 2
        result[ch] = data * attenuation

    return result


def _apply_transient_repair_v3(y, sr, intensity):
    """瞬态修复 v3"""
    return y * (1 + intensity * 0.05)


def _apply_harmonic_enhance_v4(y, sr, intensity, n_fft, hop_length):
    """谐波增强 v4 - 优化版"""
    result = y.copy()
    nyquist = sr / 2

    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        phase = np.angle(S)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        harmonic_content = np.zeros_like(mag)

        # 简化：只处理关键频段
        base_indices = np.where((freqs >= 80) & (freqs <= 4000))[0]

        for i in base_indices[::2]:  # 每隔一个频点
            f = freqs[i]
            for h_num, h_gain in [(2, 0.1), (3, 0.05)]:
                h_freq = f * h_num
                if h_freq > nyquist - 100:
                    break
                h_idx = np.argmin(np.abs(freqs - h_freq))
                if h_idx < mag.shape[0]:
                    harmonic_content[h_idx, :] += np.sqrt(mag[i, :]) * h_gain * intensity

        # 超高频（简化）
        if nyquist >= 48000 and intensity > 0.3:
            hf_indices = np.where((freqs >= 5000) & (freqs <= 8000))[0]
            for i in hf_indices[::4]:  # 更稀疏
                f = freqs[i]
                h_freq = f * 4
                if h_freq < 20000 or h_freq > nyquist - 100:
                    continue
                h_idx = np.argmin(np.abs(freqs - h_freq))
                if h_idx < mag.shape[0]:
                    air_absorption = np.exp(-(h_freq - 20000) / 20000)
                    harmonic_content[h_idx, :] += mag[i, :] * 0.02 * intensity * air_absorption

        enhanced_mag = mag + harmonic_content * intensity * 0.5
        S_enhanced = enhanced_mag * np.exp(1j * phase)
        result[ch] = librosa.istft(S_enhanced, hop_length=hop_length, length=len(data))

    return result


def _apply_spatial_enhance_v4(y, sr, intensity):
    """空间感增强 v4"""
    if y.shape[0] != 2:
        return y

    result = y.copy()
    mid = (y[0] + y[1]) * 0.5
    side = (y[0] - y[1]) * 0.5

    side_gain = 1 + intensity * 0.2
    result[0] = mid + side * side_gain
    result[1] = mid - side * side_gain

    return result


def _apply_presence_boost_v3(y, sr, intensity):
    """临场感增强 v3"""
    result = y.copy()
    b, a = butter(2, [2000 / (sr / 2), 6000 / (sr / 2)], btype='band')

    for ch in range(y.shape[0]):
        presence = filtfilt(b, a, result[ch])
        result[ch] += presence * intensity * 0.3

    return result


def _apply_bass_enhance_v3(y, sr, intensity):
    """低频增强 v3"""
    result = y.copy()
    b, a = butter(2, 120 / (sr / 2), btype='low')

    for ch in range(y.shape[0]):
        bass = filtfilt(b, a, result[ch])
        result[ch] += bass * intensity * 0.25

    return result


def _apply_stereo_width(y, sr, intensity):
    """立体声宽度"""
    if y.shape[0] != 2:
        return y

    result = y.copy()
    mid = (y[0] + y[1]) * 0.5
    side = (y[0] - y[1]) * 0.5

    width = 1 + intensity * 0.5
    result[0] = mid + side * width
    result[1] = mid - side * width

    max_val = np.max(np.abs(result))
    if max_val > 1.0:
        result /= max_val

    return result


def _apply_harmonic_richness(y, sr, intensity, n_fft, hop_length):
    """谐波丰富度 - 优化版"""
    result = y.copy()
    nyquist = sr / 2

    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        phase = np.angle(S)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        harmonic_enhancement = np.zeros_like(mag)
        base_indices = np.where((freqs >= 100) & (freqs <= 5000))[0]

        for i in base_indices[::2]:
            f = freqs[i]
            for h in [2, 3]:
                h_freq = f * h
                if h_freq > nyquist - 100:
                    break
                h_idx = np.argmin(np.abs(freqs - h_freq))
                if h_idx < mag.shape[0]:
                    gain = 0.1 / h * intensity
                    harmonic_enhancement[h_idx, :] += mag[i, :] * gain

        if nyquist >= 48000 and intensity > 0.4:
            hf_indices = np.where((freqs >= 8000) & (freqs <= 12000))[0]
            for i in hf_indices[::4]:
                f = freqs[i]
                h_freq = f * 3
                if h_freq < 24000 or h_freq > nyquist - 50:
                    continue
                h_idx = np.argmin(np.abs(freqs - h_freq))
                if h_idx < mag.shape[0]:
                    air_gain = 0.05 * intensity
                    freq_attenuation = np.exp(-(h_freq - 24000) / 15000)
                    harmonic_enhancement[h_idx, :] += mag[i, :] * air_gain * freq_attenuation

        enhanced_mag = mag + harmonic_enhancement
        S_enhanced = enhanced_mag * np.exp(1j * phase)
        result[ch] = librosa.istft(S_enhanced, hop_length=hop_length, length=len(data))

    return result


def _apply_loudness_normalize_v2(y, sr, target_lufs):
    """响度归一化 v2"""
    result = y.copy()
    current_lufs = np.mean(result ** 2) ** 0.5
    if current_lufs > 0:
        target_linear = 10 ** (target_lufs / 20)
        gain = target_linear / current_lufs
        result *= gain
    return result


def _apply_peak_limit_v2(y, sr, threshold=0.98):
    """峰值限制 v2"""
    result = y.copy()
    max_val = np.max(np.abs(result))
    if max_val > threshold:
        result = np.clip(result, -threshold, threshold)
    return result
