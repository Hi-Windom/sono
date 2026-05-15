import numpy as np
from scipy.signal import butter, sosfiltfilt, lfilter
from scipy.ndimage import gaussian_filter1d


def _soft_peak_limit(y, threshold=0.95):
    if threshold <= 0:
        return y
    if y.ndim == 1:
        return _soft_peak_limit_1d(y, threshold)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        out[ch] = _soft_peak_limit_1d(y[ch], threshold)
    return out


def _soft_peak_limit_1d(data, threshold):
    abs_data = np.abs(data)
    mask = abs_data > threshold
    if not np.any(mask):
        return data.copy()
    headroom = 1.0 - threshold
    over = abs_data[mask] - threshold
    scale = headroom * 0.98
    out = data.copy().astype(np.float64)
    out[mask] = np.sign(data[mask]) * (threshold + scale * np.tanh(over / scale))
    return out.astype(data.dtype)


def _global_gain(y, target_rms):
    if target_rms <= 0:
        return y
    if y.ndim == 1:
        return _global_gain_1d(y, target_rms)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        out[ch] = _global_gain_1d(y[ch], target_rms)
    return out


def _global_gain_1d(data, target_rms):
    current_rms = np.sqrt(np.mean(data.astype(np.float64) ** 2))
    if current_rms < 1e-12:
        return data.copy()
    gain = target_rms / current_rms
    return (data.astype(np.float64) * gain).astype(data.dtype)


def _safe_postprocess(y, sr, params):
    peak_threshold = params.get("peak_threshold", 0.95)
    target_rms = params.get("target_rms", 0.12)
    residual_strength = params.get("residual_refine", 0.0)

    y = _soft_peak_limit(y, threshold=peak_threshold)

    current_rms = np.sqrt(np.mean(y.astype(np.float64) ** 2))
    if current_rms > 1e-12 and current_rms < target_rms * 0.5:
        y = _global_gain(y, target_rms)

    if residual_strength > 0 and "residual_original" in params:
        original = params["residual_original"]
        y = _residual_refine(original, y, residual_strength)

    return y


def _streaming_process(y, sr, process_fn, params, chunk_duration=10.0):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True
    else:
        was_mono = False

    n_channels, n_samples = y.shape
    chunk_samples = int(chunk_duration * sr)
    hop_samples = chunk_samples // 2

    if n_samples <= chunk_samples:
        result = process_fn(y, sr, params)
        if was_mono and result.ndim > 1:
            result = result[0]
        return result

    window = np.hanning(chunk_samples)
    output = np.zeros((n_channels, n_samples + chunk_samples), dtype=np.float64)
    norm = np.zeros(n_samples + chunk_samples, dtype=np.float64)

    pos = 0
    while pos < n_samples:
        end = min(pos + chunk_samples, n_samples)
        chunk = y[:, pos:end]
        actual_len = chunk.shape[1]

        if actual_len < chunk_samples:
            padded = np.zeros((n_channels, chunk_samples), dtype=y.dtype)
            padded[:, :actual_len] = chunk
            chunk = padded
        else:
            chunk = chunk[:, :chunk_samples]

        processed = process_fn(chunk, sr, params)
        if processed.ndim == 1:
            processed = processed.reshape(1, -1)

        weighted = processed * window[np.newaxis, :]
        output[:, pos:pos + chunk_samples] += weighted
        norm[pos:pos + chunk_samples] += window

        pos += hop_samples

    norm = np.maximum(norm, 1e-12)
    output = output[:, :n_samples] / norm[:n_samples]

    if was_mono:
        output = output[0]

    return output


def _residual_refine(original, processed, strength):
    if strength <= 0:
        return processed
    if original.shape != processed.shape:
        return processed

    if original.ndim == 1:
        return _residual_refine_1d(original, processed, strength)
    out = np.empty_like(processed)
    for ch in range(original.shape[0]):
        out[ch] = _residual_refine_1d(original[ch], processed[ch], strength)
    return out


def _residual_refine_1d(original, processed, strength):
    residual = original.astype(np.float64) - processed.astype(np.float64)
    n = len(residual)
    if n < 64:
        return processed

    b_allpass = np.array([0.6, 1.0])
    a_allpass = np.array([1.0, 0.6])
    diffused = lfilter(b_allpass, a_allpass, residual)

    freqs = np.fft.rfftfreq(n)
    freqs[0] = 1e-10
    one_over_f = 1.0 / np.sqrt(freqs)
    one_over_f[:1] = 0.0
    noise = np.random.randn(len(one_over_f)) * one_over_f
    noise = np.fft.irfft(noise, n=n)
    noise = noise / (np.std(noise) + 1e-12)
    noise = noise * np.std(residual) * 0.1

    refined = diffused + noise * strength
    blend = strength * 0.3
    result = processed.astype(np.float64) + refined * blend
    return np.clip(result, -1.0, 1.0).astype(processed.dtype)


def _estimate_loudness(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
    n_channels, n_samples = y.shape
    if n_samples < 1:
        return -70.0

    nyquist = sr / 2.0
    if nyquist > 60:
        sos_hp = butter(4, 60.0 / nyquist, btype='high', output='sos')
    else:
        sos_hp = None

    channel_loudness = np.zeros(n_channels)
    for ch in range(n_channels):
        data = y[ch].astype(np.float64)
        if sos_hp is not None:
            data = sosfiltfilt(sos_hp, data)

        squared = data ** 2
        mean_sq = np.mean(squared)
        if mean_sq > 1e-12:
            lufs = -0.691 + 10.0 * np.log10(mean_sq)
        else:
            lufs = -70.0
        channel_loudness[ch] = lufs

    if n_channels == 1:
        return channel_loudness[0]

    linear = 10.0 ** (channel_loudness / 10.0)
    combined = np.sum(linear) / n_channels
    return -0.691 + 10.0 * np.log10(combined)


def _match_loudness(y, sr, target_lufs=-14.0):
    current = _estimate_loudness(y, sr)
    if current < -70:
        return y
    gain_db = target_lufs - current
    gain_linear = 10.0 ** (gain_db / 20.0)
    if y.ndim == 1:
        return (y.astype(np.float64) * gain_linear).astype(y.dtype)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        out[ch] = (y[ch].astype(np.float64) * gain_linear).astype(y.dtype)
    return out