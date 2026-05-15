import numpy as np
from scipy.signal import butter, sosfiltfilt, lfilter
from scipy.ndimage import gaussian_filter1d
from services.dsp_utils import stft, istft, fft_frequencies, rms
from .config import ERB_N_BANDS, N_FFT, HOP_LENGTH


def _erb_space(fmin, fmax, n_bands):
    def erb_number(f):
        return 21.4 * np.log10(4.37 * f / 1000.0 + 1.0)
    erb_min = erb_number(max(fmin, 1.0))
    erb_max = erb_number(fmax)
    erb_points = np.linspace(erb_min, erb_max, n_bands + 1)
    hz_points = (10.0 ** (erb_points / 21.4) - 1.0) * 1000.0 / 4.37
    return hz_points


def _pink_noise(n_samples):
    white = np.random.randn(n_samples)
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n_samples)
    freqs[0] = 1.0 / n_samples
    fft = fft / np.sqrt(np.maximum(freqs, 1e-12))
    pink = np.fft.irfft(fft, n=n_samples)
    return pink / (np.std(pink) + 1e-12)


def _f0_track(y, sr):
    if y.ndim > 1:
        y = y[0] if y.shape[0] == 1 else y.mean(axis=0)
    n_frames = 1 + (len(y) - N_FFT) // HOP_LENGTH
    if n_frames <= 0:
        return np.zeros(0)
    f0 = np.zeros(n_frames)
    min_lag = max(2, int(sr / 500.0))
    max_lag = int(sr / 50.0)
    if max_lag > N_FFT // 2:
        max_lag = N_FFT // 2
    if min_lag >= max_lag:
        return f0
    frames = np.lib.stride_tricks.as_strided(
        y, shape=(n_frames, N_FFT),
        strides=(y.strides[0] * HOP_LENGTH, y.strides[0])
    )
    frames_centered = frames - np.mean(frames, axis=1, keepdims=True)
    rms_vals = np.sqrt(np.mean(frames_centered ** 2, axis=1))
    n_fft_pad = 1
    while n_fft_pad < 2 * N_FFT:
        n_fft_pad *= 2
    lags = np.arange(min_lag, max_lag + 1)
    for i in range(n_frames):
        if rms_vals[i] < 1e-6:
            continue
        frame = frames_centered[i]
        energy = np.sum(frame ** 2)
        if energy < 1e-10:
            continue
        fft_frame = np.fft.rfft(frame, n=n_fft_pad)
        corr_full = np.fft.irfft(fft_frame * np.conj(fft_frame), n=n_fft_pad)
        corr = corr_full[:N_FFT]
        corr_norm = corr / energy
        valid_corr = corr_norm[lags]
        best_idx = np.argmax(valid_corr)
        best_corr = valid_corr[best_idx]
        best_lag = lags[best_idx]
        if best_corr > 0.3 and best_lag > 0:
            f0[i] = sr / best_lag
    return f0


def _onset_detect(y, sr):
    if y.ndim > 1:
        y = y[0] if y.shape[0] == 1 else y.mean(axis=0)
    frame_rms = rms(y, n_fft=N_FFT, hop_length=HOP_LENGTH)[0]
    if len(frame_rms) < 3:
        return np.zeros(len(frame_rms), dtype=bool)
    diff_rms = np.diff(frame_rms)
    diff_rms = np.maximum(diff_rms, 0)
    med_diff = np.median(diff_rms[diff_rms > 1e-12])
    if med_diff < 1e-12:
        return np.zeros(len(frame_rms), dtype=bool)
    onset_frames = diff_rms > (2.0 * med_diff)
    onset_mask = np.zeros(len(frame_rms), dtype=bool)
    onset_mask[1:] = onset_frames
    return onset_mask


