import numpy as np
import soundfile as sf
import gc
from scipy.signal import resample_poly

from services.audio_loader import load_audio_with_fallback
from .config import DESKTOP_WORKING_SR, N_FFT, HOP_LENGTH, DEFAULT_PARAMS
from .spectral import _pre_analysis, _spectral_naturalize
from .transient import _transient_protect, _transient_detect
from .phase import _phase_naturalize
from .dynamic import _dynamic_naturalize, _loudness_normalize
from .utils import _soft_peak_limit, _safe_postprocess, _streaming_process, _match_loudness


def process_v3_3(y, sr, params):
    strength = params.get("strength", 1.0)

    analysis = _pre_analysis(y, sr, params)

    if params.get("spectral_naturalize", 0) > 0:
        s = params["spectral_naturalize"] * strength
        f0 = analysis.get("f0", None) if "f0" in analysis else None
        y = _spectral_naturalize(y, sr, s, f0)

    if params.get("transient_protect", 0) > 0:
        s = params["transient_protect"] * strength
        onset_mask = analysis.get("onset_mask", None)
        gain_env = _transient_protect(y, sr, s, onset_mask)
        if gain_env is not None:
            if y.ndim == 1:
                frame_len = HOP_LENGTH
                n_frames = (len(y) - frame_len) // (frame_len // 2) + 1
                if n_frames < 2:
                    pass
                else:
                    result = np.zeros_like(y)
                    overlap = np.zeros(len(y))
                    for i in range(n_frames):
                        start = i * (frame_len // 2)
                        end = min(start + frame_len, len(y))
                        gain = gain_env[i] if i < len(gain_env) else 1.0
                        result[start:end] += y[start:end] * gain
                        overlap[start:end] += 1.0
                    overlap[overlap < 1] = 1.0
                    y = (result / overlap).astype(y.dtype)
            else:
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
                        gain = gain_env[i] if i < len(gain_env) else 1.0
                        result[start:end] += y[ch, start:end] * gain
                        overlap[start:end] += 1.0
                    overlap[overlap < 1] = 1.0
                    y[ch] = (result / overlap).astype(y.dtype)

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
        progress_callback(0.05, "v3.3 加载音频...")

    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)
    issues_found = []

    working_sr = DESKTOP_WORKING_SR

    from services.memory_guard import check_memory_before_repair, should_use_float32
    working_sr = check_memory_before_repair(
        n_samples=y.shape[1],
        n_channels=y.shape[0],
        sr=sr,
        working_sr=working_sr,
        algorithm_version="v3.3",
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
        progress_callback(0.10, "v3.3 预分析...")

    merged_params = dict(DEFAULT_PARAMS)
    for k, v in params.items():
        if k in merged_params or k == "strength":
            merged_params[k] = v
    merged_params["_issues"] = issues_found

    preset = params.get("preset", "none")
    if preset in ("anti-detect", "hifi-pure", "vocal"):
        from .config import PRESETS
        if preset in PRESETS:
            for k, v in PRESETS[preset].items():
                if k in merged_params and merged_params[k] == 0:
                    merged_params[k] = v

    if progress_callback:
        progress_callback(0.15, "v3.3 处理音频...")

    def _pipeline_chunk(y_chunk, sr_chunk, p):
        return process_v3_3(y_chunk, sr_chunk, p)

    audio_len = y.shape[1]
    is_long = audio_len > 30 * sr

    if is_long:
        if progress_callback:
            progress_callback(0.20, "v3.3 流式处理...")
        y = _streaming_process(y, sr, process_v3_3, merged_params)
    else:
        y = process_v3_3(y, sr, merged_params)

    if progress_callback:
        progress_callback(0.80, "v3.3 响度匹配...")

    if params.get("loudness", 0) > 0:
        y = _match_loudness(y, sr)

    if progress_callback:
        progress_callback(0.85, "v3.3 导出...")

    y = _soft_peak_limit(y, threshold=0.95)

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if y.dtype == np.float32:
        y = y.astype(np.float64)

    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)

    channels = y.shape[0] if y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, "v3.3 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.3",
        "processing_mode": "single",
    }