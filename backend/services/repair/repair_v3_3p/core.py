import numpy as np
import soundfile as sf
import gc
from scipy.signal import resample_poly

from services.audio_loader import load_audio_with_fallback
from services.dsp_utils import stft, istft
from services.repair.repair_v3_3.spectral import _pre_analysis, _spectral_naturalize
from services.repair.repair_v3_3.transient import _transient_protect
from services.repair.repair_v3_3.phase import _phase_naturalize
from services.repair.repair_v3_3.dynamic import _dynamic_naturalize
from services.repair.repair_v3_3.utils import _soft_peak_limit, _safe_postprocess, _streaming_process, _match_loudness
from .config import DESKTOP_WORKING_SR, N_FFT, HOP_LENGTH, DEFAULT_PARAMS, PRESETS


def _f0_track(y, sr):
    if y.ndim == 2:
        y_mono = np.mean(y, axis=0)
    else:
        y_mono = y
    frame_len = int(2048)
    hop = int(512)
    n_frames = (len(y_mono) - frame_len) // hop + 1
    if n_frames < 2:
        return np.zeros(n_frames)
    f0_out = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop
        frame = y_mono[start:start + frame_len] * np.hanning(frame_len)
        ac = np.correlate(frame, frame, mode='same')
        mid = len(ac) // 2
        min_lag = int(sr / 1000)
        max_lag = int(sr / 50)
        if max_lag >= mid:
            max_lag = mid - 1
        segment = ac[mid + min_lag:mid + max_lag + 1]
        if len(segment) < 2:
            continue
        peak_idx = np.argmax(segment) + min_lag
        if peak_idx > 0 and segment[np.argmax(segment)] > np.max(ac) * 0.3:
            f0_out[i] = sr / peak_idx
    return f0_out


def _f0_guided_harmonic_process(y, sr, strength, f0):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        S = stft(y_in, n_fft=N_FFT, hop_length=HOP_LENGTH)
        n_bins, n_frames = S.shape
        freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
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
            for h in range(1, min(max_harmonic + 1, 20)):
                target_freq = h * current_f0
                target_bin = int(np.round(target_freq * N_FFT / sr))
                if target_bin < 1 or target_bin >= n_bins - 1:
                    continue
                mag = np.abs(S[target_bin, f])
                phase = np.angle(S[target_bin, f])
                boost = 1.0 + strength * 0.15
                S[target_bin, f] = mag * boost * np.exp(1j * phase)
                if target_bin > 1:
                    S[target_bin - 1, f] *= 1.0 + strength * 0.05
                if target_bin < n_bins - 2:
                    S[target_bin + 1, f] *= 1.0 + strength * 0.05
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
            ch_out = _f0_guided_harmonic_process(y_in[ch], sr, strength, f0)
            results.append(ch_out)
        return np.stack(results).astype(original_dtype)


def _perceptual_weight_process(y, sr, strength):
    if strength <= 0:
        return y
    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64)
        n = len(y_in)
        S = stft(y_in, n_fft=N_FFT, hop_length=HOP_LENGTH)
        n_bins = S.shape[0]
        freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
        weights = np.ones(n_bins)
        low_mask = freqs < 500
        mid_mask = (freqs >= 500) & (freqs <= 4000)
        high_mask = freqs > 4000
        weights[low_mask] = 0.8
        weights[mid_mask] = 1.0
        weights[high_mask] = 1.2
        weights = 1.0 + (weights - 1.0) * strength
        mag = np.abs(S)
        phase = np.angle(S)
        S = (mag * weights[:, np.newaxis]) * np.exp(1j * phase)
        y_out = istft(S, hop_length=HOP_LENGTH, length=n)
        if len(y_out) < n:
            y_out = np.pad(y_out, (0, n - len(y_out)))
        elif len(y_out) > n:
            y_out = y_out[:n]
        return y_out.astype(original_dtype)
    else:
        y_in = y.astype(np.float64)
        results = []
        for ch in range(y_in.shape[0]):
            ch_out = _perceptual_weight_process(y_in[ch], sr, strength)
            results.append(ch_out)
        return np.stack(results).astype(original_dtype)


