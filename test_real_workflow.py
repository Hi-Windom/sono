#!/usr/bin/env python3
"""模拟实际业务音频处理流程"""
import sys
sys.path.insert(0, '/workspace/backend')
import numpy as np
import soundfile as sf
from services.repair.repair_v3_2a.core import (
    loudness_normalize,
    soft_peak_limit,
    apply_air_texture_lite,
)

def simulate_real_processing():
    """模拟真实音频的完整处理流程"""
    print("="*60)
    print("模拟实际业务处理流程")
    print("="*60)
    
    # 生成模拟真实音频（类似音乐/语音）
    sr = 44100
    duration = 10.0
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    # 混合多个频率（模拟音乐）
    y = np.zeros_like(t, dtype=np.float32)
    for freq, amp in [(200, 0.3), (400, 0.2), (800, 0.15), (1000, 0.25), (4000, 0.1)]:
        y += amp * np.sin(2 * np.pi * freq * t)
    
    # 添加瞬态脉冲（鼓声等）
    impulse_pos = int(sr * 2.5)  # 2.5秒处
    y[impulse_pos:impulse_pos+100] *= 3.0  # 瞬时高峰
    
    # 归一化到-3dB（真实音频常见）
    y = y / (np.max(np.abs(y)) + 1e-10) * 0.7
    
    print(f"\n初始信号:")
    print(f"  采样率: {sr} Hz, 时长: {duration}s")
    print(f"  dtype: {y.dtype}")
    print(f"  min/max: [{y.min():.4f}, {y.max():.4f}]")
    print(f"  RMS: {np.sqrt(np.mean(y**2)):.4f}")
    print(f"  Peak: {np.max(np.abs(y)):.4f}")
    
    # 步骤1: loudness_normalize (关键步骤！)
    print(f"\n{'─'*60}")
    print("步骤1: loudness_normalize (target_lufs=-14)")
    print(f"{'─'*60}")
    
    y_before = y.copy()
    y = loudness_normalize(y, sr, target_lufs=-14.0)
    
    print(f"  min/max: [{y.min():.4f}, {y.max():.4f}]")
    print(f"  RMS: {np.sqrt(np.mean(y**2)):.4f}")
    print(f"  Peak: {np.max(np.abs(y)):.4f}")
    print(f"  是否溢出(>1.0): {np.any(np.abs(y) > 1.0)}")
    if np.any(np.abs(y) > 1.0):
        overflow_count = np.sum(np.abs(y) > 1.0)
        overflow_max = np.max(np.abs(y))
        print(f"  ⚠️ 溢出样本数: {overflow_count} ({overflow_count/len(y)*100:.2f}%)")
        print(f"  ⚠️ 最大溢出值: {overflow_max:.4f}")
    
    # 步骤2: soft_peak_limit
    print(f"\n{'─'*60}")
    print("步骤2: soft_peak_limit (threshold=0.9)")
    print(f"{'─'*60}")
    
    y_before_peak = y.copy()
    y = soft_peak_limit(y, threshold=0.9)
    
    print(f"  min/max: [{y.min():.4f}, {y.max():.4f}]")
    print(f"  Peak: {np.max(np.abs(y)):.4f}")
    print(f"  是否仍有溢出: {np.any(np.abs(y) > 1.0)}")
    
    # 步骤3: air_texture
    print(f"\n{'─'*60}")
    print("步骤3: apply_air_texture_lite (amount=0.5)")
    print(f"{'─'*60}")
    
    y_before_air = y.copy()
    y = apply_air_texture_lite(y, sr, amount=0.5)
    
    print(f"  min/max: [{y.min():.4f}, {y.max():.4f}]")
    print(f"  Peak: {np.max(np.abs(y)):.4f}")
    
    # 步骤4: 最终soft_peak_limit
    print(f"\n{'─'*60}")
    print("步骤4: 最终 soft_peak_limit")
    print(f"{'─'*60}")
    
    y = soft_peak_limit(y, threshold=0.9)
    
    print(f"  min/max: [{y.min():.4f}, {y.max():.4f}]")
    print(f"  Peak: {np.max(np.abs(y)):.4f}")
    
    # 步骤5: 导出PCM_24
    print(f"\n{'─'*60}")
    print("步骤5: PCM_24导出")
    print(f"{'─'*60}")
    
    # 模拟v4.0a的导出逻辑
    if y.dtype == np.float32:
        y_export = y.astype(np.float64)
    else:
        y_export = y
    
    print(f"  导出dtype: {y_export.dtype}")
    print(f"  导出min/max: [{y_export.min():.6f}, {y_export.max():.6f}]")
    
    # 写入并读取
    sf.write('/tmp/test_real_workflow.wav', y_export, sr, subtype='PCM_24')
    y_read, _ = sf.read('/tmp/test_real_workflow.wav', dtype='float32')
    
    print(f"\n  读取后min/max: [{y_read.min():.4f}, {y_read.max():.4f}]")
    
    # 计算整体SNR
    min_len = min(len(y_read), len(y_before))
    snr = 20 * np.log10(
        np.std(y_before[:min_len].astype(np.float64)) / 
        (np.std(y_read[:min_len] - y_before[:min_len].astype(np.float32)) + 1e-12)
    )
    
    print(f"\n  整体处理SNR: {snr:.1f} dB")
    
    if snr < 20:
        print(f"  ❗ 严重失真！")
    elif snr < 30:
        print(f"  ⚠️ 明显失真")
    elif snr < 40:
        print(f"  ⚠️ 轻微失真")
    else:
        print(f"  ✓ 质量良好")
    
    return y_read


