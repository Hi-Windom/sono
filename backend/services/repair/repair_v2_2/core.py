import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt, resample_poly
from config import MOBILE_MODE
import gc
from services.audio_loader import load_audio_with_fallback

from .music_type_detector import detect_music_type
from .type_params import apply_music_type_params, get_repair_mode_params
from .declip import apply_de_clipping_v5
from .depop import apply_de_pop_v5
from .spectral_group_a import apply_spectral_group_a
from .spectral_group_b import apply_spectral_group_b
from .transient import apply_transient_repair_v7
from .filters import apply_presence_boost_v5, apply_bass_enhance_v5, apply_warmth_v2, apply_clarity_v2
from .spatial import apply_spatial_enhance_v6, apply_stereo_width_v3
from .dynamics import apply_multiband_compression_v5, apply_softness_v5
from .postprocess import apply_loudness_normalize_v5, apply_peak_limit_v5

DESKTOP_WORKING_SR = 48000

# 优化：减小 FFT 尺寸和 hop 长度，减少计算量
# 2048/512 比 4096/1024 快约 2-3 倍，音质损失很小
N_FFT = 2048
HOP_LENGTH = 512


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    target_sr = params.get("sample_rate", sr)
    original_duration = round(y.shape[1] / sr, 2)

    # 获取处理质量模式
    quality_mode = params.get("quality", "standard")  # standard / hifi
    is_hifi = quality_mode == "hifi"

    # 优化：移动端直接使用原始采样率，避免重采样开销
    if MOBILE_MODE:
        working_sr = sr
    else:
        # 桌面端：如果采样率已经较高，不再强制提升到 48kHz
        working_sr = min(DESKTOP_WORKING_SR, sr) if sr > DESKTOP_WORKING_SR else sr

    if sr != working_sr:
        if progress_callback:
            progress_callback(0.02, f"v2.2 重采样到 {working_sr//1000}kHz...")
        target_len = int(y.shape[1] * working_sr / sr)
        y_new = np.zeros((y.shape[0], target_len))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            y_new[ch, :len(resampled)] = resampled[:target_len]
        y = y_new
        sr = working_sr
        gc.collect()

    issues_found = []

    # Music type detection
    if progress_callback:
        progress_callback(0.04, "v2.2 检测音乐类型...")

    music_type_override = params.get("music_type", "auto")
    repair_mode = params.get("repair_mode", "smart")

    if music_type_override != "auto":
        music_type = music_type_override
        confidence = 1.0
    else:
        music_type, confidence, features = detect_music_type(y, sr)
        issues_found.append(f"类型检测: {music_type} ({confidence:.0%})")

    # Apply repair mode params
    if repair_mode != "smart":
        mode_params = get_repair_mode_params(repair_mode)
        params = {**params, **mode_params}
    else:
        params = apply_music_type_params(params, music_type, confidence)

    # HiFi 模式：进一步降低处理强度
    if is_hifi:
        for key in params:
            if isinstance(params[key], (int, float)) and 0 < params[key] <= 1:
                params[key] *= 0.6  # HiFi 模式降低 40% 处理强度

    active_steps = _count_active_steps(params, y.shape[0], is_hifi)
    total_steps = active_steps + 2
    step_idx = 0

    if progress_callback:
        mode_label = "HiFi" if is_hifi else "标准"
        progress_callback(0.05, f"v2.2 {mode_label}模式处理({active_steps}步)...")

    def advance(label):
        nonlocal step_idx
        step_idx += 1
        gc.collect()
        if progress_callback:
            progress_callback(0.05 + 0.85 * step_idx / total_steps, f"v2.2 {label}...")

    # 时域修复（优先处理，保护原始波形）
    if params.get("de_clipping", 0) > 0:
        y = apply_de_clipping_v5(y, sr, params["de_clipping"])
        if "削波修复v5" not in issues_found:
            issues_found.append("削波修复v5")
        advance("削波修复")

    if params.get("de_pop", 0) > 0:
        y = apply_de_pop_v5(y, sr, params["de_pop"])
        if "爆音修复v5" not in issues_found:
            issues_found.append("爆音修复v5")
        advance("爆音修复")

    if params.get("transient_repair", 0) > 0:
        y = apply_transient_repair_v7(y, sr, params["transient_repair"])
        if "瞬态修复v7" not in issues_found:
            issues_found.append("瞬态修复v7")
        advance("瞬态修复")

    # 动态处理（在频谱处理之前，避免压缩已处理的频谱）
    if params.get("dynamic_range", 0) > 0:
        # 使用优化的 v5 压缩
        y = apply_multiband_compression_v5(y, sr, params["dynamic_range"], music_type)
        if "多段压缩v5" not in issues_found:
            issues_found.append("多段压缩v5")
        advance("动态处理")

    # 优化：频谱修复 - 合并多个处理步骤，减少 STFT/ISTFT 次数
    need_group_a = (params.get("de_crackle", 0) > 0 or
                    params.get("de_essing", 0) > 0 or
                    params.get("noise_reduction", 0) > 0)
    if need_group_a:
        y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
        advance("频谱修复")

    # 谐波增强（HiFi 模式下可选跳过）
    if not is_hifi:
        need_group_b = (params.get("harmonic_enhance", 0) > 0 or
                        params.get("harmonic_richness", 0) > 0)
        if need_group_b:
            y = apply_spectral_group_b(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
            advance("谐波增强")

    # 空间处理
    if params.get("spatial_enhance", 0) > 0:
        y = apply_spatial_enhance_v6(y, sr, params["spatial_enhance"], music_type)
        if "空间感增强v6" not in issues_found:
            issues_found.append("空间感增强v6")
        advance("空间感")

    # 音色调整（HiFi 模式下减少）
    if not is_hifi:
        if params.get("presence_boost", 0) > 0:
            y = apply_presence_boost_v5(y, sr, params["presence_boost"], music_type)
            if "临场增强v5" not in issues_found:
                issues_found.append("临场增强v5")
            advance("临场增强")

        if params.get("bass_enhance", 0) > 0:
            y = apply_bass_enhance_v5(y, sr, params["bass_enhance"], music_type)
            if "低音增强v5" not in issues_found:
                issues_found.append("低音增强v5")
            advance("低音增强")

        if params.get("warmth", 0) > 0:
            y = apply_warmth_v2(y, sr, params["warmth"], music_type)
            if "温暖度v2" not in issues_found:
                issues_found.append("温暖度v2")
            advance("温暖度")

        if params.get("clarity", 0) > 0:
            y = apply_clarity_v2(y, sr, params["clarity"], music_type)
            if "清晰度v2" not in issues_found:
                issues_found.append("清晰度v2")
            advance("清晰度")

    # 立体声宽度
    if params.get("stereo_width", 0) > 0 and y.shape[0] == 2:
        y = apply_stereo_width_v3(y, sr, params["stereo_width"])
        if "立体声宽度v3" not in issues_found:
            issues_found.append("立体声宽度v3")
        advance("立体声宽度")

    # 柔化处理（最后）
    if params.get("softness", 0) > 0:
        y = apply_softness_v5(y, sr, params["softness"])
        if "柔化处理v5" not in issues_found:
            issues_found.append("柔化处理v5")
        advance("柔化处理")

    # 重采样
    if target_sr != sr:
        if progress_callback:
            progress_callback(0.92, f"v2.2 重采样到 {target_sr//1000}kHz...")
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

    # 后期处理
    if progress_callback:
        progress_callback(0.95, "v2.2 响度归一化...")

    y = apply_loudness_normalize_v5(y, sr, -16.0)
    y = apply_peak_limit_v5(y, sr)

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.97, "导出WAV...")

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v2.2 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": y.shape[0] if y.ndim > 1 else 1,
        "music_type": music_type,
        "confidence": confidence,
        "quality_mode": quality_mode,
    }


def _count_active_steps(params, num_channels, is_hifi=False):
    count = 0
    if params.get("de_clipping", 0) > 0: count += 1
    if params.get("de_pop", 0) > 0: count += 1
    if params.get("transient_repair", 0) > 0: count += 1
    if params.get("dynamic_range", 0) > 0: count += 1
    if params.get("de_crackle", 0) > 0 or params.get("de_essing", 0) > 0 or params.get("noise_reduction", 0) > 0: count += 1
    
    if not is_hifi:
        if params.get("harmonic_enhance", 0) > 0 or params.get("harmonic_richness", 0) > 0: count += 1
        if params.get("presence_boost", 0) > 0: count += 1
        if params.get("bass_enhance", 0) > 0: count += 1
        if params.get("warmth", 0) > 0: count += 1
        if params.get("clarity", 0) > 0: count += 1
    
    if params.get("spatial_enhance", 0) > 0: count += 1
    if params.get("stereo_width", 0) > 0 and num_channels == 2: count += 1
    if params.get("softness", 0) > 0: count += 1
    return count
