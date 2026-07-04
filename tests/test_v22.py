#!/usr/bin/env python3
"""
v2.2 修复算法测试脚本
"""
import sys
import os
sys.path.insert(0, '/workspace/backend')

import numpy as np
from services.repair.repair_v2_2.music_type_detector import detect_music_type
from services.repair.repair_v2_2.type_params import TYPE_PARAMS_MAP, get_repair_mode_params
from services.dsp_native import is_native_available
from services.audio_repair import ALGORITHM_VERSIONS

def test_music_type_detection():
    """测试音乐类型检测"""
    print("=" * 50)
    print("测试音乐类型检测")
    print("=" * 50)

    # 生成测试信号
    sr = 48000
    duration = 2
    t = np.linspace(0, duration, int(sr * duration))

    # 模拟人声信号（低频 + 中频谐波）
    vocal_signal = np.sin(2 * np.pi * 440 * t) * 0.5  # 基频
    vocal_signal += np.sin(2 * np.pi * 880 * t) * 0.3  # 2次谐波
    vocal_signal += np.sin(2 * np.pi * 1320 * t) * 0.2  # 3次谐波
    vocal_signal += np.random.randn(len(t)) * 0.01

    music_type, confidence, features = detect_music_type(vocal_signal, sr)
    print(f"人声测试信号检测: {music_type} (置信度: {confidence:.2%})")
    print(f"  特征: 人声频段能量={features['vocal_band_energy']:.2%}, "
          f"频谱质心={features['spectral_centroid']:.0f}Hz")

    # 模拟电子音乐（高频 + 节奏规律）
    electronic_signal = np.sin(2 * np.pi * 100 * t) * 0.4
    electronic_signal += np.sin(2 * np.pi * 5000 * t) * 0.3
    electronic_signal += np.random.randn(len(t)) * 0.02

    music_type, confidence, features = detect_music_type(electronic_signal, sr)
    print(f"电子音乐测试信号检测: {music_type} (置信度: {confidence:.2%})")

    print("✓ 音乐类型检测测试完成\n")

def test_type_params():
    """测试类型参数配置"""
    print("=" * 50)
    print("测试类型参数配置")
    print("=" * 50)

    for music_type in ["vocal", "instrumental", "electronic", "classical", "pop", "generic"]:
        params = TYPE_PARAMS_MAP.get(music_type)
        print(f"{music_type}: 去齿音={params['de_essing']:.2f}, "
              f"谐波增强={params['harmonic_enhance']:.2f}, "
              f"动态范围={params['dynamic_range']:.2f}")

    # 测试修复模式参数
    for mode in ["smart", "vocal", "instrumental", "deep", "gentle"]:
        params = get_repair_mode_params(mode)
        print(f"模式 {mode}: 降噪={params['noise_reduction']:.2f}, "
              f"清晰度={params['clarity']:.2f}")

    print("✓ 类型参数配置测试完成\n")

def test_native_dsp():
    """测试 C 原生库 DSP"""
    print("=" * 50)
    print("测试 C 原生库 DSP")
    print("=" * 50)

    available = is_native_available()
    print(f"原生 DSP 库可用: {available}")

    if available:
        from services.dsp_native import stft_python, istft_python

        # 测试 STFT/ISTFT
        sr = 48000
        t = np.linspace(0, 1, sr)
        signal = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

        real, imag = stft_python(signal, n_fft=2048, hop_length=512)
        print(f"STFT 输出形状: {real.shape}")

        reconstructed = istft_python(real, imag, n_fft=2048, hop_length=512)
        print(f"ISTFT 重建信号长度: {len(reconstructed)}")

        # 计算重建误差
        error = np.mean((signal[:len(reconstructed)] - reconstructed) ** 2)
        print(f"重建误差 (MSE): {error:.6f}")

    print("✓ C 原生库 DSP 测试完成\n")

def test_v22_registration():
    """测试 v2.2 版本注册"""
    print("=" * 50)
    print("测试 v2.2 版本注册")
    print("=" * 50)

    assert "v2.2" in ALGORITHM_VERSIONS, "v2.2 未注册"
    v22_info = ALGORITHM_VERSIONS["v2.2"]

    print(f"版本名称: {v22_info['name']}")
    print(f"描述: {v22_info['description']}")
    print(f"移动端兼容: {v22_info['mobile_compatible']}")
    print(f"修复模式数量: {len(v22_info['modes'])}")

    for mode in v22_info['modes']:
        print(f"  - {mode['name']}: {mode['description']}")

    print("✓ v2.2 版本注册测试完成\n")

def main():
    print("\n" + "=" * 50)
    print("AI 修复算法 v2.2 集成测试")
    print("=" * 50 + "\n")

    try:
        test_music_type_detection()
        test_type_params()
        test_native_dsp()
        test_v22_registration()

        print("=" * 50)
        print("所有测试通过！✓")
        print("=" * 50)
        return 0
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
