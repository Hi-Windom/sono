"""v4.0a 修复算法 —— Analysis-Driven Adaptive Pipeline（移动端，单遍）。

架构升级相对 v3.2a：
  v3.2a: 固定顺序管线 if param>0: y=effect(...) —— 盲处理，参数即操作点
  v4.0a: Analyze → Adapt → Process
    1) analyzer 一次扫描出 SignalProfile（系统首次"看见"音频）
    2) adaptive 把用户意图 × profile 调制为有效操作点（干净处不处理，问题处加强）
    3) 复用 v3.2a 全部原语执行（能力 100% 保留），issues_found 反映真实检测

完全保留 v3.2a 的所有能力与优点：人声/伴奏分轨、双轨混音、母带、变速、移动端内存安全。
"""
from __future__ import annotations

import logging
import os
from typing import Any
import gc

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from services.audio_loader import load_audio_with_fallback
from services.memory_guard import check_memory_before_repair, should_use_float32

# 复用 v3.2a 全部 DSP 原语（能力保留）
from services.repair.repair_v3_2a.core import (
    MOBILE_WORKING_SR,
    REVERSE_VOCAL_MAP,
    REVERSE_INST_MAP,
    simple_declip as _v32a_declip,
    simple_depop as _v32a_depop,
    de_ess as _v32a_de_ess,
    spectral_denoise as _v32a_spectral_denoise,
    vocal_ai_repair_adaptive_lite as _v32a_ai_repair_adaptive,
    vocal_exciter_lite as _v32a_exciter,
    vocal_smart_compressor_lite as _v32a_compressor,
    transient_aware_process_lite as _v32a_transient,
    resonance_suppress_lite as _v32a_resonance,
    apply_bass_enhance_lite as _v32a_bass,
    apply_air_texture_lite as _v32a_air,
    transparent_compress as _v32a_dynamic,
    loudness_normalize as _v32a_loudness,
    soft_peak_limit,
    mastering_standard_lite,
    mastering_powerful_lite,
    mastering_warm_lite,
    mastering_adaptive_lite,
    mix_tracks,
    repair_single_track as _v32a_repair_single_track,
    repair_audio as _v32a_repair_audio,
)

logger = logging.getLogger(__name__)

from .analyzer import analyze_signal, profile_summary
from .adaptive import build_strategy

VERSION_TAG = "v4.0a"

# 单轨参数键映射（兼容前端 mapParamsToBackend 发送的单轨键 + 专业键）
_SINGLE_KEY_MAP = {
    "de_clipping": "declip", "de_pop": "depop", "de_essing": "de_ess",
    "dynamic_range": "dynamic", "spatial_enhance": "spatial",
    "loudness_optimize": "loudness",
    "ai_repair_adaptive_lite": "ai_repair_adaptive_lite",
    "ai_repair_adaptive": "ai_repair_adaptive_lite",
    "exciter": "exciter", "exciter_improved": "exciter",
    "transient": "transient", "transient_repair": "transient", "transient_aware": "transient",
    "resonance": "resonance", "resonance_suppress": "resonance",
    "bass_enhance": "bass_enhance",
    "air_texture": "air_texture", "clarity": "air_texture",
    "noise_reduction": "noise_reduction",
    "smart_compressor": "compressor", "compressor": "compressor",
    "de_esser_improved": "de_ess",
}


def _adaptive_declip(y: np.ndarray, amount: float, threshold: float = 0.90) -> np.ndarray:
    """自适应去削波：支持可变阈值，amount 控制修复强度。

    相比 v3.2a simple_declip（固定阈值 0.90），这里阈值可自适应下调，
    保护干净段的同时精准修复削波。amount∈(0,1] 控制 tanh 软拐点的强度。
    """
    if amount <= 0:
        return y
    threshold = max(0.80, min(0.99, float(threshold)))
    mask = np.abs(y) > threshold
    if not np.any(mask):
        return y
    y64 = y.astype(np.float64, copy=False)
    masked_vals = y64[mask]
    abs_masked = np.abs(masked_vals)
    over = abs_masked - threshold
    headroom = 1.0 - threshold
    strength = max(0.1, min(1.0, float(amount)))
    y64[mask] = np.sign(masked_vals) * (threshold + headroom * np.tanh(over / headroom) * strength)
    return y64.astype(y.dtype)


