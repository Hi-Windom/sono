import numpy as np
import soundfile as sf
from functools import lru_cache
from scipy.signal import butter, resample_poly, sosfiltfilt, medfilt
from config import MOBILE_MODE
import gc
from services.audio_loader import load_audio_with_fallback
from services.dsp_utils import stft, istft, streaming_spectral_process

from services.repair.repair_v2_2.spectral_group_a import apply_spectral_group_a
from services.repair.repair_v2_2.spectral_group_b import apply_spectral_group_b
from services.repair.repair_v2_2.subband_processing import apply_subband_repair
from services.repair.repair_v2_2.spatial import apply_spatial_enhance_v6, apply_stereo_width_v3
from services.repair.repair_v2_2.filters import apply_warmth_v2
from services.repair.repair_v2_2.dynamics import apply_softness_v5
from services.repair.repair_v2_2.music_type_detector import detect_music_type
from services.repair.repair_v2_2.type_params import apply_music_type_params, get_repair_mode_params

# v2.4 HiFi 优化模块
from .tempo_analyzer import TempoAnalyzer, get_tempo_params
from .hifi_multiband import apply_hifi_multiband_compress
from .hifi_ai_repair import apply_hifi_ai_repair
from .detail_enhance import apply_adaptive_detail_enhance, apply_stereo_enhance

DESKTOP_WORKING_SR = 48000
N_FFT = 2048
HOP_LENGTH = 512


def _tanh_declip_1d(data, threshold):
    mask = np.abs(data) > threshold
    if not np.any(mask):
        return data.copy()
    y_out = data.copy().astype(np.float64)
    abs_y = np.abs(y_out[mask])
    over = abs_y - threshold
    headroom = 1.0 - threshold
    y_out[mask] = np.sign(y_out[mask]) * (threshold + headroom * np.tanh(over / headroom))
    return y_out.astype(data.dtype)


def _tanh_declip(y, amount):
    if amount <= 0:
        return y
    threshold = 0.90
    if y.ndim == 1:
        return _tanh_declip_1d(y, threshold)
    for ch in range(y.shape[0]):
        y[ch] = _tanh_declip_1d(y[ch], threshold)
    return y


def _diff_clamp_depop_1d(data, sr, amount):
    diff = np.diff(data)
    abs_diff = np.abs(diff)
    median_diff = np.median(abs_diff)
    if median_diff < 1e-10:
        return data.copy()
    threshold = median_diff * (80 + 120 * amount)
    pop_mask = np.concatenate(([False], abs_diff > threshold))
    if not np.any(pop_mask):
        return data.copy()
    y_out = data.copy()
    indices = np.where(pop_mask)[0]
    i = 0
    while i < len(indices):
        start = indices[i]
        run_end = start
        while i + 1 < len(indices) and indices[i + 1] == run_end + 1:
            i += 1
            run_end = indices[i]
        max_modify = min(2, run_end - start + 1)
        for idx in range(start, start + max_modify):
            if idx > 0 and idx < len(y_out) - 1:
                prev = y_out[idx - 1]
                next_val = y_out[idx + 1]
                actual_diff = y_out[idx] - prev
                if abs(actual_diff) > threshold:
                    clamped = prev + np.sign(actual_diff) * threshold
                    y_out[idx] = 0.5 * (clamped + next_val)
        i += 1
    return y_out


