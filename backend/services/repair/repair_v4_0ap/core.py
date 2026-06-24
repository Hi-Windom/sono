"""v4.0a+ 修复算法 —— 移动端增强版：两遍验证 + 前视压缩（Analysis-Driven Adaptive Pipeline Premium）。

相对 v4.0a 的增量：
  1) 两遍验证(Two-pass verify)：第一遍自适应修复后，对结果再次画像，仅在残差超阈值处
     触发针对性二次校正，避免对已干净区域的过处理（v3.2a 无此机制）。
  2) 前视压缩器(Lookahead compressor)：用 lookahead delay 预读包络，实现无伪影的瞬态感知
     压缩，替代 v3.2a 即时包络压缩的过冲问题。
完全复用 v4.0a 的 analyzer/adaptive 与 v3.2a 原语，能力 100% 保留。
"""
from __future__ import annotations

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
)

from services.repair.repair_v4_0a.core import (
    _resample_to_working,
    _map_flat_params,
    _map_single_params,
    _apply_mastering,
    _SINGLE_KEY_MAP,
)
from services.repair.repair_v4_0a.analyzer import analyze_signal, profile_summary
from services.repair.repair_v4_0a.adaptive import build_strategy

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
    sq = x ** 2
    # 移动平均包络（近似 RMS）
    kernel = np.ones(win, dtype=np.float64) / win
    env = np.convolve(sq, kernel, mode='same')
    env_db = 10.0 * np.log10(env + 1e-12)
    # 前视：把包络向后平移 lookahead，使增益在瞬态到达前已就位
    env_db_shifted = np.empty_like(env_db)
    env_db_shifted[:-lookahead] = env_db[lookahead:]
    env_db_shifted[-lookahead:] = env_db[-1]

    thr = threshold_db
    over = env_db_shifted > thr
    # 压缩增益（dB）：超阈部分按 ratio 压缩，amount 控制混合比例
    gain_db = np.zeros_like(env_db_shifted)
    gain_db[over] = -(env_db_shifted[over] - thr) * (1.0 - 1.0 / ratio) * amount
    # 释放平滑（指数）
    gain_lin = 10.0 ** (gain_db / 20.0)
    # 简单一阶平滑避免增益抖动
    smooth = 0.85
    for i in range(1, n):
        gain_lin[i] = smooth * gain_lin[i - 1] + (1 - smooth) * gain_lin[i]
    # 补偿前视延迟
    out = np.zeros(n, dtype=np.float64)
    out[lookahead:] = x[:-lookahead] * gain_lin[lookahead:]
    out[:lookahead] = x[:lookahead] * gain_lin[:lookahead]
    return out


def process_track_adaptive_premium(y: np.ndarray, sr: int, intent: dict) -> tuple[np.ndarray, list[str]]:
    """v4.0a+ 单轨：Analyze→Adapt→Process(pass1)→Re-analyze→Targeted verify(pass2)。"""
    # Pass 1: 自适应修复（与 v4.0a 一致，但 premium=True 触发更激进调制）
    profile1 = analyze_signal(y, sr)
    strategy = build_strategy(intent, profile1, premium=True)
    notes = [f"检测: {', '.join(profile1.detected_issues) or '无显著问题'}"] + list(strategy.notes)

    speed = float(intent.get("speed", 1.0) or 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)

    if strategy.declip > 0:
        y = _v32a_declip(y, strategy.declip)
    if strategy.depop > 0:
        from services.repair.repair_v3_2a.core import simple_depop
        y = simple_depop(y, sr, strategy.depop)
    if strategy.de_ess > 0:
        y = _v32a_de_ess(y, sr, strategy.de_ess)
    if strategy.noise_reduction > 0:
        y = _v32a_spectral_denoise(y, sr, strategy.noise_reduction)
    if strategy.ai_repair_adaptive > 0:
        from services.repair.repair_v3_2a.core import vocal_ai_repair_adaptive_lite
        y = vocal_ai_repair_adaptive_lite(y, sr, strategy.ai_repair_adaptive)
    if strategy.exciter > 0:
        y = _v32a_exciter(y, sr, strategy.exciter)
    if strategy.compressor > 0:
        # v4.0a+ 用前视压缩替代即时压缩
        y = lookahead_compress(y, sr, strategy.compressor)
    if strategy.transient > 0:
        from services.repair.repair_v3_2a.core import transient_aware_process_lite
        y = transient_aware_process_lite(y, sr, strategy.transient)
    if strategy.resonance > 0:
        from services.repair.repair_v3_2a.core import resonance_suppress_lite
        y = resonance_suppress_lite(y, sr, strategy.resonance)
    if strategy.bass_enhance > 0:
        y = _v32a_bass(y, sr, strategy.bass_enhance)
    if strategy.air_texture > 0:
        y = _v32a_air(y, sr, strategy.air_texture)
    if strategy.dynamic > 0:
        y = _v32a_dynamic(y, sr, strategy.dynamic)
    if strategy.loudness > 0:
        y = _v32a_loudness(y, sr, strategy.target_lufs)

    # Pass 2: 验证 —— 仅在残差问题超阈值时做针对性校正
    if strategy.needs_verify and y.size:
        residual = analyze_signal(y, sr)
        verify_notes: list[str] = []
        # 残留削波 → 再轻量去削波一次
        if residual.has_clipping(threshold=0.003) and strategy.declip > 0:
            y = _v32a_declip(y, strategy.declip * 0.5)
            verify_notes.append("二遍清除残留削波")
        # 残留齿音 → 轻量再处理
        if residual.has_sibilance(threshold=0.10) and strategy.de_ess > 0:
            y = _v32a_de_ess(y, sr, strategy.de_ess * 0.4)
            verify_notes.append("二遍清除残留齿音")
        # 残留噪声 → 轻量再降噪
        if residual.is_noisy(threshold_snr=33.0) and strategy.noise_reduction > 0:
            y = _v32a_spectral_denoise(y, sr, strategy.noise_reduction * 0.4)
            verify_notes.append("二遍清除残留噪声")
        if verify_notes:
            notes.append("二遍验证: " + ", ".join(verify_notes))
        else:
            notes.append("二遍验证通过(无需校正)")

    y = soft_peak_limit(y, threshold=0.9)
    return y, notes


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
        progress_callback(0.12, f"{VERSION_TAG} 分析+自适应处理...")
    y, notes = process_track_adaptive_premium(y, sr, intent)
    issues_found = ["单轨·自适应分析(两遍)"] + notes

    mastering_style = intent.get("mastering_style", "none")
    if mastering_style != "none":
        if progress_callback:
            progress_callback(0.85, f"{VERSION_TAG} 母带处理...")
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
    vocal_y, v_notes = process_track_adaptive_premium(vocal_y, vocal_sr, vocal_intent)

    if progress_callback:
        progress_callback(0.50, f"{VERSION_TAG} 自适应分析+两遍处理伴奏轨...")
    accompaniment_y, i_notes = process_track_adaptive_premium(accompaniment_y, accompaniment_sr, inst_intent)
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