def _resample_to_working(y: np.ndarray, sr: int, working_sr: int) -> tuple[np.ndarray, int]:
    if sr == working_sr:
        return y, sr
    target_len = int(y.shape[1] * working_sr / sr)
    new_y = np.zeros((y.shape[0], target_len), dtype=y.dtype)
    for ch in range(y.shape[0]):
        resampled = resample_poly(y[ch], working_sr, sr)
        copy_len = min(target_len, len(resampled))
        new_y[ch, :copy_len] = resampled[:copy_len]
    return new_y, working_sr


def _apply_mastering(y: np.ndarray, working_sr: int, style: str) -> tuple[np.ndarray, str | None]:
    # 自适应母带已与标准母带合并：standard 自身即按信号画像自适应；
    # 保留 "adaptive" 别名以兼容历史参数/已保存设置，统一走合并后的标准母带。
    if style in ("standard", "adaptive"):
        return mastering_standard_lite(y, working_sr), "标准母带(自适应)"
    if style == "powerful":
        return mastering_powerful_lite(y, working_sr), "强劲母带"
    if style == "warm":
        return mastering_warm_lite(y, working_sr), "温暖母带"
    return y, None


def _make_sub_progress(parent: Any, lo: float, hi: float) -> Any:
    """把父进度回调映射到 [lo, hi] 子区间，供逐原语进度上报。"""
    if parent is None:
        return None
    span = hi - lo

    def sub(frac: float, step: str):
        f = lo + span * max(0.0, min(1.0, float(frac)))
        parent(f, step)

    return sub


def _db(x: float) -> float:
    if x <= 1e-12:
        return -120.0
    return 20.0 * np.log10(x)


def _validate_output_quality(profile, input_duration: float) -> list[str]:
    """基础质量校验：检查输出音频的关键质量指标。

    返回 quality_warning 列表（空列表表示通过校验）。
    使用已有的 profile 数据，开销 < 5%。
    """
    warnings: list[str] = []

    if profile is None:
        return ["无法获取输出信号画像"]

    rms_db = _db(profile.rms)
    if rms_db <= -60.0:
        warnings.append(f"输出近静音 (RMS={rms_db:.1f}dB)")
        logger.error(f"修复输出质量严重问题：输出近静音，RMS={rms_db:.1f}dB")

    if profile.clip_density >= 0.10:
        warnings.append(f"输出严重削波 (clip_density={profile.clip_density * 100:.1f}%)")

    if profile.duration > 0 and input_duration > 0:
        duration_diff_pct = abs(profile.duration - input_duration) / input_duration * 100.0
        if duration_diff_pct > 1.0:
            warnings.append(f"输出时长差异过大 (输入={input_duration:.2f}s, 输出={profile.duration:.2f}s, 差异={duration_diff_pct:.1f}%)")

    if warnings:
        logger.warning(f"修复输出质量警告: {', '.join(warnings)}")

    return warnings


# 各原语在 process 中的进度权重（顺序即执行顺序），用于细颗粒度上报
_STEP_LABELS = [
    ("declip", "去削波"), ("depop", "去爆音"), ("de_ess", "去齿音"),
    ("noise_reduction", "降噪"), ("ai_repair_adaptive", "自适应AI修复"),
    ("exciter", "激励器"), ("compressor", "压缩器"), ("transient", "瞬态感知"),
    ("resonance", "共振抑制"), ("bass_enhance", "低音增强"), ("air_texture", "空气感"),
    ("dynamic", "动态控制"), ("loudness", "响度优化"),
]


