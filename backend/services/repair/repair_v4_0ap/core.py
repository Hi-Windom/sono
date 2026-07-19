"""v4.0a+ 修复算法 —— 移动端增强版：两遍验证 + 前视压缩（Analysis-Driven Adaptive Pipeline Premium）。

相对 v4.0a 的增量：
  1) 两遍验证(Two-pass verify)：第一遍自适应修复后，对结果再次画像，仅在残差超阈值处
     触发针对性二次校正，避免对已干净区域的过处理（v3.2a 无此机制）。
  2) 前视压缩器(Lookahead compressor)：用 lookahead delay 预读包络，实现无伪影的瞬态感知
     压缩，替代 v3.2a 即时包络压缩的过冲问题。
完全复用 v4.0a 的 analyzer/adaptive 与 v3.2a 原语，能力 100% 保留。
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

from services.repair.repair_v3_2a.core import (
    MOBILE_WORKING_SR,
    REVERSE_VOCAL_MAP,
    REVERSE_INST_MAP,
    soft_peak_limit,
    mastering_standard_lite,
    mastering_powerful_lite,
    mastering_warm_lite,
    mastering_adaptive_lite,
    mix_tracks,
    simple_declip as _v32a_declip,
    de_ess as _v32a_de_ess,
    spectral_denoise as _v32a_spectral_denoise,
    vocal_exciter_lite as _v32a_exciter,
    apply_bass_enhance_lite as _v32a_bass,
    apply_air_texture_lite as _v32a_air,
    transparent_compress as _v32a_dynamic,
    loudness_normalize as _v32a_loudness,
    repair_single_track as _v32a_repair_single_track,
    repair_audio as _v32a_repair_audio,
)

from services.repair.repair_v4_0a.core import (
    _resample_to_working,
    _map_flat_params,
    _map_single_params,
    _apply_mastering,
    _make_sub_progress,
    _SINGLE_KEY_MAP,
    _adaptive_declip,
    _validate_output_quality,
)
from services.repair.repair_v4_0a.analyzer import analyze_signal, profile_summary
from services.repair.repair_v4_0a.adaptive import build_strategy

logger = logging.getLogger(__name__)

VERSION_TAG = "v4.0a+"


def lookahead_compress(y: np.ndarray, sr: int, amount: float, *,
                        lookahead_ms: float = 5.0, threshold_db: float = -18.0,
                        ratio: float = 2.5) -> np.ndarray:
    """前视压缩器：lookahead delay 预读包络，瞬态响应无过冲。

    相对 v3.2a 即时包络压缩：避免前导过冲(transient overshoot)，更自然。
    amount∈(0,1] 控制压缩深度。
    """
    if amount <= 0:
        return y
    if y.ndim == 1:
        return _lookahead_compress_1d(y, sr, amount, lookahead_ms, threshold_db, ratio)
    out = np.empty_like(y, dtype=np.float64)
    for ch in range(y.shape[0]):
        out[ch] = _lookahead_compress_1d(y[ch].astype(np.float64), sr, amount, lookahead_ms, threshold_db, ratio)
    return out


def _lookahead_compress_1d(x: np.ndarray, sr: int, amount: float, lookahead_ms: float,
                           threshold_db: float, ratio: float) -> np.ndarray:
    n = len(x)
    lookahead = max(1, int(sr * lookahead_ms / 1000.0))
    # 环境友好：长音频用平滑窗估计包络
    win = max(1, int(sr * 0.005))  # 5ms 攻击窗
    x64 = x.astype(np.float64, copy=False)
    sq = np.square(x64)
    # 移动平均包络（近似 RMS）—— 用 cumsum O(n) 替代 convolve，省内存
    csum = np.concatenate(([0.0], np.cumsum(sq)))
    env = (csum[win:] - csum[:-win]) / win
    # 对齐到与输入等长（前 win-1 个用首个有效值填充）
    if env.size < n:
        env = np.concatenate((np.full(n - env.size, env[0] if env.size else 0.0), env))
    else:
        env = env[:n]
    del sq, csum
    env_db = 10.0 * np.log10(env + 1e-12)
    # 前视：把包络向后平移 lookahead，使增益在瞬态到达前已就位
    env_db_shifted = np.empty_like(env_db)
    env_db_shifted[:-lookahead] = env_db[lookahead:]
    env_db_shifted[-lookahead:] = env_db[-1]
    del env, env_db

    thr = threshold_db
    over = env_db_shifted > thr
    # 压缩增益（dB）：超阈部分按 ratio 压缩，amount 控制混合比例
    gain_db = np.zeros_like(env_db_shifted)
    if np.any(over):
        gain_db[over] = -(env_db_shifted[over] - thr) * (1.0 - 1.0 / ratio) * amount
    del env_db_shifted
    gain_lin = np.power(10.0, gain_db / 20.0)
    del gain_db
    # 释放平滑（一阶 IIR）—— 向量化：等价于 lfilter([1-smooth],[1,-smooth], gain_lin)
    smooth = 0.85
    from scipy.signal import lfilter
    gain_lin = lfilter(np.array([1.0 - smooth]), np.array([1.0, -smooth]), gain_lin)
    # 补偿前视延迟
    out = np.zeros(n, dtype=np.float64)
    out[lookahead:] = x64[:-lookahead] * gain_lin[lookahead:]
    out[:lookahead] = x64[:lookahead] * gain_lin[:lookahead]
    return out


def process_track_adaptive_premium(y: np.ndarray, sr: int, intent: dict,
                                   progress: Any = None,
                                   debug_output_dir: str | None = None) -> tuple[np.ndarray, list[str]]:
    """v4.0a+ 单轨：Analyze→Adapt→Process(pass1)→Re-analyze→Targeted verify(pass2)。

    debug_output_dir: 若提供，每完成一个处理阶段后将当前音频保存到该目录。
    """
    # Pass 1: 自适应修复（与 v4.0a 一致，但 premium=True 触发更激进调制）
    if progress:
        progress(0.02, "分析信号画像...")
    profile1 = analyze_signal(y, sr)
    strategy = build_strategy(intent, profile1, premium=True)
    notes = [f"检测: {', '.join(profile1.detected_issues) or '无显著问题'}"] + list(strategy.notes)

    speed = float(intent.get("speed", 1.0) or 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)

    # 调试：保存原始音频
    save_idx = 0
    if debug_output_dir:
        save_idx += 1
        sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_original.wav"),
                 y.T if y.ndim > 1 else y, sr, subtype="PCM_24")

    # 逐原语上报进度（pass1 占 0.05~0.70）
    _pass1_steps = [
        ("declip", "去削波", lambda: _adaptive_declip(y, strategy.declip, strategy.declip_threshold)),
        ("depop", "去爆音", lambda: _depop(y, sr, strategy.depop)),
        ("de_ess", "去齿音", lambda: _v32a_de_ess(y, sr, strategy.de_ess)),
        ("noise_reduction", "降噪", lambda: _v32a_spectral_denoise(y, sr, strategy.noise_reduction)),
        ("ai_repair_adaptive", "自适应AI修复", lambda: _ai_repair(y, sr, strategy.ai_repair_adaptive)),
        ("exciter", "激励器", lambda: _v32a_exciter(y, sr, strategy.exciter)),
        ("compressor", "前视压缩", lambda: lookahead_compress(y, sr, strategy.compressor)),
        ("transient", "瞬态感知", lambda: _transient(y, sr, strategy.transient)),
        ("resonance", "共振抑制", lambda: _resonance(y, sr, strategy.resonance)),
        ("bass_enhance", "低音增强", lambda: _v32a_bass(y, sr, strategy.bass_enhance)),
        ("air_texture", "空气感", lambda: _v32a_air(y, sr, strategy.air_texture)),
        ("dynamic", "动态控制", lambda: _v32a_dynamic(y, sr, strategy.dynamic)),
        ("loudness", "响度优化", lambda: _v32a_loudness(y, sr, strategy.target_lufs)),
    ]
    active = [(key, lbl, fn) for (key, lbl, fn) in _pass1_steps if getattr(strategy, key, 0.0) > 0]
    n_active = max(1, len(active))
    # 延迟求值：用可变 y，闭包捕获策略值
    for idx, (key, lbl, fn) in enumerate(active):
        if progress:
            progress(0.05 + 0.65 * (idx / n_active), f"{lbl}...")
        y = fn()
        if debug_output_dir:
            save_idx += 1
            sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_{key}.wav"),
                     y.T if y.ndim > 1 else y, sr, subtype="PCM_24")

    # Pass 2: 验证 —— 仅在残差问题超阈值时做针对性校正（占 0.72~0.95）
    if strategy.needs_verify and y.size:
        if progress:
            progress(0.72, "二遍验证扫描...")
        residual = analyze_signal(y, sr)
        verify_notes: list[str] = []
        v_idx = 0
        if residual.has_clipping(threshold=0.003) and strategy.declip > 0:
            if progress:
                progress(0.78, "二遍清除残留削波...")
            y = _adaptive_declip(y, strategy.declip * 0.5, strategy.declip_threshold)
            verify_notes.append("二遍清除残留削波")
            if debug_output_dir:
                save_idx += 1
                sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_pass2_declip.wav"),
                         y.T if y.ndim > 1 else y, sr, subtype="PCM_24")
        if residual.has_sibilance(threshold=0.10) and strategy.de_ess > 0:
            if progress:
                progress(0.84, "二遍清除残留齿音...")
            y = _v32a_de_ess(y, sr, strategy.de_ess * 0.4)
            verify_notes.append("二遍清除残留齿音")
            if debug_output_dir:
                save_idx += 1
                sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_pass2_deess.wav"),
                         y.T if y.ndim > 1 else y, sr, subtype="PCM_24")
        if residual.is_noisy(threshold_snr=33.0) and strategy.noise_reduction > 0:
            if progress:
                progress(0.90, "二遍清除残留噪声...")
            y = _v32a_spectral_denoise(y, sr, strategy.noise_reduction * 0.4)
            verify_notes.append("二遍清除残留噪声")
            if debug_output_dir:
                save_idx += 1
                sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_pass2_denoise.wav"),
                         y.T if y.ndim > 1 else y, sr, subtype="PCM_24")
        if verify_notes:
            notes.append("二遍验证: " + ", ".join(verify_notes))
        else:
            notes.append("二遍验证通过(无需校正)")
    if progress:
        progress(0.99, "峰值限制...")
    y = soft_peak_limit(y, threshold=0.9)

    if debug_output_dir:
        save_idx += 1
        sf.write(os.path.join(debug_output_dir, f"{save_idx:02d}_peak_limit.wav"),
                 y.T if y.ndim > 1 else y, sr, subtype="PCM_24")

    return y, notes


# pass1 闭包用的轻量包装（按需 import，避免顶层循环依赖）
def _depop(y, sr, amount):
    if amount <= 0:
        return y
    from services.repair.repair_v3_2a.core import simple_depop
    return simple_depop(y, sr, amount)


def _ai_repair(y, sr, amount):
    if amount <= 0:
        return y
    from services.repair.repair_v3_2a.core import vocal_ai_repair_adaptive_lite
    return vocal_ai_repair_adaptive_lite(y, sr, amount)


def _transient(y, sr, amount):
    if amount <= 0:
        return y
    from services.repair.repair_v3_2a.core import transient_aware_process_lite
    return transient_aware_process_lite(y, sr, amount)


def _resonance(y, sr, amount):
    if amount <= 0:
        return y
    from services.repair.repair_v3_2a.core import resonance_suppress_lite
    return resonance_suppress_lite(y, sr, amount)


def _repair_single_track_v4p_impl(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
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
        progress_callback(0.12, f"{VERSION_TAG} 分析+自适应处理...")
    sub = _make_sub_progress(progress_callback, 0.14, 0.83)
    y, notes = process_track_adaptive_premium(y, sr, intent, progress=sub,
                                              debug_output_dir=debug_output_dir)
    issues_found = ["单轨·自适应分析(两遍)"] + notes

    mastering_style = intent.get("mastering_style", "none")
    if mastering_style != "none":
        if progress_callback:
            progress_callback(0.85, f"{VERSION_TAG} 母带处理...")
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
    if y.dtype == np.float32:
        y = y.astype(np.float64)
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
        return _repair_single_track_v4p_impl(input_path, output_path, params, progress_callback)
    except Exception as e:
        logger.warning(f"{VERSION_TAG} 单轨修复失败，降级到 v3.2a: {e}", exc_info=True)
        if progress_callback:
            progress_callback(0.0, f"{VERSION_TAG} 修复异常，降级到 v3.2a...")
        result = _v32a_repair_single_track(input_path, output_path, params, progress_callback)
        result["algorithm_version"] = f"{VERSION_TAG}(fallback:v3.2a)"
        result["fallback_reason"] = str(e)
        return result


def _repair_audio_v4p_dual_impl(input_path: str, output_path: str, params: dict, progress_callback: Any = None) -> dict:
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
        progress_callback(0.20, f"{VERSION_TAG} 自适应分析+两遍处理人声轨...")
    vocal_y, v_notes = process_track_adaptive_premium(vocal_y, vocal_sr, vocal_intent,
                                                      progress=_make_sub_progress(progress_callback, 0.20, 0.46))

    if progress_callback:
        progress_callback(0.50, f"{VERSION_TAG} 自适应分析+两遍处理伴奏轨...")
    accompaniment_y, i_notes = process_track_adaptive_premium(accompaniment_y, accompaniment_sr, inst_intent,
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

    issues_found = ["双轨·自适应分析(两遍)", f"人声: {', '.join(v_notes) or '无显著问题'}",
                    f"伴奏: {', '.join(i_notes) or '无显著问题'}", "混音完成"]

    mastering_style = params.get("mastering_style", "none")
    if mastering_style != "none":
        if progress_callback:
            progress_callback(0.85, f"{VERSION_TAG} 母带处理...")
        mixed, mnote = _apply_mastering(mixed, working_sr, mastering_style)
        if mnote:
            issues_found.append(mnote)

    output_volume_db = params.get("output_volume", 0.0)
    if output_volume_db != 0.0:
        volume_gain = 10 ** (output_volume_db / 20.0)
        mixed = (mixed * volume_gain).astype(mixed.dtype)

    if progress_callback:
        progress_callback(0.90, f"{VERSION_TAG} 导出...")
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
        return _repair_audio_v4p_dual_impl(input_path, output_path, params, progress_callback)
    except Exception as e:
        logger.warning(f"{VERSION_TAG} 双轨修复失败，降级到 v3.2a: {e}", exc_info=True)
        if progress_callback:
            progress_callback(0.0, f"{VERSION_TAG} 修复异常，降级到 v3.2a...")
        result = _v32a_repair_audio(input_path, output_path, params, progress_callback)
        result["algorithm_version"] = f"{VERSION_TAG}(fallback:v3.2a)"
        result["fallback_reason"] = str(e)
        return result
