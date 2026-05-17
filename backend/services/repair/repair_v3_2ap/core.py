import numpy as np
from scipy import signal
from scipy.signal import butter, sosfiltfilt

from ..repair_v3_2a.core import (
    _simple_declip, _simple_depop, _de_ess, _spectral_denoise,
    _transient_aware_process_lite, _apply_bass_enhance_lite,
    _apply_air_texture_lite, _transparent_compress, _loudness_normalize,
    _soft_peak_limit, _resonance_suppress_lite, _vocal_exciter_lite,
    _vocal_smart_compressor_lite, load_audio_with_fallback,
    resample_poly, stft, istft, sf, gc,
)
from ..repair_v3_2a.core import repair_audio as _v3_2a_repair_audio
from ..repair_v3_2a.core import process_vocal_track as _v3_2a_process_vocal_track
from ..repair_v3_2a.core import process_instrument_track as _v3_2a_process_instrument_track
from ..repair_v3_2a.core import _repair_single_track as _v3_2a_repair_single_track
from ..repair_v3_2a.core import mix_tracks as _v3_2a_mix_tracks

MOBILE_WORKING_SR = 48000
N_FFT = 4096
HOP_LENGTH = 1024


def _soft_clip_saturation(y, threshold=0.9, drive=1.1):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _soft_clip_saturation(y, threshold, drive)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        scaled = data * drive
        clipped = np.tanh(scaled / threshold) * threshold
        y[ch] = clipped.astype(y.dtype)

    return y


def _analog_tape_warmth(y, sr, amount=0.3):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _analog_tape_warmth(y, sr, amount)
        return y[0]

    nyq = sr / 2

    sos_low = butter(4, 100 / nyq, btype='low', output='sos')
    sos_high = butter(4, 2000 / nyq, btype='high', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)

        low_band = sosfiltfilt(sos_low, data)
        high_band = sosfiltfilt(sos_high, data)

        harmonics_2nd = np.sin(low_band * 2 * np.pi * 0.5)
        harmonics_3rd = np.sin(low_band * 3 * np.pi * 0.3)

        saturation = np.tanh(low_band * (1 + amount * 2)) * amount * 0.15

        processed = data + saturation + harmonics_2nd * amount * 0.02 + harmonics_3rd * amount * 0.01

        high_boost = 1.0 + amount * 0.05
        processed = processed + high_band * (high_boost - 1)

        y[ch] = processed.astype(y.dtype)

    return y


def _tube_emulator(y, sr, amount=0.4):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _tube_emulator(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)

        drive = 1.0 + amount * 1.5

        positive = np.where(data > 0, np.tanh(data * drive) / np.tanh(drive), data * 1.05)

        harmonics = positive * (1 + np.sin(np.arange(len(data)) * 0.001 * amount) * amount * 0.02)

        warmth = np.tanh(data * 0.5) * amount * 0.1

        processed = harmonics + warmth

        y[ch] = processed.astype(y.dtype)

    return y


def _spatial_image_enhancer(y, sr, amount=0.3):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _spatial_image_enhancer(y, sr, amount)
        return y[0]

    if y.shape[0] < 2:
        return y

    for ch in range(y.shape[0]):
        y[ch] = y[ch].astype(np.float64)

    left = y[0]
    right = y[1]

    mid = (left + right) * 0.5
    side = (left - right) * 0.5

    width_boost = 1.0 + amount * 0.4
    enhanced_side = side * width_boost

    delay_ms = int(amount * 5)
    if delay_ms > 0 and delay_ms < len(left):
        left_delay = np.zeros_like(left)
        right_delay = np.zeros_like(right)
        left_delay[delay_ms:] = left[:-delay_ms]
        right_delay[:-delay_ms] = right[delay_ms:]

        left = (left * 0.5 + left_delay * 0.3)
        right = (right * 0.5 + right_delay * 0.3)

    new_left = mid + enhanced_side * 0.9
    new_right = mid - enhanced_side * 0.9

    correlation_bonus = amount * 0.1
    new_left = new_left * (1 + correlation_bonus)
    new_right = new_right * (1 + correlation_bonus)

    peak = max(np.max(np.abs(new_left)), np.max(np.abs(new_right)))
    if peak > 0.99:
        norm = 0.99 / peak
        new_left *= norm
        new_right *= norm

    y[0] = new_left.astype(y.dtype)
    y[1] = new_right.astype(y.dtype)

    return y