def process_track_adaptive(y: np.ndarray, sr: int, intent: dict, *, premium: bool = False,
                           progress: Any = None,
                           debug_output_dir: str | None = None) -> tuple[np.ndarray, list[str]]:
    """对单条轨道执行 Analyze→Adapt→Process，返回处理结果与策略说明。

    progress: 子进度回调 (frac 0~1, step)，细颗粒度上报，避免前端长间隔无更新。
    debug_output_dir: 若提供，每完成一个处理阶段后将当前音频保存到该目录
                     （文件名格式: {idx:02d}_{key}.wav），用于验证管线各环节。
    """
    # 1) Analyze
    if progress:
        progress(0.02, "分析信号画像...")
    profile = analyze_signal(y, sr)
    # 2) Adapt
    strategy = build_strategy(intent, profile, premium=premium)
    notes = list(strategy.notes)
    if profile.detected_issues:
        notes = [f"检测: {', '.join(profile.detected_issues)}"] + notes

    # 3) Process —— 复用 v3.2a 原语，但用自适应操作点
    # 变速（保留 v3.2a 能力）
    speed = float(intent.get("speed", 1.0) or 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)

    # 预建"将执行的原语"队列，按顺序上报进度（即使某原语被自适应跳过也推进一格，
    # 保证前端在长音频上每若干秒都能收到进度心跳）
    active = [(k, lbl) for (k, lbl) in _STEP_LABELS if getattr(strategy, k, 0.0) > 0]
    n_active = max(1, len(active))

    # 调试：保存原始音频（去削波预处理前）
    save_idx = 0
    if debug_output_dir:
        save_idx += 1
        sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_original.wav"),
                 y.T if y.ndim > 1 else y, sr, subtype="PCM_24")

    # 进度基线：分析后到末尾分配 0.05~0.98
    for idx, (key, label) in enumerate(active):
        if progress:
            progress(0.05 + 0.93 * (idx / n_active), f"{label}...")
        if key == "declip":
            y = _adaptive_declip(y, strategy.declip, strategy.declip_threshold)
        elif key == "depop":
            y = _v32a_depop(y, sr, strategy.depop)
        elif key == "de_ess":
            y = _v32a_de_ess(y, sr, strategy.de_ess)
        elif key == "noise_reduction":
            y = _v32a_spectral_denoise(y, sr, strategy.noise_reduction)
        elif key == "ai_repair_adaptive":
            y = _v32a_ai_repair_adaptive(y, sr, strategy.ai_repair_adaptive)
        elif key == "exciter":
            y = _v32a_exciter(y, sr, strategy.exciter)
        elif key == "compressor":
            y = _v32a_compressor(y, sr, strategy.compressor)
        elif key == "transient":
            y = _v32a_transient(y, sr, strategy.transient)
        elif key == "resonance":
            y = _v32a_resonance(y, sr, strategy.resonance)
        elif key == "bass_enhance":
            y = _v32a_bass(y, sr, strategy.bass_enhance)
        elif key == "air_texture":
            y = _v32a_air(y, sr, strategy.air_texture)
        elif key == "dynamic":
            y = _v32a_dynamic(y, sr, strategy.dynamic)
        elif key == "loudness":
            y = _v32a_loudness(y, sr, strategy.target_lufs)

        # 调试：每个阶段后保存中间结果
        if debug_output_dir:
            save_idx += 1
            sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_{key}.wav"),
                     y.T if y.ndim > 1 else y, sr, subtype="PCM_24")

    if progress:
        progress(0.99, "峰值限制...")
    y = soft_peak_limit(y, threshold=0.9)

    if debug_output_dir:
        save_idx += 1
        sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_peak_limit.wav"),
                 y.T if y.ndim > 1 else y, sr, subtype="PCM_24")

    return y, notes


def _map_flat_params(params: dict, reverse_map: dict) -> dict:
    """把扁平参数 (vocal_*/inst_*) 映射为 short-key 意图。"""
    out = {}
    for flat_key, short_key in reverse_map.items():
        if flat_key in params:
            out[short_key] = params[flat_key]
    for shared_key in ("speed",):
        if shared_key in params:
            out[shared_key] = params[shared_key]
    return out


def _map_single_params(params: dict) -> dict:
    out = dict(params)
    for sk, dk in _SINGLE_KEY_MAP.items():
        if sk in out and dk not in out:
            out[dk] = out[sk]
    return out


