import gc
import numpy as np

from services.audio_loader import load_audio_with_fallback


def _harmonic_enhance(y, sr, amount=0.15):
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


def render_output(input_path, output_path, target_sr, bit_depth, progress_callback=None):
    from scipy.signal import butter, sosfiltfilt, resample_poly

    if progress_callback:
        progress_callback(0.1, "加载修复结果...")

    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
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
                progress_callback(0.6, "谐波增强...")
            y = _harmonic_enhance(y, sr, amount=0.15)
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
        if y_out.dtype != np.int16:
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
