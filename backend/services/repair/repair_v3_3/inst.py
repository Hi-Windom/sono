import numpy as np
from scipy.signal import butter, sosfiltfilt, lfilter
from services.dsp_utils import stft, istft, fft_frequencies
from .config import N_FFT, HOP_LENGTH


def _inst_aggressive_spectral_naturalize(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        S = stft(y_in, n_fft=N_FFT, hop_length=HOP_LENGTH)
        mag = np.abs(S)
        phase = np.angle(S)
        n_bins, n_frames = mag.shape
        eps = 1e-12
        rng = np.random.RandomState(42)
        pink = _pink_noise_inst(n, rng)
        noise_S = stft(pink, n_fft=N_FFT, hop_length=HOP_LENGTH)
        noise_mag = np.abs(noise_S)
        peak_mag = np.max(mag)
        noise_target_db = -65.0 + (1.0 - strength) * 10.0
        noise_target_linear = peak_mag * (10.0 ** (noise_target_db / 20.0))
        noise_scale = noise_target_linear / (np.mean(noise_mag) + eps)
        per_band_var = np.var(mag, axis=1)
        var_threshold = np.mean(per_band_var) * 0.4
        flat_bands = per_band_var < var_threshold
        shaped = mag.copy()
        for b in range(n_bins):
            if flat_bands[b]:
                noise_b = noise_mag[b, :n_frames] * noise_scale * strength
                shaped[b, :] = mag[b, :] + noise_b
        freqs = fft_frequencies(sr=sr, n_fft=N_FFT)
        target_spec = 1.0 / (freqs + eps)
        target_spec = target_spec / np.max(target_spec)
        current_spec = np.mean(shaped, axis=1)
        current_spec = current_spec / (np.max(current_spec) + eps)
        blend = strength * 0.3
        target_spec = (1.0 - blend) * current_spec + blend * target_spec
        ratio = target_spec / (current_spec + eps)
        shaped = shaped * ratio[:, np.newaxis]
        S_out = shaped * np.exp(1j * phase)
        y_out = istft(S_out, hop_length=HOP_LENGTH, length=n)
        if len(y_out) < n:
            y_out = np.pad(y_out, (0, n - len(y_out)))
        elif len(y_out) > n:
            y_out = y_out[:n]
        return y_out.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        results = []
        for ch in range(y_in.shape[0]):
            results.append(_inst_aggressive_spectral_naturalize(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def _pink_noise_inst(n_samples, rng):
    white = rng.randn(n_samples)
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n_samples)
    freqs[0] = 1.0 / n_samples
    fft = fft / np.sqrt(np.maximum(freqs, 1e-12))
    pink = np.fft.irfft(fft, n=n_samples)
    return pink / (np.std(pink) + 1e-12)


def _inst_multiband_harmonic_dereg(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        S = stft(y_in, n_fft=N_FFT, hop_length=HOP_LENGTH)
        mag = np.abs(S)
        phase = np.angle(S)
        n_bins, n_frames = mag.shape
        eps = 1e-12
        rng = np.random.RandomState(42)
        freqs = fft_frequencies(sr=sr, n_fft=N_FFT)
        low_mask = freqs < 250.0
        mid_mask = (freqs >= 250.0) & (freqs <= 4000.0)
        high_mask = freqs > 4000.0
        perturbed = mag.copy()
        if np.any(low_mask):
            low_perturb = rng.uniform(-0.01 * strength, 0.01 * strength, size=(np.sum(low_mask), n_frames))
            perturbed[low_mask] *= 1.0 + low_perturb
        if np.any(mid_mask):
            mid_perturb = rng.uniform(-0.03 * strength, 0.03 * strength, size=(np.sum(mid_mask), n_frames))
            perturbed[mid_mask] *= 1.0 + mid_perturb
        if np.any(high_mask):
            high_perturb = rng.uniform(-0.06 * strength, 0.06 * strength, size=(np.sum(high_mask), n_frames))
            perturbed[high_mask] *= 1.0 + high_perturb
        step = max(1, n_frames // 200)
        processed_frames = list(range(0, n_frames, step))
        for j in processed_frames:
            col = perturbed[:, j]
            mean_col = np.mean(col)
            is_peak = np.zeros(n_bins, dtype=bool)
            is_peak[1:-1] = (col[1:-1] > col[:-2]) & (col[1:-1] > col[2:]) & (col[1:-1] > mean_col * 1.5)
            peak_indices = np.where(is_peak)[0]
            if len(peak_indices) > 1:
                for pi in range(len(peak_indices) - 1):
                    b1 = peak_indices[pi]
                    b2 = peak_indices[pi + 1]
                    ratio_noise = rng.uniform(-0.1 * strength, 0.1 * strength)
                    ratio = col[b2] / (col[b1] + eps)
                    new_ratio = ratio * (1.0 + ratio_noise)
                    perturbed[b2, j] = col[b1] * new_ratio
        if step > 1:
            for b in range(n_bins):
                row = perturbed[b]
                proc_vals = row[processed_frames]
                perturbed[b] = np.interp(np.arange(n_frames), processed_frames, proc_vals)
        S_out = perturbed * np.exp(1j * phase)
        y_out = istft(S_out, hop_length=HOP_LENGTH, length=n)
        if len(y_out) < n:
            y_out = np.pad(y_out, (0, n - len(y_out)))
        elif len(y_out) > n:
            y_out = y_out[:n]
        if strength > 0.5:
            signal_power = np.mean(y_in ** 2)
            noise_power = np.mean((y_out - y_in) ** 2)
            if noise_power > eps:
                snr_db = 10.0 * np.log10(signal_power / noise_power)
                if snr_db < 45.0:
                    scale = 10.0 ** ((45.0 - snr_db) / 20.0)
                    y_out = y_in + (y_out - y_in) * scale
        return y_out.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        results = []
        for ch in range(y_in.shape[0]):
            results.append(_inst_multiband_harmonic_dereg(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def _inst_spatial_enhance(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim == 1:
        return y
    if y.shape[0] < 2:
        return y
    original_dtype = y.dtype
    L = y[0].astype(np.float64)
    R = y[1].astype(np.float64)
    M = (L + R) * 0.5
    S = (L - R) * 0.5
    a_m = 0.02 + 0.1 * strength
    a_s = 0.1 + 0.3 * strength
    b_m = np.array([a_m, 1.0])
    a_m_coeff = np.array([1.0, a_m])
    M_processed = lfilter(b_m, a_m_coeff, M)
    M_processed = lfilter(b_m, a_m_coeff, M_processed[::-1])[::-1]
    b_s = np.array([a_s, 1.0])
    a_s_coeff = np.array([1.0, a_s])
    S_processed = lfilter(b_s, a_s_coeff, S)
    S_processed = lfilter(b_s, a_s_coeff, S_processed[::-1])[::-1]
    n = len(M)
    S_stft = stft(S_processed, n_fft=N_FFT, hop_length=HOP_LENGTH)
    n_bins, n_frames = S_stft.shape
    freqs = fft_frequencies(sr=sr, n_fft=N_FFT)
    high_mask = freqs > 8000.0
    if np.any(high_mask):
        high_indices = np.where(high_mask)[0]
        rng = np.random.RandomState(42)
        phase_shift = (rng.rand(len(high_indices), n_frames) - 0.5) * 2 * np.pi * strength * 0.08
        mag_s = np.abs(S_stft)
        phase_s = np.angle(S_stft)
        phase_s[high_indices] += phase_shift
        S_stft = mag_s * np.exp(1j * phase_s)
    S_processed = istft(S_stft, hop_length=HOP_LENGTH, length=n)
    if len(S_processed) < n:
        S_processed = np.pad(S_processed, (0, n - len(S_processed)))
    elif len(S_processed) > n:
        S_processed = S_processed[:n]
    L_out = M_processed + S_processed
    R_out = M_processed - S_processed
    out = np.stack([L_out, R_out])
    peak = np.max(np.abs(out))
    if peak > 0.99:
        out *= 0.99 / peak
    return out.astype(original_dtype)


def _inst_transient_impact_protect(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        onset_mask = _detect_impact_inst(y_in, sr)
        if onset_mask is None or len(onset_mask) < 2:
            return y
        n_frames = len(onset_mask)
        gain = np.ones(n_frames, dtype=np.float64)
        transient_frames = np.where(onset_mask)[0]
        if len(transient_frames) > 0:
            reduce_factor = 1.0 - strength * 0.4
            for i in transient_frames:
                left = max(0, i - 1)
                right = min(n_frames, i + 3)
                gain[left:right] = np.minimum(gain[left:right], reduce_factor)
        result = np.zeros(n, dtype=np.float64)
        overlap = np.zeros(n, dtype=np.float64)
        for i in range(n_frames):
            start = i * HOP_LENGTH
            end = min(n, start + N_FFT)
            if end <= start:
                continue
            g = gain[i] if i < len(gain) else 1.0
            result[start:end] += y_in[start:end] * g
            overlap[start:end] += 1.0
        overlap[overlap < 1] = 1.0
        y_out = result / overlap
        return y_out.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        results = []
        for ch in range(y_in.shape[0]):
            results.append(_inst_transient_impact_protect(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def _detect_impact_inst(y, sr):
    n_frames = 1 + (len(y) - N_FFT) // HOP_LENGTH
    if n_frames < 3:
        return None
    frames = np.lib.stride_tricks.as_strided(
        y, shape=(n_frames, N_FFT),
        strides=(y.strides[0] * HOP_LENGTH, y.strides[0])
    )
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    diff = np.diff(rms)
    diff = np.maximum(diff, 0)
    med = np.median(diff[diff > 1e-12]) if np.any(diff > 1e-12) else 1e-12
    if med < 1e-12:
        return np.zeros(n_frames, dtype=bool)
    onset = diff > (4.0 * med)
    mask = np.zeros(n_frames, dtype=bool)
    mask[1:] = onset
    return mask


def _inst_upward_compression(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        nyq = sr / 2.0
        low_cross = min(250.0 / nyq, 0.99)
        high_cross = min(4000.0 / nyq, 0.99)
        sos_low = butter(4, low_cross, btype='low', output='sos')
        sos_high = butter(4, high_cross, btype='high', output='sos')
        low_band = sosfiltfilt(sos_low, y_in)
        high_band = sosfiltfilt(sos_high, y_in)
        mid_band = y_in - low_band - high_band
        ratio = 1.2 + (2.0 - 1.2) * strength
        threshold_offset = -35.0 + 10.0 * (1.0 - strength)
        for band_data in [low_band, mid_band, high_band]:
            peak_db = 20.0 * np.log10(np.max(np.abs(band_data)) + 1e-12)
            thr = peak_db + threshold_offset
            frame_hop = HOP_LENGTH
            n_frames = (n - HOP_LENGTH) // frame_hop + 1
            if n_frames < 2:
                continue
            rms_frames = np.zeros(n_frames)
            for i in range(n_frames):
                start = i * frame_hop
                end = min(start + HOP_LENGTH, n)
                chunk = band_data[start:end]
                rms_frames[i] = np.sqrt(np.mean(chunk ** 2) + 1e-12)
            rms_db = 20.0 * np.log10(rms_frames + 1e-12)
            tau_frames = 100.0 * 0.001 * sr / frame_hop
            alpha = np.exp(-1.0 / max(tau_frames, 1.0))
            smoothed_db = np.zeros_like(rms_db)
            smoothed_db[0] = rms_db[0]
            for i in range(1, n_frames):
                if rms_db[i] < smoothed_db[i - 1]:
                    smoothed_db[i] = 0.3 * rms_db[i] + 0.7 * smoothed_db[i - 1]
                else:
                    smoothed_db[i] = alpha * smoothed_db[i - 1] + (1.0 - alpha) * rms_db[i]
            gain = np.ones(n_frames)
            below = smoothed_db < thr
            if np.any(below):
                diff_db = thr - smoothed_db[below]
                gain[below] = (10.0 ** (diff_db / 20.0)) ** (1.0 - 1.0 / ratio)
            max_gain = 10.0 ** (4.0 / 20.0)
            gain = np.clip(gain, 0.0, max_gain)
            window = np.hanning(HOP_LENGTH)
            output = np.zeros(n + HOP_LENGTH, dtype=np.float64)
            norm = np.zeros(n + HOP_LENGTH, dtype=np.float64)
            for i in range(n_frames):
                start = i * frame_hop
                end = min(start + HOP_LENGTH, n)
                frame = band_data[start:end]
                weighted = frame * window[:len(frame)] * gain[i]
                output[start:end] += weighted
                norm[start:end] += window[:len(frame)]
            norm = np.maximum(norm, 1e-12)
            band_data[:] = output[:n] / norm[:n]
        result = low_band + mid_band + high_band
        return result.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        results = []
        for ch in range(y_in.shape[0]):
            results.append(_inst_upward_compression(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def process_inst_v33(y, sr, params, progress_callback=None, progress_start=0.0, progress_end=1.0):
    strength = params.get("strength", 1.0)
    stages = []
    if params.get("spectral_naturalize", 0) > 0:
        stages.append(("spectral_naturalize", "谱自然化"))
    if params.get("harmonic_deregularize", 0) > 0:
        stages.append(("harmonic_deregularize", "谐波去规整"))
    if params.get("spatial_enhance", 0) > 0:
        stages.append(("spatial_enhance", "空间感增强"))
    if params.get("transient_protect", 0) > 0:
        stages.append(("transient_protect", "瞬态保护"))
    if params.get("dynamic_naturalize", 0) > 0:
        stages.append(("dynamic_naturalize", "动态自然化"))
    n_stages = len(stages)
    for idx, (key, label) in enumerate(stages):
        s = params[key] * strength
        if progress_callback and n_stages > 0:
            p = progress_start + (progress_end - progress_start) * (idx / n_stages)
            progress_callback(p, f"伴奏{label}...")
        y = _INST_STAGE_MAP[key](y, sr, s)
    if progress_callback:
        progress_callback(progress_end, "伴奏处理完成")
    return y


_INST_STAGE_MAP = {
    "spectral_naturalize": _inst_aggressive_spectral_naturalize,
    "harmonic_deregularize": _inst_multiband_harmonic_dereg,
    "spatial_enhance": _inst_spatial_enhance,
    "transient_protect": _inst_transient_impact_protect,
    "dynamic_naturalize": _inst_upward_compression,
}