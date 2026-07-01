"""测试复杂处理链路的失真问题"""
import sys
sys.path.insert(0, 'backend')

import numpy as np
import soundfile as sf

from services.repair.repair_v3_2a.core import (
    loudness_normalize,
    soft_peak_limit,
    apply_air_texture_lite,
    vocal_exciter_lite,
    vocal_smart_compressor_lite,
    transparent_compress,
    apply_bass_enhance_lite,
    mastering_standard_lite,
    process_vocal_track,
)


def test_complex_chain():
    """测试复杂的处理链路"""
    print("\n" + "=" * 60)
    print("🔬 复杂处理链路测试")
    print("=" * 60)
    
    sr = 44100
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    # 生成复杂信号（类似真实音乐）
    y = (
        0.2 * np.sin(2 * np.pi * 60 * t) +        # 低音
        0.15 * np.sin(2 * np.pi * 120 * t) +      # 贝斯
        0.1 * np.sin(2 * np.pi * 250 * t) +       # 中低频
        0.1 * np.sin(2 * np.pi * 500 * t) +       # 中频
        0.08 * np.sin(2 * np.pi * 1000 * t) +     # 中高频
        0.05 * np.sin(2 * np.pi * 4000 * t) +     # 高频
        0.03 * np.random.randn(len(t))             # 噪声
    ).astype(np.float32)
    
    print(f"\n原始信号:")
    print(f"  RMS: {np.sqrt(np.mean(y**2)):.4f}")
    print(f"  峰值: {np.max(np.abs(y)):.4f}")
    
    # 模拟实际业务中的完整处理流程
    params = {
        "exciter": 0.5,           # 激励器
        "compressor": 0.6,        # 压缩器
        "loudness": 1.0,          # 响度优化
        "air_texture": 0.3,       # 空气感
        "bass_enhance": 0.4,      # 低音增强
    }
    
    print(f"\n处理参数: {params}")
    
    # 步骤1: exciter
    print(f"\n--- 1. exciter (0.5) ---")
    y_excited = vocal_exciter_lite(y.copy(), sr, 0.5)
    print(f"  峰值: {np.max(np.abs(y_excited)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_excited) > 1.0)} ({np.sum(np.abs(y_excited) > 1.0)/len(y)*100:.1f}%)")
    
    # 步骤2: compressor
    print(f"\n--- 2. compressor (0.6) ---")
    y_compressed = vocal_smart_compressor_lite(y_excited, sr, 0.6)
    print(f"  峰值: {np.max(np.abs(y_compressed)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_compressed) > 1.0)} ({np.sum(np.abs(y_compressed) > 1.0)/len(y)*100:.1f}%)")
    
    # 步骤3: bass_enhance
    print(f"\n--- 3. bass_enhance (0.4) ---")
    y_bass = apply_bass_enhance_lite(y_compressed, sr, 0.4)
    print(f"  峰值: {np.max(np.abs(y_bass)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_bass) > 1.0)} ({np.sum(np.abs(y_bass) > 1.0)/len(y)*100:.1f}%)")
    
    # 步骤4: loudness_normalize (关键步骤！)
    print(f"\n--- 4. loudness_normalize (-14 LUFS) ---")
    y_loud = loudness_normalize(y_bass, sr, -14.0)
    print(f"  峰值: {np.max(np.abs(y_loud)):.4f}")
    print(f"  RMS: {np.sqrt(np.mean(y_loud**2)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_loud) > 1.0)} ({np.sum(np.abs(y_loud) > 1.0)/len(y)*100:.1f}%)")
    
    if np.max(np.abs(y_loud)) > 1.1:
        print(f"  ⚠️  严重溢出！峰值超过1.0以上{(np.max(np.abs(y_loud)) - 1.0) * 100:.1f}%")
    
    # 步骤5: air_texture
    print(f"\n--- 5. air_texture (0.3) ---")
    y_air = apply_air_texture_lite(y_loud, sr, 0.3)
    print(f"  峰值: {np.max(np.abs(y_air)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_air) > 1.0)} ({np.sum(np.abs(y_air) > 1.0)/len(y)*100:.1f}%)")
    
    # 步骤6: soft_peak_limit
    print(f"\n--- 6. soft_peak_limit ---")
    y_final = soft_peak_limit(y_air, threshold=0.9)
    print(f"  峰值: {np.max(np.abs(y_final)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_final) > 1.0)} ({np.sum(np.abs(y_final) > 1.0)/len(y)*100:.1f}%)")
    
    # 步骤7: 导出PCM_24
    print(f"\n--- 7. 导出PCM_24 ---")
    sf.write('/tmp/test_complex.wav', y_final, sr, subtype='PCM_24')
    y_read, _ = sf.read('/tmp/test_complex.wav', dtype='float32')
    
    max_diff = np.max(np.abs(y_final - y_read))
    snr = 20 * np.log10(np.sqrt(np.mean(y_final**2)) / np.sqrt(np.mean((y_final - y_read)**2)))
    
    print(f"  导出差异: {max_diff:.8f}")
    print(f"  SNR: {snr:.1f} dB")
    
    if max_diff > 0.01:
        print(f"\n❌ 检测到严重失真！")
        print(f"  PCM_24无法准确表示超出[-1,1]范围的信号")
        print(f"  导致波形被截断，产生大量谐波失真")
    
    return max_diff, snr


def test_process_vocal_track():
    """测试完整的process_vocal_track函数"""
    print("\n" + "=" * 60)
    print("🔬 process_vocal_track 完整流程测试")
    print("=" * 60)
    
    sr = 44100
    duration = 1.5
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    # 真实音乐信号
    y = np.random.randn(len(t)).astype(np.float32) * 0.3
    y += 0.2 * np.sin(2 * np.pi * 200 * t).astype(np.float32)
    y += 0.1 * np.sin(2 * np.pi * 800 * t).astype(np.float32)
    
    params = {
        "declip": 0.0,
        "depop": 0.0,
        "de_ess": 0.0,
        "ai_repair": 0.0,
        "ai_repair_adaptive_lite": 0.0,
        "exciter": 0.5,
        "compressor": 0.6,
        "smart_compressor": 0.0,
        "transient": 0.0,
        "resonance": 0.0,
        "bass_enhance": 0.3,
        "air_texture": 0.4,
        "loudness": 1.0,
        "mastering_style": "standard",
        "bit_depth": 24,
    }
    
    print(f"\n输入峰值: {np.max(np.abs(y)):.4f}")
    
    # 调用完整处理流程（不包括export，只看process_vocal_track）
    y_processed = process_vocal_track(y.copy(), sr, params)
    
    print(f"输出峰值: {np.max(np.abs(y_processed)):.4f}")
    print(f"溢出样本: {np.sum(np.abs(y_processed) > 1.0)}")
    
    # 导出并读回
    sf.write('/tmp/test_vocal_track.wav', y_processed, sr, subtype='PCM_24')
    y_read, _ = sf.read('/tmp/test_vocal_track.wav', dtype='float32')
    
    max_diff = np.max(np.abs(y_processed - y_read))
    print(f"导出差异: {max_diff:.8f}")
    
    if max_diff > 0.005:
        print(f"⚠️  导出失真严重！")
    
    return max_diff


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔍 复杂处理链路失真排查")
    print("=" * 60)
    
    test_complex_chain()
    test_process_vocal_track()
