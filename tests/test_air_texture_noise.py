#!/usr/bin/env python3
"""测试air_texture模块引入随机噪声的问题"""
import sys
sys.path.insert(0, '/workspace/backend')

import numpy as np
import soundfile as sf

from services.repair.repair_v3_2a.core import apply_air_texture_lite


def compute_snr(original, processed):
    """计算SNR (dB)"""
    min_len = min(len(original), len(processed))
    sig = original[:min_len].astype(np.float64)
    noise = processed[:min_len].astype(np.float64) - sig
    if np.std(sig) < 1e-10:
        return float('inf')
    snr = 20 * np.log10(np.std(sig) / (np.std(noise) + 1e-12))
    return snr


def test_air_texture_noise():
    """测试air_texture是否引入了随机噪声"""
    print("=" * 60)
    print("测试 air_texture 模块引入随机噪声")
    print("=" * 60)
    
    # 生成干净的测试信号 (1kHz正弦波 + 低频 + 高频成分)
    sr = 44100
    duration = 5.0  # 5秒
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    # 干净的复合信号 (包含高频成分以触发air_texture处理)
    y_clean = (0.5 * np.sin(2 * np.pi * 1000 * t) + 
               0.3 * np.sin(2 * np.pi * 200 * t) +
               0.1 * np.sin(2 * np.pi * 8000 * t)).astype(np.float32)
    
    print(f"\n测试信号: 1kHz + 200Hz + 8kHz 正弦波")
    print(f"采样率: {sr} Hz, 时长: {duration}s, 样本数: {len(y_clean)}")
    
    # 多次测试，看每次是否产生不同的噪声
    snrs = []
    for i in range(5):
        y_test = y_clean.copy()
        y_processed = apply_air_texture_lite(y_test, sr, amount=0.5)
        
        snr = compute_snr(y_clean, y_processed)
        snrs.append(snr)
        
        noise = y_processed - y_clean
        noise_rms = np.sqrt(np.mean(noise**2))
        
        print(f"\n测试 #{i+1}:")
        print(f"  SNR: {snr:.1f} dB")
        print(f"  噪声RMS: {noise_rms:.6f}")
        
        if snr < 40:
            print(f"  ⚠️ SNR过低! 输出包含显著噪声!")
        else:
            print(f"  ✓ SNR较高")
    
    print(f"\n平均SNR: {np.mean(snrs):.1f} ± {np.std(snrs):.1f} dB")
    
    # 测试可复现性
    print("\n" + "=" * 60)
    print("测试可复现性 (相同输入是否产生相同输出)")
    print("=" * 60)
    
    y1 = y_clean.copy()
    y2 = y_clean.copy()
    
    y_out1 = apply_air_texture_lite(y1, sr, amount=0.5)
    y_out2 = apply_air_texture_lite(y2, sr, amount=0.5)
    
    diff = np.max(np.abs(y_out1 - y_out2))
    print(f"\n两次调用最大差异: {diff:.10f}")
    
    if diff > 1e-6:
        print("  ❌ 不可复现! 每次调用产生不同输出 (随机噪声)")
        print("  ✅ 确认问题根源: apply_air_texture_lite 使用 np.random.randn()")
        return False
    else:
        print("  ✓ 可复现")
        return True


def test_air_texture_real_world():
    """使用真实音频测试"""
    print("\n" + "=" * 60)
    print("真实音频测试")
    print("=" * 60)
    
    # 找一个测试音频
    test_audio = "/workspace/test_audio_input.wav"
    
    try:
        y, sr = sf.read(test_audio, dtype='float32')
        if y.ndim > 1:
            y = y.mean(axis=1)
        
        print(f"\n加载测试音频: {sr} Hz, {len(y)} 样本")
        
        # 处理前后对比
        y_processed = apply_air_texture_lite(y.copy(), sr, amount=0.5)
        
        # 保存处理后的音频
        output_path = "/workspace/test_air_texture_output.wav"
        sf.write(output_path, y_processed, sr)
        print(f"已保存到: {output_path}")
        
        # 计算SNR
        snr = compute_snr(y, y_processed)
        print(f"\n处理前后SNR: {snr:.1f} dB")
        
        if snr < 30:
            print("  ⚠️ 噪声显著!")
            return False
        else:
            print("  ✓ SNR尚可接受")
            return True
            
    except FileNotFoundError:
        print(f"\n⚠️ 测试音频不存在: {test_audio}")
        print("  跳过真实音频测试")
        return None


if __name__ == "__main__":
    print("\n🔍 排查杂音问题 - air_texture模块分析\n")
    
    result1 = test_air_texture_noise()
    result2 = test_air_texture_real_world()
    
    print("\n" + "=" * 60)
    print("结论")
    print("=" * 60)
    
    if result1 is False:
        print("\n❌ 确认问题根源:")
        print("   apply_air_texture_lite() 函数使用 np.random.randn() 添加随机噪声")
        print("   每次调用产生不同输出，导致不可控的杂音")
        print("\n📍 问题位置:")
        print("   backend/services/repair/repair_v3_2a/core.py:688-689")
        print("   backend/services/repair/repair_v4_0a/core.py: 调用此函数")
        print("\n💡 建议修复方案:")
        print("   1. 移除随机噪声添加 (推荐)")
        print("   2. 或使用确定性的高频增强算法 (如倍频、谐波激励)")
        print("   3. 如需随机性，应设置固定随机种子")
    elif result1 is True:
        print("\n✓ air_texture模块未引入随机噪声")
    else:
        print("\n⚠️ 测试结果不确定")
