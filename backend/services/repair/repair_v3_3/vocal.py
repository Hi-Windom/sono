import numpy as np
from scipy.signal import butter, sosfiltfilt, lfilter
from services.dsp_utils import stft, istft, fft_frequencies
from .config import N_FFT, HOP_LENGTH


def _vocal_f0_harmonic_naturalize(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        S = stft(y_in, n_fft=N_FFT, hop_length=HOP_LENGTH)
        n_bins, n_frames = S.shape
        f0 = _f0_track_vocal(y_in, sr)
        if len(f0) < 2:
            return y
        f0_per_frame = np.interp(
            np.linspace(0, n_frames - 1, n_frames),
            np.linspace(0, n_frames - 1, len(f0)),
            f0
        )
        for f in range(n_frames):
            current_f0 = f0_per_frame[f]
            if current_f0 < 50 or current_f0 > 2000:
                continue
            max_harmonic = int(np.floor(sr / (2 * current_f0)))
            for h in range(1, min(max_harmonic + 1, 15)):
                target_freq = h * current_f0
                target_bin = int(np.round(target_freq * N_FFT / sr))
                if target_bin < 1 or target_bin >= n_bins - 1:
                    continue
                mag = np.abs(S[target_bin, f])
                phase = np.angle(S[target_bin, f])
                boost = 1.0 + strength * 0.12
                S[target_bin, f] = mag * boost * np.exp(1j * phase)
                if target_bin > 1:
                    S[target_bin - 1, f] *= 1.0 + strength * 0.04
                if target_bin < n_bins - 2:
                    S[target_bin + 1, f] *= 1.0 + strength * 0.04
        y_out = istft(S, hop_length=HOP_LENGTH, length=n)
        if len(y_out) < n:
            y_out = np.pad(y_out, (0, n - len(y_out)))
        elif len(y_out) > n:
            y_out = y_out[:n]
        return y_out.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        n = y_in.shape[1]
        results = []
        for ch in range(y_in.shape[0]):
            ch_out = _vocal_f0_harmonic_naturalize(y_in[ch], sr, strength)
            results.append(ch_out)
        return np.stack(results).astype(original_dtype)


def _f0_track_vocal(y, sr):
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


def _vocal_microtremor_breath(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        rng = np.random.RandomState(42)
        frame_len = int(0.02 * sr)
        hop = frame_len // 4
        n_frames = max(1, (n - frame_len) // hop + 1)
        env = np.zeros(n)
        count = np.zeros(n)
        for i in range(n_frames):
            start = i * hop
            end = min(start + frame_len, n)
            rms = np.sqrt(np.mean(y_in[start:end] ** 2) + 1e-12)
            tremble = 1.0 + rng.uniform(-0.015, 0.015) * strength
            env[start:end] += rms * tremble
            count[start:end] += 1.0
        count[count < 1] = 1.0
        env = env / count
        env_smooth = np.convolve(env, np.ones(5) / 5, mode='same')
        breath_noise = rng.randn(n).astype(np.float64)
        nyq = sr / 2.0
        sos_bp = butter(2, [200.0 / nyq, 2000.0 / nyq], btype='band', output='sos')
        breath_noise = sosfiltfilt(sos_bp, breath_noise)
        breath_level = np.mean(np.abs(y_in)) * 0.02 * strength
        y_out = y_in * (env_smooth / (np.mean(env_smooth) + 1e-12))
        y_out = y_out + breath_noise * breath_level
        peak = np.max(np.abs(y_out))
        if peak > 0.99:
            y_out *= 0.99 / peak
        return y_out.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        results = []
        for ch in range(y_in.shape[0]):
            results.append(_vocal_microtremor_breath(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def _vocal_emotional_transient_protect(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        onset_mask = _detect_onset_vocal(y_in, sr)
        if onset_mask is None or len(onset_mask) < 2:
            return y
        n_frames = len(onset_mask)
        gain = np.ones(n_frames, dtype=np.float64)
        transient_frames = np.where(onset_mask)[0]
        if len(transient_frames) > 0:
            reduce_factor = 1.0 - strength * 0.6
            for i in transient_frames:
                left = max(0, i - 1)
                right = min(n_frames, i + 2)
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
            results.append(_vocal_emotional_transient_protect(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def _detect_onset_vocal(y, sr):
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
    onset = diff > (3.0 * med)
    mask = np.zeros(n_frames, dtype=bool)
    mask[1:] = onset
    return mask


def _vocal_de_shimmer(y, sr, strength):
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
        freqs = fft_frequencies(sr=sr, n_fft=N_FFT)
        high_mask = freqs > 6000.0
        if not np.any(high_mask):
            return y
        high_indices = np.where(high_mask)[0]
        for b in high_indices:
            smoothed = np.convolve(mag[b], np.ones(5) / 5, mode='same')
            blend = strength * 0.4
            mag[b] = (1.0 - blend) * mag[b] + blend * smoothed
        S_out = mag * np.exp(1j * phase)
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
            results.append(_vocal_de_shimmer(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def _vocal_light_phase_diffuse(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        a = 0.03 + 0.1 * strength
        b = np.array([a, 1.0])
        a_coeff = np.array([1.0, a])
        y_out = lfilter(b, a_coeff, y_in)
        y_out = lfilter(b, a_coeff, y_out[::-1])[::-1]
        return y_out.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        results = []
        for ch in range(y_in.shape[0]):
            a = 0.03 + 0.1 * strength
            b = np.array([a, 1.0])
            a_coeff = np.array([1.0, a])
            ch_out = lfilter(b, a_coeff, y_in[ch])
            ch_out = lfilter(b, a_coeff, ch_out[::-1])[::-1]
            results.append(ch_out)
        return np.stack(results).astype(original_dtype)


def _vocal_light_noise_floor(y, sr, strength):
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
        per_band_var = np.var(mag, axis=1)
        var_threshold = np.mean(per_band_var) * 0.2
        flat_bands = per_band_var < var_threshold
        if not np.any(flat_bands):
            return y
        rng = np.random.RandomState(42)
        pink = _pink_noise_vocal(n, rng)
        noise_S = stft(pink, n_fft=N_FFT, hop_length=HOP_LENGTH)
        noise_mag = np.abs(noise_S)
        peak_mag = np.max(mag)
        noise_target_db = -80.0
        noise_target_linear = peak_mag * (10.0 ** (noise_target_db / 20.0))
        noise_scale = noise_target_linear / (np.mean(noise_mag) + eps)
        shaped = mag.copy()
        for b in range(n_bins):
            if flat_bands[b]:
                noise_b = noise_mag[b, :n_frames] * noise_scale * strength * 0.5
                shaped[b, :] = mag[b, :] + noise_b
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
            results.append(_vocal_light_noise_floor(y_in[ch], sr, strength))
        return np.stack(results).astype(original_dtype)


def _pink_noise_vocal(n_samples, rng):
    white = rng.randn(n_samples)
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n_samples)
    freqs[0] = 1.0 / n_samples
    fft = fft / np.sqrt(np.maximum(freqs, 1e-12))
    pink = np.fft.irfft(fft, n=n_samples)
    return pink / (np.std(pink) + 1e-12)


def process_vocal_v33(y, sr, params, progress_callback=None, progress_start=0.0, progress_end=1.0):
    strength = params.get("strength", 1.0)
    stages = []
    if params.get("f0_harmonic", 0) > 0:
        stages.append(("f0_harmonic", "f0谐波自然化"))
    if params.get("microtremor_breath", 0) > 0:
        stages.append(("microtremor_breath", "微颤音呼吸"))
    if params.get("transient_protect", 0) > 0:
        stages.append(("transient_protect", "情感瞬态保护"))
    if params.get("de_shimmer", 0) > 0:
        stages.append(("de_shimmer", "去金属感"))
    if params.get("phase_diffuse", 0) > 0:
        stages.append(("phase_diffuse", "相位扩散"))
    if params.get("noise_floor", 0) > 0:
        stages.append(("noise_floor", "噪声地板"))
    n_stages = len(stages)
    for idx, (key, label) in enumerate(stages):
        s = params[key] * strength
        if progress_callback and n_stages > 0:
            p = progress_start + (progress_end - progress_start) * (idx / n_stages)
            progress_callback(p, f"人声{label}...")
        y = _STAGE_MAP[key](y, sr, s)
    if progress_callback:
        progress_callback(progress_end, "人声处理完成")
    return y


_STAGE_MAP = {
    "f0_harmonic": _vocal_f0_harmonic_naturalize,
    "microtremor_breath": _vocal_microtremor_breath,
    "transient_protect": _vocal_emotional_transient_protect,
    "de_shimmer": _vocal_de_shimmer,
    "phase_diffuse": _vocal_light_phase_diffuse,
    "noise_floor": _vocal_light_noise_floor,
}