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


def process_vocal_track(y, sr, params):
    if params.get("de_clipping", 0) > 0:
        y = _simple_declip(y, params["de_clipping"])

    if params.get("de_pop", 0) > 0:
        y = _simple_depop(y, sr, params["de_pop"])

    if params.get("de_essing", 0) > 0:
        y = _de_ess(y, sr, params["de_essing"])

    if params.get("ai_repair", 0) > 0:
        from services.repair.repair_v2_3a.core import _spectral_denoise
        try:
            y = _spectral_denoise(y, sr, params["ai_repair"])
        except Exception:
            pass

    if params.get("bass_enhance", 0) > 0:
        y = _apply_bass_enhance_lite(y, sr, params["bass_enhance"])

    if params.get("clarity", 0) > 0:
        y = _apply_air_texture_lite(y, sr, params["clarity"])

    if params.get("loudness_optimize", 0) > 0:
        y = _loudness_normalize(y, sr, -14.0)

    y = _soft_peak_limit(y, threshold=0.9)
    return y


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


def process_instrument_track(y, sr, params):
    if params.get("de_clipping", 0) > 0:
        y = _simple_declip(y, params["de_clipping"])

    if params.get("de_pop", 0) > 0:
        y = _simple_depop(y, sr, params["de_pop"])

    if params.get("noise_reduction", 0) > 0:
        y = _spectral_denoise(y, sr, params["noise_reduction"])

    if params.get("dynamic_range", 0) > 0:
        y = _transparent_compress(y, sr, params["dynamic_range"])

    if params.get("loudness_optimize", 0) > 0:
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


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    vocal_path = params.get("vocal_path", input_path)
    accompaniment_path = params.get("accompaniment_path", input_path)

    if progress_callback:
        progress_callback(0.05, "v3.0a 加载人声轨...")

    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    if vocal_y.ndim == 1:
        vocal_y = vocal_y.reshape(1, -1)

    if progress_callback:
        progress_callback(0.10, "v3.0a 加载伴奏轨...")

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
        algorithm_version="v3.0a",
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

    vocal_params = {k.replace("vocal_", ""): v for k, v in params.items() if k.startswith("vocal_")}
    inst_params = {k.replace("inst_", ""): v for k, v in params.items() if k.startswith("inst_")}

    if progress_callback:
        progress_callback(0.20, "v3.0a 处理人声轨...")

    vocal_y = process_vocal_track(vocal_y, vocal_sr, vocal_params)
    issues_found.append("人声处理完成")

    if progress_callback:
        progress_callback(0.50, "v3.0a 处理伴奏轨...")

    accompaniment_y = process_instrument_track(accompaniment_y, accompaniment_sr, inst_params)
    issues_found.append("伴奏处理完成")

    gc.collect()

    if progress_callback:
        progress_callback(0.75, "v3.0a 混音...")

    vocal_ratio = params.get("vocal_ratio", 1.0)
    accompaniment_ratio = params.get("accompaniment_ratio", 1.0)
    mixed = mix_tracks(vocal_y, accompaniment_y, vocal_ratio, accompaniment_ratio)

    issues_found.append("混音完成")

    if progress_callback:
        progress_callback(0.90, "v3.0a 导出...")

    mixed = _soft_peak_limit(mixed, threshold=0.9)

    if mixed.dtype == np.float32:
        mixed = mixed.astype(np.float64)

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v3.0a 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": vocal_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": mixed.shape[0] if mixed.ndim > 1 else 1,
        "algorithm_version": "v3.0a",
        "processing_mode": "dual",
    }
