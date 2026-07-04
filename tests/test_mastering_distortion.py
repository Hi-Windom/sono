"""测试包含mastering的复杂流程"""
import sys
sys.path.insert(0, 'backend')

import numpy as np
import soundfile as sf

from services.repair.repair_v3_2a.core import (
    loudness_normalize,
    soft_peak_limit,
    apply_air_texture_lite,
    mastering_standard_lite,
    mastering_powerful_lite,
    process_vocal_track,
)


def test_mastering_distortion():
    """测试mastering导致的失真"""
    print("\n" + "=" * 60)
    print("🔬 Mastering失真测试")
    print("=" * 60)
    
    sr = 44100
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    # 生成高动态范围信号
    y = (
        0.4 * np.sin(2 * np.pi * 100 * t) +
        0.3 * np.random.randn(len(t)).astype(np.float32) * 0.5
    )
    
    print(f"\n原始信号:")
    print(f"  RMS: {np.sqrt(np.mean(y**2)):.4f}")
    print(f"  峰值: {np.max(np.abs(y)):.4f}")
    
    # 场景1: 先loudness_normalize再mastering
    print(f"\n--- 场景1: loudness → mastering_standard ---")
    y1 = loudness_normalize(y.copy(), sr, -14.0)
    print(f"  loudness后峰值: {np.max(np.abs(y1)):.4f}")
    
    y1_master = mastering_standard_lite(y1.copy(), sr)
    print(f"  mastering后峰值: {np.max(np.abs(y1_master)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y1_master) > 1.0)} ({np.sum(np.abs(y1_master) > 1.0)/len(y1_master)*100:.1f}%)")
    
    # 导出
    sf.write('/tmp/test_mastering1.wav', y1_master, sr, subtype='PCM_24')
    y1_read, _ = sf.read('/tmp/test_mastering1.wav', dtype='float32')
    diff1 = np.max(np.abs(y1_master - y1_read))
    print(f"  导出差异: {diff1:.8f}")
    
    # 场景2: 先mastering再loudness_normalize
    print(f"\n--- 场景2: mastering_standard → loudness ---")
    y2 = mastering_standard_lite(y.copy(), sr)
    print(f"  mastering后峰值: {np.max(np.abs(y2)):.4f}")
    
    y2_loud = loudness_normalize(y2.copy(), sr, -14.0)
    print(f"  loudness后峰值: {np.max(np.abs(y2_loud)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y2_loud) > 1.0)} ({np.sum(np.abs(y2_loud) > 1.0)/len(y2_loud)*100:.1f}%)")
    
    # 场景3: powerful mastering
    print(f"\n--- 场景3: mastering_powerful ---")
    y3 = mastering_powerful_lite(y.copy(), sr)
    print(f"  mastering后峰值: {np.max(np.abs(y3)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y3) > 1.0)} ({np.sum(np.abs(y3) > 1.0)/len(y3)*100:.1f}%)")
    
    # 场景4: 完整process_vocal_track包含mastering
    print(f"\n--- 场景4: process_vocal_track with mastering ---")
    params = {
        "declip": 0.0,
        "depop": 0.0,
        "de_ess": 0.0,
        "ai_repair": 0.0,
        "ai_repair_adaptive_lite": 0.0,
        "exciter": 0.3,
        "compressor": 0.4,
        "smart_compressor": 0.0,
        "transient": 0.0,
        "resonance": 0.0,
        "bass_enhance": 0.2,
        "air_texture": 0.3,
        "loudness": 1.0,
        "mastering_style": "standard",
        "bit_depth": 24,
    }
    
    y4 = process_vocal_track(y.copy(), sr, params)
    print(f"  输出峰值: {np.max(np.abs(y4)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y4) > 1.0)} ({np.sum(np.abs(y4) > 1.0)/len(y4)*100:.1f}%)")
    
    # 导出
    sf.write('/tmp/test_vocal_full.wav', y4, sr, subtype='PCM_24')
    y4_read, _ = sf.read('/tmp/test_vocal_full.wav', dtype='float32')
    diff4 = np.max(np.abs(y4 - y4_read))
    snr4 = 20 * np.log10(np.sqrt(np.mean(y4**2)) / np.sqrt(np.mean((y4 - y4_read)**2)))
    
    print(f"\n  导出差异: {diff4:.8f}")
    print(f"  SNR: {snr4:.1f} dB")
    
    if diff4 > 0.01:
        print(f"\n❌ 严重失真！PCM_24截断导致大量谐波")
        print(f"   这解释了为什么用户听到'全程失真听不出原曲'")
    
    return diff4, snr4


def test_high_input_level():
    """测试高输入电平的极端情况"""
    print("\n" + "=" * 60)
    print("🔬 高输入电平测试")
    print("=" * 60)
    
    sr = 44100
    duration = 1.0
    t = np.linspace(0, duration, sr, dtype=np.float32)
    
    # 假设输入已经是高峰值信号（如未经压缩的打击乐）
    y = np.sin(2 * np.pi * 1000 * t).astype(np.float32) * 0.9
    
    print(f"\n高电平输入:")
    print(f"  峰值: {np.max(np.abs(y)):.4f}")
    
    # 直接应用loudness_normalize（会大幅放大低电平部分）
    y_norm = loudness_normalize(y.copy(), sr, -14.0)
    print(f"\nloudness_normalize后:")
    print(f"  峰值: {np.max(np.abs(y_norm)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_norm) > 1.0)}")
    
    # 再应用mastering
    y_master = mastering_standard_lite(y_norm.copy(), sr)
    print(f"\nmastering_standard后:")
    print(f"  峰值: {np.max(np.abs(y_master)):.4f}")
    print(f"  溢出: {np.sum(np.abs(y_master) > 1.0)} ({np.sum(np.abs(y_master) > 1.0)/len(y_master)*100:.1f}%)")
    
    # soft_peak_limit后
    y_final = soft_peak_limit(y_master, threshold=0.9)
    print(f"\nsoft_peak_limit后:")
    print(f"  峰值: {np.max(np.abs(y_final)):.4f}")
    
    # 导出
    sf.write('/tmp/test_high_level.wav', y_final, sr, subtype='PCM_24')
    y_read, _ = sf.read('/tmp/test_high_level.wav', dtype='float32')
    diff = np.max(np.abs(y_final - y_read))
    
    print(f"\n导出差异: {diff:.8f}")
    if diff > 0.001:
        print(f"⚠️  即使经过soft_peak_limit仍有导出失真！")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔍 Mastering导致的失真排查")
    print("=" * 60)
    
    test_mastering_distortion()
    test_high_input_level()
