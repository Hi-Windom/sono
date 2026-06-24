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
)

from .analyzer import analyze_signal, profile_summary
from .adaptive import build_strategy

VERSION_TAG = "v4.0a"

# 单轨参数键映射（与 v3.2a 一致）
_SINGLE_KEY_MAP = {
    "de_clipping": "declip", "de_pop": "depop", "de_essing": "de_ess",
    "dynamic_range": "dynamic", "spatial_enhance": "spatial",
    "loudness_optimize": "loudness",
    "ai_repair_adaptive_lite": "ai_repair_adaptive_lite",
    "exciter": "exciter",
    "transient": "transient",
    "resonance": "resonance",
    "bass_enhance": "bass_enhance",
    "air_texture": "air_texture",
    "noise_reduction": "noise_reduction",
    "smart_compressor": "smart_compressor",
    "compressor": "compressor",
}


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
    if style == "standard":
        return mastering_standard_lite(y, working_sr), "标准母带"
    if style == "powerful":
        return mastering_powerful_lite(y, working_sr), "强劲母带"
    if style == "warm":
        return mastering_warm_lite(y, working_sr), "温暖母带"
    if style == "adaptive":
        return mastering_adaptive_lite(y, working_sr), "自适应母带"
    return y, None


def process_track_adaptive(y: np.ndarray, sr: int, intent: dict, *, premium: bool = False) -> tuple[np.ndarray, list[str]]:
    """对单条轨道执行 Analyze→Adapt→Process，返回处理结果与策略说明。"""
    # 1) Analyze
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

    if strategy.declip > 0:
        # 自适应阈值通过临时包装实现：v3.2a simple_declip 阈值固定 0.90，
        # 这里在调用前对超阈值样本预衰减以等效下移阈值（保护干净段）。
        if strategy.declip_threshold < 0.90:
            thr = strategy.declip_threshold
            over = np.abs(y) > thr
            if np.any(over):
                # 等效：把 [thr,1] 段软压到 [thr, thr+0.05]，使 simple_declip 在 0.90 处只处理真正满幅
                y = y.astype(np.float64, copy=False)
                mag = np.abs(y)
                scale = np.where(over, thr + 0.05 * np.tanh((mag - thr) / 0.05) / max(1e-6, np.tanh((1.0 - thr) / 0.05)), mag)
                y = y / np.maximum(mag, 1e-9) * scale
                if y.dtype != np.float64:
                    y = y.astype(np.float64)
        y = _v32a_declip(y, strategy.declip)

    if strategy.depop > 0:
        y = _v32a_depop(y, sr, strategy.depop)

    if strategy.de_ess > 0:
        y = _v32a_de_ess(y, sr, strategy.de_ess)

    if strategy.noise_reduction > 0:
        y = _v32a_spectral_denoise(y, sr, strategy.noise_reduction)

    if strategy.ai_repair_adaptive > 0:
        y = _v32a_ai_repair_adaptive(y, sr, strategy.ai_repair_adaptive)

    if strategy.exciter > 0:
        y = _v32a_exciter(y, sr, strategy.exciter)

    if strategy.compressor > 0:
        y = _v32a_compressor(y, sr, strategy.compressor)

    if strategy.transient > 0:
        y = _v32a_transient(y, sr, strategy.transient)

    if strategy.resonance > 0:
        y = _v32a_resonance(y, sr, strategy.resonance)

    if strategy.bass_enhance > 0:
        y = _v32a_bass(y, sr, strategy.bass_enhance)

    if strategy.air_texture > 0:
        y = _v32a_air(y, sr, strategy.air_texture)

    if strategy.dynamic > 0:
        y = _v32a_dynamic(y, sr, strategy.dynamic)

    if strategy.loudness > 0:
        y = _v32a_loudness(y, sr, strategy.target_lufs)

    y = soft_peak_limit(y, threshold=0.9)
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


def repair_single_track(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
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

    if progress_callback:
        progress_callback(0.12, f"{VERSION_TAG} 分析信号画像...")

    y, notes = process_track_adaptive(y, sr, intent, premium=False)
    issues_found = ["单轨·自适应分析"] + notes

    mastering_style = intent.get("mastering_style", "none")
    if mastering_style != "none":
        if progress_callback:
            progress_callback(0.82, f"{VERSION_TAG} 母带处理...")
        y, mnote = _apply_mastering(y, working_sr, mastering_style)
        if mnote:
            issues_found.append(mnote)

    if progress_callback:
        progress_callback(0.90, f"{VERSION_TAG} 导出...")

    y = soft_peak_limit(y, threshold=0.9)
    bit_depth = int(params.get("bit_depth", 24))
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")
    if y.dtype == np.float32:
        y = y.astype(np.float64)
    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)
    channels = y.shape[0] if y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, f"{VERSION_TAG} 修复完成")

    # 回传真实检测画像（前端可展示）
    final_profile = analyze_signal(y, working_sr) if y.size else None
    return {
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


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
    processing_mode = params.get("processing_mode", "single")
    if processing_mode == "single":
        return repair_single_track(input_path, output_path, params, progress_callback)

    # —— 双轨：人声/伴奏分别 Analyze→Adapt→Process，再混音+母带 ——
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
    vocal_y, v_notes = process_track_adaptive(vocal_y, vocal_sr, vocal_intent, premium=False)

    if progress_callback:
        progress_callback(0.50, f"{VERSION_TAG} 自适应分析+处理伴奏轨...")
    accompaniment_y, i_notes = process_track_adaptive(accompaniment_y, accompaniment_sr, inst_intent, premium=False)
    gc.collect()

    bit_depth = int(params.get("bit_depth", 24))
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    # 保存分轨修复结果（保留 v3.2a 能力）
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
    mixed = soft_peak_limit(mixed, threshold=0.9)
    if mixed.dtype == np.float32:
        mixed = mixed.astype(np.float64)
    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, f"{VERSION_TAG} 修复完成")

    final_profile = analyze_signal(mixed, working_sr) if mixed.size else None
    return {
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