def _diff_clamp_depop(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        return _diff_clamp_depop_1d(y, sr, amount)
    for ch in range(y.shape[0]):
        y[ch] = _diff_clamp_depop_1d(y[ch], sr, amount)
    return y


def _soft_peak_limit_1d(data, threshold):
    abs_data = np.abs(data)
    mask = abs_data > threshold
    if not np.any(mask):
        return data.copy()
    headroom = 1.0 - threshold
    over = abs_data[mask] - threshold
    scale = headroom * 0.98
    out = data.copy().astype(np.float64)
    out[mask] = np.sign(out[mask]) * (threshold + scale * np.tanh(over / scale))
    return out.astype(data.dtype)


def _soft_peak_limit(y, threshold=0.9):
    abs_max = np.max(np.abs(y))
    if abs_max <= threshold:
        return y
    if y.ndim == 1:
        return _soft_peak_limit_1d(y, threshold)
    for ch in range(y.shape[0]):
        y[ch] = _soft_peak_limit_1d(y[ch], threshold)
    return y


def _soft_transient_limit(y, sr, amount):
    if amount < 0.05:
        return y
    if y.ndim == 1:
        y_2d = y.reshape(1, -1)
        _soft_transient_limit(y_2d, sr, amount)
        return y
    frame_size = int(sr * 0.1)
    for ch in range(y.shape[0]):
        data = y[ch]
        n_frames = len(data) // frame_size
        if n_frames < 4:
            continue
        frames = data[:n_frames * frame_size].reshape(n_frames, frame_size)
        frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
        window = 3
        kernel = np.ones(window) / window
        smooth_rms = np.convolve(frame_rms, kernel, mode='same')
        diff = np.abs(np.diff(frame_rms, prepend=frame_rms[0]))
        threshold = np.mean(diff) + np.std(diff) * (1.5 - amount)
        anomaly = diff > threshold
        if not np.any(anomaly):
            continue
        anomaly_indices = np.where(anomaly)[0]
        left_rms = smooth_rms[np.maximum(anomaly_indices - 1, 0)]
        right_rms = smooth_rms[np.minimum(anomaly_indices + 1, n_frames - 1)]
        target_rms_arr = (left_rms + right_rms) / 2
        current_rms_arr = frame_rms[anomaly_indices]
        valid = (current_rms_arr > 0) & (target_rms_arr > 0)
        if not np.any(valid):
            continue
        ratios = target_rms_arr[valid] / current_rms_arr[valid]
        max_ratio = float(np.min(ratios)) if len(ratios) > 0 else 1.0
        global_gain = max_ratio * amount * 0.3 + 1.0 * (1 - amount * 0.3)
        for idx in anomaly_indices:
            start = idx * frame_size
            end = min(len(data), (idx + 1) * frame_size)
            region = y[ch, start:end]
            peak = np.max(np.abs(region))
            if peak > 0:
                target_peak = peak * global_gain
                if target_peak < peak:
                    y[ch, start:end] = _soft_peak_limit_1d(region, target_peak / peak * 0.98)
    return y


@lru_cache(maxsize=32)
def _multiband_sos_cache(sr, low_cross, high_cross):
    nyq = sr / 2
    w_low = low_cross / nyq
    w_high = high_cross / nyq
    if w_low >= 1.0 or w_high >= 1.0 or w_low <= 0 or w_high <= 0:
        return None
    sos_low = butter(4, w_low, btype='low', output='sos')
    sos_mid_low = butter(4, w_low, btype='high', output='sos')
    sos_mid_high = butter(4, w_high, btype='low', output='sos')
    sos_high = butter(4, w_high, btype='high', output='sos')
    return sos_low, sos_mid_low, sos_mid_high, sos_high


def _adaptive_loudness_normalize(y, sr, target_lufs=-14.0):
    if y.ndim == 1:
        y_2d = y.reshape(1, -1)
        _adaptive_loudness_normalize(y_2d, sr, target_lufs)
        return y
    try:
        for ch in range(y.shape[0]):
            data = y[ch].copy()
            if 60 < sr / 2:
                sos_hp = butter(2, 60 / (sr / 2), btype='high', output='sos')
                data = sosfiltfilt(sos_hp, data)
            shelf_low = 1000 / (sr / 2)
            shelf_high = 4000 / (sr / 2)
            if shelf_high < 1.0 and shelf_high > shelf_low:
                sos_shelf = butter(2, [shelf_low, shelf_high], btype='band', output='sos')
                shelf_signal = sosfiltfilt(sos_shelf, data)
                data = data + shelf_signal * (10 ** (4.0 / 20) - 1)
            rms_val = np.sqrt(np.mean(data ** 2))
            if rms_val < 1e-10:
                continue
            current_lufs = -0.691 + 20 * np.log10(rms_val)
            gain_db = np.clip(target_lufs - current_lufs, -15, 9)
            y[ch] *= 10 ** (gain_db / 20)
    except Exception:
        for ch in range(y.shape[0]):
            rms = np.sqrt(np.mean(y[ch] ** 2))
            if rms > 1e-10:
                current_lufs = -0.691 + 20 * np.log10(rms)
                gain_db = np.clip(target_lufs - current_lufs, -15, 9)
                y[ch] *= 10 ** (gain_db / 20)
    return y


def _enhanced_multiband_compress(y, sr, amount, music_type):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y_2d = y.reshape(1, -1)
        _enhanced_multiband_compress(y_2d, sr, amount, music_type)
        return y
    if music_type == "vocal":
        low_cross = 250
        high_cross = 4000
    elif music_type == "electronic":
        low_cross = 200
        high_cross = 5000
    elif music_type == "classical":
        low_cross = 300
        high_cross = 3500
    else:
        low_cross = 250
        high_cross = 4000
    nyq = sr / 2
    w_low = low_cross / nyq
    w_high = high_cross / nyq
    cached = _multiband_sos_cache(sr, low_cross, high_cross)
    if cached is None:
        return y
    sos_low, sos_mid_low, sos_mid_high, sos_high = cached
    threshold_db = -18.0
    threshold_lin = 10 ** (threshold_db / 20.0)
    effective_ratio = 1.0 + (2.0 - 1.0) * min(amount, 1.0)
    for ch in range(y.shape[0]):
        data = y[ch].copy()
        low_band = sosfiltfilt(sos_low, data)
        low_rms = np.sqrt(np.mean(low_band ** 2))
        low_gain = 1.0
        if low_rms > threshold_lin and low_rms > 1e-10:
            target_rms = threshold_lin + (low_rms - threshold_lin) / effective_ratio
            low_gain = target_rms / low_rms
        low_gain *= 10 ** (2.0 / 20.0)
        y[ch] = low_band * low_gain
        del low_band
        mid_band = sosfiltfilt(sos_mid_low, data)
        mid_band = sosfiltfilt(sos_mid_high, mid_band)
        mid_rms = np.sqrt(np.mean(mid_band ** 2))
        mid_gain = 1.0
        if mid_rms > threshold_lin and mid_rms > 1e-10:
            target_rms = threshold_lin + (mid_rms - threshold_lin) / effective_ratio
            mid_gain = target_rms / mid_rms
        y[ch] += mid_band * mid_gain
        del mid_band
        high_band = sosfiltfilt(sos_high, data)
        high_rms = np.sqrt(np.mean(high_band ** 2))
        high_gain = 1.0
        if high_rms > threshold_lin and high_rms > 1e-10:
            target_rms = threshold_lin + (high_rms - threshold_lin) / effective_ratio
            high_gain = target_rms / high_rms
        y[ch] += high_band * high_gain
        del high_band
        del data
    makeup_gain_db = min(5.0, 1.5 * amount)
    y *= 10 ** (makeup_gain_db / 20)
    peak = np.max(np.abs(y))
    if peak > 0.95:
        y *= 0.95 / peak
    return y


def _ai_artifact_repair_channel(y_1d, sr, amount):
    n_samples = len(y_1d)
    if n_samples < N_FFT:
        return y_1d

    duration_sec = n_samples / sr
    use_streaming = duration_sec > 300

    if use_streaming:
        def _ai_process_chunk(S, sr_chunk, n_fft, hop_length):
            return _ai_artifact_repair_spectral(S, sr_chunk, amount)
        result = streaming_spectral_process(
            y_1d.astype(np.float64), sr,
            _ai_process_chunk,
            n_fft=N_FFT, hop_length=HOP_LENGTH,
            chunk_seconds=10
        )
        return result.astype(y_1d.dtype)

    S = stft(y_1d, n_fft=N_FFT, hop_length=HOP_LENGTH)
    S = _ai_artifact_repair_spectral(S, sr, amount)
    y_out = istft(S, hop_length=HOP_LENGTH, length=n_samples)
    return y_out.astype(y_1d.dtype)


def _ai_artifact_repair_spectral(S, sr, amount):
    mag = np.abs(S)
    phase = np.angle(S)

    frame_energy = np.sum(mag ** 2, axis=0)
    energy_change = np.abs(np.diff(frame_energy, prepend=frame_energy[0]))
    mean_change = np.mean(energy_change)
    std_change = np.std(energy_change)
    transient_threshold = mean_change + 2 * std_change
    transient_frames = energy_change > transient_threshold

    smoothed_mag = np.empty_like(mag)
    for i in range(mag.shape[0]):
        m3 = medfilt(mag[i], 3)
        m5 = medfilt(mag[i], 5)
        m7 = medfilt(mag[i], 7)
        smoothed_mag[i] = np.minimum(np.minimum(m3, m5), m7)

    for j in range(S.shape[1]):
        if not transient_frames[j]:
            S[:, j] = smoothed_mag[:, j] * np.exp(1j * phase[:, j])

    mag = np.abs(S)
    phase = np.angle(S)

    jitter_db = 0.5 + amount * 1.0
    mag *= 10 ** (np.random.uniform(-jitter_db, jitter_db, mag.shape) / 20)

    freqs = np.arange(S.shape[0]) * sr / N_FFT
    presence_low = 2000
    presence_high = 5000
    presence_mask = (freqs >= presence_low) & (freqs <= presence_high)
    if np.any(presence_mask):
        presence_rms = np.sqrt(np.mean(mag[presence_mask, :] ** 2, axis=0))
        global_rms = np.sqrt(np.mean(mag ** 2))
        threshold = global_rms * 1.5
        for j in range(S.shape[1]):
            if presence_rms[j] > threshold:
                attenuation = 1.0 - amount * 0.3 * (presence_rms[j] / (global_rms * threshold) - 1.0)
                attenuation = np.clip(attenuation, 0.5, 1.0)
                S[presence_mask, j] *= attenuation

    block_size = int(0.5 * sr / HOP_LENGTH)
    if block_size < 1:
        block_size = 1
    n_blocks = S.shape[1] // block_size
    if n_blocks >= 2:
        block_energy = np.zeros(n_blocks)
        for b in range(n_blocks):
            start_f = b * block_size
            end_f = min((b + 1) * block_size, S.shape[1])
            block_energy[b] = np.mean(mag[:, start_f:end_f] ** 2)
        section_boundaries = [0]
        for b in range(1, n_blocks):
            if block_energy[b - 1] > 1e-10:
                change = abs(block_energy[b] - block_energy[b - 1]) / block_energy[b - 1]
                if change > 0.2:
                    section_boundaries.append(b)
        section_boundaries.append(n_blocks)
        for s in range(len(section_boundaries) - 1):
            brightness_offset = 0.5 if s % 2 == 0 else -0.5
            gain = 10 ** (brightness_offset / 20)
            start_f = section_boundaries[s] * block_size
            end_f = section_boundaries[s + 1] * block_size
            end_f = min(end_f, S.shape[1])
            if start_f < end_f:
                S[:, start_f:end_f] *= gain

    freqs = np.arange(S.shape[0]) * sr / N_FFT
    air_bins = freqs >= 10000
    if np.any(air_bins):
        mid_mask = (freqs >= 2000) & (freqs < 8000)
        if np.any(mid_mask):
            mid_energy = np.mean(mag[mid_mask, :] ** 2, axis=0)
            mid_envelope = mid_energy / (np.max(mid_energy) + 1e-10)
        else:
            mid_envelope = np.ones(S.shape[1])
        noise = np.random.randn(int(np.sum(air_bins)), S.shape[1]) * 0.001 * amount
        noise *= mid_envelope[np.newaxis, :]
        S[air_bins, :] += noise * np.exp(1j * np.angle(S[air_bins, :]))

    return S


def _ai_artifact_repair(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        return _ai_artifact_repair_channel(y, sr, amount)
    for ch in range(y.shape[0]):
        y[ch] = _ai_artifact_repair_channel(y[ch], sr, amount)
    return y


def _harmonic_bass_enhance(y, sr, amount, music_type):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y_2d = y.reshape(1, -1)
        _harmonic_bass_enhance(y_2d, sr, amount, music_type)
        return y
    nyq = sr / 2
    low_cut = min(250, nyq * 0.9)
    sos_low = butter(4, low_cut / nyq, btype='low', output='sos')
    body_low = min(500, nyq * 0.9)
    body_high = min(200, nyq * 0.9)
    if body_low > body_high:
        sos_body = butter(4, [body_high / nyq, body_low / nyq], btype='band', output='sos')
    else:
        sos_body = None
    for ch in range(y.shape[0]):
        low_band = sosfiltfilt(sos_low, y[ch])
        half_len = len(low_band) // 2
        averaged = (low_band[0::2][:half_len] + low_band[1::2][:half_len]) * 0.5
        x_short = np.linspace(0, 1, len(averaged))
        x_long = np.linspace(0, 1, len(low_band))
        sub_harmonic = np.interp(x_long, x_short, averaged)
        sub_harmonic = sosfiltfilt(sos_low, sub_harmonic)
        excited = np.tanh(low_band * 2.0) * np.max(np.abs(low_band)) / (np.max(np.abs(np.tanh(low_band * 2.0))) + 1e-10)
        body = np.zeros_like(y[ch])
        if sos_body is not None:
            body = sosfiltfilt(sos_body, y[ch])
        y[ch] += sub_harmonic * amount * 0.15 + excited * amount * 0.1 + body * (10 ** (1.5 / 20) - 1) * amount
        del low_band, sub_harmonic, excited, body
    return y


def _air_texture_reconstruct(y, sr, amount, music_type):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y_2d = y.reshape(1, -1)
        _air_texture_reconstruct(y_2d, sr, amount, music_type)
        return y
    for ch in range(y.shape[0]):
        n_samples = y.shape[1]
        if n_samples < N_FFT:
            continue
        S = stft(y[ch], n_fft=N_FFT, hop_length=HOP_LENGTH)
        freqs = np.arange(S.shape[0]) * sr / N_FFT
        mid_mask = (freqs >= 2000) & (freqs < 8000)
        high_mask = (freqs >= 8000) & (freqs < 16000)
        air_mask = freqs >= 10000
        reconstructed = np.zeros_like(S)
        if np.any(mid_mask) and np.any(high_mask):
            mid_energy = np.mean(np.abs(S[mid_mask, :]) ** 2, axis=0)
            mid_envelope = np.sqrt(mid_energy + 1e-10)
            mid_envelope_norm = mid_envelope / (np.max(mid_envelope) + 1e-10)
            harmonic_ratio = 0.6
            for j in range(S.shape[1]):
                high_indices = np.where(high_mask)[0]
                mid_indices = np.where(mid_mask)[0]
                n_map = min(len(high_indices), len(mid_indices))
                if n_map > 0:
                    for k in range(n_map):
                        hi = high_indices[k]
                        mi = mid_indices[k]
                        reconstructed[hi, j] = np.abs(S[mi, j]) * harmonic_ratio * mid_envelope_norm[j] * np.exp(1j * np.angle(S[hi, j]))
        if np.any(air_mask):
            mid_energy_per_frame = np.mean(np.abs(S[mid_mask, :]) ** 2, axis=0) if np.any(mid_mask) else np.ones(S.shape[1])
            mid_env = np.sqrt(mid_energy_per_frame + 1e-10)
            mid_env_norm = mid_env / (np.max(mid_env) + 1e-10)
            air_indices = np.where(air_mask)[0]
            noise = np.random.randn(len(air_indices), S.shape[1]) * 0.001 * amount
            noise *= mid_env_norm[np.newaxis, :]
            reconstructed[air_indices, :] += noise * np.exp(1j * np.angle(S[air_indices, :]))
        y_recon = istft(reconstructed, hop_length=HOP_LENGTH, length=n_samples)
        y[ch] += y_recon * amount * 0.2
        del S, reconstructed, y_recon
    return y


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)

    quality_mode = params.get("quality", "standard")
    is_hifi = quality_mode == "hifi"

    if MOBILE_MODE:
        working_sr = sr
    else:
        working_sr = DESKTOP_WORKING_SR

    from services.memory_guard import check_memory_before_repair, should_use_float32
    working_sr = check_memory_before_repair(
        n_samples=y.shape[1],
        n_channels=y.shape[0],
        sr=original_sr,
        working_sr=working_sr,
        algorithm_version="v2.4",
    )

    use_f32 = should_use_float32(y.shape[1], y.shape[0])
    if use_f32:
        y = y.astype(np.float32)

    if sr != working_sr:
        if progress_callback:
            progress_callback(0.02, f"v2.4 重采样到 {working_sr//1000}kHz...")
        target_len = int(y.shape[1] * working_sr / sr)
        y_new = np.zeros((y.shape[0], target_len))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            y_new[ch, :len(resampled)] = resampled[:target_len]
        y = y_new
        sr = working_sr
        gc.collect()

    issues_found = []

    if progress_callback:
        progress_callback(0.04, "v2.4 检测音乐类型...")

    music_type_override = params.get("music_type", "auto")
    repair_mode = params.get("repair_mode", "smart")

    if music_type_override != "auto":
        music_type = music_type_override
        confidence = 1.0
    else:
        music_type, confidence, features = detect_music_type(y, sr)
        issues_found.append(f"类型检测: {music_type} ({confidence:.0%})")

    if repair_mode != "smart":
        mode_params = get_repair_mode_params(repair_mode)
        params = {**params, **mode_params}
    else:
        params = apply_music_type_params(params, music_type, confidence)

    # v2.4 HiFi 优化：节奏分析
    tempo_info = None
    tempo_params = {}
    if progress_callback:
        progress_callback(0.05, "v2.4 节奏分析...")

    try:
        tempo_analyzer = TempoAnalyzer(sr)
        tempo_info = tempo_analyzer.analyze(y)
        tempo_params = get_tempo_params(tempo_info)
        issues_found.append(f"节奏分析: {tempo_info['tempo_class']} ({tempo_info['bpm']:.0f} BPM)")
    except Exception:
        # 节奏分析失败时使用默认参数
        tempo_params = get_tempo_params({})

    if is_hifi:
        for key in params:
            if isinstance(params[key], (int, float)) and 0 < params[key] <= 1:
                params[key] *= 0.6

    active_steps = _count_active_steps(params, y.shape[0], is_hifi, tempo_info is not None)
    total_steps = active_steps + 2
    step_idx = 0

    if progress_callback:
        mode_label = "HiFi" if is_hifi else "标准"
        progress_callback(0.06, f"v2.4 {mode_label}模式处理({active_steps}步)...")

    def advance(label):
        nonlocal step_idx
        step_idx += 1
        if progress_callback:
            progress_callback(0.05 + 0.85 * step_idx / total_steps, f"v2.4 {label}...")

    if params.get("de_clipping", 0) > 0:
        y = _tanh_declip(y, params["de_clipping"])
        if "削波修复(tanh)" not in issues_found:
            issues_found.append("削波修复(tanh)")
        advance("削波修复")

    if params.get("de_pop", 0) > 0:
        y = _diff_clamp_depop(y, sr, params["de_pop"])
        if "爆音修复(diff)" not in issues_found:
            issues_found.append("爆音修复(diff)")
        advance("爆音修复")

    if params.get("transient_repair", 0) > 0:
        y = _soft_transient_limit(y, sr, params["transient_repair"])
        if "瞬态修复(soft)" not in issues_found:
            issues_found.append("瞬态修复(soft)")
        advance("瞬态修复")

    y = _adaptive_loudness_normalize(y, sr, -14.0)
    if "响度归一化(adaptive)" not in issues_found:
        issues_found.append("响度归一化(adaptive)")
    advance("响度归一化")

    # v2.4 HiFi 优化：使用新的 HiFi 多段压缩
    if params.get("dynamic_range", 0) > 0:
        y = apply_hifi_multiband_compress(
            y, sr, params["dynamic_range"], music_type, tempo_params
        )
        if "HiFi多段压缩" not in issues_found:
            issues_found.append("HiFi多段压缩")
        advance("动态处理")

    # v2.4 HiFi 优化：使用新的 HiFi AI 修复
    if params.get("ai_repair", 0) > 0:
        y = apply_hifi_ai_repair(y, sr, params["ai_repair"], tempo_params)
        if "HiFi AI频谱修复" not in issues_found:
            issues_found.append("HiFi AI频谱修复")
        advance("AI频谱修复")

    use_subband = params.get("subband_processing", False)
    if use_subband and not is_hifi:
        need_subband = (params.get("noise_reduction", 0) > 0 or
                       params.get("de_essing", 0) > 0 or
                       params.get("harmonic_enhance", 0) > 0)
        if need_subband:
            y = apply_subband_repair(y, sr, params, music_type, N_FFT, HOP_LENGTH)
            if "子带修复" not in issues_found:
                issues_found.append("子带修复")
            advance("子带修复")
    else:
        need_group_a = (params.get("de_crackle", 0) > 0 or
                        params.get("de_essing", 0) > 0 or
                        params.get("noise_reduction", 0) > 0)
        if need_group_a:
            try:
                import noisereduce as nr
                if params.get("noise_reduction", 0) > 0.5:
                    if y.ndim == 1:
                        y = nr.reduce_noise(y=y, sr=sr, stationary=False, prop_decrease=params["noise_reduction"])
                    else:
                        for ch in range(y.shape[0]):
                            y[ch] = nr.reduce_noise(y=y[ch], sr=sr, stationary=False, prop_decrease=params["noise_reduction"])
                    if "降噪(noisereduce)" not in issues_found:
                        issues_found.append("降噪(noisereduce)")
                else:
                    y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
            except ImportError:
                y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
            advance("频谱修复")

        if not is_hifi:
            need_group_b = (params.get("harmonic_enhance", 0) > 0 or
                            params.get("harmonic_richness", 0) > 0)
            if need_group_b:
                y = apply_spectral_group_b(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
                advance("谐波增强")

    if not use_subband and params.get("spatial_enhance", 0) > 0:
        y = apply_spatial_enhance_v6(y, sr, params["spatial_enhance"], music_type)
        if "空间感增强v6" not in issues_found:
            issues_found.append("空间感增强v6")
        advance("空间感")

    if not is_hifi:
        if params.get("bass_enhance", 0) > 0 and not use_subband:
            y = _harmonic_bass_enhance(y, sr, params["bass_enhance"], music_type)
            if "低频增强(harmonic)" not in issues_found:
                issues_found.append("低频增强(harmonic)")
            advance("低频增强")

        if params.get("clarity", 0) > 0 and not use_subband:
            y = _air_texture_reconstruct(y, sr, params["clarity"], music_type)
            if "空气质感重建" not in issues_found:
                issues_found.append("空气质感重建")
            advance("空气质感重建")

        if params.get("warmth", 0) > 0 and not use_subband:
            y = apply_warmth_v2(y, sr, params["warmth"], music_type)
            if "温暖度v2" not in issues_found:
                issues_found.append("温暖度v2")
            advance("温暖度")

    # v2.4 HiFi 优化：自适应细节增强（v2.4 专属）
    if not is_hifi and tempo_info is not None:
        detail_amount = params.get("detail_enhance", 0.3)
        if detail_amount > 0:
            y = apply_adaptive_detail_enhance(y, sr, detail_amount, tempo_params)
            if "自适应细节增强" not in issues_found:
                issues_found.append("自适应细节增强")
            advance("细节增强")

    # v2.4 HiFi 优化：基于节奏的立体声增强
    if y.shape[0] == 2:
        stereo_width = tempo_params.get("stereo_width", 1.0)
        if stereo_width > 1.0:
            y = apply_stereo_enhance(y, sr, stereo_width)
            if "HiFi立体声增强" not in issues_found:
                issues_found.append("HiFi立体声增强")
            advance("立体声增强")
        elif params.get("stereo_width", 0) > 0:
            y = apply_stereo_width_v3(y, sr, params["stereo_width"])
            if "立体声宽度v3" not in issues_found:
                issues_found.append("立体声宽度v3")
            advance("立体声宽度")

    if params.get("softness", 0) > 0:
        y = apply_softness_v5(y, sr, params["softness"])
        if "柔化处理v5" not in issues_found:
            issues_found.append("柔化处理v5")
        advance("柔化处理")

    if progress_callback:
        progress_callback(0.95, "v2.4 峰值限制...")

    y = _soft_peak_limit(y, threshold=0.9)

    if y.dtype == np.float32:
        y = y.astype(np.float64)

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.97, "导出WAV...")

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v2.4 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": y.shape[0] if y.ndim > 1 else 1,
        "music_type": music_type,
        "confidence": confidence,
        "quality_mode": quality_mode,
        "algorithm_version": "v2.4",
    }