def _high_freq_smoother(y, sr, amount=0.3):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _high_freq_smoother(y, sr, amount)
        return y[0]

    nyq = sr / 2
    sos_high = butter(2, 6000 / nyq, btype='high', output='sos')
    sos_air = butter(2, [8000 / nyq, min(16000, nyq * 0.95) / nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)

        high_band = sosfiltfilt(sos_high, data)
        air_band = sosfiltfilt(sos_air, data)

        air_smoothed = np.tanh(air_band * 2) * 0.9 + air_band * 0.1

        air_amount = amount * 0.15
        processed = data + air_smoothed * air_amount

        bright_amount = amount * 0.1
        processed = processed + high_band * bright_amount * 0.5

        y[ch] = processed.astype(y.dtype)

    return y


def _punch_bass_processor(y, sr, amount=0.4):
    if amount <= 0:
        return y

    if y.ndim == 1:
        y = y.reshape(1, -1)
        _punch_bass_processor(y, sr, amount)
        return y[0]

    nyq = sr / 2
    sos_sub = butter(4, 80 / nyq, btype='low', output='sos')
    sos_bass = butter(4, [80 / nyq, 200 / nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)

        sub_bass = sosfiltfilt(sos_sub, data)
        bass_band = sosfiltfilt(sos_bass, data)

        sub_envelope = np.abs(sub_bass)
        window = int(0.02 * sr)
        if window > 0:
            for i in range(len(sub_envelope)):
                start = max(0, i - window)
                sub_envelope[i] = np.mean(sub_envelope[start:i+1])

        punch = np.tanh(sub_envelope * 3) * amount * 0.2

        processed = data + bass_band * amount * 0.25 + sub_bass * punch

        y[ch] = processed.astype(y.dtype)

    return y


def _mastering_standard_hifi(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_standard_hifi(y, sr)
        return y[0]

    nyq = sr / 2

    sos_hp = butter(2, 20 / nyq, btype='high', output='sos')
    sos_presence = butter(2, [3000 / nyq, 5000 / nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        data = sosfiltfilt(sos_hp, data)

        presence = sosfiltfilt(sos_presence, data)
        data = data + presence * 0.08

        rms = np.sqrt(np.mean(data ** 2))
        if rms > 1e-10:
            target = 0.11
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain

        y[ch] = data.astype(y.dtype)

    y = _high_freq_smoother(y, sr, amount=0.2)
    y = _spatial_image_enhancer(y, sr, amount=0.15)

    return _soft_peak_limit(y, threshold=0.95)


def _mastering_powerful_hifi(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_powerful_hifi(y, sr)
        return y[0]

    nyq = sr / 2

    sos_hp = butter(2, 30 / nyq, btype='high', output='sos')
    sos_bass = butter(3, [50 / nyq, 200 / nyq], btype='band', output='sos')
    sos_low = butter(2, 150 / nyq, btype='low', output='sos')
    sos_presence = butter(2, [2500 / nyq, 6000 / nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        data = sosfiltfilt(sos_hp, data)

        bass = sosfiltfilt(sos_bass, data)
        low_body = sosfiltfilt(sos_low, data)

        analog_saturation = np.tanh(bass * 1.5) * 0.15
        data = data + bass * 0.35 + analog_saturation + low_body * 0.1

        presence = sosfiltfilt(sos_presence, data)
        data = data + presence * 0.18

        rms = np.sqrt(np.mean(data ** 2))
        if rms > 1e-10:
            target = 0.16
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain

        y[ch] = data.astype(y.dtype)

    y = _punch_bass_processor(y, sr, amount=0.35)
    y = _analog_tape_warmth(y, sr, amount=0.2)
    y = _spatial_image_enhancer(y, sr, amount=0.25)

    return _soft_peak_limit(y, threshold=0.93)


def _mastering_warm_hifi(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_warm_hifi(y, sr)
        return y[0]

    nyq = sr / 2

    sos_hp = butter(2, 25 / nyq, btype='high', output='sos')
    sos_low = butter(3, [100 / nyq, 800 / nyq], btype='band', output='sos')
    sos_mid = butter(2, [800 / nyq, 4000 / nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        data = sosfiltfilt(sos_hp, data)

        low_band = sosfiltfilt(sos_low, data)
        mid_band = sosfiltfilt(sos_mid, data)

        tube_warmth = np.tanh(low_band * 1.2) * 0.2
        data = data + tube_warmth + low_band * 0.2

        mid_body = np.tanh(mid_band * 0.8) * 0.1
        data = data + mid_body

        rms = np.sqrt(np.mean(data ** 2))
        if rms > 1e-10:
            target = 0.12
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain

        y[ch] = data.astype(y.dtype)

    y = _tube_emulator(y, sr, amount=0.35)
    y = _analog_tape_warmth(y, sr, amount=0.25)
    y = _high_freq_smoother(y, sr, amount=0.15)

    return _soft_peak_limit(y, threshold=0.94)


def _mastering_adaptive_hifi(y, sr):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _mastering_adaptive_hifi(y, sr)
        return y[0]

    nyq = sr / 2

    sos_low = butter(2, 200 / nyq, btype='low', output='sos')
    sos_mid = butter(2, [200 / nyq, 4000 / nyq], btype='band', output='sos')
    sos_high = butter(2, 4000 / nyq, btype='high', output='sos')

    low_band = sosfiltfilt(sos_low, y.astype(np.float64))
    mid_band = sosfiltfilt(sos_mid, y.astype(np.float64))
    high_band = sosfiltfilt(sos_high, y.astype(np.float64))

    low_rms = np.sqrt(np.mean(low_band ** 2))
    mid_rms = np.sqrt(np.mean(mid_band ** 2))
    high_rms = np.sqrt(np.mean(high_band ** 2))
    total_rms = low_rms + mid_rms + high_rms + 1e-10

    low_ratio = low_rms / total_rms
    mid_ratio = mid_rms / total_rms
    high_ratio = high_rms / total_rms

    dominant = 'mid'
    if low_ratio > 0.35:
        dominant = 'bass'
    elif high_ratio > 0.25:
        dominant = ' treble'

    if dominant == 'bass':
        return _mastering_powerful_hifi(y, sr)
    elif dominant == 'treble':
        return _mastering_warm_hifi(y, sr)
    else:
        return _mastering_standard_hifi(y, sr)


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
    if progress_callback:
        progress_callback(0.05, "v3.2a+ 加载音频...")

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
        algorithm_version="v3.2a+",
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
        "ai_repair_adaptive_lite": "ai_repair_adaptive_lite",
        "exciter": "exciter",
        "transient": "transient",
        "resonance": "resonance",
        "bass_enhance": "bass_enhance",
        "air_texture": "air_texture",
        "noise_reduction": "noise_reduction",
    }
    for _sk, _dk in _SINGLE_KEY_MAP.items():
        if _sk in single_params and _dk not in single_params:
            single_params[_dk] = single_params[_sk]

    if progress_callback:
        progress_callback(0.10, "v3.2a+ 处理音频...")

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

    if single_params.get("compressor", 0) > 0 or single_params.get("smart_compressor", 0) > 0:
        y = _vocal_smart_compressor_lite(y, sr, single_params.get("compressor", single_params.get("smart_compressor", 0)))

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
            progress_callback(0.80, "v3.2a+ 参考级母带...")
        y = _mastering_standard_hifi(y, working_sr)
        issues_found.append("参考级母带")
    elif mastering_style == "powerful":
        if progress_callback:
            progress_callback(0.80, "v3.2a+ 模拟调音台...")
        y = _mastering_powerful_hifi(y, working_sr)
        issues_found.append("模拟调音台母带")
    elif mastering_style == "warm":
        if progress_callback:
            progress_callback(0.80, "v3.2a+ 胆机调音...")
        y = _mastering_warm_hifi(y, working_sr)
        issues_found.append("胆机调音母带")
    elif mastering_style == "adaptive":
        if progress_callback:
            progress_callback(0.80, "v3.2a+ 智能母带...")
        y = _mastering_adaptive_hifi(y, working_sr)
        issues_found.append("智能母带")

    if progress_callback:
        progress_callback(0.90, "v3.2a+ 导出...")

    y = _soft_peak_limit(y, threshold=0.9)

    bit_depth = single_params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if y.dtype == np.float32:
        y = y.astype(np.float64)

    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)

    channels = y.shape[0] if y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, "v3.2a+ 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.2a+",
        "processing_mode": "single",
    }


def repair_audio(input_path, output_path, params, progress_callback=None):
    processing_mode = params.get("processing_mode", "single")

    if processing_mode == "single":
        return _repair_single_track(input_path, output_path, params, progress_callback)

    vocal_path = params.get("vocal_path", input_path)
    accompaniment_path = params.get("accompaniment_path", input_path)

    if progress_callback:
        progress_callback(0.05, "v3.2a+ 加载人声轨...")

    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    if vocal_y.ndim == 1:
        vocal_y = vocal_y.reshape(1, -1)

    if progress_callback:
        progress_callback(0.10, "v3.2a+ 加载伴奏轨...")

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
        algorithm_version="v3.2a+",
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
        progress_callback(0.20, "v3.2a+ 处理人声轨...")

    vocal_y = process_vocal_track(vocal_y, vocal_sr, vocal_params)
    issues_found.append("人声处理完成")

    if progress_callback:
        progress_callback(0.50, "v3.2a+ 处理伴奏轨...")

    accompaniment_y = process_instrument_track(accompaniment_y, accompaniment_sr, inst_params)
    issues_found.append("伴奏处理完成")

    gc.collect()

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if progress_callback:
        progress_callback(0.70, "v3.2a+ 保存人声修复结果...")

    vocal_output_path = params.get("vocal_output_path")
    if vocal_output_path:
        vocal_out = _soft_peak_limit(vocal_y, threshold=0.9)
        if vocal_out.dtype == np.float32:
            vocal_out = vocal_out.astype(np.float64)
        sf.write(vocal_output_path, vocal_out.T if vocal_out.ndim > 1 else vocal_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.75, "v3.2a+ 保存伴奏修复结果...")

    accompaniment_output_path = params.get("accompaniment_output_path")
    if accompaniment_output_path:
        acc_out = _soft_peak_limit(accompaniment_y, threshold=0.9)
        if acc_out.dtype == np.float32:
            acc_out = acc_out.astype(np.float64)
        sf.write(accompaniment_output_path, acc_out.T if acc_out.ndim > 1 else acc_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.80, "v3.2a+ 混音...")

    vocal_ratio = params.get("vocal_ratio", 1.0)
    accompaniment_ratio = params.get("accompaniment_ratio", 1.0)
    mixed = mix_tracks(vocal_y, accompaniment_y, vocal_ratio, accompaniment_ratio)

    issues_found.append("混音完成")

    mastering_style = params.get("mastering_style", "none")
    if mastering_style == "standard":
        if progress_callback:
            progress_callback(0.85, "v3.2a+ 参考级母带...")
        mixed = _mastering_standard_hifi(mixed, working_sr)
        issues_found.append("参考级母带")
    elif mastering_style == "powerful":
        if progress_callback:
            progress_callback(0.85, "v3.2a+ 模拟调音台...")
        mixed = _mastering_powerful_hifi(mixed, working_sr)
        issues_found.append("模拟调音台母带")
    elif mastering_style == "warm":
        if progress_callback:
            progress_callback(0.85, "v3.2a+ 胆机调音...")
        mixed = _mastering_warm_hifi(mixed, working_sr)
        issues_found.append("胆机调音母带")
    elif mastering_style == "adaptive":
        if progress_callback:
            progress_callback(0.85, "v3.2a+ 智能母带...")
        mixed = _mastering_adaptive_hifi(mixed, working_sr)
        issues_found.append("智能母带")

    if progress_callback:
        progress_callback(0.90, "v3.2a+ 导出...")

    mixed = _soft_peak_limit(mixed, threshold=0.9)

    if mixed.dtype == np.float32:
        mixed = mixed.astype(np.float64)

    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v3.2a+ 修复完成")

    result = {
        "issues_found": issues_found,
        "original_sample_rate": vocal_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": mixed.shape[0] if mixed.ndim > 1 else 1,
        "algorithm_version": "v3.2a+",
        "processing_mode": "dual",
    }
    if vocal_output_path:
        result["vocal_output_path"] = vocal_output_path
    if accompaniment_output_path:
        result["accompaniment_output_path"] = accompaniment_output_path
    return result
