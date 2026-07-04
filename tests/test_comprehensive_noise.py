#!/usr/bin/env python3
"""全面排查杂音问题 - 模拟完整处理链路"""
import sys
sys.path.insert(0, '/workspace/backend')

import numpy as np
import soundfile as sf
import tempfile
import os

from services.repair.repair_v3_2a.core import (
    soft_peak_limit,
    apply_air_texture_lite,
    loudness_normalize,
)
from services.repair.repair_v4_0a.core import process_track_adaptive


def compute_snr(original, processed):
    """计算SNR (dB)"""
    min_len = min(len(original), len(processed))
    sig = original[:min_len].astype(np.float64)
    proc = processed[:min_len].astype(np.float64)
    noise = proc - sig
    if np.std(sig) < 1e-10:
        return float('inf')
    snr = 20 * np.log10(np.std(sig) / (np.std(noise) + 1e-12))
    return snr


def generate_realistic_audio(duration=10.0, sr=44100):
    """生成更接近真实音频的信号 (包含语音和音乐特征)"""
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    # 模拟语音/音乐: 基频 + 泛音 + 噪声基底
    y = np.zeros(int(sr * duration), dtype=np.float32)
    
    # 基频 (100-300Hz 语音范围)
    for f0 in [150, 200, 250]:
        y += 0.2 * np.sin(2 * np.pi * f0 * t)
    
    # 泛音 (1kHz-8kHz)
    for h in [2, 3, 4, 5, 8]:
        y += (0.1 / h) * np.sin(2 * np.pi * 150 * h * t)
    
    # 高频空气感 (10kHz-16kHz)
    for fh in [10000, 12000, 14000, 15500]:
        y += 0.02 * np.sin(2 * np.pi * fh * t)
    
    # 轻微的自然噪声
    y += 0.001 * np.random.randn(len(t)).astype(np.float32)
    
    # 归一化到-6dB
    y = y / (np.max(np.abs(y)) + 1e-10) * 0.5
    
    return y


def test_air_texture_only():
    """单独测试air_texture"""
    print("\n" + "="*60)
    print("测试1: apply_air_texture_lite 独立测试")
    print("="*60)
    
    sr = 44100
    y = generate_realistic_audio(duration=5.0)
    
    print(f"\n输入信号: {len(y)} 样本, SR={sr}")
    print(f"输入最大值: {np.max(np.abs(y)):.6f}")
    
    # 测试多次，看是否每次产生不同输出
    results = []
    for i in range(3):
        y_test = y.copy()
        y_out = apply_air_texture_lite(y_test, sr, amount=0.5)
        results.append(y_out.copy())
        
        snr = compute_snr(y, y_out)
        noise_rms = np.sqrt(np.mean((y_out - y)**2))
        
        print(f"\n调用#{i+1}:")
        print(f"  SNR: {snr:.1f} dB")
        print(f"  噪声RMS: {noise_rms:.8f}")
        
        if i > 0:
            diff = np.max(np.abs(results[i] - results[0]))
            print(f"  与#1的最大差异: {diff:.10f}")
            if diff > 1e-6:
                print(f"  ❗ 不可复现! 随机噪声被添加")
    
    return results[0] if results else None


def test_v40a_pipeline():
    """测试v4.0a完整管线"""
    print("\n" + "="*60)
    print("测试2: v4.0a process_track_adaptive 管线")
    print("="*60)
    
    sr = 44100
    y = generate_realistic_audio(duration=5.0)
    
    print(f"\n输入信号: {len(y)} 样本, SR={sr}")
    
    intent = {
        'air_texture': 0.5,
        'clarity': 0.3,
        'exciter': 0.2,
        'resonance': 0.1,
    }
    
    print(f"意图参数: {intent}")
    
    y_processed, notes = process_track_adaptive(y, sr, intent)
    
    snr = compute_snr(y, y_processed)
    noise_rms = np.sqrt(np.mean((y_processed - y)**2))
    
    print(f"\n处理笔记: {notes}")
    print(f"SNR: {snr:.1f} dB")
    print(f"输入最大值: {np.max(np.abs(y)):.6f}")
    print(f"输出最大值: {np.max(np.abs(y_processed)):.6f}")
    print(f"噪声RMS: {noise_rms:.8f}")
    
    if snr < 30:
        print(f"\n❗ v4.0a管线引入严重失真!")
    elif snr < 40:
        print(f"\n⚠️ v4.0a管线引入明显失真")
    else:
        print(f"\n✓ v4.0a管线质量良好")
    
    return y_processed