def process_v3_3p(y, sr, params):
    strength = params.get("strength", 1.0)
    analysis = _pre_analysis(y, sr, params)
    f0 = analysis.get("f0", None)
    if isinstance(f0, list):
        if len(f0) > 0 and hasattr(f0[0], '__len__'):
            f0 = np.mean(f0, axis=0)
        elif len(f0) > 0:
            f0 = np.asarray(f0)
    if isinstance(f0, np.ndarray) and f0.ndim > 1:
        f0 = np.mean(f0, axis=0)
    if f0 is not None and hasattr(f0, '__len__') and len(f0) == 0:
        f0 = None
    if params.get("spectral_naturalize", 0) > 0:
        s = params["spectral_naturalize"] * strength
        y = _spectral_naturalize(y, sr, s, f0)
    if params.get("transient_protect", 0) > 0:
        s = params["transient_protect"] * strength
        onset_mask = analysis.get("onset_mask", None)
        gain_env = _transient_protect(y, sr, s, onset_mask)
        if gain_env is not None and y.ndim == 1:
            frame_len = HOP_LENGTH
            n_frames = (len(y) - frame_len) // (frame_len // 2) + 1
            if n_frames >= 2:
                result = np.zeros_like(y)
                overlap = np.zeros(len(y))
                for i in range(n_frames):
                    start = i * (frame_len // 2)
                    end = min(start + frame_len, len(y))
                    g = gain_env[i] if i < len(gain_env) else 1.0
                    result[start:end] += y[start:end] * g
                    overlap[start:end] += 1.0
                overlap[overlap < 1] = 1.0
                y = (result / overlap).astype(y.dtype)
        elif gain_env is not None and y.ndim == 2:
            for ch in range(y.shape[0]):
                frame_len = HOP_LENGTH
                n_frames = (y.shape[1] - frame_len) // (frame_len // 2) + 1
                if n_frames < 2:
                    continue
                result = np.zeros(y.shape[1])
                overlap = np.zeros(y.shape[1])
                for i in range(n_frames):
                    start = i * (frame_len // 2)
                    end = min(start + frame_len, y.shape[1])
                    g = gain_env[i] if i < len(gain_env) else 1.0
                    result[start:end] += y[ch, start:end] * g
                    overlap[start:end] += 1.0
                overlap[overlap < 1] = 1.0
                y[ch] = (result / overlap).astype(y.dtype)
    if params.get("f0_guided_depth", 0) > 0:
        s = params["f0_guided_depth"] * strength
        if f0 is None:
            f0 = _f0_track(y, sr)
        y = _f0_guided_harmonic_process(y, sr, s, f0)
    if params.get("perceptual_weight", 0) > 0:
        s = params["perceptual_weight"] * strength
        y = _perceptual_weight_process(y, sr, s)
    if params.get("phase_naturalize", 0) > 0:
        s = params["phase_naturalize"] * strength
        y = _phase_naturalize(y, sr, s)
    if params.get("dynamic_naturalize", 0) > 0:
        s = params["dynamic_naturalize"] * strength
        y = _dynamic_naturalize(y, sr, s)
    y = _safe_postprocess(y, sr, params)
    return y


def repair_audio(input_path, output_path, params, progress_callback=None):
    if progress_callback:
        progress_callback(0.05, "v3.3+ 加载音频...")
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)
    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)
    issues_found = []
    working_sr = DESKTOP_WORKING_SR
    from services.memory_guard import check_memory_before_repair, should_use_float32
    working_sr = check_memory_before_repair(
        n_samples=y.shape[1], n_channels=y.shape[0], sr=sr,
        working_sr=working_sr, algorithm_version="v3.3+",
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
    if progress_callback:
        progress_callback(0.10, "v3.3+ 预分析...")
    merged_params = dict(DEFAULT_PARAMS)
    for k, v in params.items():
        if k in merged_params or k in ("strength", "preset", "f0_guided_depth", "perceptual_weight"):
            merged_params[k] = v
    merged_params["_issues"] = issues_found
    preset = params.get("preset", "none")
    if preset in PRESETS:
        for k, v in PRESETS[preset].items():
            if k in merged_params and merged_params[k] == 0:
                merged_params[k] = v
    if progress_callback:
        progress_callback(0.15, "v3.3+ 处理音频...")
    y = process_v3_3p(y, sr, merged_params)
    if progress_callback:
        progress_callback(0.80, "v3.3+ 响度匹配...")
    if params.get("loudness", 0) > 0:
        y = _match_loudness(y, sr)
    if progress_callback:
        progress_callback(0.85, "v3.3+ 导出...")
    y = _soft_peak_limit(y, threshold=0.95)
    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")
    if y.dtype == np.float32:
        y = y.astype(np.float64)
    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)
    channels = y.shape[0] if y.ndim > 1 else 1
    if progress_callback:
        progress_callback(1.0, "v3.3+ 修复完成")
    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.3+",
        "processing_mode": "single",
    }