def _repair_single_track_v4_impl(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
    if progress_callback:
        progress_callback(0.05, f"{VERSION_TAG} 加载音频...")

    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)

    working_sr = MOBILE_WORKING_SR
    working_sr = check_memory_before_repair(
        n_samples=y.shape[1], n_channels=y.shape[0], sr=sr,
        working_sr=working_sr, algorithm_version=VERSION_TAG,
    )
    if should_use_float32(y.shape[1], y.shape[0]):
        y = y.astype(np.float32)

    y, sr = _resample_to_working(y, sr, working_sr)
    gc.collect()

    intent = _map_single_params(params)
    debug_output_dir = params.get("_debug_output_dir")

    if progress_callback:
        progress_callback(0.12, f"{VERSION_TAG} 分析信号画像...")
    sub = _make_sub_progress(progress_callback, 0.14, 0.80)
    y, notes = process_track_adaptive(y, sr, intent, premium=False, progress=sub,
                                      debug_output_dir=debug_output_dir)
    issues_found = ["单轨·自适应分析"] + notes

    mastering_style = intent.get("mastering_style", "none")
    if mastering_style != "none":
        if progress_callback:
            progress_callback(0.82, f"{VERSION_TAG} 母带处理...")
        y, mnote = _apply_mastering(y, working_sr, mastering_style)
        if mnote:
            issues_found.append(mnote)
        if debug_output_dir:
            sf.write(os.path.join(debug_output_dir, "99_mastering.wav"),
                     y.T if y.ndim > 1 else y, working_sr, subtype="PCM_24")

    if progress_callback:
        progress_callback(0.90, f"{VERSION_TAG} 导出...")

    output_volume_db = params.get("output_volume", 0.0)
    if output_volume_db != 0.0:
        volume_gain = 10 ** (output_volume_db / 20.0)
        y = (y * volume_gain).astype(y.dtype)

    y = soft_peak_limit(y, threshold=0.9)
    bit_depth = int(params.get("bit_depth", 24))
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")
    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)
    channels = y.shape[0] if y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, f"{VERSION_TAG} 修复完成")

    final_profile = analyze_signal(y, working_sr, light=True) if y.size else None
    quality_warnings = _validate_output_quality(final_profile, original_duration)

    result = {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": VERSION_TAG,
        "processing_mode": "single",
        "signal_profile": profile_summary(final_profile) if final_profile else None,
    }
    if quality_warnings:
        result["quality_warning"] = quality_warnings
    return result


