import numpy as np
from scipy import signal
from ..repair_v3_2.core import *
from ..repair_v3_2.core import repair_audio as _v3_2_repair_audio
from ..repair_v3_2.core import process_vocal_track as _v3_2_process_vocal_track
from ..repair_v3_2.core import process_instrument_track as _v3_2_process_instrument_track
from ..repair_v3_2.core import _repair_single_track as _v3_2_repair_single_track
from ..repair_v3_2.core import mix_tracks as _v3_2_mix_tracks

DESKTOP_WORKING_SR = 48000
N_FFT = 2048
HOP_LENGTH = 512

def _lookahead_compressor(y, sr, amount):
    lookahead_ms = 5
    lookahead_samples = int(0.001 * lookahead_ms * sr)
    if lookahead_samples < 1:
        return _vocal_smart_compressor(y, sr, amount)
    shifted = np.pad(y, (lookahead_samples, 0))[:-lookahead_samples]
    window_size = int(0.01 * sr)
    env = np.zeros_like(y)
    for i in range(len(y)):
        start = max(0, i - window_size)
        chunk = shifted[start:i + 1]
        rms = np.sqrt(np.mean(chunk ** 2) + 1e-10)
        peak = np.abs(shifted[i])
        env[i] = 0.6 * rms + 0.4 * peak
    threshold = np.median(np.abs(y)) * 2.0
    ratio = 4.0
    knee = 6.0
    gain = np.ones_like(y)
    for i in range(len(y)):
        e = env[i]
        if e > threshold - knee / 2:
            if e < threshold + knee / 2:
                g = 1.0 - (1.0 / ratio) * ((e - threshold + knee / 2) / knee) ** 2
            else:
                g = 1.0 - (1.0 - 1.0 / ratio) * (1.0 - (threshold - knee / 2) / e)
            gain[i] = 1.0 - (1.0 - g) * amount
    return y * gain

def _vocal_ai_repair_dual_resolution(y, sr, strength):
    n_fft_high = 2048
    n_fft_low = 1024
    hop = 512
    D_high = _stft(y, n_fft_high, hop)
    D_low = _stft(y, n_fft_low, hop)
    mag_high = np.abs(D_high)
    mag_low = np.abs(D_low)
    n_frames_high = mag_high.shape[1]
    n_frames_low = mag_low.shape[1]
    spec_flux = np.zeros(n_frames_low)
    for i in range(1, n_frames_low):
        diff = mag_low[:, i] - mag_low[:, i - 1]
        spec_flux[i] = np.mean(np.maximum(diff, 0))
    flux_threshold = np.median(spec_flux) + 2.0 * np.std(spec_flux)
    transient_frames_low = spec_flux > flux_threshold
    transient_frames_high = np.zeros(n_frames_high, dtype=bool)
    for i in range(n_frames_high):
        idx_low = int(i * n_frames_low / n_frames_high)
        if idx_low < n_frames_low:
            transient_frames_high[i] = transient_frames_low[idx_low]
    D_out = D_high.copy()
    blend_width = 2
    for i in range(n_frames_high):
        start = max(0, i - blend_width)
        end = min(n_frames_high, i + blend_width + 1)
        transient_count = np.sum(transient_frames_high[start:end])
        transient_ratio = transient_count / (end - start) if end > start else 0.0
        if transient_ratio > 0.3:
            idx_low = min(int(i * n_frames_low / n_frames_high), n_frames_low - 1)
            n_bins_low = n_fft_low // 2 + 1
            D_out[:n_bins_low, i] = (1 - transient_ratio) * D_high[:n_bins_low, i] + transient_ratio * D_low[:, idx_low]
    y_out = _istft(D_out, hop, len(y))
    y_out = np.clip(y_out, -1, 1)
    return y * (1 - strength * 0.3) + y_out * (strength * 0.3)

def _resonance_suppress_enhanced(y, sr, amount):
    n_fft = 2048
    hop = 512
    D = _stft(y, n_fft, hop)
    mag = np.abs(D)
    gain = np.ones_like(mag)
    for i in range(mag.shape[1]):
        for j in range(2, mag.shape[0] - 2):
            neighbors = mag[j - 2:j + 3, i]
            median_val = np.median(neighbors)
            if mag[j, i] > median_val * 2.0 and median_val > 1e-10:
                reduction = 1.0 - amount * 0.5 * (1.0 - median_val / (mag[j, i] + 1e-10))
                gain[j, i] = max(reduction, 0.3)
    alpha = 0.3
    gain_smooth = np.zeros_like(gain)
    gain_smooth[:, 0] = gain[:, 0]
    for i in range(1, gain.shape[1]):
        gain_smooth[:, i] = alpha * gain_smooth[:, i - 1] + (1 - alpha) * gain[:, i]
    D = D * gain_smooth
    y_out = _istft(D, hop, len(y))
    y_out = np.clip(y_out, -1, 1)
    return y * (1 - amount * 0.3) + y_out * (amount * 0.3)

