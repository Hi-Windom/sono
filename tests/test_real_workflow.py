"""测试实际业务流程中的失真问题"""
import sys
sys.path.insert(0, 'backend')

import numpy as np
import soundfile as sf

from services.repair.repair_v3_2a.core import (
    loudness_normalize,
    soft_peak_limit,
    apply_air_texture_lite,
    mix_tracks,
)


def test_realistic_workflow():
    """模拟真实业务流程：处理→混音→导出"""
    print("\n" + "=" * 60)
    print("🔬 真实业务流程测试")
    print("=" * 60)
    
    # 生成更接近真实的测试信号
    sr = 44100
    duration = 3.0  # 3秒
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    # 人声轨道：中频为主的复合信号
    vocal = (
        0.3 * np.sin(2 * np.pi * 250 * t) +      # 男声中频
        0.2 * np.sin(2 * np.pi * 500 * t) +      # 人声基频泛音
        0.15 * np.sin(2 * np.pi * 1000 * t) +    # 清晰度
        0.1 * np.random.randn(len(t)) * 0.3       # 噪声基底
    ).astype(np.float32)
    
    # 伴奏轨道：丰富的全频段
    accompaniment = (
        0.25 * np.sin(2 * np.pi * 80 * t) +       # 低音
        0.2 * np.sin(2 * np.pi * 200 * t) +       # 贝斯
        0.15 * np.sin(2 * np.pi * 400 * t) +      # 吉他
        0.1 * np.sin(2 * np.pi * 800 * t) +       # 键盘
        0.08 * np.sin(2 * np.pi * 4000 * t) +     # 镲片
        0.05 * np.random.randn(len(t)) * 0.5       # 噪声
    ).astype(np.float32)
    
    print(f"\n原始信号:")
    print(f"  人声 RMS: {np.sqrt(np.mean(vocal**2)):.4f}")
    print(f"  伴奏 RMS: {np.sqrt(np.mean(accompaniment**2)):.4f}")
    print(f"  人声峰值: {np.max(np.abs(vocal)):.4f}")
    print(f"  伴奏峰值: {np.max(np.abs(accompaniment)):.4f}")
    
    # 步骤1: 对人声进行loudness_normalize
    print(f"\n--- 步骤1: 人声 loudness_normalize ---")
    vocal_processed = loudness_normalize(vocal.copy(), sr, -14.0)
    print(f"  RMS: {np.sqrt(np.mean(vocal_processed**2)):.4f}")
    print(f"  峰值: {np.max(np.abs(vocal_processed)):.4f}")
    print(f"  溢出样本: {np.sum(np.abs(vocal_processed) > 1.0)} ({np.sum(np.abs(vocal_processed) > 1.0) / len(vocal_processed) * 100:.1f}%)")
    
    # 步骤2: 对伴奏进行loudness_normalize
    print(f"\n--- 步骤2: 伴奏 loudness_normalize ---")
    accompaniment_processed = loudness_normalize(accompaniment.copy(), sr, -14.0)
    print(f"  RMS: {np.sqrt(np.mean(accompaniment_processed**2)):.4f}")
    print(f"  峰值: {np.max(np.abs(accompaniment_processed)):.4f}")
    print(f"  溢出样本: {np.sum(np.abs(accompaniment_processed) > 1.0)} ({np.sum(np.abs(accompaniment_processed) > 1.0) / len(accompaniment_processed) * 100:.1f}%)")
    
    # 步骤3: 混音
    print(f"\n--- 步骤3: 混音 (vocal_ratio=1.0, accompaniment_ratio=1.0) ---")
    mixed = mix_tracks(vocal_processed, accompaniment_processed, 1.0, 1.0)
    print(f"  混音后 RMS: {np.sqrt(np.mean(mixed**2)):.4f}")
    print(f"  混音后峰值: {np.max(np.abs(mixed)):.4f}")
    print(f"  溢出样本: {np.sum(np.abs(mixed) > 1.0)} ({np.sum(np.abs(mixed) > 1.0) / len(mixed) * 100:.1f}%)")
    
    # 步骤4: soft_peak_limit
    print(f"\n--- 步骤4: soft_peak_limit ---")
    peaked = soft_peak_limit(mixed, threshold=0.9)
    print(f"  峰值限制后 RMS: {np.sqrt(np.mean(peaked**2)):.4f}")
    print(f"  峰值限制后峰值: {np.max(np.abs(peaked)):.4f}")
    print(f"  溢出样本: {np.sum(np.abs(peaked) > 1.0)} ({np.sum(np.abs(peaked) > 1.0) / len(peaked) * 100:.1f}%)")
    
    # 步骤5: air_texture
    print(f"\n--- 步骤5: air_texture (amount=0.3) ---")
    with_air = apply_air_texture_lite(peaked.copy(), sr, 0.3)
    print(f"  air_texture后 RMS: {np.sqrt(np.mean(with_air**2)):.4f}")
    print(f"  air_texture后峰值: {np.max(np.abs(with_air)):.4f}")
    print(f"  溢出样本: {np.sum(np.abs(with_air) > 1.0)} ({np.sum(np.abs(with_air) > 1.0) / len(with_air) * 100:.1f}%)")
    
    # 步骤6: 最终导出为PCM_24
    print(f"\n--- 步骤6: 导出为PCM_24 ---")
    output_path = '/tmp/test_real_workflow.wav'
    # 确保是mono以便soundfile写入
    if with_air.ndim > 1:
        with_air = with_air[0]
    sf.write(output_path, with_air, sr, subtype='PCM_24')
    
    # 读回检查
    y_read, sr_read = sf.read(output_path, dtype='float32')
    print(f"  读回后 RMS: {np.sqrt(np.mean(y_read**2)):.4f}")
    print(f"  读回后峰值: {np.max(np.abs(y_read)):.4f}")
    
    # 计算失真度 - 使用flatten确保维度匹配
    original_length = min(len(with_air.flatten()), len(y_read.flatten()))
    diff = np.abs(with_air.flatten()[:original_length] - y_read.flatten()[:original_length])
    
    max_diff = np.max(diff)
    snr = 20 * np.log10(np.sqrt(np.mean(with_air**2)) / np.sqrt(np.mean(diff**2))) if np.mean(diff**2) > 0 else float('inf')
    
    print(f"\n--- 失真分析 ---")
    print(f"  最大差异: {max_diff:.8f}")
    print(f"  SNR: {snr:.1f} dB")
    
    if max_diff > 0.01:
        print(f"\n⚠️  警告: 检测到显著失真!")
        print(f"  可能原因: PCM_24导出时浮点值超出[-1, 1]范围被截断")
    
    return max_diff, snr


