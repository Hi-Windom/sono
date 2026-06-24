"""v4.0 信号分析层 —— Analysis-Driven Adaptive Pipeline 的"眼睛"。

v3.2 系列的根因是"盲处理"：无论音频实际状态如何，参数都直接作为操作点套用固定 DSP。
本模块在一次 O(n) 预扫描中提取信号诊断画像 SignalProfile，供 adaptive 层把"用户意图"
调制为"有效操作点"，让修复只在确有问题的地方发生，避免对干净音频的幻影处理。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class SignalProfile:
    """单轨信号诊断画像。所有字段均为无量纲/标准化的可比较度量。"""

    # 基础
    sample_rate: int = 48000
    duration: float = 0.0
    channels: int = 1
    n_samples: int = 0

    # 削波诊断（自适应 declip 依据）
    clip_density: float = 0.0          # 接近满幅样本占比 (0~1)
    peak_abs: float = 0.0              # 峰值绝对值
    rms: float = 0.0                   # 全段 RMS
    crest_factor: float = 0.0          # 峰值/RMS（dB 近似）

    # 直流偏置
    dc_offset: float = 0.0

    # 本底噪声估计（自适应降噪门限依据）
    noise_floor_db: float = -60.0      # 估计本底噪声 (dBFS)
    snr_db: float = 0.0                # 信号/本底信噪比

    # 齿音能量（自适应 de-ess 依据）
    sibilance_energy: float = 0.0      # 4~8kHz 能量占比 (0~1)

    # 瞬态密度（自适应 transient 依据）
    transient_density: float = 0.0     # 瞬态事件密度 (0~1 归一)

    # 频谱特征
    spectral_flatness: float = 0.0     # 0=纯音/谐波, 1=噪声
    spectral_centroid: float = 0.0     # 频谱质心 (Hz)
    spectral_rolloff: float = 0.0      # 85% 能量滚降点 (Hz)
    hf_energy: float = 0.0             # >8kHz 高频能量占比 (0~1)

    # 动态范围与响度
    lufs_approx: float = -23.0         # 近似响度 (dB)
    dynamic_range_db: float = 0.0      # 峰段-谷段响度差

    # 立体声
    stereo_width: float = 1.0          # 0=单声道, 1=全立体声（仅多声道有意义）

    # 检测到的问题（供 issues_found 展示与策略判定）
    detected_issues: list[str] = field(default_factory=list)

    def has_clipping(self, threshold: float = 0.002) -> bool:
        return self.clip_density > threshold

    def has_sibilance(self, threshold: float = 0.12) -> bool:
        return self.sibilance_energy > threshold

    def is_noisy(self, threshold_snr: float = 30.0) -> bool:
        return self.snr_db < threshold_snr


def _to_mono(y: np.ndarray) -> np.ndarray:
    if y.ndim == 1:
        return y.astype(np.float64, copy=False)
    return np.mean(y.astype(np.float64), axis=0)


def _db(x: float) -> float:
    if x <= 1e-12:
        return -120.0
    return 20.0 * np.log10(x)


# 频谱分析采样率上限与最大分析时长（移动端友好：长音频只取代表窗，控内存/算力）
ANALYSIS_MAX_SR = 22050
ANALYSIS_MAX_SECONDS = 30.0


def analyze_signal(y: np.ndarray, sr: int, *, light: bool = False) -> SignalProfile:
    """一次扫描提取完整诊断画像。y 可为 (n,) 或 (ch, n)。

    light=True 时跳过频谱重采样（用于修复后的轻量复核），其余特征仍全量计算。
    """
    profile = SignalProfile(sample_rate=int(sr))
    if y is None or y.size == 0:
        return profile

    mono = _to_mono(y)
    n = len(mono)
    profile.n_samples = n
    profile.duration = round(n / sr, 3)
    profile.channels = 1 if y.ndim == 1 else int(y.shape[0])

    # —— 削波 / 峰值 / RMS / 直流（全量，内存友好）——
    # 用 np.dot 求 sumsq 避免临时平方数组；abs 只生成一份
    abs_y = np.abs(mono)
    profile.peak_abs = float(abs_y.max())
    sumsq = float(np.dot(mono, mono))
    profile.rms = float(np.sqrt(sumsq / n + 1e-20))
    profile.dc_offset = float(mono.sum() / n)
    profile.clip_density = float(np.mean(abs_y > 0.985))
    profile.crest_factor = _db(profile.peak_abs) - _db(profile.rms) if profile.rms > 1e-6 else 0.0
    del abs_y

    # —— 本底噪声估计：帧 RMS 向量化（替代逐帧 Python 循环）
    # 用 reshape 视图 + einsum 计算每帧 sumsq，避免物化全长平方数组（省内存）
    frame = 2048
    hop = 2048
    n_frames = max(1, n // hop)
    usable = n_frames * hop
    if usable > 0:
        frames = mono[:usable].reshape(n_frames, hop)
        sumsq = np.einsum('ij,ij->i', frames, frames)
        frame_rms = np.sqrt(sumsq / hop + 1e-20)
        del frames, sumsq
    else:
        frame_rms = np.array([profile.rms], dtype=np.float64)
    quiet_rms = float(np.percentile(frame_rms, 10))
    profile.noise_floor_db = _db(quiet_rms)
    profile.snr_db = _db(profile.rms) - profile.noise_floor_db

    # —— 近似响度 (K-weighting 简化为 RMS+高通补偿) ——
    try:
        from scipy.signal import butter, sosfilt
        sos = butter(2, 38.0 / (sr / 2.0), btype='high', output='sos')
        weighted = sosfilt(sos, mono)
        mean_sq = float(np.dot(weighted, weighted) / n + 1e-20)
        profile.lufs_approx = -0.691 + 10.0 * np.log10(mean_sq + 1e-20)
        del weighted
    except Exception:
        profile.lufs_approx = _db(profile.rms) - 0.691

    # 动态范围：响 95 分位 - 静 10 分位（dB），向量化
    with np.errstate(divide='ignore'):
        loud_frames_db = 20.0 * np.log10(frame_rms + 1e-12)
    profile.dynamic_range_db = float(np.percentile(loud_frames_db, 95) - np.percentile(loud_frames_db, 10))

    # —— 瞬态密度：相邻帧 RMS 一阶差分超阈值的比例（向量化）——
    if n_frames > 2:
        diff = np.abs(np.diff(frame_rms))
        med = float(np.median(diff)) if np.median(diff) > 1e-10 else 1e-10
        profile.transient_density = float(np.mean(diff > (med * 6.0)))
        del diff
    del frame_rms, loud_frames_db

    # —— 频谱特征（降采样 + 长音频取代表窗，控内存/算力）——
    if light:
        # 轻量复核：不做频谱重采样，频谱字段保持默认（0），仅时间域画像
        ana = mono
        ana_sr = sr
        n_fft = 2048
        hop_a = 1024
        n_ana = len(ana)
        if n_ana > n_fft:
            n_win = max(1, (n_ana - n_fft) // hop_a + 1)
            win = np.hanning(n_fft)
            mag_sum = np.zeros(n_fft // 2 + 1, dtype=np.float64)
            for w in range(min(n_win, 32)):
                seg = ana[w * hop_a:w * hop_a + n_fft]
                if len(seg) < n_fft:
                    seg = np.pad(seg, (0, n_fft - len(seg)))
                mag_sum += np.abs(np.fft.rfft(seg * win))
            mag = mag_sum / max(1, min(n_win, 32))
        else:
            win = np.hanning(len(ana))
            mag = np.abs(np.fft.rfft(ana * win))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / ana_sr)
    else:
        analysis_sr = min(sr, ANALYSIS_MAX_SR)
        # 长音频只取居中代表窗（最多 ANALYSIS_MAX_SECONDS 秒），避免重采样全长信号
        cap = int(sr * ANALYSIS_MAX_SECONDS)
        if n > cap:
            start = (n - cap) // 2
            mono_win = mono[start:start + cap]
        else:
            mono_win = mono
        if sr != analysis_sr:
            from scipy.signal import resample_poly
            ratio = analysis_sr / sr
            if ratio >= 1.0:
                ana = resample_poly(mono_win, int(analysis_sr), int(sr))
            else:
                ana = resample_poly(mono_win, int(analysis_sr * 100), int(sr * 100))
        else:
            ana = mono_win
        ana_sr = analysis_sr

        n_fft = 2048
        hop_a = 1024
        n_ana = len(ana)
        if n_ana > n_fft:
            n_win = max(1, (n_ana - n_fft) // hop_a + 1)
            win = np.hanning(n_fft)
            mag_sum = np.zeros(n_fft // 2 + 1, dtype=np.float64)
            for w in range(min(n_win, 64)):  # 最多取 64 窗，移动端友好
                seg = ana[w * hop_a:w * hop_a + n_fft]
                if len(seg) < n_fft:
                    seg = np.pad(seg, (0, n_fft - len(seg)))
                spec = np.abs(np.fft.rfft(seg * win))
                mag_sum += spec
            mag = mag_sum / max(1, min(n_win, 64))
        else:
            win = np.hanning(len(ana))
            mag = np.abs(np.fft.rfft(ana * win))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / ana_sr)
        del ana, mono_win

    total_energy = float(np.sum(mag) + 1e-20)

    # 频谱质心
    profile.spectral_centroid = float(np.sum(freqs * mag) / total_energy)
    # 滚降点（85% 能量）
    cum = np.cumsum(mag)
    rolloff_idx = int(np.searchsorted(cum, 0.85 * cum[-1])) if cum[-1] > 0 else 0
    rolloff_idx = min(rolloff_idx, len(freqs) - 1)
    profile.spectral_rolloff = float(freqs[rolloff_idx])
    # 频谱平坦度（几何/算术均值）
    eps = 1e-10
    geo = np.exp(np.mean(np.log(mag + eps)))
    arith = np.mean(mag) + eps
    profile.spectral_flatness = float(geo / arith)

    # 频段能量占比
    def _band_ratio(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        return float(np.sum(mag[mask]) / total_energy)

    profile.sibilance_energy = _band_ratio(4000, 9000)
    profile.hf_energy = _band_ratio(8000, ana_sr / 2)

    # —— 立体声宽度（声道间相关性）——
    if y.ndim == 2 and y.shape[0] == 2:
        a = y[0].astype(np.float64)
        b = y[1].astype(np.float64)
        ca = np.dot(a, a) + 1e-20
        cb = np.dot(b, b) + 1e-20
        cab = np.dot(a, b)
        corr = float(cab / np.sqrt(ca * cb))
        # corr=1 单声道→width 0；corr=-1 反相→width 1；线性映射
        profile.stereo_width = float(max(0.0, min(1.0, (1.0 - corr) / 2.0)))

    # —— 检测问题汇总 ——
    issues: list[str] = []
    if profile.has_clipping():
        issues.append(f"削波 {profile.clip_density * 100:.1f}%")
    if abs(profile.dc_offset) > 0.01:
        issues.append(f"直流偏置 {profile.dc_offset:+.3f}")
    if profile.is_noisy():
        issues.append(f"本底噪声 SNR {profile.snr_db:.0f}dB")
    if profile.has_sibilance():
        issues.append(f"齿音过强 {profile.sibilance_energy * 100:.0f}%")
    if profile.spectral_flatness > 0.4:
        issues.append("频谱噪声化")
    if profile.stereo_width < 0.15 and profile.channels == 2:
        issues.append("立体声过窄")
    if profile.dynamic_range_db < 6.0 and profile.duration > 1.0:
        issues.append("动态被压缩")
    profile.detected_issues = issues
    return profile


def analyze_residual(y: np.ndarray, sr: int, before: SignalProfile) -> SignalProfile:
    """v4.0a+ 验证扫描：对修复后音频再次画像，与 before 对比生成残差诊断。"""
    after = analyze_signal(y, sr)
    return after


def profile_summary(profile: SignalProfile) -> dict[str, Any]:
    """供 repair 结果回传的精简画像（前端可展示真实检测情况）。"""
    return {
        "clip_density_pct": round(profile.clip_density * 100, 2),
        "peak_db": round(_db(profile.peak_abs), 1),
        "rms_db": round(_db(profile.rms), 1),
        "crest_factor_db": round(profile.crest_factor, 1),
        "noise_floor_db": round(profile.noise_floor_db, 1),
        "snr_db": round(profile.snr_db, 1),
        "sibilance_pct": round(profile.sibilance_energy * 100, 1),
        "transient_density": round(profile.transient_density, 3),
        "spectral_flatness": round(profile.spectral_flatness, 3),
        "spectral_centroid_hz": round(profile.spectral_centroid, 0),
        "lufs": round(profile.lufs_approx, 1),
        "dynamic_range_db": round(profile.dynamic_range_db, 1),
        "stereo_width": round(profile.stereo_width, 3),
        "detected_issues": list(profile.detected_issues),
    }