def _erb_filterbank(y, sr, n_bands=ERB_N_BANDS):
    fmin = 20.0
    fmax = sr / 2.0
    boundaries = _erb_space(fmin, fmax, n_bands)
    if y.ndim > 1:
        y = y[0] if y.shape[0] == 1 else y.mean(axis=0)
    subbands = []
    for i in range(n_bands):
        low = boundaries[i]
        high = boundaries[i + 1]
        if high - low < 10.0:
            low = max(1.0, low - 5.0)
            high = high + 5.0
        low_norm = low / (sr / 2.0)
        high_norm = high / (sr / 2.0)
        low_norm = max(1e-6, min(low_norm, 1.0 - 1e-6))
        high_norm = max(low_norm + 1e-6, min(high_norm, 1.0 - 1e-6))
        sos = butter(2, [low_norm, high_norm], btype='band', output='sos')
        filtered = sosfiltfilt(sos, y.astype(np.float64))
        subbands.append(filtered.astype(y.dtype))
    return subbands


def _ai_trace_assess(S):
    mag = np.abs(S)
    n_bins, n_frames = mag.shape
    if n_frames < 2 or n_bins < 4:
        return {
            "spectral_flatness": 0.5,
            "harmonic_regularity": 0.5,
            "noise_floor_variance": 0.5,
            "overall_ai_probability": 0.5
        }
    eps = 1e-10
    geo_mean = np.exp(np.mean(np.log(mag + eps), axis=0))
    arith_mean = np.mean(mag, axis=0) + eps
    per_frame_flatness = geo_mean / arith_mean
    spectral_flatness = float(np.mean(per_frame_flatness))
    mag_mean = np.mean(mag, axis=1)
    mag_detrend = mag_mean - np.mean(mag_mean)
    if np.std(mag_detrend) > eps:
        mag_detrend = mag_detrend / np.std(mag_detrend)
    spec_autocorr = np.correlate(mag_detrend, mag_detrend, mode='full')
    spec_autocorr = spec_autocorr[len(spec_autocorr) // 2:]
    spec_autocorr = spec_autocorr / (spec_autocorr[0] + eps)
    mid_point = n_bins // 2
    if mid_point > 1:
        peak_regions = spec_autocorr[2:mid_point]
        harmonic_regularity = float(np.max(peak_regions)) if len(peak_regions) > 0 else 0.5
    else:
        harmonic_regularity = 0.5
    noise_floor = np.median(mag, axis=1)
    noise_floor_var = float(np.std(noise_floor) / (np.mean(noise_floor) + eps))
    noise_floor_variance = min(1.0, noise_floor_var / 2.0)
    ai_from_flatness = 1.0 - min(1.0, spectral_flatness * 3.0)
    ai_from_harmonic = min(1.0, harmonic_regularity * 1.5)
    ai_from_noise = 1.0 - min(1.0, noise_floor_variance * 2.0)
    overall = 0.3 * ai_from_flatness + 0.35 * ai_from_harmonic + 0.35 * ai_from_noise
    overall = min(1.0, max(0.0, overall))
    return {
        "spectral_flatness": spectral_flatness,
        "harmonic_regularity": harmonic_regularity,
        "noise_floor_variance": noise_floor_variance,
        "overall_ai_probability": overall
    }


def _pre_analysis(y, sr, params):
    if y.ndim == 1:
        y = y.reshape(1, -1)
    n_channels = y.shape[0]
    all_f0 = []
    all_onset = []
    all_subbands = []
    all_ai = []
    for ch in range(n_channels):
        ch_data = y[ch]
        f0 = _f0_track(ch_data, sr)
        onset = _onset_detect(ch_data, sr)
        subbands = _erb_filterbank(ch_data, sr)
        S = stft(ch_data, n_fft=N_FFT, hop_length=HOP_LENGTH)
        ai = _ai_trace_assess(np.abs(S))
        all_f0.append(f0)
        all_onset.append(onset)
        all_subbands.append(subbands)
        all_ai.append(ai)
    if n_channels == 1:
        return {
            "f0": all_f0[0],
            "onset_mask": all_onset[0],
            "subbands": all_subbands[0],
            "ai_trace": all_ai[0]
        }
    avg_ai = {k: float(np.mean([a[k] for a in all_ai])) for k in all_ai[0]}
    return {
        "f0": all_f0,
        "onset_mask": all_onset,
        "subbands": all_subbands,
        "ai_trace": avg_ai
    }


def _perceptual_spectral_completion(y, sr, strength, f0=None):
    if strength <= 0:
        return y
    if y.ndim == 1:
        return _psc_channel(y, sr, strength, f0)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        f0_ch = f0[ch] if isinstance(f0, list) and f0 is not None else f0
        out[ch] = _psc_channel(y[ch], sr, strength, f0_ch)
    return out


def _psc_channel(y, sr, strength, f0):
    n_samples = len(y)
    if n_samples < N_FFT:
        return y
    S = stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)
    mag = np.abs(S)
    phase = np.angle(S)
    n_bins, n_frames = mag.shape
    freqs = fft_frequencies(sr=sr, n_fft=N_FFT)
    high_mask = freqs > 8000.0
    if not np.any(high_mask):
        return y
    high_indices = np.where(high_mask)[0]
    enhanced = mag.copy()
    if f0 is not None and len(f0) > 0:
        guide = mag.copy()
        guide_smooth = np.zeros_like(mag)
        for j in range(n_frames):
            col = mag[:, j]
            smoothed = gaussian_filter1d(col, sigma=2.0)
            guide_smooth[:, j] = smoothed
        for j in range(n_frames):
            if j >= len(f0):
                break
            current_f0 = f0[j] if isinstance(f0, (list, np.ndarray)) else f0
            if current_f0 <= 0:
                continue
            n_harmonics = int((sr / 2.0) / current_f0)
            harm_bins = set()
            for h in range(1, n_harmonics + 1):
                hz = h * current_f0
                if hz > 8000.0 and hz < sr / 2.0:
                    bin_idx = int(round(hz * N_FFT / sr))
                    if bin_idx < n_bins:
                        harm_bins.add(bin_idx)
            if len(harm_bins) > 0:
                low_freq_env = np.mean(mag[:high_indices[0], j])
                for bin_idx in harm_bins:
                    if bin_idx in high_indices:
                        harmonic_strength = low_freq_env * (1.0 / max(1, bin_idx // (high_indices[0] + 1)))
                        guide_val = guide_smooth[bin_idx, j]
                        completion = 0.5 * guide_val + 0.5 * harmonic_strength
                        blend = strength * 0.3
                        enhanced[bin_idx, j] = (1.0 - blend) * mag[bin_idx, j] + blend * completion
    S_out = enhanced * np.exp(1j * phase)
    y_out = istft(S_out, hop_length=HOP_LENGTH, length=n_samples)
    return y_out.astype(y.dtype)


def _noise_floor_shape(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim == 1:
        return _nfs_channel(y, sr, strength)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        out[ch] = _nfs_channel(y[ch], sr, strength)
    return out


def _nfs_channel(y, sr, strength):
    n_samples = len(y)
    if n_samples < N_FFT:
        return y
    S = stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)
    mag = np.abs(S)
    phase = np.angle(S)
    n_bins, n_frames = mag.shape
    eps = 1e-12
    per_band_var = np.var(mag, axis=1)
    var_threshold = np.mean(per_band_var) * 0.3
    flat_bands = per_band_var < var_threshold
    if not np.any(flat_bands):
        return y
    np.random.seed(42)
    noise_len = n_samples
    pink = _pink_noise(noise_len)
    noise_S = stft(pink, n_fft=N_FFT, hop_length=HOP_LENGTH)
    noise_mag = np.abs(noise_S)
    peak_mag = np.max(mag)
    noise_target_db = -78.0 + (1.0 - strength) * 7.0
    noise_target_linear = peak_mag * (10.0 ** (noise_target_db / 20.0))
    noise_scale = noise_target_linear / (np.mean(noise_mag) + eps)
    shaped = mag.copy()
    for b in range(n_bins):
        if flat_bands[b]:
            noise_b = noise_mag[b, :n_frames] * noise_scale * strength * 0.5
            shaped[b, :] = mag[b, :] + noise_b
    S_out = shaped * np.exp(1j * phase)
    y_out = istft(S_out, hop_length=HOP_LENGTH, length=n_samples)
    return y_out.astype(y.dtype)


def _harmonic_deregularize(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim == 1:
        return _hd_channel(y, sr, strength)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        out[ch] = _hd_channel(y[ch], sr, strength)
    return out


def _hd_channel(y, sr, strength):
    n_samples = len(y)
    if n_samples < N_FFT:
        return y
    S = stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)
    mag = np.abs(S)
    phase = np.angle(S)
    n_bins, n_frames = mag.shape
    eps = 1e-12
    np.random.seed(42)
    perturb_scale = 0.005 * strength
    energy_noise = np.random.uniform(-perturb_scale, perturb_scale, size=mag.shape)
    perturbed_mag = mag * (1.0 + energy_noise)
    freqs = fft_frequencies(sr=sr, n_fft=N_FFT)
    for j in range(n_frames):
        col = perturbed_mag[:, j]
        peaks = np.zeros(n_bins, dtype=bool)
        for b in range(1, n_bins - 1):
            if col[b] > col[b - 1] and col[b] > col[b + 1] and col[b] > np.mean(col) * 1.5:
                peaks[b] = True
        peak_indices = np.where(peaks)[0]
        if len(peak_indices) > 1:
            for pi in range(len(peak_indices) - 1):
                b1 = peak_indices[pi]
                b2 = peak_indices[pi + 1]
                ratio_noise = np.random.uniform(-0.02 * strength, 0.02 * strength)
                ratio = col[b2] / (col[b1] + eps)
                new_ratio = ratio * (1.0 + ratio_noise)
                perturbed_mag[b2, j] = col[b1] * new_ratio
    S_out = perturbed_mag * np.exp(1j * phase)
    y_out = istft(S_out, hop_length=HOP_LENGTH, length=n_samples)
    signal_power = np.mean(y.astype(np.float64) ** 2)
    noise_power = np.mean((y_out.astype(np.float64) - y.astype(np.float64)) ** 2)
    if noise_power > eps:
        snr_db = 10.0 * np.log10(signal_power / noise_power)
        if snr_db < 50.0:
            scale = 10.0 ** ((50.0 - snr_db) / 20.0)
            y_out = y.astype(np.float64) + (y_out.astype(np.float64) - y.astype(np.float64)) * scale
    return y_out.astype(y.dtype)


def _subband_decorrelate(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim == 1:
        return _sdc_channel(y, sr, strength)
    out = np.empty_like(y)
    for ch in range(y.shape[0]):
        out[ch] = _sdc_channel(y[ch], sr, strength)
    return out


def _sdc_channel(y, sr, strength):
    n_samples = len(y)
    if n_samples < N_FFT:
        return y
    subbands = _erb_filterbank(y, sr)
    boundaries = _erb_space(20.0, sr / 2.0, len(subbands))
    centers = (boundaries[:-1] + boundaries[1:]) / 2.0
    processed = np.zeros(n_samples, dtype=np.float64)
    np.random.seed(42)
    for i, sb in enumerate(subbands):
        if centers[i] > 2000.0:
            a_param = 0.1 + 0.4 * min(1.0, (centers[i] - 2000.0) / (sr / 2.0 - 2000.0))
            a_perturbed = a_param * strength
            sb_float = sb.astype(np.float64)
            processed_sb = lfilter([a_perturbed, 1.0], [1.0, a_perturbed], sb_float)
            processed += processed_sb
        else:
            processed += sb.astype(np.float64)
    orig_rms = np.sqrt(np.mean(y.astype(np.float64) ** 2) + 1e-12)
    proc_rms = np.sqrt(np.mean(processed ** 2) + 1e-12)
    if proc_rms > 1e-12:
        processed = processed * (orig_rms / proc_rms)
    return processed.astype(y.dtype)


def _spectral_naturalize(y, sr, strength, f0=None):
    if strength <= 0:
        return y
    if y.ndim == 1:
        y_in = y.reshape(1, -1)
        was_mono = True
    else:
        y_in = y
        was_mono = False
    n_channels = y_in.shape[0]
    f0_list = f0 if isinstance(f0, list) else ([f0] * n_channels if f0 is not None else [None] * n_channels)
    result = np.empty_like(y_in)
    for ch in range(n_channels):
        ch_data = y_in[ch]
        ch_f0 = f0_list[ch] if ch < len(f0_list) else None
        ch_data = _perceptual_spectral_completion(ch_data, sr, strength * 0.7, ch_f0)
        ch_data = _noise_floor_shape(ch_data, sr, strength * 0.6)
        ch_data = _harmonic_deregularize(ch_data, sr, strength * 0.5)
        ch_data = _subband_decorrelate(ch_data, sr, strength * 0.4)
        result[ch] = ch_data
    if was_mono:
        return result[0]
    return result