def _vocal_spatial_enhanced(y, sr, amount):
    early_taps_ms = [5, 10, 15]
    early_decays = [0.4, 0.3, 0.2]
    early = np.zeros_like(y)
    for tap_ms, decay in zip(early_taps_ms, early_decays):
        delay = int(tap_ms * sr / 1000)
        if delay < len(y):
            early[delay:] += decay * y[:-delay]
    fb_len = int(0.1 * sr)
    fb = np.zeros(fb_len)
    for i in range(1, fb_len):
        fb[i] = 0.5 * fb[i - 1] + 0.3 * y[min(i, len(y) - 1)]
    reverb_tail = np.zeros_like(y)
    reverb_tail[:fb_len] = fb * 0.2
    freqs = np.fft.rfftfreq(2048, 1.0 / sr)
    width_gain = np.where(freqs < 200, 0.0, 1.0)
    y_spatial = y + early * 0.5 + reverb_tail * 0.3
    y_spatial = y * (1 - amount * 0.3) + y_spatial * (amount * 0.3)
    return np.clip(y_spatial, -1, 1)

def _stft(y, n_fft, hop_length):
    return np.array([np.fft.rfft(y[i:i + n_fft] * np.hanning(n_fft)) for i in range(0, len(y) - n_fft, hop_length)]).T

def _istft(D, hop_length, length):
    n_fft = (D.shape[0] - 1) * 2
    y = np.zeros(length)
    window = np.hanning(n_fft)
    for i in range(D.shape[1]):
        start = i * hop_length
        if start + n_fft > length:
            break
        frame = np.fft.irfft(D[:, i])
        y[start:start + n_fft] += frame * window
    return y

def process_vocal_track(y, sr, params):
    speed = params.get('speed', 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)
    amount = params.get('amount', 1.0)
    y = y.copy().astype(np.float64)
    y = _tanh_declip(y, amount * params.get('declip', 0.5))
    y = _diff_clamp_depop(y, sr, amount * params.get('depop', 0.5))
    y = _vocal_formant_repair(y, sr, amount * params.get('formant_repair', 0.5))
    y = _apply_vocal_de_ess(y, sr, amount * params.get('de_ess', 0.5))
    y = _de_esser_improved(y, sr, amount * params.get('de_esser_improved', 0.5))
    y = _vocal_ai_repair_dual_resolution(y, sr, amount * params.get('ai_repair_adaptive', 0.5))
    y = _resonance_suppress_enhanced(y, sr, amount * params.get('resonance_suppress', 0.3))
    y = _vocal_breath_enhance(y, sr, amount * params.get('breath_enhance', 0.3))
    y = _vocal_exciter_improved(y, sr, amount * params.get('exciter_improved', 0.3))
    y = _lookahead_compressor(y, sr, amount * params.get('smart_compressor', 0.5))
    y = _transient_aware_process(y, sr, amount * params.get('transient_aware', 0.3))
    y = _vocal_warmth(y, sr, amount * params.get('vocal_warmth', 0.3))
    y = _vocal_spatial_enhanced(y, sr, amount * params.get('vocal_spatial', 0.3))
    y = _adaptive_loudness_normalize(y, sr)
    y = _soft_peak_limit(y)
    return np.clip(y, -1, 1)

def process_instrument_track(y, sr, params):
    return _v3_2_process_instrument_track(y, sr, params)

def mix_tracks(vocal, accompaniment, vocal_ratio=1.0, accompaniment_ratio=1.0):
    return _v3_2_mix_tracks(vocal, accompaniment, vocal_ratio, accompaniment_ratio)

def _repair_single_track(input_path, output_path, params, progress_callback=None):
    return _v3_2_repair_single_track(input_path, output_path, params, progress_callback)

def repair_audio(input_path, output_path, params, progress_callback=None):
    return _v3_2_repair_audio(input_path, output_path, params, progress_callback)