def test_gain_stacking():
    """测试增益叠加问题"""
    print("\n" + "=" * 60)
    print("🔬 增益叠加测试")
    print("=" * 60)
    
    sr = 44100
    duration = 1.0
    t = np.linspace(0, duration, sr, dtype=np.float32)
    y = np.sin(2 * np.pi * 1000 * t).astype(np.float32) * 0.5
    
    print(f"\n初始信号:")
    print(f"  峰值: {np.max(np.abs(y)):.4f}")
    print(f"  RMS: {np.sqrt(np.mean(y**2)):.4f}")
    
    # 连续应用loudness_normalize
    for i in range(3):
        y_norm = loudness_normalize(y.copy(), sr, -14.0)
        peak_after = np.max(np.abs(y_norm))
        rms_after = np.sqrt(np.mean(y_norm**2))
        
        # 紧接着soft_peak_limit
        y_peaked = soft_peak_limit(y_norm)
        peak_peaked = np.max(np.abs(y_peaked))
        
        print(f"\n  loudness_normalize #{i+1}:")
        print(f"    峰值: {peak_after:.4f}, RMS: {rms_after:.4f}")
        print(f"    soft_peak_limit后峰值: {peak_peaked:.4f}")
        
        if peak_after > 1.0:
            print(f"    ⚠️  溢出: {(peak_after - 1.0) * 100:.2f}% 超出范围!")
        
        y = y_norm  # 用normalized的结果继续
    
    print(f"\n结论: 多次loudness_normalize叠加会导致严重溢出")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔍 真实业务流程失真排查")
    print("=" * 60)
    
    test_realistic_workflow()
    test_gain_stacking()
