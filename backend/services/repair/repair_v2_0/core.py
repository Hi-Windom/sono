import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt, resample_poly
from config import MOBILE_MODE
import gc
from services.audio_loader import load_audio_with_fallback

from services.repair.repair_v2_0.declip import apply_de_clipping_v4
from services.repair.repair_v2_0.depop import apply_de_pop_v4
from services.repair.repair_v2_0.spectral_group_a import apply_spectral_group_a
from services.repair.repair_v2_0.spectral_group_b import apply_spectral_group_b
from services.repair.repair_v2_0.transient import apply_transient_repair_v4
from services.repair.repair_v2_0.filters import apply_presence_boost_v4, apply_bass_enhance_v4, apply_warmth, apply_clarity
from services.repair.repair_v2_0.spatial import apply_spatial_enhance_v5, apply_stereo_width_v2
from services.repair.repair_v2_0.dynamics import apply_multiband_compression_v2, apply_softness_v2
from services.repair.repair_v2_0.postprocess import apply_loudness_normalize_v3, apply_peak_limit_v3

DESKTOP_WORKING_SR = 48000

N_FFT = 4096
HOP_LENGTH = 1024


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    target_sr = params.get("sample_rate", sr)
    original_duration = round(y.shape[1] / sr, 2)

    if MOBILE_MODE:
        working_sr = sr
    else:
        working_sr = DESKTOP_WORKING_SR if sr < DESKTOP_WORKING_SR else sr

    if sr != working_sr:
        if progress_callback:
            progress_callback(0.02, f"v2.0 重采样到 {working_sr//1000}kHz...")
        target_len = int(y.shape[1] * working_sr / sr)
        y_new = np.zeros((y.shape[0], target_len))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            y_new[ch, :len(resampled)] = resampled[:target_len]
        y = y_new
        sr = working_sr
        gc.collect()

    issues_found = []
    active_steps = _count_active_steps(params, y.shape[0])
    total_steps = active_steps + 2
    step_idx = 0

    if progress_callback:
        progress_callback(0.05, f"v2.0 处理({active_steps}步)...")

    def advance(label):
        nonlocal step_idx
        step_idx += 1
        gc.collect()
        if progress_callback:
            progress_callback(0.05 + 0.85 * step_idx / total_steps, f"v2.0 {label}...")

    if params.get("de_clipping", 0) > 0:
        y = apply_de_clipping_v4(y, sr, params["de_clipping"])
        if "削波修复v4" not in issues_found:
            issues_found.append("削波修复v4")
        advance("削波修复v4")

    if params.get("de_pop", 0) > 0:
        y = apply_de_pop_v4(y, sr, params["de_pop"])
        if "爆音修复v4" not in issues_found:
            issues_found.append("爆音修复v4")
        advance("爆音修复v4")

    if params.get("transient_repair", 0) > 0:
        y = apply_transient_repair_v4(y, sr, params["transient_repair"])
        if "瞬态修复v4" not in issues_found:
            issues_found.append("瞬态修复v4")
        advance("瞬态修复v4")

    need_group_a = (params.get("de_crackle", 0) > 0 or
                    params.get("de_essing", 0) > 0 or
                    params.get("noise_reduction", 0) > 0)
    if need_group_a:
        y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found)
        advance("频谱修复")

    need_group_b = (params.get("harmonic_enhance", 0) > 0 or
                    params.get("harmonic_richness", 0) > 0)
    if need_group_b:
        y = apply_spectral_group_b(y, sr, params, N_FFT, HOP_LENGTH, issues_found)
        advance("谐波增强")

    if params.get("spatial_enhance", 0) > 0:
        y = apply_spatial_enhance_v5(y, sr, params["spatial_enhance"])
        if "空间感增强v5" not in issues_found:
            issues_found.append("空间感增强v5")
        advance("空间感增强v5")

    if params.get("presence_boost", 0) > 0:
        y = apply_presence_boost_v4(y, sr, params["presence_boost"])
        if "临场增强v4" not in issues_found:
            issues_found.append("临场增强v4")
        advance("临场增强v4")

    if params.get("bass_enhance", 0) > 0:
        y = apply_bass_enhance_v4(y, sr, params["bass_enhance"])
        if "低音增强v4" not in issues_found:
            issues_found.append("低音增强v4")
        advance("低音增强v4")

    if params.get("warmth", 0) > 0:
        y = apply_warmth(y, sr, params["warmth"])
        if "温暖度" not in issues_found:
            issues_found.append("温暖度")
        advance("温暖度")

    if params.get("clarity", 0) > 0:
        y = apply_clarity(y, sr, params["clarity"])
        if "清晰度" not in issues_found:
            issues_found.append("清晰度")
        advance("清晰度")

    if params.get("dynamic_range", 0) > 0:
        y = apply_multiband_compression_v2(y, sr, params["dynamic_range"])
        if "多段压缩v4" not in issues_found:
            issues_found.append("多段压缩v4")
        advance("多段压缩v4")

    if params.get("stereo_width", 0) > 0 and y.shape[0] == 2:
        y = apply_stereo_width_v2(y, sr, params["stereo_width"])
        if "立体声宽度v2" not in issues_found:
            issues_found.append("立体声宽度v2")
        advance("立体声宽度v2")

    if params.get("softness", 0) > 0:
        y = apply_softness_v2(y, sr, params["softness"])
        if "柔化处理v2" not in issues_found:
            issues_found.append("柔化处理v2")
        advance("柔化处理v2")

    if target_sr != sr:
        if progress_callback:
            progress_callback(0.92, f"v2.0 重采样到 {target_sr//1000}kHz...")
        if target_sr < sr:
            nyquist = target_sr / 2
            cutoff = nyquist * 0.95
            b, a = butter(6, cutoff / (sr / 2), btype='low')
            for ch in range(y.shape[0]):
                y[ch] = filtfilt(b, a, y[ch])
        y_resampled = np.zeros((y.shape[0], int(y.shape[1] * target_sr / sr)))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], target_sr, sr)
            y_resampled[ch, :len(resampled)] = resampled[:y_resampled.shape[1]]
        y = y_resampled
        sr = target_sr
        gc.collect()

    if progress_callback:
        progress_callback(0.95, "v2.0 响度归一化...")

    y = apply_loudness_normalize_v3(y, sr, -16.0)
    y = apply_peak_limit_v3(y, sr)

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.97, "导出WAV...")

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v2.0 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": y.shape[0] if y.ndim > 1 else 1,
    }


def _count_active_steps(params, num_channels):
    count = 0
    if params.get("de_clipping", 0) > 0: count += 1
    if params.get("de_pop", 0) > 0: count += 1
    if params.get("transient_repair", 0) > 0: count += 1
    if params.get("de_crackle", 0) > 0 or params.get("de_essing", 0) > 0 or params.get("noise_reduction", 0) > 0: count += 1
    if params.get("harmonic_enhance", 0) > 0 or params.get("harmonic_richness", 0) > 0: count += 1
    if params.get("spatial_enhance", 0) > 0: count += 1
    if params.get("presence_boost", 0) > 0: count += 1
    if params.get("bass_enhance", 0) > 0: count += 1
    if params.get("warmth", 0) > 0: count += 1
    if params.get("clarity", 0) > 0: count += 1
    if params.get("dynamic_range", 0) > 0: count += 1
    if params.get("stereo_width", 0) > 0 and num_channels == 2: count += 1
    if params.get("softness", 0) > 0: count += 1
    return count
