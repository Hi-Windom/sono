import gc
import numpy as np

from services.audio_loader import load_audio_with_fallback
from services.repair.repair_v2_4.spectral_superres import hifi_spectral_superresolution


def _harmonic_enhance(y, sr, amount=0.15):
    """谐波增强 - 在上采样后添加更多高频细节"""
    if y.ndim > 1:
        for ch in range(y.shape[0]):
            y[ch] = _harmonic_enhance_1d(y[ch], sr, amount)
        return y
    return _harmonic_enhance_1d(y, sr, amount)


def _harmonic_enhance_1d(y, sr, amount):
    if amount <= 0 or len(y) < 2048:
        return y

    from scipy.signal import butter, sosfiltfilt

    y_64 = y.astype(np.float64)
    rms = np.sqrt(np.mean(y_64 ** 2))
    if rms < 1e-10:
        return y

    drive = 1.0 + amount * 2.0
    soft_clipped = np.tanh(y_64 * drive) / drive

    h2 = soft_clipped - y_64
    h2_fundamental = np.mean(h2 * y_64)
    if h2_fundamental > 0:
        h2 = h2 - h2_fundamental * y_64 / (rms ** 2 + 1e-10)

    nyquist = sr / 2
    if nyquist > 8000:
        cutoff = min(16000, nyquist * 0.8)
        sos = butter(4, cutoff / (sr / 2), btype='low', output='sos')
        h2_filtered = sosfiltfilt(sos, h2)
    else:
        h2_filtered = h2

    envelope = np.abs(y_64)
    window_len = int(sr * 0.01)
    if window_len > 1 and len(envelope) > window_len:
        kernel = np.ones(window_len) / window_len
        envelope = np.convolve(envelope, kernel, mode='same')

    gain = amount * 0.5
    result = y_64 + gain * h2_filtered * (1.0 - 0.5 * envelope / (envelope.max() + 1e-10))

    peak = np.max(np.abs(result))
    if peak > 0.99:
        result = result * 0.99 / peak

    y[:] = result.astype(y.dtype)
    return y


def _spectral_superres_upsample(y, sr, amount=0.3):
    """
    上采样时的频谱超分增强 - 为高频重建添加更多细节
    类似 QQ 音乐臻品母带的上采样处理
    """
    if y.ndim > 1:
        for ch in range(y.shape[0]):
            y[ch] = _spectral_superres_upsample_1d(y[ch], sr, amount)
        return y
    return _spectral_superres_upsample_1d(y, sr, amount)


def _spectral_superres_upsample_1d(y, sr, amount):
    """单声道频谱超分增强"""
    if amount <= 0 or len(y) < 4096:
        return y

    from scipy.signal import stft, istft
    from scipy.ndimage import uniform_filter1d

    n_fft = 2048
    hop_length = 512

    # STFT
    f, t, S = stft(y, fs=sr, nperseg=n_fft, noverlap=n_fft - hop_length, boundary='zeros')
    mag = np.abs(S)
    phase = np.angle(S)

    freqs = f
    nyquist = sr / 2

    # 1. 高频谐波重建 (8kHz+)
    high_start_idx = np.searchsorted(freqs, 8000)
    if high_start_idx < len(freqs):
        # 基于中频(4-8kHz)重建高频
        mid_start_idx = np.searchsorted(freqs, 4000)
        mid_end_idx = high_start_idx

        if mid_start_idx < mid_end_idx:
            for j in range(mag.shape[1]):
                # 计算中频包络
                mid_env = mag[mid_start_idx:mid_end_idx, j]
                mid_energy = np.sqrt(np.mean(mid_env ** 2) + 1e-10)

                # 重建高频
                for i in range(high_start_idx, len(freqs)):
                    # 谐波关系外推
                    harmonic_order = 2
                    source_freq = freqs[i] / harmonic_order
                    source_idx = np.searchsorted(freqs, source_freq)
                    if source_idx < high_start_idx and source_idx < len(mag):
                        # 基于谐波关系重建，带衰减
                        freq_ratio = freqs[i] / source_freq
                        decay = 1.0 / (1.0 + (freqs[i] / 18000) ** 1.5)
                        reconstructed = mag[source_idx, j] * decay * 0.8
                        # 混合
                        blend = amount * 0.5
                        mag[i, j] = blend * reconstructed + (1 - blend) * mag[i, j]

    # 2. 临场感频段增强 (2-8kHz)
    presence_low = np.searchsorted(freqs, 2000)
    presence_high = np.searchsorted(freqs, 8000)
    if presence_low < presence_high:
        for j in range(mag.shape[1]):
            freq_line = mag[presence_low:presence_high, j]
            # 提取细节
            smoothed = uniform_filter1d(freq_line, size=3, mode='nearest')
            details = freq_line - smoothed
            # 增强细节
            enhanced = smoothed + details * (1.0 + amount * 0.5)
            # 整体增益
            enhanced *= (1.0 + amount * 0.15)
            mag[presence_low:presence_high, j] = enhanced

    # 3. 极高频空气感 (>16kHz)
    air_start_idx = np.searchsorted(freqs, 16000)
    if air_start_idx < len(freqs):
        for j in range(mag.shape[1]):
            # 基于 10-16kHz 的能量生成空气感
            source_start = np.searchsorted(freqs, 10000)
            source_end = air_start_idx
            if source_start < source_end:
                source_energy = np.sqrt(np.mean(mag[source_start:source_end, j] ** 2) + 1e-10)
                air_len = len(freqs) - air_start_idx
                # 生成带结构的噪声
                air_noise = np.random.randn(air_len) * 0.015 * amount * source_energy
                # 频谱衰减
                for i in range(air_len):
                    freq = freqs[air_start_idx + i]
                    decay = 1.0 / (1.0 + (freq / 20000) ** 1.2)
                    air_noise[i] *= decay
                # 混合
                mag[air_start_idx:, j] = mag[air_start_idx:, j] * (1 - amount * 0.3) + air_noise * amount * 0.3

    # 重建信号
    S_enhanced = mag * np.exp(1j * phase)
    _, y_out = istft(S_enhanced, fs=sr, nperseg=n_fft, noverlap=n_fft - hop_length, boundary='zeros')

    # 确保长度一致
    if len(y_out) > len(y):
        y_out = y_out[:len(y)]
    elif len(y_out) < len(y):
        y_out = np.pad(y_out, (0, len(y) - len(y_out)))

    y[:] = y_out.astype(y.dtype)
    return y