def test_export_conversion():
    """测试导出时的dtype转换"""
    print("\n" + "="*60)
    print("测试3: soundfile导出与dtype转换")
    print("="*60)
    
    sr = 44100
    y = generate_realistic_audio(duration=5.0)
    
    print(f"\n原始float32: min={y.min():.6f}, max={y.max():.6f}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试PCM_24导出
        path_pcm24 = os.path.join(tmpdir, 'test_pcm24.wav')
        sf.write(path_pcm24, y, sr, subtype='PCM_24')
        
        y_read, sr_read = sf.read(path_pcm24, dtype='float32')
        
        diff = np.max(np.abs(y.astype(np.float64) - y_read))
        snr = compute_snr(y, y_read)
        
        print(f"\nPCM_24导出后:")
        print(f"  采样率: {sr_read} Hz")
        print(f"  最大值: {np.max(np.abs(y_read)):.6f}")
        print(f"  往返误差: {diff:.8f}")
        print(f"  SNR: {snr:.1f} dB")
        
        # 测试先转float64再导出
        y_float64 = y.astype(np.float64)
        path_pcm24_2 = os.path.join(tmpdir, 'test_pcm24_2.wav')
        sf.write(path_pcm24_2, y_float64, sr, subtype='PCM_24')
        
        y_read2, _ = sf.read(path_pcm24_2, dtype='float32')
        diff2 = np.max(np.abs(y.astype(np.float64) - y_read2))
        
        print(f"\n先转float64再PCM_24:")
        print(f"  往返误差: {diff2:.8f}")
        print(f"  与直接PCM_24的差异: {np.max(np.abs(y_read - y_read2)):.10f}")
        
        if diff > 0.001 or diff2 > 0.001:
            print(f"  ⚠️ PCM_24量化误差较大但正常")
        else:
            print(f"  ✓ 转换误差极小")


def test_soft_peak_limit_edge_cases():
    """测试soft_peak_limit的边界情况"""
    print("\n" + "="*60)
    print("测试4: soft_peak_limit 边界情况")
    print("="*60)
    
    sr = 44100
    
    # 情况1: 信号远低于阈值
    y1 = np.random.randn(44100).astype(np.float32) * 0.1
    y1_out = soft_peak_limit(y1.copy())
    print(f"\n低电平信号 (max=0.1):")
    print(f"  输入max: {np.max(np.abs(y1)):.4f}")
    print(f"  输出max: {np.max(np.abs(y1_out)):.4f}")
    print(f"  是否被修改: {not np.allclose(y1, y1_out)}")
    
    # 情况2: 信号接近阈值
    y2 = np.random.randn(44100).astype(np.float32) * 0.85
    y2_out = soft_peak_limit(y2.copy())
    print(f"\n中等电平信号 (max=0.85):")
    print(f"  输入max: {np.max(np.abs(y2)):.4f}")
    print(f"  输出max: {np.max(np.abs(y2_out)):.4f}")
    print(f"  是否被修改: {not np.allclose(y2, y2_out)}")
    
    # 情况3: 信号超过阈值
    y3 = np.random.randn(44100).astype(np.float32) * 0.95
    y3_out = soft_peak_limit(y3.copy())
    print(f"\n高电平信号 (max=0.95):")
    print(f"  输入max: {np.max(np.abs(y3)):.4f}")
    print(f"  输出max: {np.max(np.abs(y3_out)):.4f}")
    print(f"  是否被修改: {not np.allclose(y3, y3_out)}")
    
    # 情况4: 满幅信号
    y4 = np.ones(44100, dtype=np.float32) * 1.0
    y4_out = soft_peak_limit(y4.copy())
    print(f"\n满幅信号 (max=1.0):")
    print(f"  输入max: {np.max(np.abs(y4)):.4f}")
    print(f"  输出max: {np.max(np.abs(y4_out)):.4f}")
    print(f"  是否被修改: {not np.allclose(y4, y4_out)}")


def test_mixed_signals():
    """测试混合信号处理"""
    print("\n" + "="*60)
    print("测试5: 模拟实际处理流程")
    print("="*60)
    
    sr = 44100
    y = generate_realistic_audio(duration=5.0)
    
    print(f"\n原始信号:")
    print(f"  最大值: {np.max(np.abs(y)):.6f}")
    print(f"  RMS: {np.sqrt(np.mean(y**2)):.6f}")
    
    # 步骤1: soft_peak_limit
    y = soft_peak_limit(y)
    print(f"\nsoft_peak_limit后:")
    print(f"  最大值: {np.max(np.abs(y)):.6f}")
    
    # 步骤2: air_texture
    y_air = y.copy()
    y = apply_air_texture_lite(y, sr, amount=0.5)
    snr_air = compute_snr(y_air, y)
    print(f"\napply_air_texture_lite后:")
    print(f"  最大值: {np.max(np.abs(y)):.6f}")
    print(f"  与处理前的SNR: {snr_air:.1f} dB")
    
    # 步骤3: 再次soft_peak_limit (模拟导出前处理)
    y_before = y.copy()
    y = soft_peak_limit(y)
    snr_peak = compute_snr(y_before, y)
    print(f"\n最终soft_peak_limit后:")
    print(f"  最大值: {np.max(np.abs(y)):.6f}")
    print(f"  与处理前的SNR: {snr_peak:.1f} dB")
    
    # 步骤4: 导出PCM_24
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        sf.write(tmp_path, y, sr, subtype='PCM_24')
        y_final, _ = sf.read(tmp_path, dtype='float32')
        
        snr_final = compute_snr(generate_realistic_audio(duration=5.0), y_final)
        diff_final = np.max(np.abs(y.astype(np.float64) - y_final))
        
        print(f"\nPCM_24导出后:")
        print(f"  最大值: {np.max(np.abs(y_final)):.6f}")
        print(f"  与导出前的差异: {diff_final:.8f}")
        print(f"  总SNR: {snr_final:.1f} dB")
        
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔍 杂音问题全面排查")
    print("="*60)
    
    test_air_texture_only()
    test_v40a_pipeline()
    test_export_conversion()
    test_soft_peak_limit_edge_cases()
    test_mixed_signals()
    
    print("\n" + "="*60)
    print("排查结论")
    print("="*60)
    print("\n请检查以上测试结果，特别关注:")
    print("1. air_texture是否每次产生不同输出 (随机性)")
    print("2. v4.0a管线的整体SNR")
    print("3. PCM_24导出的量化误差")
    print("4. soft_peak_limit是否过度处理")