def _count_active_steps(params, num_channels, is_hifi=False, has_tempo_info=False):
    count = 0
    if params.get("de_clipping", 0) > 0: count += 1
    if params.get("de_pop", 0) > 0: count += 1
    if params.get("transient_repair", 0) > 0: count += 1
    if params.get("dynamic_range", 0) > 0: count += 1
    if params.get("ai_repair", 0) > 0: count += 1
    if params.get("de_crackle", 0) > 0 or params.get("de_essing", 0) > 0 or params.get("noise_reduction", 0) > 0: count += 1

    if not is_hifi:
        if params.get("harmonic_enhance", 0) > 0 or params.get("harmonic_richness", 0) > 0: count += 1
        if params.get("bass_enhance", 0) > 0: count += 1
        if params.get("clarity", 0) > 0: count += 1
        if params.get("warmth", 0) > 0: count += 1
        # v2.4 HiFi 优化：自适应细节增强
        if has_tempo_info and params.get("detail_enhance", 0.3) > 0: count += 1

    if params.get("spatial_enhance", 0) > 0: count += 1
    # v2.4 HiFi 优化：基于节奏的立体声增强
    if num_channels == 2:
        if has_tempo_info: count += 1  # HiFi立体声增强或原有立体声宽度
        elif params.get("stereo_width", 0) > 0: count += 1
    if params.get("softness", 0) > 0: count += 1
    return count
