import numpy as np
from scipy.signal import stft as sp_stft, butter, sosfiltfilt
from .config import HOP_LENGTH


def _transient_detect(y, sr):
    if y.ndim > 1:
        y = y[0] if y.shape[0] == 1 else y.mean(axis=0)
    nperseg = HOP_LENGTH * 2
    noverlap = HOP_LENGTH
    f, t, Zxx = sp_stft(y, fs=sr, nperseg=nperseg, noverlap=noverlap)
    mag = np.abs(Zxx)
    n_frames = mag.shape[1]
    if n_frames < 2:
        return np.zeros(n_frames, dtype=bool)
    diff = np.diff(mag, axis=1)
    flux = np.sum(np.maximum(diff, 0.0), axis=0)
    if len(flux) < 1:
        return np.zeros(n_frames, dtype=bool)
    med = np.median(flux)
    sigma = np.std(flux)
    threshold = med + 2.0 * sigma
    is_transient = flux > threshold
    onset_mask = np.zeros(n_frames, dtype=bool)
    onset_mask[1:] = is_transient
    return onset_mask


def _transient_protect(y, sr, strength, onset_mask=None):
    if strength <= 0:
        n_samples = len(y) if y.ndim == 1 else y.shape[1]
        n_frames = max(1, 1 + (n_samples - 0) // HOP_LENGTH)
        return np.ones(n_frames, dtype=np.float64)

    if onset_mask is None:
        if y.ndim == 1:
            onset_mask = _transient_detect(y, sr)
        else:
            onset_mask = _transient_detect(
                y[0] if y.shape[0] == 1 else y.mean(axis=0), sr
            )

    n_frames = len(onset_mask)
    n_samples = len(y) if y.ndim == 1 else y.shape[1]
    gain = np.ones(n_frames, dtype=np.float64)

    transient_frames = np.where(onset_mask)[0]
    if len(transient_frames) == 0:
        return gain

    sample_gain = np.ones(n_samples, dtype=np.float64)
    window_samples = int(0.005 * sr)
    reduce_factor = 1.0 - strength * 0.5

    for i in transient_frames:
        center = i * HOP_LENGTH
        left = max(0, center - window_samples)
        right = min(n_samples, center + window_samples)
        mask = sample_gain[left:right] > reduce_factor
        sample_gain[left:right][mask] = reduce_factor

    for i in range(n_frames):
        start = i * HOP_LENGTH
        end = min(n_samples, (i + 1) * HOP_LENGTH)
        if end > start:
            gain[i] = np.mean(sample_gain[start:end])

    if y.ndim == 1:
        frame_rms = np.zeros(n_frames, dtype=np.float64)
        for i in range(n_frames):
            start = i * HOP_LENGTH
            end = min(n_samples, (i + 1) * HOP_LENGTH)
            if end > start:
                frame_rms[i] = np.sqrt(np.mean(y[start:end].astype(np.float64) ** 2))
    else:
        frame_rms = np.zeros(n_frames, dtype=np.float64)
        for i in range(n_frames):
            start = i * HOP_LENGTH
            end = min(n_samples, (i + 1) * HOP_LENGTH)
            if end > start:
                chunk = y[:, start:end].astype(np.float64)
                frame_rms[i] = np.sqrt(np.mean(chunk ** 2))

    positive_rms = frame_rms[frame_rms > 1e-12]
    if len(positive_rms) > 0:
        median_energy = np.median(positive_rms)
        sharp_mask = frame_rms > 3.0 * median_energy
        gain[sharp_mask] = np.minimum(gain[sharp_mask], 1.0 - strength * 0.7)

    return gain


def _protect_microdynamics(y, sr, strength, onset_mask):
    if strength <= 0:
        return y.copy() if hasattr(y, 'copy') else y

    if y.ndim == 1:
        return _protect_microdynamics_ch(y, sr, strength, onset_mask)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        onset_ch = onset_mask[ch] if isinstance(onset_mask, list) else onset_mask
        out[ch] = _protect_microdynamics_ch(y[ch], sr, strength, onset_ch)
    return out


def _protect_microdynamics_ch(y, sr, strength, onset_mask):
    n_samples = len(y)
    n_frames = len(onset_mask)
    if n_frames < 3:
        return y.copy() if hasattr(y, 'copy') else y

    hop = HOP_LENGTH
    frame_rms = np.zeros(n_frames, dtype=np.float64)
    for i in range(n_frames):
        start = i * hop
        end = min(n_samples, (i + 1) * hop)
        if end > start:
            chunk = y[start:end].astype(np.float64)
            frame_rms[i] = np.sqrt(np.mean(chunk ** 2))

    nyquist = sr / 2.0
    if nyquist < 3.0:
        return y.copy() if hasattr(y, 'copy') else y

    sos_lp = butter(2, 3.0 / nyquist, btype='low', output='sos')
    slow_env = sosfiltfilt(sos_lp, frame_rms)

    sos_bp = butter(2, [0.5 / nyquist, 3.0 / nyquist], btype='band', output='sos')
    modulation = sosfiltfilt(sos_bp, frame_rms)

    non_transient = ~onset_mask
    rms_min = np.percentile(frame_rms, 10)
    has_energy = frame_rms > (rms_min + 1e-12)
    valid = non_transient & has_energy

    boost = np.ones(n_frames, dtype=np.float64)
    if np.any(valid):
        mod_ratio = np.abs(modulation) / (slow_env + 1e-12)
        mod_boost = 1.0 + strength * 0.15 * mod_ratio
        mod_boost = np.clip(mod_boost, 0.97, 1.03)
        boost[valid] = mod_boost[valid]

    boost_samples = np.ones(n_samples, dtype=np.float64)
    for i in range(n_frames):
        start = i * hop
        end = min(n_samples, (i + 1) * hop)
        boost_samples[start:end] = boost[i]

    result = y.astype(np.float64) * boost_samples
    return result.astype(y.dtype)