def repair_single_track(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
    try:
        return _repair_single_track_v4_impl(input_path, output_path, params, progress_callback)
    except Exception as e:
        logger.warning(f"{VERSION_TAG} 单轨修复失败，降级到 v3.2a: {e}", exc_info=True)
        if progress_callback:
            progress_callback(0.0, f"{VERSION_TAG} 修复异常，降级到 v3.2a...")
        result = _v32a_repair_single_track(input_path, output_path, params, progress_callback)
        result["algorithm_version"] = f"{VERSION_TAG}(fallback:v3.2a)"
        result["fallback_reason"] = str(e)
        return result


def _repair_audio_v4_dual_impl(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
    vocal_path = params.get("vocal_path", input_path)
    accompaniment_path = params.get("accompaniment_path", input_path)

    if progress_callback:
        progress_callback(0.05, f"{VERSION_TAG} 加载人声轨...")
    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    if vocal_y.ndim == 1:
        vocal_y = vocal_y.reshape(1, -1)

    if progress_callback:
        progress_callback(0.10, f"{VERSION_TAG} 加载伴奏轨...")
    accompaniment_y, accompaniment_sr = load_audio_with_fallback(accompaniment_path, sr=None, mono=False)
    if accompaniment_y.ndim == 1:
        accompaniment_y = accompaniment_y.reshape(1, -1)

    original_duration = round(max(vocal_y.shape[1] / vocal_sr, accompaniment_y.shape[1] / accompaniment_sr), 2)
    working_sr = MOBILE_WORKING_SR
    working_sr = check_memory_before_repair(
        n_samples=vocal_y.shape[1], n_channels=vocal_y.shape[0], sr=vocal_sr,
        working_sr=working_sr, algorithm_version=VERSION_TAG,
    )
    if should_use_float32(vocal_y.shape[1], vocal_y.shape[0]):
        vocal_y = vocal_y.astype(np.float32)
        accompaniment_y = accompaniment_y.astype(np.float32)

    vocal_y, vocal_sr = _resample_to_working(vocal_y, vocal_sr, working_sr)
    accompaniment_y, accompaniment_sr = _resample_to_working(accompaniment_y, accompaniment_sr, working_sr)
    gc.collect()

    vocal_intent = _map_flat_params(params, REVERSE_VOCAL_MAP)
    inst_intent = _map_flat_params(params, REVERSE_INST_MAP)

    if progress_callback:
        progress_callback(0.20, f"{VERSION_TAG} 自适应分析+处理人声轨...")
    vocal_y, v_notes = process_track_adaptive(vocal_y, vocal_sr, vocal_intent, premium=False,
                                              progress=_make_sub_progress(progress_callback, 0.20, 0.48))

    if progress_callback:
        progress_callback(0.50, f"{VERSION_TAG} 自适应分析+处理伴奏轨...")
    accompaniment_y, i_notes = process_track_adaptive(accompaniment_y, accompaniment_sr, inst_intent, premium=False,
                                                      progress=_make_sub_progress(progress_callback, 0.50, 0.68))
    gc.collect()

    bit_depth = int(params.get("bit_depth", 24))
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if progress_callback:
        progress_callback(0.70, f"{VERSION_TAG} 保存人声修复结果...")
    vocal_output_path = params.get("vocal_output_path")
    if vocal_output_path:
        vocal_out = soft_peak_limit(vocal_y, threshold=0.9)
        if vocal_out.dtype == np.float32:
            vocal_out = vocal_out.astype(np.float64)
        sf.write(vocal_output_path, vocal_out.T if vocal_out.ndim > 1 else vocal_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.75, f"{VERSION_TAG} 保存伴奏修复结果...")
    accompaniment_output_path = params.get("accompaniment_output_path")
    if accompaniment_output_path:
        acc_out = soft_peak_limit(accompaniment_y, threshold=0.9)
        if acc_out.dtype == np.float32:
            acc_out = acc_out.astype(np.float64)
        sf.write(accompaniment_output_path, acc_out.T if acc_out.ndim > 1 else acc_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.80, f"{VERSION_TAG} 混音...")
    vocal_ratio = float(params.get("vocal_ratio", 1.0) or 1.0)
    accompaniment_ratio = float(params.get("accompaniment_ratio", 1.0) or 1.0)
    mixed = mix_tracks(vocal_y, accompaniment_y, vocal_ratio, accompaniment_ratio)

    issues_found = ["双轨·自适应分析", f"人声: {', '.join(v_notes) or '无显著问题'}",
                    f"伴奏: {', '.join(i_notes) or '无显著问题'}", "混音完成"]

    mastering_style = params.get("mastering_style", "none")
    if mastering_style != "none":
        if progress_callback:
            progress_callback(0.85, f"{VERSION_TAG} 母带处理...")
        mixed, mnote = _apply_mastering(mixed, working_sr, mastering_style)
        if mnote:
            issues_found.append(mnote)

    if progress_callback:
        progress_callback(0.90, f"{VERSION_TAG} 导出...")

    output_volume_db = params.get("output_volume", 0.0)
    if output_volume_db != 0.0:
        volume_gain = 10 ** (output_volume_db / 20.0)
        mixed = (mixed * volume_gain).astype(mixed.dtype)

    mixed = soft_peak_limit(mixed, threshold=0.9)
    if mixed.dtype == np.float32:
        mixed = mixed.astype(np.float64)
    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, f"{VERSION_TAG} 修复完成")

    final_profile = analyze_signal(mixed, working_sr, light=True) if mixed.size else None
    quality_warnings = _validate_output_quality(final_profile, original_duration)

    result = {
        "issues_found": issues_found,
        "original_sample_rate": vocal_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": mixed.shape[0] if mixed.ndim > 1 else 1,
        "algorithm_version": VERSION_TAG,
        "processing_mode": "dual",
        "signal_profile": profile_summary(final_profile) if final_profile else None,
    }
    if quality_warnings:
        result["quality_warning"] = quality_warnings
    return result


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
    processing_mode = params.get("processing_mode", "single")
    if processing_mode == "single":
        return repair_single_track(input_path, output_path, params, progress_callback)

    try:
        return _repair_audio_v4_dual_impl(input_path, output_path, params, progress_callback)
    except Exception as e:
        logger.warning(f"{VERSION_TAG} 双轨修复失败，降级到 v3.2a: {e}", exc_info=True)
        if progress_callback:
            progress_callback(0.0, f"{VERSION_TAG} 修复异常，降级到 v3.2a...")
        result = _v32a_repair_audio(input_path, output_path, params, progress_callback)
        result["algorithm_version"] = f"{VERSION_TAG}(fallback:v3.2a)"
        result["fallback_reason"] = str(e)
        return result