def test_gain_overflow():
    """专门测试gain导致的溢出"""
    print("\n" + "="*60)
    print("测试gain溢出问题")
    print("="*60)
    
    sr = 44100
    
    # 场景1: 安静信号 (RMS=0.01)
    y1 = np.random.randn(sr * 10).astype(np.float32) * 0.01
    rms1 = np.sqrt(np.mean(y1**2))
    target_rms = 10 ** (-14.0 / 20.0)  # ≈ 0.1995
    gain1 = target_rms / rms1
    gain1_clipped = min(gain1, 5.0)
    
    print(f"\n场景1: 安静信号")
    print(f"  输入RMS: {rms1:.4f}")
    print(f"  目标RMS: {target_rms:.4f}")
    print(f"  理论gain: {gain1:.2f}")
    print(f"   clipped gain: {gain1_clipped:.2f}")
    
    y1_out = y1 * gain1_clipped
    print(f"  输出Peak: {np.max(np.abs(y1_out)):.4f}")
    print(f"  溢出: {np.max(np.abs(y1_out)) > 1.0}")
    
    # 场景2: 中等信号 (RMS=0.1)
    y2 = np.random.randn(sr * 10).astype(np.float32) * 0.1
    rms2 = np.sqrt(np.mean(y2**2))
    gain2 = target_rms / rms2
    gain2_clipped = min(max(gain2, 0.2), 5.0)
    
    print(f"\n场景2: 中等信号")
    print(f"  输入RMS: {rms2:.4f}")
    print(f"  理论gain: {gain2:.2f}")
    print(f"  clipped gain: {gain2_clipped:.2f}")
    
    y2_out = y2 * gain2_clipped
    print(f"  输出Peak: {np.max(np.abs(y2_out)):.4f}")
    print(f"  溢出: {np.max(np.abs(y2_out)) > 1.0}")
    
    # 场景3: 已有较高RMS的信号 (RMS=0.3)
    y3 = np.random.randn(sr * 10).astype(np.float32) * 0.3
    rms3 = np.sqrt(np.mean(y3**2))
    gain3 = target_rms / rms3
    gain3_clipped = min(max(gain3, 0.2), 5.0)
    
    print(f"\n场景3: 较高信号")
    print(f"  输入RMS: {rms3:.4f}")
    print(f"  理论gain: {gain3:.2f}")
    print(f"  clipped gain: {gain3_clipped:.2f}")
    
    y3_out = y3 * gain3_clipped
    print(f"  输出Peak: {np.max(np.abs(y3_out)):.4f}")
    print(f"  溢出: {np.max(np.abs(y3_out)) > 1.0}")


if __name__ == "__main__":
    simulate_real_processing()
    test_gain_overflow()
    
    print("\n" + "="*60)
    print("诊断结论")
    print("="*60)
    print("\n如果看到溢出(>1.0)，问题可能是:")
    print("1. loudness_normalize的gain过大")
    print("2. soft_peak_limit无法完全修复溢出")
    print("3. 多重处理叠加导致失真累积")
