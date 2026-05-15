import numpy as np
from scipy.signal import butter, sosfiltfilt, lfilter
from .config import HOP_LENGTH


def _cross_bleed(vocal, accompaniment, strength):
    if strength <= 0:
        return vocal.copy(), accompaniment.copy()
    v = vocal.astype(np.float64)
    a = accompaniment.astype(np.float64)
    if v.ndim == 1:
        v = v.reshape(1, -1)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    min_len = min(v.shape[1], a.shape[1])
    v = v[:, :min_len]
    a = a[:, :min_len]
    if v.shape[0] != a.shape[0]:
        if v.shape[0] == 1 and a.shape[0] == 2:
            v = np.repeat(v, 2, axis=0)
        elif v.shape[0] == 2 and a.shape[0] == 1:
            a = np.repeat(a, 2, axis=0)
    bleed_amount = strength * 0.05
    v_out = v + a * bleed_amount
    a_out = a + v * bleed_amount * 0.3
    peak_v = np.max(np.abs(v_out))
    if peak_v > 0.99:
        v_out *= 0.99 / peak_v
    peak_a = np.max(np.abs(a_out))
    if peak_a > 0.99:
        a_out *= 0.99 / peak_a
    return v_out.astype(vocal.dtype), a_out.astype(accompaniment.dtype)


def _loudness_match(mixed, sr, target_lufs=-14.0):
    if mixed.ndim == 1:
        mixed = mixed.reshape(1, -1)
    n_channels, n_samples = mixed.shape
    if n_samples < 1:
        return mixed
    nyquist = sr / 2.0
    if nyquist > 60:
        sos_hp = butter(4, 60.0 / nyquist, btype='high', output='sos')
    else:
        sos_hp = None
    channel_loudness = np.zeros(n_channels)
    for ch in range(n_channels):
        data = mixed[ch].astype(np.float64)
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
        current_loudness = channel_loudness[0]
    else:
        linear = 10.0 ** (channel_loudness / 10.0)
        combined = np.sum(linear) / n_channels
        current_loudness = -0.691 + 10.0 * np.log10(combined)
    if current_loudness < -70:
        return mixed
    gain_db = target_lufs - current_loudness
    gain_linear = 10.0 ** (gain_db / 20.0)
    gain_linear = np.clip(gain_linear, 0.2, 5.0)
    out = np.empty_like(mixed)
    for ch in range(n_channels):
        out[ch] = (mixed[ch].astype(np.float64) * gain_linear).astype(mixed.dtype)
    return out


def _soft_limit_slow_gain(mixed, sr):
    original_dtype = mixed.dtype
    if mixed.ndim == 1:
        mixed = mixed.reshape(1, -1)
    y = mixed.astype(np.float64)
    n_channels, n_samples = y.shape
    peak = np.max(np.abs(y))
    if peak > 0.95:
        x = y * 4.0 / peak
        y = np.tanh(x) * peak / 4.0
    frame_len = int(0.05 * sr)
    hop = frame_len // 2
    n_frames = max(1, (n_samples - frame_len) // hop + 1)
    rms_frames = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop
        end = min(start + frame_len, n_samples)
        chunk = y[:, start:end]
        rms_frames[i] = np.sqrt(np.mean(chunk ** 2))
    target_rms = np.percentile(rms_frames, 80)
    if target_rms < 1e-12:
        target_rms = 0.1
    gain = target_rms / (rms_frames + 1e-12)
    gain = np.clip(gain, 0.5, 2.0)
    tau = int(0.2 * sr / hop)
    alpha = np.exp(-1.0 / max(tau, 1))
    smooth_gain = np.zeros_like(gain)
    smooth_gain[0] = gain[0]
    for i in range(1, n_frames):
        smooth_gain[i] = alpha * smooth_gain[i - 1] + (1.0 - alpha) * gain[i]
    result = np.zeros_like(y)
    overlap = np.zeros(n_samples)
    for i in range(n_frames):
        start = i * hop
        end = min(start + frame_len, n_samples)
        g = smooth_gain[i]
        result[:, start:end] += y[:, start:end] * g
        overlap[start:end] += 1.0
    overlap[overlap < 1] = 1.0
    result = result / overlap
    final_peak = np.max(np.abs(result))
    if final_peak > 0.99:
        result *= 0.99 / final_peak
    if original_dtype == mixed.dtype:
        return result.astype(original_dtype)
    return result.astype(original_dtype)


def _final_residual_refine(original, processed, strength):
    if strength <= 0:
        return processed
    if original.shape != processed.shape:
        return processed
    original_dtype = processed.dtype
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
    diffused = lfilter(b_allpass, a_allpass, diffused[::-1])[::-1]
    rng = np.random.RandomState(42)
    freqs = np.fft.rfftfreq(n)
    freqs[0] = 1e-10
    one_over_f = 1.0 / np.sqrt(freqs)
    noise = rng.randn(len(one_over_f)) * one_over_f
    noise = np.fft.irfft(noise, n=n)
    noise = noise / (np.std(noise) + 1e-12)
    noise = noise * np.std(residual) * 0.1
    refined = diffused + noise * strength
    blend = strength * 0.3
    result = processed.astype(np.float64) + refined * blend
    return np.clip(result, -1.0, 1.0).astype(original_dtype)


def mixback(vocal, accompaniment, sr, params):
    strength = params.get("strength", 1.0)
    vocal_ratio = params.get("vocal_ratio", 1.0)
    accompaniment_ratio = params.get("accompaniment_ratio", 1.0)
    cross_bleed_strength = params.get("cross_bleed", 0.3) * strength
    v, a = _cross_bleed(vocal, accompaniment, cross_bleed_strength)
    if v.ndim == 1:
        v = v.reshape(1, -1)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    min_len = min(v.shape[1], a.shape[1])
    v = v[:, :min_len]
    a = a[:, :min_len]
    if v.shape[0] != a.shape[0]:
        if v.shape[0] == 1 and a.shape[0] == 2:
            v = np.repeat(v, 2, axis=0)
        elif v.shape[0] == 2 and a.shape[0] == 1:
            a = np.repeat(a, 2, axis=0)
    mixed = v * vocal_ratio + a * accompaniment_ratio
    peak = np.max(np.abs(mixed))
    if peak > 0.99:
        mixed *= 0.99 / peak
    target_lufs = params.get("target_lufs", -14.0)
    mixed = _loudness_match(mixed, sr, target_lufs)
    mixed = _soft_limit_slow_gain(mixed, sr)
    residual_refine = params.get("residual_refine", 0.0)
    if residual_refine > 0:
        original_mixed = v * vocal_ratio + a * accompaniment_ratio
        mixed = _final_residual_refine(original_mixed, mixed, residual_refine)
    return mixed