def render_output(input_path, output_path, target_sr, bit_depth, progress_callback=None, source_bit_depth=None):
    from scipy.signal import butter, sosfiltfilt, resample_poly

    if progress_callback:
        progress_callback(0.1, "加载修复结果...")

    if source_bit_depth is not None:
        y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    else:
        y, sr, src_bd = load_audio_with_fallback(input_path, sr=None, mono=False, return_bit_depth=True)
        source_bit_depth = src_bd
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr

    if target_sr != sr:
        if target_sr > sr:
            if progress_callback:
                progress_callback(0.3, f"上采样到 {target_sr // 1000}kHz...")
            target_len = int(y.shape[1] * target_sr / sr)
            y_new = np.zeros((y.shape[0], target_len))
            for ch in range(y.shape[0]):
                resampled = resample_poly(y[ch], target_sr, sr)
                y_new[ch, :len(resampled)] = resampled[:target_len]
            y = y_new
            sr = target_sr
            gc.collect()

            if progress_callback:
                progress_callback(0.5, "频谱超分增强...")
            y = hifi_spectral_superresolution(y, sr, amount=0.35)

            if progress_callback:
                progress_callback(0.75, "谐波增强...")
            y = _harmonic_enhance(y, sr, amount=0.2)
        else:
            if progress_callback:
                progress_callback(0.3, f"下采样到 {target_sr // 1000}kHz...")
            nyquist = target_sr / 2
            cutoff = nyquist * 0.95
            sos = butter(6, cutoff / (sr / 2), btype='low', output='sos')
            for ch in range(y.shape[0]):
                y[ch] = sosfiltfilt(sos, y[ch])
            target_len = int(y.shape[1] * target_sr / sr)
            y_new = np.zeros((y.shape[0], target_len))
            for ch in range(y.shape[0]):
                resampled = resample_poly(y[ch], target_sr, sr)
                y_new[ch, :len(resampled)] = resampled[:target_len]
            y = y_new
            sr = target_sr
            gc.collect()

    if was_mono:
        y = y[0]

    if y.dtype == np.float32:
        y = y.astype(np.float64)

    if source_bit_depth is not None and source_bit_depth < bit_depth:
        from services.repair.repair_v2_4.bit_depth_enhance import apply_bit_depth_enhance
        y = apply_bit_depth_enhance(y, source_bit_depth, bit_depth, sr)

    if progress_callback:
        progress_callback(0.9, "导出...")

    try:
        import soundfile as sf
        subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
        subtype = subtype_map.get(bit_depth, "PCM_24")
        sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)
    except Exception:
        from scipy.io import wavfile
        if y.ndim > 1:
            y_out = y.T
        else:
            y_out = y
        if bit_depth == 24:
            y_out = np.clip(y_out * 8388607, -8388608, 8388607).astype(np.int32)
        elif y_out.dtype != np.int16:
            y_out = np.clip(y_out * 32767, -32768, 32767).astype(np.int16)
        wavfile.write(output_path, sr, y_out)

    if progress_callback:
        progress_callback(1.0, "渲染完成")

    return {
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": round(y.shape[-1] / sr if y.ndim > 1 else len(y) / sr, 2),
        "channels": y.shape[0] if y.ndim > 1 else 1,
    }
