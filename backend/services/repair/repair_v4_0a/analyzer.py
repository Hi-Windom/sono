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
    channel_imbalance_db: float = 0.0  # 左右声道 RMS 差异 (dB)，正值=左声道大

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
MULTI_WINDOW_THRESHOLD = 90.0  # 超过此时长用多窗口扫描


def _quick_hf_energy(mono: np.ndarray, sr: int, hf_threshold: float = 12000.0) -> float:
    """原始采样率下快速估计高频能量占比。

    使用较少 FFT 帧做近似估计，避免降采样丢失高频信息。
    """
    n = len(mono)
    if n < 512 or sr <= hf_threshold * 2:
        return 0.0

    n_fft = 2048
    hop = 4096
    n_win = min(32, max(1, (n - n_fft) // hop + 1))

    win = np.hanning(n_fft)
    hf_sum = 0.0
    total_sum = 0.0

    for w in range(n_win):
        start = w * hop
        if start + n_fft > n:
            break
        seg = mono[start:start + n_fft] * win
        mag = np.abs(np.fft.rfft(seg))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        total_sum += float(np.sum(mag))
        mask = freqs >= hf_threshold
        hf_sum += float(np.sum(mag[mask]))

    if total_sum < 1e-20:
        return 0.0
    return hf_sum / total_sum


def _analyze_window(mono_win: np.ndarray, sr: int, *, light: bool = False) -> SignalProfile:
    """对单个音频窗口做完整分析，返回 SignalProfile。"""
    profile = SignalProfile(sample_rate=int(sr))
    n = len(mono_win)
    profile.n_samples = n
    profile.duration = round(n / sr, 3)
    profile.channels = 1

    # —— 削波 / 峰值 / RMS / 直流（全窗口）——
    abs_y = np.abs(mono_win)
    profile.peak_abs = float(abs_y.max())
    sumsq = float(np.dot(mono_win, mono_win))
    profile.rms = float(np.sqrt(sumsq / n + 1e-20))
    profile.dc_offset = float(mono_win.sum() / n)
    profile.clip_density = float(np.mean(abs_y > 0.985))
    profile.crest_factor = _db(profile.peak_abs) - _db(profile.rms) if profile.rms > 1e-6 else 0.0
    del abs_y

    # —— 本底噪声估计 ——
    frame = 2048
    hop = 2048
    n_frames = max(1, n // hop)
    usable = n_frames * hop
    if usable > 0:
        frames = mono_win[:usable].reshape(n_frames, hop)
        sumsq = np.einsum('ij,ij->i', frames, frames)
        frame_rms = np.sqrt(sumsq / hop + 1e-20)
        del frames, sumsq
    else:
        frame_rms = np.array([profile.rms], dtype=np.float64)
    quiet_rms = float(np.percentile(frame_rms, 10))
    profile.noise_floor_db = _db(quiet_rms)
    profile.snr_db = _db(profile.rms) - profile.noise_floor_db

    # —— 近似响度 ——
    try:
        from scipy.signal import butter, sosfilt
        sos = butter(2, 38.0 / (sr / 2.0), btype='high', output='sos')
        weighted = sosfilt(sos, mono_win)
        mean_sq = float(np.dot(weighted, weighted) / n + 1e-20)
        profile.lufs_approx = -0.691 + 10.0 * np.log10(mean_sq + 1e-20)
        del weighted
    except Exception:
        profile.lufs_approx = _db(profile.rms) - 0.691

    # 动态范围
    with np.errstate(divide='ignore'):
        loud_frames_db = 20.0 * np.log10(frame_rms + 1e-12)
    profile.dynamic_range_db = float(np.percentile(loud_frames_db, 95) - np.percentile(loud_frames_db, 10))

    # —— 瞬态密度 ——
    if n_frames > 2:
        diff = np.abs(np.diff(frame_rms))
        med = float(np.median(diff)) if np.median(diff) > 1e-10 else 1e-10
        profile.transient_density = float(np.mean(diff > (med * 6.0)))
        del diff
    del frame_rms, loud_frames_db

    # —— 原始采样率高频快速检测（问题2修复：不降采样也能检测高频）——
    raw_hf_ratio = 0.0
    if not light:
        raw_hf_ratio = _quick_hf_energy(mono_win, sr)

    # —— 频谱特征（降采样）——
    if light:
        ana = mono_win
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
            for w in range(min(n_win, 64)):
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
        del ana

    total_energy = float(np.sum(mag) + 1e-20)

    # 频谱质心
    profile.spectral_centroid = float(np.sum(freqs * mag) / total_energy)
    # 滚降点
    cum = np.cumsum(mag)
    rolloff_idx = int(np.searchsorted(cum, 0.85 * cum[-1])) if cum[-1] > 0 else 0
    rolloff_idx = min(rolloff_idx, len(freqs) - 1)
    profile.spectral_rolloff = float(freqs[rolloff_idx])
    # 频谱平坦度
    eps = 1e-10
    geo = np.exp(np.mean(np.log(mag + eps)))
    arith = np.mean(mag) + eps
    profile.spectral_flatness = float(geo / arith)

    # 频段能量占比
    def _band_ratio(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        return float(np.sum(mag[mask]) / total_energy)

    profile.sibilance_energy = _band_ratio(4000, 9000)

    # hf_energy：如果原始采样率检测到高能量，用原始采样率的估计（问题2修复）
    downsampled_hf = _band_ratio(8000, ana_sr / 2)
    if raw_hf_ratio > downsampled_hf:
        profile.hf_energy = raw_hf_ratio
    else:
        profile.hf_energy = downsampled_hf

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
    if profile.dynamic_range_db < 6.0 and profile.duration > 1.0:
        issues.append("动态被压缩")
    profile.detected_issues = issues
    return profile


def _merge_profiles(profiles: list[SignalProfile]) -> SignalProfile:
    """合并多个窗口的 profile，取各指标的最坏值/最大值。"""
    if not profiles:
        return SignalProfile()
    if len(profiles) == 1:
        return profiles[0]

    base = profiles[0]
    merged = SignalProfile(sample_rate=base.sample_rate)
    merged.n_samples = base.n_samples
    merged.duration = base.duration
    merged.channels = base.channels

    # 取最大值/最坏值的指标
    merged.clip_density = max(p.clip_density for p in profiles)
    merged.peak_abs = max(p.peak_abs for p in profiles)
    merged.rms = max(p.rms for p in profiles)
    merged.crest_factor = max(p.crest_factor for p in profiles)
    merged.dc_offset = max((p.dc_offset for p in profiles), key=abs)
    merged.noise_floor_db = max(p.noise_floor_db for p in profiles)  # 越高越坏
    merged.snr_db = min(p.snr_db for p in profiles)  # 越低越坏
    merged.sibilance_energy = max(p.sibilance_energy for p in profiles)
    merged.transient_density = max(p.transient_density for p in profiles)
    merged.spectral_flatness = max(p.spectral_flatness for p in profiles)
    merged.spectral_centroid = max(p.spectral_centroid for p in profiles)
    merged.spectral_rolloff = max(p.spectral_rolloff for p in profiles)
    merged.hf_energy = max(p.hf_energy for p in profiles)
    merged.lufs_approx = max(p.lufs_approx for p in profiles)
    merged.dynamic_range_db = min(p.dynamic_range_db for p in profiles)  # 越小越坏
    merged.stereo_width = min(p.stereo_width for p in profiles)  # 越窄越坏
    merged.channel_imbalance_db = max((p.channel_imbalance_db for p in profiles), key=abs)  # 绝对值越大越坏

    # 合并 detected_issues（去重）
    seen: set[str] = set()
    all_issues: list[str] = []
    for p in profiles:
        for issue in p.detected_issues:
            if issue not in seen:
                seen.add(issue)
                all_issues.append(issue)
    merged.detected_issues = all_issues

    return merged


def analyze_signal(y: np.ndarray, sr: int, *, light: bool = False) -> SignalProfile:
    """一次扫描提取完整诊断画像。y 可为 (n,) 或 (ch, n)。

    light=True 时跳过频谱重采样（用于修复后的轻量复核），其余特征仍全量计算。

    v4.0 修复（V4-001）：长音频采用多窗口扫描（开头+中间+结尾各30秒），
    避免只分析中间而遗漏开头/结尾的问题。各窗口取最坏值合并。
    时长 < 90 秒时直接分析全量。

    v4.0 修复（V4-002）：在原始采样率下做快速高频检测，
    避免降采样到 22050Hz 而丢失 >11kHz 的高频信息。
    """
    if y is None or y.size == 0:
        return SignalProfile(sample_rate=int(sr))

    mono = _to_mono(y)
    n = len(mono)
    duration = n / sr
    channels = 1 if y.ndim == 1 else int(y.shape[0])

    # 判断是否需要多窗口扫描
    need_multi_window = (not light) and (duration > MULTI_WINDOW_THRESHOLD)

    if need_multi_window:
        # 多窗口扫描：开头30秒 + 中间30秒 + 结尾30秒
        win_len = int(sr * ANALYSIS_MAX_SECONDS)
        window_starts = [
            0,                          # 开头
            (n - win_len) // 2,         # 中间
            n - win_len,                # 结尾
        ]
        profiles: list[SignalProfile] = []
        for start in window_starts:
            start = max(0, min(start, n - win_len))
            end = start + win_len
            mono_win = mono[start:end]
            p = _analyze_window(mono_win, sr, light=light)
            profiles.append(p)

        profile = _merge_profiles(profiles)
        # 用全量信号的元信息覆盖
        profile.sample_rate = int(sr)
        profile.n_samples = n
        profile.duration = round(duration, 3)
        profile.channels = channels

        # 立体声宽度 + 声道不平衡（全量信号计算）
        if y.ndim == 2 and y.shape[0] == 2:
            a = y[0].astype(np.float64)
            b = y[1].astype(np.float64)
            ca = np.dot(a, a) + 1e-20
            cb = np.dot(b, b) + 1e-20
            cab = np.dot(a, b)
            corr = float(cab / np.sqrt(ca * cb))
            profile.stereo_width = float(max(0.0, min(1.0, (1.0 - corr) / 2.0)))
            rms_l = float(np.sqrt(ca / len(a)))
            rms_r = float(np.sqrt(cb / len(b)))
            if rms_l > 1e-12 and rms_r > 1e-12:
                profile.channel_imbalance_db = float(20.0 * np.log10(rms_l / rms_r))
            else:
                profile.channel_imbalance_db = 0.0

        # 重新生成 detected_issues（基于合并后的指标）
        _update_detected_issues(profile)
    else:
        # 短音频：直接全量分析
        profile = _analyze_window(mono, sr, light=light)
        profile.sample_rate = int(sr)
        profile.n_samples = n
        profile.duration = round(duration, 3)
        profile.channels = channels

        # 立体声宽度 + 声道不平衡
        if y.ndim == 2 and y.shape[0] == 2:
            a = y[0].astype(np.float64)
            b = y[1].astype(np.float64)
            ca = np.dot(a, a) + 1e-20
            cb = np.dot(b, b) + 1e-20
            cab = np.dot(a, b)
            corr = float(cab / np.sqrt(ca * cb))
            profile.stereo_width = float(max(0.0, min(1.0, (1.0 - corr) / 2.0)))
            rms_l = float(np.sqrt(ca / len(a)))
            rms_r = float(np.sqrt(cb / len(b)))
            if rms_l > 1e-12 and rms_r > 1e-12:
                profile.channel_imbalance_db = float(20.0 * np.log10(rms_l / rms_r))
            else:
                profile.channel_imbalance_db = 0.0

        if not light:
            _update_detected_issues(profile)

    return profile


def _update_detected_issues(profile: SignalProfile) -> None:
    """根据 profile 指标重新生成 detected_issues 列表。"""
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
    if abs(profile.channel_imbalance_db) > 3.0 and profile.channels == 2:
        side = "左" if profile.channel_imbalance_db > 0 else "右"
        issues.append(f"立体声不平衡（{side}声道大 {abs(profile.channel_imbalance_db):.1f}dB）")
    if profile.dynamic_range_db < 6.0 and profile.duration > 1.0:
        issues.append("动态被压缩")
    profile.detected_issues = issues


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
        "channel_imbalance_db": round(profile.channel_imbalance_db, 1),
        "detected_issues": list(profile.detected_issues),
    }
