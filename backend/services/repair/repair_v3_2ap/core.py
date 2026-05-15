import numpy as np
from scipy import signal
from ..repair_v3_2a.core import *
from ..repair_v3_2a.core import repair_audio as _v3_2a_repair_audio
from ..repair_v3_2a.core import process_vocal_track as _v3_2a_process_vocal_track
from ..repair_v3_2a.core import process_instrument_track as _v3_2a_process_instrument_track
from ..repair_v3_2a.core import _repair_single_track as _v3_2a_repair_single_track
from ..repair_v3_2a.core import mix_tracks as _v3_2a_mix_tracks

MOBILE_WORKING_SR = 48000
N_FFT = 2048
HOP_LENGTH = 512

def _lookahead_compressor_lite(y, sr, amount):
    lookahead_ms = 3
    lookahead_samples = int(0.001 * lookahead_ms * sr)
    if lookahead_samples < 1:
        return _vocal_smart_compressor_lite(y, sr, amount)
    shifted = np.pad(y, (lookahead_samples, 0))[:-lookahead_samples]
    window_size = int(0.01 * sr)
    env = np.zeros_like(y)
    for i in range(len(y)):
        start = max(0, i - window_size)
        chunk = shifted[start:i + 1]
        rms = np.sqrt(np.mean(chunk ** 2) + 1e-10)
        env[i] = rms
    threshold = np.median(np.abs(y)) * 2.0
    ratio = 4.0
    gain = np.ones_like(y)
    for i in range(len(y)):
        e = env[i]
        if e > threshold:
            db_over = 20 * np.log10(e / threshold + 1e-10)
            g_db = db_over / ratio
            g = 10 ** (g_db / 20)
            gain[i] = 1.0 - (1.0 - g) * amount
    return y * gain

def _vocal_ai_repair_adaptive_lite(y, sr, strength):
    n_fft = 2048
    hop = 512
    D = _stft(y, n_fft, hop)
    mag = np.abs(D)
    phase = np.angle(D)
    n_frames = mag.shape[1]
    n_bins = mag.shape[0]
    noise_floor = np.zeros_like(mag)
    for j in range(n_bins):
        history = mag[j, :]
        for i in range(n_frames):
            start = max(0, i - 10)
            noise_floor[j, i] = np.min(history[start:i + 1])
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    threshold_mult = np.ones(n_bins)
    for j in range(n_bins):
        if freqs[j] < 4000:
            threshold_mult[j] = 2.0
        else:
            threshold_mult[j] = 3.5
    mask = np.ones_like(mag)
    for j in range(n_bins):
        for i in range(n_frames):
            if noise_floor[j, i] > 1e-10:
                ratio = mag[j, i] / noise_floor[j, i]
                if ratio < threshold_mult[j]:
                    mask[j, i] = ratio / threshold_mult[j]
    D_out = D * mask
    y_out = _istft(D_out, hop, len(y))
    y_out = np.clip(y_out, -1, 1)
    return y * (1 - strength * 0.3) + y_out * (strength * 0.3)

def _vocal_spatial_lite_enhanced(y, sr, amount):
    tap_ms = 8
    delay = int(tap_ms * sr / 1000)
    early = np.zeros_like(y)
    if delay < len(y):
        early[delay:] = 0.3 * y[:-delay]
    fb_len = int(0.05 * sr)
    fb = np.zeros(fb_len)
    for i in range(1, fb_len):
        fb[i] = 0.4 * fb[i - 1] + 0.2 * y[min(i, len(y) - 1)]
    reverb_tail = np.zeros_like(y)
    reverb_tail[:fb_len] = fb * 0.15
    y_spatial = y + early + reverb_tail
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
    amount = params.get('amount', 1.0)
    y = y.copy().astype(np.float64)
    y = _simple_declip(y, amount * params.get('declip', 0.5))
    y = _simple_depop(y, sr, amount * params.get('depop', 0.5))
    y = _de_ess(y, sr, amount * params.get('de_ess', 0.5))
    y = _vocal_ai_repair_adaptive_lite(y, sr, amount * params.get('ai_repair_adaptive', 0.5))
    y = _resonance_suppress_lite(y, sr, amount * params.get('resonance_suppress', 0.3))
    y = _vocal_exciter_lite(y, sr, amount * params.get('exciter_improved', 0.3))
    y = _lookahead_compressor_lite(y, sr, amount * params.get('smart_compressor', 0.5))
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
    result = _v3_2a_repair_audio(input_path, output_path, params, progress_callback)
    if isinstance(result, dict) and 'output_path' in result:
        import soundfile as sf
        y, sr = sf.read(result['output_path'])
        y = y.astype(np.float64)
        if y.ndim > 1:
            y = np.mean(y, axis=1)
        second_pass_amount = 0.3
        y = _lookahead_compressor_lite(y, sr, second_pass_amount * params.get('smart_compressor', 0.5))
        y = _vocal_exciter_lite(y, sr, second_pass_amount * params.get('exciter_improved', 0.3))
        y = _transient_aware_process_lite(y, sr, second_pass_amount * params.get('transient_aware', 0.3))
        y = np.clip(y, -1, 1)
        sf.write(result['output_path'], y, sr)
    return result