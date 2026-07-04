"""v4.0 自适应策略层 —— Analysis-Driven Adaptive Pipeline 的"大脑"。

把"用户意图"(0~1) 与 SignalProfile 结合，映射为各 DSP 原语的有效操作点。
核心思想：意图是"想做到多少"，profile 决定"实际该做多少"。
- 干净音频不被幻影处理（intent 高但 profile 无问题 → effective≈0）
- 问题严重处自动加强（intent 低但 profile 严重 → effective 提升）
- 操作点仍走 v3.2a 的原语，故能力 100% 保留，仅"何时做/做多重"变得自适应
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .analyzer import SignalProfile


@dataclass
class AdaptiveStrategy:
    """各原语的有效操作点（已结合 profile 调制）。0 表示跳过该原语。"""

    declip: float = 0.0
    depop: float = 0.0
    de_ess: float = 0.0
    noise_reduction: float = 0.0
    ai_repair_adaptive: float = 0.0
    exciter: float = 0.0
    compressor: float = 0.0
    transient: float = 0.0
    resonance: float = 0.0
    bass_enhance: float = 0.0
    air_texture: float = 0.0
    dynamic: float = 0.0
    loudness: float = 0.0
    # 自适应派生量（供原语内部使用/展示）
    declip_threshold: float = 0.90       # 自适应削波阈值
    noise_gate_db: float = -60.0         # 自适应降噪门限
    target_lufs: float = -14.0           # 自适应响度目标
    # 自适应增益（sibilance/resonance 仅在问题段生效的强度系数）
    sibilance_gate: float = 0.0
    # 该策略是否触发二遍验证（v4.0a+）
    needs_verify: bool = False
    # 策略说明（供 issues_found / 日志）
    notes: list[str] = field(default_factory=list)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def build_strategy(intent: dict, profile: SignalProfile, *, premium: bool = False) -> AdaptiveStrategy:
    """由用户意图参数 + 信号画像构建自适应策略。

    intent: 已按 v3.2a 约定映射后的 short-key 参数 (declip/depop/de_ess/...)
    premium: True 表示 v4.0a+，启用更激进的调制与二遍验证
    """
    s = AdaptiveStrategy()
    notes: list[str] = []

    # —— 自适应 declip ——
    # v3.2a 固定阈值 0.90：v4.0 按实际削波密度调制，且阈值随峰值下移
    declip_intent = float(intent.get("declip", 0) or 0)
    if profile.has_clipping() and declip_intent > 0:
        # 削波越严重，有效强度越高
        boost = 1.0 + min(2.0, profile.clip_density * 20.0)
        s.declip = _clamp(declip_intent * boost)
        # 峰值未达满幅时阈值下移到实际峰值附近，避免误伤
        if profile.peak_abs < 0.999:
            s.declip_threshold = max(0.80, min(0.95, profile.peak_abs * 0.97))
        else:
            s.declip_threshold = 0.90
        notes.append(f"自适应去削波(阈值{s.declip_threshold:.2f})")
    else:
        # 无削波 → 即使 intent>0 也跳过，保护干净音频
        s.declip = 0.0
        if declip_intent > 0:
            notes.append("无削波，跳过去削波")

    # —— 自适应 depop ——
    # 瞬态密度高 → 更可能含爆音；否则弱化
    depop_intent = float(intent.get("depop", 0) or 0)
    if depop_intent > 0:
        factor = 0.6 + profile.transient_density * 4.0  # transient 高→加强
        s.depop = _clamp(depop_intent * factor)

    # —— 自适应 de_ess ——
    # 仅在齿音能量确实偏高时生效；否则跳过，避免齿音被误削
    de_ess_intent = float(intent.get("de_ess", 0) or 0)
    if profile.has_sibilance() and de_ess_intent > 0:
        s.de_ess = _clamp(de_ess_intent * (1.0 + profile.sibilance_energy))
        s.sibilance_gate = profile.sibilance_energy
        notes.append(f"自适应去齿音(齿音{sibilance_pct(profile):.0f}%)")
    else:
        s.de_ess = 0.0
        if de_ess_intent > 0:
            notes.append("齿音正常，跳过去齿音")

    # —— 自适应降噪 ——
    # 门限=测量本底噪声；SNR 低才降噪，避免降噪剂吞噬高频空气感
    nr_intent = float(intent.get("noise_reduction", 0) or intent.get("ai_repair", 0) or 0)
    if profile.is_noisy() and nr_intent > 0:
        s.noise_reduction = _clamp(nr_intent)
        s.noise_gate_db = profile.noise_floor_db
        # ai_repair 自适应（谱减）强度受 SNR 调制
        ai_intent = float(intent.get("ai_repair_adaptive_lite", 0) or intent.get("ai_repair_adaptive", 0) or 0)
        if ai_intent > 0:
            s.ai_repair_adaptive = _clamp(ai_intent * (1.0 + max(0.0, (30.0 - profile.snr_db) / 30.0)))
        notes.append(f"自适应降噪(门限{s.noise_gate_db:.0f}dB)")
    else:
        s.noise_reduction = 0.0
        s.ai_repair_adaptive = 0.0
        if nr_intent > 0:
            notes.append("信噪比良好，跳过降噪")

    # —— exciter / compressor / transient / resonance ——
    # 这些是"增强类"操作，保留 intent，但 transient/resonance 受 profile 微调
    s.exciter = _clamp(float(intent.get("exciter", 0) or 0))
    comp_intent = float(intent.get("compressor", 0) or intent.get("smart_compressor", 0) or 0)
    s.compressor = _clamp(comp_intent)
    trans_intent = float(intent.get("transient", 0) or 0)
    if trans_intent > 0:
        # 瞬态密度高时加强瞬态修复
        s.transient = _clamp(trans_intent * (0.7 + profile.transient_density * 2.0))
    res_intent = float(intent.get("resonance", 0) or 0)
    # 频谱越不平（谐波多）越需要共振抑制
    if res_intent > 0 and profile.spectral_flatness < 0.5:
        s.resonance = _clamp(res_intent * (1.0 - profile.spectral_flatness))
    else:
        s.resonance = 0.0

    # —— bass / air / dynamic ——
    s.bass_enhance = _clamp(float(intent.get("bass_enhance", 0) or 0))
    # air_texture 仅在 HF 能量不足时增强
    air_intent = float(intent.get("air_texture", 0) or 0)
    if air_intent > 0:
        s.air_texture = _clamp(air_intent * (0.5 + max(0.0, 0.05 - profile.hf_energy) * 10.0))
    s.dynamic = _clamp(float(intent.get("dynamic", 0) or 0))

    # —— 自适应响度 ——
    loudness_intent = float(intent.get("loudness", 0) or 0)
    if loudness_intent > 0:
        # 目标 LUFS 随当前响度与动态范围调整，避免压扁已有动态
        target = -14.0
        if profile.dynamic_range_db < 6.0:
            # 动态已被压缩，目标偏保守
            target = -15.0
        elif profile.lufs_approx < -20.0:
            target = -13.0
        s.target_lufs = target
        s.loudness = loudness_intent
        notes.append(f"自适应响度(目标{target:.0f}LUFS)")

    # —— 二遍验证触发条件（v4.0a+）——
    # 检测到削波/噪声/齿音任一较严重时，premium 版触发二遍精修
    if premium:
        severe = (
            profile.clip_density > 0.01
            or profile.snr_db < 24.0
            or profile.sibilance_energy > 0.18
        )
        s.needs_verify = severe
        if severe:
            notes.append("触发二遍精修验证")

    s.notes = notes
    return s


def sibilance_pct(profile: SignalProfile) -> float:
    return profile.sibilance_energy * 100
