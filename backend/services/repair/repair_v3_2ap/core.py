import numpy as np
from scipy import signal
from scipy.signal import butter, sosfiltfilt
from ..repair_v3_2a.core import *
from ..repair_v3_2a.core import repair_audio as _v3_2a_repair_audio
from ..repair_v3_2a.core import process_vocal_track as _v3_2a_process_vocal_track
from ..repair_v3_2a.core import process_instrument_track as _v3_2a_process_instrument_track
from ..repair_v3_2a.core import _repair_single_track as _v3_2a_repair_single_track
from ..repair_v3_2a.core import mix_tracks as _v3_2a_mix_tracks

MOBILE_WORKING_SR = 48000
N_FFT = 4096
HOP_LENGTH = 1024


def _lookahead_compressor_lite(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _lookahead_compressor_lite(y, sr, amount)
        return y[0]

    lookahead_ms = 10
    lookahead_samples = int(0.001 * lookahead_ms * sr)
    if lookahead_samples < 1:
        from ..repair_v3_2a.core import _vocal_smart_compressor_lite
        return _vocal_smart_compressor_lite(y, sr, amount)

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        shifted = np.pad(data, (lookahead_samples, 0))[:-lookahead_samples]
        window_size = int(0.01 * sr)
        env = np.zeros_like(data)
        for i in range(len(data)):
            start = max(0, i - window_size)
            chunk = shifted[start:i + 1]
            rms = np.sqrt(np.mean(chunk ** 2) + 1e-10)
            peak = np.abs(shifted[i])
            env[i] = 0.6 * rms + 0.4 * peak

        threshold = np.median(np.abs(data)) * 2.0
        ratio = 4.0
        knee = 6.0
        gain = np.ones_like(data)

        for i in range(len(data)):
            e = env[i]
            if e > threshold - knee / 2:
                if e < threshold + knee / 2:
                    g = 1.0 - (1.0 / ratio) * ((e - threshold + knee / 2) / knee) ** 2
                else:
                    g = 1.0 - (1.0 - 1.0 / ratio) * (1.0 - (threshold - knee / 2) / e)
                gain[i] = 1.0 - (1.0 - g) * amount

        y[ch] = (data * gain).astype(y.dtype)

    return y


def _vocal_ai_repair_adaptive_lite(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_ai_repair_adaptive_lite(y, sr, strength)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        n_samples = len(data)
        S = stft(data, n_fft=N_FFT, hop_length=HOP_LENGTH)
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
        y_out = istft(S_processed, hop_length=HOP_LENGTH, length=n_samples)

        if len(y_out) > n_samples:
            y_out = y_out[:n_samples]
        elif len(y_out) < n_samples:
            y_out = np.pad(y_out, (0, n_samples - len(y_out)))

        y[ch] = y_out.astype(y.dtype)

    return y


def _vocal_spatial_lite_enhanced(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_spatial_lite_enhanced(y, sr, amount)
        return y[0]

    tap_ms = [50, 75, 100]
    tap_gains = [0.4, 0.3, 0.2]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        early = np.zeros_like(data)
        for ms, gain in zip(tap_ms, tap_gains):
            delay = int(ms * sr / 1000)
            if delay < len(data):
                early[delay:] += gain * data[:-delay]

        fb_len = int(0.1 * sr)
        fb = np.zeros(fb_len)
        for i in range(1, fb_len):
            fb[i] = 0.5 * fb[i-1] + 0.3 * data[min(i, len(data) - 1)]
        reverb_tail = np.zeros_like(data)
        reverb_tail[:fb_len] = fb * 0.2

        y_spatial = data + early * 0.5 + reverb_tail * 0.3
        y_spatial = data * (1 - amount * 0.3) + y_spatial * (amount * 0.3)
        y[ch] = np.clip(y_spatial, -1, 1).astype(y.dtype)

    return y


def _resonance_suppress_enhanced_lite(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _resonance_suppress_enhanced_lite(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        n_samples = len(data)
        S = stft(data, n_fft=N_FFT, hop_length=HOP_LENGTH)
        magnitude = np.abs(S)
        phase = np.angle(S)

        n_bins = magnitude.shape[0]
        gain = np.ones_like(magnitude)

        for i in range(magnitude.shape[1]):
            for j in range(2, n_bins - 2):
                neighbors = magnitude[j-2:j+3, i]
                median_val = np.median(neighbors)
                if magnitude[j, i] > median_val * 2.5 and median_val > 1e-10:
                    reduction = 1.0 - amount * 0.6 * (1.0 - median_val / (magnitude[j, i] + 1e-10))
                    gain[j, i] = max(reduction, 0.25)

        alpha = 0.3
        gain_smooth = np.zeros_like(gain)
        gain_smooth[:, 0] = gain[:, 0]
        for i in range(1, gain.shape[1]):
            gain_smooth[:, i] = alpha * gain_smooth[:, i-1] + (1 - alpha) * gain[:, i]

        S_processed = S * gain_smooth
        y_out = istft(S_processed, hop_length=HOP_LENGTH, length=n_samples)
        y_out = np.clip(y_out, -1, 1)
        y[ch] = (data * (1 - amount * 0.35) + y_out * (amount * 0.35)).astype(y.dtype)

    return y


def _vocal_multiband_compressor_lite(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_multiband_compressor_lite(y, sr, amount)
        return y[0]

    nyq = sr / 2
    crossover1 = min(300, nyq * 0.9)
    crossover2 = min(2000, nyq * 0.9)

    sos_low = butter(4, crossover1 / nyq, btype='low', output='sos')
    sos_mid_bp = butter(4, [crossover1 / nyq, crossover2 / nyq], btype='band', output='sos')
    sos_high = butter(4, crossover2 / nyq, btype='high', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        low_band = sosfiltfilt(sos_low, data)
        mid_band = sosfiltfilt(sos_mid_bp, data)
        high_band = sosfiltfilt(sos_high, data)

        for band, ratio, thresh_mult in [(low_band, 3.0, 1.5), (mid_band, 4.0, 2.0), (high_band, 2.5, 1.8)]:
            if np.max(np.abs(band)) < 1e-10:
                continue
            threshold = np.median(np.abs(band)) * thresh_mult
            if threshold < 1e-10:
                continue

            env = np.zeros_like(band)
            window = int(0.01 * sr)
            for i in range(len(band)):
                start = max(0, i - window)
                chunk = band[start:i+1]
                env[i] = np.sqrt(np.mean(chunk ** 2) + 1e-10)

            gain = np.ones_like(band)
            for i in range(len(band)):
                e = env[i]
                if e > threshold:
                    db_over = 20 * np.log10(e / threshold + 1e-10)
                    g_db = -db_over * (1 - 1 / ratio)
                    g = 10 ** (g_db / 20.0)
                    gain[i] = 1.0 - (1.0 - g) * amount

            band[:] *= gain

        y_out = low_band + mid_band + high_band
        y[ch] = y_out.astype(y.dtype)

    return y


def process_vocal_track(y, sr, params):
    speed = params.get('speed', 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)
    amount = params.get('amount', 1.0)
    y = y.copy().astype(np.float64)
    y = _simple_declip(y, amount * params.get('declip', 0.5))
    y = _simple_depop(y, sr, amount * params.get('depop', 0.5))
    y = _de_ess(y, sr, amount * params.get('de_ess', 0.5))
    y = _vocal_ai_repair_adaptive_lite(y, sr, amount * params.get('ai_repair_adaptive_lite', 0.5))
    y = _resonance_suppress_enhanced_lite(y, sr, amount * params.get('resonance_suppress', 0.3))
    y = _vocal_exciter_lite(y, sr, amount * params.get('exciter_improved', 0.3))
    y = _lookahead_compressor_lite(y, sr, amount * params.get('smart_compressor', 0.5))
    y = _vocal_multiband_compressor_lite(y, sr, amount * params.get('multiband_compressor', 0.3))
    y = _transient_aware_process_lite(y, sr, amount * params.get('transient_aware', 0.3))
    y = _apply_bass_enhance_lite(y, sr, amount * params.get('bass_enhance', 0.3))
    y = _apply_air_texture_lite(y, sr, amount * params.get('air_texture', 0.3))
    y = _vocal_spatial_lite_enhanced(y, sr, amount * params.get('vocal_spatial', 0.3))
    y = _transparent_compress(y, sr, amount * params.get('compressor', 0.3))
    y = _loudness_normalize(y, sr)
    y = _soft_peak_limit(y)
    return np.clip(y, -1, 1)


def process_instrument_track(y, sr, params):
    return _v3_2a_process_instrument_track(y, sr, params)


def mix_tracks(vocal, accompaniment, vocal_ratio=1.0, accompaniment_ratio=1.0):
    return _v3_2a_mix_tracks(vocal, accompaniment, vocal_ratio, accompaniment_ratio)


def _repair_single_track(input_path, output_path, params, progress_callback=None):
    return _v3_2a_repair_single_track(input_path, output_path, params, progress_callback)


def repair_audio(input_path, output_path, params, progress_callback=None):
    return _v3_2a_repair_audio(input_path, output_path, params, progress_callback)
