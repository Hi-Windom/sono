import numpy as np
import soundfile as sf
import gc
from scipy.signal import butter, sosfiltfilt, resample_poly

from services.audio_loader import load_audio_with_fallback
from services.dsp_utils import stft, istft, streaming_spectral_process

MOBILE_WORKING_SR = 48000
N_FFT = 2048
HOP_LENGTH = 512


def _simple_declip(y, amount):
    if amount <= 0:
        return y
    threshold = 0.90
    mask = np.abs(y) > threshold
    if not np.any(mask):
        return y
    masked_vals = y[mask].astype(np.float64)
    abs_masked = np.abs(masked_vals)
    over = abs_masked - threshold
    headroom = 1.0 - threshold
    y[mask] = (np.sign(masked_vals) * (threshold + headroom * np.tanh(over / headroom))).astype(y.dtype)
    return y


def _simple_depop(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _simple_depop(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        diff = np.diff(data)
        abs_diff = np.abs(diff)
        median_diff = np.median(abs_diff)
        if median_diff < 1e-10:
            continue
        threshold_val = median_diff * (80 + 120 * amount)
        pop_mask = np.concatenate(([False], abs_diff > threshold_val))
        if not np.any(pop_mask):
            continue
        indices = np.where(pop_mask)[0]
        for idx in indices:
            if 0 < idx < len(data) - 1:
                prev = data[idx - 1]
                next_val = data[idx + 1]
                actual_diff = data[idx] - prev
                if abs(actual_diff) > threshold_val:
                    clamped = prev + np.sign(actual_diff) * threshold_val
                    data[idx] = 0.5 * (clamped + next_val)
        y[ch] = data.astype(y.dtype)
    return y


def _de_ess(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _de_ess(y, sr, amount)
        return y[0]

    nyq = sr / 2
    low_hz, high_hz = 4000, 8000
    if high_hz >= nyq:
        high_hz = nyq * 0.95
    if low_hz >= high_hz:
        return y

    sos = butter(4, [low_hz/nyq, high_hz/nyq], btype='band', output='sos')
    high_band = sosfiltfilt(sos, y, axis=-1)
    low_band = y.astype(np.float64) - high_band.astype(np.float64)

    gain = 1 - amount * 0.3
    gain = max(gain, 0.1)

    y = (low_band + high_band * gain).astype(y.dtype)
    return y


def _spectral_denoise(y, sr, amount):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _spectral_denoise(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        result = _spectral_denoise_1d(y[ch], sr, amount)
        y[ch] = result
    return y


def _spectral_denoise_1d(data, sr, amount):
    n_samples = len(data)
    use_streaming = n_samples > 5 * 60 * sr

    if use_streaming:
        def _analyze_fn(y_ch, sr_ch):
            chunk_dur = 1.0
            chunk_len = int(sr_ch * chunk_dur)
            n_positions = min(20, max(5, len(y_ch) // chunk_len))
            positions = np.linspace(0, max(0, len(y_ch) - chunk_len), n_positions, dtype=int)
            all_mag = []
            for pos in positions:
                segment = y_ch[pos:pos + chunk_len].astype(np.float64)
                if len(segment) < N_FFT:
                    continue
                S_seg = stft(segment, n_fft=N_FFT, hop_length=HOP_LENGTH)
                all_mag.append(np.abs(S_seg))
            if not all_mag:
                return 0.0
            combined_mag = np.concatenate([m.flatten() for m in all_mag])
            return np.median(combined_mag)

        def _process_fn(S, sr_p, n_fft_p, hop_length_p, global_median):
            magnitude = np.abs(S)
            threshold = global_median * (1 + amount * 3)
            mask = np.ones_like(magnitude)
            below = magnitude < threshold
            mask[below] = magnitude[below] / (threshold + 1e-10)
            denoised_magnitude = magnitude * mask
            return denoised_magnitude * np.exp(1j * np.angle(S))

        y_out = streaming_spectral_process(
            data, sr, _process_fn,
            n_fft=N_FFT, hop_length=HOP_LENGTH,
            analyze_fn=_analyze_fn
        )
        if len(y_out) > n_samples:
            y_out = y_out[:n_samples]
        elif len(y_out) < n_samples:
            y_out = np.pad(y_out, (0, n_samples - len(y_out)))
        return y_out

    S = stft(data, n_fft=N_FFT, hop_length=HOP_LENGTH)
    magnitude = np.abs(S)
    phase = np.angle(S)

    global_median = np.median(magnitude)
    threshold = global_median * (1 + amount * 3)

    mask = np.ones_like(magnitude)
    below = magnitude < threshold
    mask[below] = magnitude[below] / (threshold + 1e-10)

    denoised_magnitude = magnitude * mask
    S_denoised = denoised_magnitude * np.exp(1j * phase)

    y_out = istft(S_denoised, hop_length=HOP_LENGTH, length=n_samples)

    if len(y_out) > n_samples:
        y_out = y_out[:n_samples]
    elif len(y_out) < n_samples:
        y_out = np.pad(y_out, (0, n_samples - len(y_out)))

    return y_out


def _transparent_compress(y, sr, amount):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _transparent_compress(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        global_rms = np.sqrt(np.mean(data ** 2))
        if global_rms < 1e-10:
            continue

        threshold_db = -18.0
        threshold_lin = 10 ** (threshold_db / 20.0)
        ratio = 2.0

        if global_rms <= threshold_lin:
            continue

        target_rms = threshold_lin + (global_rms - threshold_lin) / ratio
        gain = target_rms / global_rms
        y[ch] = (data * gain).astype(y.dtype)

    return y


def _soft_peak_limit(y, threshold=0.9):
    abs_max = np.max(np.abs(y))
    if abs_max <= threshold:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _soft_peak_limit(y, threshold)
        return y[0]

    for ch in range(y.shape[0]):
        abs_data = np.abs(y[ch])
        mask = abs_data > threshold
        if not np.any(mask):
            continue
        headroom = 1.0 - threshold
        y[ch][mask] = (np.sign(y[ch][mask]) * (threshold + headroom * np.tanh((abs_data[mask] - threshold) / headroom))).astype(y.dtype)

    return y


def _loudness_normalize(y, sr, target_lufs=-14.0):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _loudness_normalize(y, sr, target_lufs)
        return y[0]

    for ch in range(y.shape[0]):
        rms_val = np.sqrt(np.mean(y[ch].astype(np.float64)**2))
        if rms_val < 1e-10:
            continue
        target_rms = 10 ** (target_lufs / 20.0)
        gain = target_rms / rms_val
        gain = np.clip(gain, 0.2, 5.0)
        y[ch] = (y[ch].astype(np.float64) * gain).astype(y.dtype)

    return y


def _vocal_ai_repair_adaptive_lite(y, sr, strength):
    if strength <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_ai_repair_adaptive_lite(y, sr, strength)
        return y[0]

    lite_n_fft = 1024
    lite_hop_length = 256

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        n_samples = len(data)
        S = stft(data, n_fft=lite_n_fft, hop_length=lite_hop_length)
        magnitude = np.abs(S)
        phase = np.angle(S)

        noise_floor = np.median(magnitude, axis=1, keepdims=True)
        noise_floor_smoothed = np.zeros_like(noise_floor)
        noise_floor_smoothed[0] = noise_floor[0]
        for f in range(1, len(noise_floor)):
            noise_floor_smoothed[f] = 0.9 * noise_floor_smoothed[f-1] + 0.1 * noise_floor[f]
        noise_floor = noise_floor_smoothed

        n_freqs = magnitude.shape[0]
        split_bin = int(n_freqs * 4000 / (sr / 2))
        split_bin = max(1, min(split_bin, n_freqs - 1))

        threshold = np.zeros_like(magnitude)
        threshold[:split_bin] = noise_floor[:split_bin] * (1 + strength * 2.0)
        threshold[split_bin:] = noise_floor[split_bin:] * (1 + strength * 3.5)

        mask = np.ones_like(magnitude)
        below = magnitude < threshold
        mask[below] = magnitude[below] / (threshold[below] + 1e-10)
        mask = np.maximum(mask, 1.0 - strength * 0.3)

        S_processed = (magnitude * mask) * np.exp(1j * phase)
        y_out = istft(S_processed, hop_length=lite_hop_length, length=n_samples)

        if len(y_out) > n_samples:
            y_out = y_out[:n_samples]
        elif len(y_out) < n_samples:
            y_out = np.pad(y_out, (0, n_samples - len(y_out)))

        y[ch] = y_out.astype(y.dtype)

    return y


def _vocal_exciter_lite(y, sr, amount):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_exciter_lite(y, sr, amount)
        return y[0]

    nyq = sr / 2
    crossover = min(2000, nyq * 0.9)
    sos_low = butter(2, crossover / nyq, btype='low', output='sos')
    sos_high = butter(2, crossover / nyq, btype='high', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        low_band = sosfiltfilt(sos_low, data)
        high_band = sosfiltfilt(sos_high, data)

        drive = 1.0 + amount * 2.0
        harmonic_2nd = np.tanh(high_band * drive) * 0.5
        harmonic_3rd = np.tanh(high_band * drive * 0.5)

        harmonic_mix = harmonic_2nd * 0.6 + harmonic_3rd * 0.4

        mix = amount * 0.4
        high_out = high_band * (1 - mix) + harmonic_mix * mix
        y[ch] = (low_band + high_out).astype(y.dtype)

    return y


def _vocal_smart_compressor_lite(y, sr, amount):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_smart_compressor_lite(y, sr, amount)
        return y[0]

    threshold = 0.3 + (1 - amount) * 0.4
    ratio = 1.0 + amount * 3.0

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        abs_data = np.abs(data)
        peak_env = np.maximum(abs_data, 0.001)

        db = 20 * np.log10(peak_env)
        db_thresh = 20 * np.log10(threshold)

        gain_db = np.zeros_like(db)
        above_thresh = db > db_thresh
        gain_db[above_thresh] = (db_thresh - db[above_thresh]) * (1 - 1 / ratio)

        gain_linear = 10 ** (gain_db / 20.0)

        release_gamma = 0.2 - (0.2 - 0.01) * amount
        env = np.ones_like(gain_linear)
        env[0] = gain_linear[0]
        for i in range(1, len(gain_linear)):
            if gain_linear[i] < env[i-1]:
                env[i] = (1 - release_gamma) * env[i-1] + release_gamma * gain_linear[i]
            else:
                env[i] = gain_linear[i]

        y[ch] = (data * env).astype(y.dtype)

    return y


def _transient_aware_process_lite(y, sr, amount):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        result = _transient_aware_process_lite(y, sr, amount)
        return result[0]

    frame_len = HOP_LENGTH
    n_samples = y.shape[1]
    n_frames = n_samples // frame_len
    if n_frames < 3:
        return y

    transient_mask = np.zeros(n_frames, dtype=bool)

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        frame_energy = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * frame_len
            end = min(start + frame_len, n_samples)
            frame = data[start:end]
            frame_energy[i] = np.sqrt(np.mean(frame ** 2))

        energy_diff = np.abs(np.diff(frame_energy))
        for i in range(1, n_frames - 1):
            prev_energy = max(frame_energy[i-1], 1e-10)
            if frame_energy[i] > prev_energy * 3.0:
                transient_mask[i] = True

    if not np.any(transient_mask):
        return y

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        for i in range(n_frames):
            if transient_mask[i]:
                start = i * frame_len
                end = min(start + frame_len, n_samples)
                gain = 1.0 - amount * 0.3
                data[start:end] *= gain
        y[ch] = data.astype(y.dtype)

    return y


def _resonance_suppress_lite(y, sr, amount):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _resonance_suppress_lite(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        n_samples = len(data)
        S = stft(data, n_fft=N_FFT, hop_length=HOP_LENGTH)
        magnitude = np.abs(S)
        phase = np.angle(S)

        n_bins = magnitude.shape[0]
        gain_mask = np.ones_like(magnitude)

        for f in range(1, n_bins - 1):
            neighbor_mean = (magnitude[f-1, :] + magnitude[f+1, :]) * 0.5
            resonance = magnitude[f, :] > neighbor_mean * 3.0
            if np.any(resonance):
                reduction = 1.0 - amount * 0.5
                gain_mask[f, resonance] = reduction

        S_processed = (magnitude * gain_mask) * np.exp(1j * phase)
        y_out = istft(S_processed, hop_length=HOP_LENGTH, length=n_samples)

        if len(y_out) > n_samples:
            y_out = y_out[:n_samples]
        elif len(y_out) < n_samples:
            y_out = np.pad(y_out, (0, n_samples - len(y_out)))

        y[ch] = y_out.astype(y.dtype)

    return y


def _mastering_standard_lite(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_standard_lite(y, sr)
        return y[0]

    nyq = sr / 2

    sos_low = butter(2, 60 / nyq, btype='high', output='sos')
    sos_presence = butter(2, [3000 / nyq, 4000 / nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        data = sosfiltfilt(sos_low, data)

        presence = sosfiltfilt(sos_presence, data)
        data = data + presence * 0.10

        rms = np.sqrt(np.mean(data ** 2))
        if rms > 1e-10:
            target = 0.12
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain

        y[ch] = data.astype(y.dtype)

    return _soft_peak_limit(y, threshold=0.95)


def _mastering_powerful_lite(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_powerful_lite(y, sr)
        return y[0]

    nyq = sr / 2

    sos_low = butter(2, 40 / nyq, btype='high', output='sos')
    sos_bass = butter(2, 150 / nyq, btype='low', output='sos')
    sos_presence = butter(2, [2500 / nyq, 6000 / nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        data = sosfiltfilt(sos_low, data)

        bass = sosfiltfilt(sos_bass, data)
        data = data + bass * 0.3

        presence = sosfiltfilt(sos_presence, data)
        data = data + presence * 0.2

        rms = np.sqrt(np.mean(data ** 2))
        if rms > 1e-10:
            target = 0.18
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain

        y[ch] = data.astype(y.dtype)

    return _soft_peak_limit(y, threshold=0.92)


def _mastering_warm_lite(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_warm_lite(y, sr)
        return y[0]

    nyq = sr / 2

    sos_low = butter(2, 30 / nyq, btype='high', output='sos')
    sos_warm = butter(2, 800 / nyq, btype='low', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        data = sosfiltfilt(sos_low, data)

        warm = sosfiltfilt(sos_warm, data)
        data = data + warm * 0.25

        rms = np.sqrt(np.mean(data ** 2))
        if rms > 1e-10:
            target = 0.14
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain

        y[ch] = data.astype(y.dtype)

    return _soft_peak_limit(y, threshold=0.95)


def _mastering_adaptive_lite(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_adaptive_lite(y, sr)
        return y[0]

    nyq = sr / 2
    low_cross = min(300, nyq * 0.9)
    sos_low = butter(2, low_cross / nyq, btype='low', output='sos')
    sos_high = butter(2, low_cross / nyq, btype='high', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        low_band = sosfiltfilt(sos_low, data)
        high_band = sosfiltfilt(sos_high, data)

        low_energy = np.sqrt(np.mean(low_band ** 2) + 1e-10)
        high_energy = np.sqrt(np.mean(high_band ** 2) + 1e-10)
        total_energy = low_energy + high_energy
        low_ratio = low_energy / total_energy

        if low_ratio < 0.2:
            boost = 1.0 + (0.2 - low_ratio) * 0.5
            data = low_band * boost + high_band
        elif low_ratio > 0.5:
            cut = 1.0 - (low_ratio - 0.5) * 0.3
            data = low_band * cut + high_band
        else:
            data = low_band + high_band

        rms = np.sqrt(np.mean(data ** 2))
        if rms > 1e-10:
            target = 0.14
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain

        y[ch] = data.astype(y.dtype)

    return _soft_peak_limit(y, threshold=0.95)


def _apply_bass_enhance_lite(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _apply_bass_enhance_lite(y, sr, amount)
        return y[0]

    nyq = sr / 2
    low_cut = min(250, nyq * 0.9)
    sos_low = butter(4, low_cut / nyq, btype='low', output='sos')

    for ch in range(y.shape[0]):
        low_band = sosfiltfilt(sos_low, y[ch].astype(np.float64))
        half_len = len(low_band) // 2
        averaged = (low_band[0::2][:half_len] + low_band[1::2][:half_len]) * 0.5
        x_short = np.linspace(0, 1, len(averaged))
        x_long = np.linspace(0, 1, len(low_band))
        sub_harmonic = np.interp(x_long, x_short, averaged)
        sub_harmonic = sosfiltfilt(sos_low, sub_harmonic)
        y[ch] = (y[ch].astype(np.float64) + sub_harmonic * amount * 0.15).astype(y.dtype)

    return y


def _apply_air_texture_lite(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _apply_air_texture_lite(y, sr, amount)
        return y[0]

    nyq = sr / 2
    high_cut = min(16000, nyq * 0.95)
    sos_high = butter(4, [8000/nyq, high_cut/nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        high_band = sosfiltfilt(sos_high, y[ch].astype(np.float64))
        high_rms = np.sqrt(np.mean(high_band**2))
        if high_rms > 1e-6:
            noise_level = high_rms * 0.05 * amount
            noise = np.random.randn(len(high_band)) * noise_level
            y[ch] = (y[ch].astype(np.float64) + noise * amount * 0.1).astype(y.dtype)

    return y


def process_vocal_track(y, sr, params):
    speed = params.get('speed', 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)
    if params.get("declip", 0) > 0:
        y = _simple_declip(y, params["declip"])

    if params.get("depop", 0) > 0:
        y = _simple_depop(y, sr, params["depop"])

    if params.get("de_ess", 0) > 0:
        y = _de_ess(y, sr, params["de_ess"])

    if params.get("ai_repair", 0) > 0:
        from services.repair.repair_v2_3a.core import _spectral_denoise
        try:
            y = _spectral_denoise(y, sr, params["ai_repair"])
        except Exception:
            pass

    if params.get("ai_repair_adaptive_lite", 0) > 0:
        y = _vocal_ai_repair_adaptive_lite(y, sr, params["ai_repair_adaptive_lite"])

    if params.get("exciter", 0) > 0:
        y = _vocal_exciter_lite(y, sr, params["exciter"])

    if params.get("compressor", 0) > 0:
        y = _vocal_smart_compressor_lite(y, sr, params["compressor"])

    if params.get("transient", 0) > 0:
        y = _transient_aware_process_lite(y, sr, params["transient"])

    if params.get("resonance", 0) > 0:
        y = _resonance_suppress_lite(y, sr, params["resonance"])

    if params.get("bass_enhance", 0) > 0:
        y = _apply_bass_enhance_lite(y, sr, params["bass_enhance"])

    if params.get("air_texture", 0) > 0:
        y = _apply_air_texture_lite(y, sr, params["air_texture"])

    if params.get("loudness", 0) > 0:
        y = _loudness_normalize(y, sr, -14.0)

    y = _soft_peak_limit(y, threshold=0.9)
    return y


def process_instrument_track(y, sr, params):
    speed = params.get('speed', 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)
    if params.get("declip", 0) > 0:
        y = _simple_declip(y, params["declip"])

    if params.get("depop", 0) > 0:
        y = _simple_depop(y, sr, params["depop"])

    if params.get("noise_reduction", 0) > 0:
        y = _spectral_denoise(y, sr, params["noise_reduction"])

    if params.get("dynamic", 0) > 0:
        y = _transparent_compress(y, sr, params["dynamic"])

    if params.get("loudness", 0) > 0:
        y = _loudness_normalize(y, sr, -14.0)

    y = _soft_peak_limit(y, threshold=0.9)
    return y


def mix_tracks(vocal, accompaniment, vocal_ratio=1.0, accompaniment_ratio=1.0):
    if vocal.ndim == 1:
        vocal = vocal.reshape(1, -1)
    if accompaniment.ndim == 1:
        accompaniment = accompaniment.reshape(1, -1)

    min_len = min(vocal.shape[1], accompaniment.shape[1])
    vocal = vocal[:, :min_len]
    accompaniment = accompaniment[:, :min_len]

    if vocal.shape[0] != accompaniment.shape[0]:
        if vocal.shape[0] == 1 and accompaniment.shape[0] == 2:
            vocal = np.repeat(vocal, 2, axis=0)
        elif vocal.shape[0] == 2 and accompaniment.shape[0] == 1:
            accompaniment = np.repeat(accompaniment, 2, axis=0)

    mixed = vocal * vocal_ratio + accompaniment * accompaniment_ratio
    peak = np.max(np.abs(mixed))
    if peak > 0.99:
        mixed *= 0.99 / peak

    return mixed


def _repair_single_track(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    if progress_callback:
        progress_callback(0.05, "v3.2a 加载音频...")

    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)
    issues_found = ["单轨处理"]

    working_sr = MOBILE_WORKING_SR

    from services.memory_guard import check_memory_before_repair, should_use_float32
    working_sr = check_memory_before_repair(
        n_samples=y.shape[1],
        n_channels=y.shape[0],
        sr=sr,
        working_sr=working_sr,
        algorithm_version="v3.2a",
    )

    if should_use_float32(y.shape[1], y.shape[0]):
        y = y.astype(np.float32)

    if sr != working_sr:
        target_len = int(y.shape[1] * working_sr / sr)
        new_y = np.zeros((y.shape[0], target_len), dtype=y.dtype)
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            copy_len = min(target_len, len(resampled))
            new_y[ch, :copy_len] = resampled[:copy_len]
        y = new_y
        sr = working_sr

    gc.collect()

    single_params = dict(params)
    _SINGLE_KEY_MAP = {
        "de_clipping": "declip", "de_pop": "depop", "de_essing": "de_ess",
        "dynamic_range": "dynamic", "spatial_enhance": "spatial",
        "loudness_optimize": "loudness",
    }
    for _sk, _dk in _SINGLE_KEY_MAP.items():
        if _sk in single_params and _dk not in single_params:
            single_params[_dk] = single_params[_sk]

    if progress_callback:
        progress_callback(0.10, "v3.2a 处理音频...")

    if single_params.get("declip", 0) > 0:
        y = _simple_declip(y, single_params["declip"])

    if single_params.get("depop", 0) > 0:
        y = _simple_depop(y, sr, single_params["depop"])

    if single_params.get("de_ess", 0) > 0:
        y = _de_ess(y, sr, single_params["de_ess"])

    if single_params.get("noise_reduction", 0) > 0:
        y = _spectral_denoise(y, sr, single_params["noise_reduction"])

    if single_params.get("ai_repair", 0) > 0:
        from services.repair.repair_v2_3a.core import _spectral_denoise as _ai_denoise
        try:
            y = _ai_denoise(y, sr, single_params["ai_repair"])
        except Exception:
            pass

    if single_params.get("ai_repair_adaptive_lite", 0) > 0:
        y = _vocal_ai_repair_adaptive_lite(y, sr, single_params["ai_repair_adaptive_lite"])

    if single_params.get("exciter", 0) > 0:
        y = _vocal_exciter_lite(y, sr, single_params["exciter"])

    if single_params.get("compressor", 0) > 0:
        y = _vocal_smart_compressor_lite(y, sr, single_params["compressor"])

    if single_params.get("transient", 0) > 0:
        y = _transient_aware_process_lite(y, sr, single_params["transient"])

    if single_params.get("resonance", 0) > 0:
        y = _resonance_suppress_lite(y, sr, single_params["resonance"])

    if single_params.get("bass_enhance", 0) > 0:
        y = _apply_bass_enhance_lite(y, sr, single_params["bass_enhance"])

    if single_params.get("air_texture", 0) > 0:
        y = _apply_air_texture_lite(y, sr, single_params["air_texture"])

    if single_params.get("dynamic", 0) > 0:
        y = _transparent_compress(y, sr, single_params["dynamic"])

    if single_params.get("loudness", 0) > 0:
        y = _loudness_normalize(y, sr, -14.0)

    mastering_style = single_params.get("mastering_style", "none")
    if mastering_style == "standard":
        if progress_callback:
            progress_callback(0.80, "v3.2a 标准母带...")
        y = _mastering_standard_lite(y, working_sr)
        issues_found.append("标准母带")
    elif mastering_style == "powerful":
        if progress_callback:
            progress_callback(0.80, "v3.2a 强劲母带...")
        y = _mastering_powerful_lite(y, working_sr)
        issues_found.append("强劲母带")
    elif mastering_style == "warm":
        if progress_callback:
            progress_callback(0.80, "v3.2a 温暖母带...")
        y = _mastering_warm_lite(y, working_sr)
        issues_found.append("温暖母带")
    elif mastering_style == "adaptive":
        if progress_callback:
            progress_callback(0.80, "v3.2a 自适应母带...")
        y = _mastering_adaptive_lite(y, working_sr)
        issues_found.append("自适应母带")

    if progress_callback:
        progress_callback(0.90, "v3.2a 导出...")

    y = _soft_peak_limit(y, threshold=0.9)

    bit_depth = single_params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if y.dtype == np.float32:
        y = y.astype(np.float64)

    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)

    channels = y.shape[0] if y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, "v3.2a 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.2a",
        "processing_mode": "single",
    }


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    processing_mode = params.get("processing_mode", "single")

    if processing_mode == "single":
        return _repair_single_track(input_path, output_path, params, progress_callback)

    vocal_path = params.get("vocal_path", input_path)
    accompaniment_path = params.get("accompaniment_path", input_path)

    if progress_callback:
        progress_callback(0.05, "v3.2a 加载人声轨...")

    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    if vocal_y.ndim == 1:
        vocal_y = vocal_y.reshape(1, -1)

    if progress_callback:
        progress_callback(0.10, "v3.2a 加载伴奏轨...")

    accompaniment_y, accompaniment_sr = load_audio_with_fallback(accompaniment_path, sr=None, mono=False)
    if accompaniment_y.ndim == 1:
        accompaniment_y = accompaniment_y.reshape(1, -1)

    original_duration = round(max(vocal_y.shape[1] / vocal_sr, accompaniment_y.shape[1] / accompaniment_sr), 2)
    issues_found = ["双轨处理"]

    working_sr = MOBILE_WORKING_SR

    from services.memory_guard import check_memory_before_repair, should_use_float32
    vocal_samples = vocal_y.shape[1]
    vocal_channels = vocal_y.shape[0]
    working_sr = check_memory_before_repair(
        n_samples=vocal_samples,
        n_channels=vocal_channels,
        sr=vocal_sr,
        working_sr=working_sr,
        algorithm_version="v3.2a",
    )

    if should_use_float32(vocal_samples, vocal_channels):
        vocal_y = vocal_y.astype(np.float32)
        accompaniment_y = accompaniment_y.astype(np.float32)

    if vocal_sr != working_sr:
        target_len = int(vocal_y.shape[1] * working_sr / vocal_sr)
        new_vocal_y = np.zeros((vocal_y.shape[0], target_len), dtype=vocal_y.dtype)
        for ch in range(vocal_y.shape[0]):
            resampled = resample_poly(vocal_y[ch], working_sr, vocal_sr)
            copy_len = min(target_len, len(resampled))
            new_vocal_y[ch, :copy_len] = resampled[:copy_len]
        vocal_y = new_vocal_y
        vocal_sr = working_sr

    if accompaniment_sr != working_sr:
        target_len = int(accompaniment_y.shape[1] * working_sr / accompaniment_sr)
        new_acc_y = np.zeros((accompaniment_y.shape[0], target_len), dtype=accompaniment_y.dtype)
        for ch in range(accompaniment_y.shape[0]):
            resampled = resample_poly(accompaniment_y[ch], working_sr, accompaniment_sr)
            copy_len = min(target_len, len(resampled))
            new_acc_y[ch, :copy_len] = resampled[:copy_len]
        accompaniment_y = new_acc_y
        accompaniment_sr = working_sr

    gc.collect()

    vocal_params = params.get("vocal_params", {}).copy()
    inst_params = params.get("inst_params", {}).copy()

    for shared_key in ("speed",):
        if shared_key in params:
            vocal_params[shared_key] = params[shared_key]
            inst_params[shared_key] = params[shared_key]

    if progress_callback:
        progress_callback(0.20, "v3.2a 处理人声轨...")

    vocal_y = process_vocal_track(vocal_y, vocal_sr, vocal_params)
    issues_found.append("人声处理完成")

    if progress_callback:
        progress_callback(0.50, "v3.2a 处理伴奏轨...")

    accompaniment_y = process_instrument_track(accompaniment_y, accompaniment_sr, inst_params)
    issues_found.append("伴奏处理完成")

    gc.collect()

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if progress_callback:
        progress_callback(0.70, "v3.2a 保存人声修复结果...")

    vocal_output_path = params.get("vocal_output_path")
    if vocal_output_path:
        vocal_out = _soft_peak_limit(vocal_y, threshold=0.9)
        if vocal_out.dtype == np.float32:
            vocal_out = vocal_out.astype(np.float64)
        sf.write(vocal_output_path, vocal_out.T if vocal_out.ndim > 1 else vocal_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.75, "v3.2a 保存伴奏修复结果...")

    accompaniment_output_path = params.get("accompaniment_output_path")
    if accompaniment_output_path:
        acc_out = _soft_peak_limit(accompaniment_y, threshold=0.9)
        if acc_out.dtype == np.float32:
            acc_out = acc_out.astype(np.float64)
        sf.write(accompaniment_output_path, acc_out.T if acc_out.ndim > 1 else acc_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.80, "v3.2a 混音...")

    vocal_ratio = params.get("vocal_ratio", 1.0)
    accompaniment_ratio = params.get("accompaniment_ratio", 1.0)
    mixed = mix_tracks(vocal_y, accompaniment_y, vocal_ratio, accompaniment_ratio)

    issues_found.append("混音完成")

    mastering_style = params.get("mastering_style", "none")
    if mastering_style == "standard":
        if progress_callback:
            progress_callback(0.85, "v3.2a 标准母带...")
        mixed = _mastering_standard_lite(mixed, working_sr)
        issues_found.append("标准母带")
    elif mastering_style == "powerful":
        if progress_callback:
            progress_callback(0.85, "v3.2a 强劲母带...")
        mixed = _mastering_powerful_lite(mixed, working_sr)
        issues_found.append("强劲母带")
    elif mastering_style == "warm":
        if progress_callback:
            progress_callback(0.85, "v3.2a 温暖母带...")
        mixed = _mastering_warm_lite(mixed, working_sr)
        issues_found.append("温暖母带")
    elif mastering_style == "adaptive":
        if progress_callback:
            progress_callback(0.85, "v3.2a 自适应母带...")
        mixed = _mastering_adaptive_lite(mixed, working_sr)
        issues_found.append("自适应母带")

    if progress_callback:
        progress_callback(0.90, "v3.2a 导出...")

    mixed = _soft_peak_limit(mixed, threshold=0.9)

    if mixed.dtype == np.float32:
        mixed = mixed.astype(np.float64)

    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v3.2a 修复完成")

    result = {
        "issues_found": issues_found,
        "original_sample_rate": vocal_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": mixed.shape[0] if mixed.ndim > 1 else 1,
        "algorithm_version": "v3.2a",
        "processing_mode": "dual",
    }
    if vocal_output_path:
        result["vocal_output_path"] = vocal_output_path
    if accompaniment_output_path:
        result["accompaniment_output_path"] = accompaniment_output_path
    return result