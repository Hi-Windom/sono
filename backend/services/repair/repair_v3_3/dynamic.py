import numpy as np
from scipy.signal import butter, sosfiltfilt, lfilter
from .config import HOP_LENGTH


def _upward_compressor_band(band, sr, strength, threshold_db=-24.0, ratio=2.0, release_ms=100.0):
    n_samples = len(band)
    if n_samples < HOP_LENGTH * 2:
        return band

    frame_hop = HOP_LENGTH
    n_frames = (n_samples - HOP_LENGTH) // frame_hop + 1
    if n_frames < 2:
        return band

    adj_ratio = 1.0 + (ratio - 1.0) * strength
    adj_threshold_db = threshold_db - (1.0 - strength) * 5.0

    rms_frames = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * frame_hop
        end = start + HOP_LENGTH
        chunk = band[start:end].astype(np.float64)
        rms_frames[i] = np.sqrt(np.mean(chunk ** 2) + 1e-12)

    rms_db = 20.0 * np.log10(rms_frames + 1e-12)

    tau_frames = release_ms * 0.001 * sr / frame_hop
    alpha = np.exp(-1.0 / max(tau_frames, 1.0))
    smoothed_db = np.zeros_like(rms_db)
    smoothed_db[0] = rms_db[0]
    for i in range(1, n_frames):
        if rms_db[i] < smoothed_db[i - 1]:
            smoothed_db[i] = 0.3 * rms_db[i] + 0.7 * smoothed_db[i - 1]
        else:
            smoothed_db[i] = alpha * smoothed_db[i - 1] + (1.0 - alpha) * rms_db[i]

    gain = np.ones(n_frames)
    below = smoothed_db < adj_threshold_db
    if np.any(below):
        diff_db = adj_threshold_db - smoothed_db[below]
        gain[below] = (10.0 ** (diff_db / 20.0)) ** (1.0 - 1.0 / adj_ratio)

    max_gain_linear = 10.0 ** (6.0 / 20.0)
    gain = np.clip(gain, 0.0, max_gain_linear)

    window = np.hanning(HOP_LENGTH)
    output = np.zeros(n_samples + HOP_LENGTH, dtype=np.float64)
    norm = np.zeros(n_samples + HOP_LENGTH, dtype=np.float64)

    for i in range(n_frames):
        start = i * frame_hop
        end = start + HOP_LENGTH
        frame = band[start:end].astype(np.float64)
        weighted = frame * window * gain[i]
        output[start:end] += weighted
        norm[start:end] += window

    norm = np.maximum(norm, 1e-12)
    result = output[:n_samples] / norm[:n_samples]
    return result.astype(band.dtype)


def _dynamic_naturalize(y, sr, strength):
    if strength <= 0.0:
        return y
    if y.ndim == 1:
        return _dynamic_naturalize_ch(y, sr, strength)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        out[ch] = _dynamic_naturalize_ch(y[ch], sr, strength)
    return out


def _dynamic_naturalize_ch(y, sr, strength):
    n_samples = len(y)
    if n_samples < HOP_LENGTH * 2:
        return y

    nyq = sr / 2.0

    low_cross = min(250.0 / nyq, 0.99)
    high_cross = min(4000.0 / nyq, 0.99)

    sos_low = butter(4, low_cross, btype='low', output='sos')
    sos_high = butter(4, high_cross, btype='high', output='sos')

    y_f64 = y.astype(np.float64)
    low_band = sosfiltfilt(sos_low, y_f64)
    high_band = sosfiltfilt(sos_high, y_f64)
    mid_band = y_f64 - low_band - high_band

    ratio = 1.5 + (3.0 - 1.5) * strength
    threshold_offset = -30.0 + 10.0 * (1.0 - strength)

    low_peak_db = 20.0 * np.log10(np.max(np.abs(low_band)) + 1e-12)
    mid_peak_db = 20.0 * np.log10(np.max(np.abs(mid_band)) + 1e-12)
    high_peak_db = 20.0 * np.log10(np.max(np.abs(high_band)) + 1e-12)

    low_thr = low_peak_db + threshold_offset
    mid_thr = mid_peak_db + threshold_offset
    high_thr = high_peak_db + threshold_offset

    low_proc = _upward_compressor_band(low_band, sr, strength, threshold_db=low_thr, ratio=ratio, release_ms=100.0)
    mid_proc = _upward_compressor_band(mid_band, sr, strength, threshold_db=mid_thr, ratio=ratio, release_ms=100.0)
    high_proc = _upward_compressor_band(high_band, sr, strength, threshold_db=high_thr, ratio=ratio, release_ms=100.0)

    result = low_proc.astype(np.float64) + mid_proc.astype(np.float64) + high_proc.astype(np.float64)
    return result.astype(y.dtype)


def _loudness_normalize(y, sr, target_lufs=-14.0):
    if y.ndim == 1:
        return _loudness_normalize_ch(y, sr, target_lufs)

    n_channels = y.shape[0]
    mean_sq_sum = 0.0
    for ch in range(n_channels):
        filtered = _apply_loudness_prefilter(y[ch].astype(np.float64), sr)
        mean_sq_sum += np.mean(filtered ** 2)

    mean_sq = mean_sq_sum / n_channels
    if mean_sq <= 1e-12:
        return y

    loudness = -0.691 + 10.0 * np.log10(mean_sq)
    gain_db = target_lufs - loudness
    gain_linear = 10.0 ** (gain_db / 20.0)
    gain_linear = np.clip(gain_linear, 0.2, 5.0)

    out = np.empty_like(y)
    for ch in range(n_channels):
        out[ch] = (y[ch].astype(np.float64) * gain_linear).astype(y.dtype)
    return out


def _loudness_normalize_ch(y, sr, target_lufs=-14.0):
    filtered = _apply_loudness_prefilter(y.astype(np.float64), sr)
    mean_sq = np.mean(filtered ** 2)
    if mean_sq <= 1e-12:
        return y

    loudness = -0.691 + 10.0 * np.log10(mean_sq)
    gain_db = target_lufs - loudness
    gain_linear = 10.0 ** (gain_db / 20.0)
    gain_linear = np.clip(gain_linear, 0.2, 5.0)

    return (y.astype(np.float64) * gain_linear).astype(y.dtype)


def _apply_loudness_prefilter(data, sr):
    nyq = sr / 2.0
    if nyq <= 38.0:
        return data

    sos_hp = butter(2, 38.0 / nyq, btype='high', output='sos')
    filtered = sosfiltfilt(sos_hp, data)

    fc = 1500.0
    gain_db = 4.0
    Q = 0.707

    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / sr
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * Q)

    sqrt_A = np.sqrt(A)
    b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + 2.0 * sqrt_A * alpha)
    b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
    b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - 2.0 * sqrt_A * alpha)
    a0 = (A + 1.0) - (A - 1.0) * cos_w0 + 2.0 * sqrt_A * alpha
    a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
    a2 = (A + 1.0) - (A - 1.0) * cos_w0 - 2.0 * sqrt_A * alpha

    b = np.array([b0, b1, b2]) / a0
    a = np.array([a0, a1, a2]) / a0

    filtered = lfilter(b, a, filtered)
    return filtered