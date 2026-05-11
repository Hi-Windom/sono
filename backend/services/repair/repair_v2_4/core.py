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
from .spectral_superres import apply_hifi_superres

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
    scaled = (abs_data - threshold) / headroom
    smooth = np.tanh(scaled)
    y_out = np.sign(data) * (threshold + headroom * smooth)
    return y_out


def _soft_peak_limit(y, threshold=0.9):
    if y.ndim == 1:
        return _soft_peak_limit_1d(y, threshold)
    for ch in range(y.shape[0]):
        y[ch] = _soft_peak_limit_1d(y[ch], threshold)
    return y


def _adaptive_loudness_normalize(y, sr, target_loudness_lu=-14.0):
    if y.ndim == 1:
        y_2d = y.reshape(1, -1)
        _adaptive_loudness_normalize(y_2d, sr, target_loudness_lu)
        return y
    y_64 = y.astype(np.float64)
    n_samples = y_64.shape[1]
    block_samples = int(sr * 0.4)
    overlap_samples = int(block_samples * 0.5)
    hop_samples = block_samples - overlap_samples
    if n_samples < block_samples:
        block_rms = np.sqrt(np.mean(y_64 ** 2, axis=1, keepdims=True))
        target_rms = 10 ** (target_loudness_lu / 20.0)
        gains = target_rms / (block_rms + 1e-10)
        gains = np.clip(gains, 0.1, 10.0)
        for ch in range(y_64.shape[0]):
            y_64[ch] *= gains[ch]
        y[:] = y_64.astype(y.dtype)
        return y
    gains = np.ones(y_64.shape[0])
    for ch in range(y_64.shape[0]):
        block_energies = []
        num_blocks = (n_samples - block_samples) // hop_samples + 1
        for i in range(num_blocks):
            start = i * hop_samples
            end = start + block_samples
            block = y_64[ch, start:end]
            rms = np.sqrt(np.mean(block ** 2))
            block_energies.append(rms)
        avg_energy = np.mean(block_energies) if block_energies else np.sqrt(np.mean(y_64[ch] ** 2))
        target_rms = 10 ** (target_loudness_lu / 20.0)
        gain = target_rms / (avg_energy + 1e-10)
        gain = np.clip(gain, 0.2, 5.0)
        gains[ch] = gain
    for ch in range(y_64.shape[0]):
        y_64[ch] *= gains[ch]
    y[:] = y_64.astype(y.dtype)
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

    # v2.4 使用 48kHz 工作采样率（桌面端）
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

    # v2.4 HiFi 优化：节奏分析（早期进行，影响后续处理）
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

    # 顺序按照 v2.4a 优化版：先修复，再归一化，最后增强
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

    # 降噪（使用 noisereduce 3.x，优化版）
    need_noise_process = (params.get("de_crackle", 0) > 0 or
                         params.get("de_essing", 0) > 0 or
                         params.get("noise_reduction", 0) > 0)
    if need_noise_process:
        try:
            import noisereduce as nr
            if params.get("noise_reduction", 0) > 0:
                if y.ndim == 1:
                    y = nr.reduce_noise(y=y, sr=sr, stationary=False, prop_decrease=params["noise_reduction"])
                else:
                    for ch in range(y.shape[0]):
                        y[ch] = nr.reduce_noise(y=y[ch], sr=sr, stationary=False, prop_decrease=params["noise_reduction"])
                if "降噪(noisereduce v3)" not in issues_found:
                    issues_found.append("降噪(noisereduce v3)")
            else:
                y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
        except ImportError:
            y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found, music_type)
        advance("频谱降噪")

    # v2.4 HiFi AI 频谱修复 + 超分（核心新增功能）
    if params.get("ai_repair", 0) > 0:
        y = apply_hifi_ai_repair(y, sr, params["ai_repair"], tempo_params)
        if "HiFi AI频谱修复" not in issues_found:
            issues_found.append("HiFi AI频谱修复")
        advance("AI频谱修复")

    # 新增：AI 超分/频谱重建（类似 QQ 音乐臻品母带）
    superres_amount = params.get("spectral_superres", 0.4)
    if not is_hifi and superres_amount > 0:
        y = apply_hifi_superres(y, sr, superres_amount, tempo_params)
        if "HiFi频谱超分" not in issues_found:
            issues_found.append("HiFi频谱超分")
        advance("频谱超分")

    # 响度归一化（放在降噪之后，压缩之前）
    y = _adaptive_loudness_normalize(y, sr, -14.0)
    if "响度归一化(adaptive)" not in issues_found:
        issues_found.append("响度归一化(adaptive)")
    advance("响度归一化")

    # v2.4 HiFi 优化：使用新的 HiFi 多段压缩（BPM 自适应）
    if params.get("dynamic_range", 0) > 0:
        y = apply_hifi_multiband_compress(
            y, sr, params["dynamic_range"], music_type, tempo_params
        )
        if "HiFi多段压缩" not in issues_found:
            issues_found.append("HiFi多段压缩")
        advance("动态处理")

    if not is_hifi:
        if params.get("bass_enhance", 0) > 0:
            y = _harmonic_bass_enhance(y, sr, params["bass_enhance"], music_type)
            if "低频增强(harmonic)" not in issues_found:
                issues_found.append("低频增强(harmonic)")
            advance("低频增强")

        if params.get("clarity", 0) > 0:
            y = _air_texture_reconstruct(y, sr, params["clarity"], music_type)
            if "空气质感重建" not in issues_found:
                issues_found.append("空气质感重建")
            advance("空气质感重建")

        if params.get("warmth", 0) > 0:
            y = apply_warmth_v2(y, sr, params["warmth"], music_type)
            if "温暖度v2" not in issues_found:
                issues_found.append("温暖度v2")
            advance("温暖度")

    # v2.4 HiFi 优化：自适应细节增强（放在后面）
    if not is_hifi and tempo_info is not None:
        detail_amount = params.get("detail_enhance", 0.3)
        if detail_amount > 0:
            y = apply_adaptive_detail_enhance(y, sr, detail_amount, tempo_params)
            if "自适应细节增强" not in issues_found:
                issues_found.append("自适应细节增强")
            advance("细节增强")

    if not is_hifi and params.get("spatial_enhance", 0) > 0:
        y = apply_spatial_enhance_v6(y, sr, params["spatial_enhance"], music_type)
        if "空间感增强v6" not in issues_found:
            issues_found.append("空间感增强v6")
        advance("空间感")

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
    if params.get("de_crackle", 0) > 0 or params.get("de_essing", 0) > 0 or params.get("noise_reduction", 0) > 0: count += 1
    if params.get("ai_repair", 0) > 0: count += 1
    # v2.4 HiFi 优化：频谱超分
    if not is_hifi and params.get("spectral_superres", 0.4) > 0: count += 1
    if params.get("dynamic_range", 0) > 0: count += 1

    if not is_hifi:
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
