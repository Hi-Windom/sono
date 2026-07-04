#!/usr/bin/env python3
"""
测试脚本: 验证"空气感"(air_texture)模块引入电滋滋杂音的问题
"""
import sys
import numpy as np
import tempfile
import soundfile as sf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from services.repair.repair_v3_2a.core import apply_air_texture_lite, soft_peak_limit
from services.repair.repair_v4_0a.core import process_track_adaptive
from services.dsp_utils import stft, istft


def generate_clean_tone(freq=440, duration=2.0, sr=44100, amp=0.5):
    """生成干净的测试音调"""
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    return amp * np.sin(2 * np.pi * freq * t)


def compute_snr(clean, noisy):
    """计算信噪比(dB)"""
    assert len(clean) == len(noisy), "长度必须一致"
    noise = noisy - clean
    clean_power = np.mean(clean ** 2)
    noise_power = np.mean(noise ** 2)
    if noise_power < 1e-20:
        return 999.0
    if clean_power < 1e-20:
        return -999.0
    snr = 10 * np.log10(clean_power / noise_power)
    return snr


def test_air_texture_adds_noise():
    """测试1: air_texture模块是否添加了随机噪声"""
    print("=" * 70)
    print("测试1: air_texture模块噪声注入验证")
    print("=" * 70)
    
    sr = 44100
    y_clean = generate_clean_tone(sr=sr)
    
    # 对同一个干净信号多次应用air_texture,看输出是否不同(随机性)
    results = []
    for i in range(3):
        y_test = y_clean.copy().reshape(1, -1)
        y_processed = apply_air_texture_lite(y_test, sr, amount=0.5)
        results.append(y_processed[0])
        
        snr = compute_snr(y_clean, y_processed[0])
        print(f"  第{i+1}次处理: SNR = {snr:.1f} dB")
    
    # 检查三次结果是否相同(如果相同说明没有随机噪声)
    for i in range(1, 3):
        diff = np.max(np.abs(results[0] - results[i]))
        print(f"  结果[{i}]与结果[0]的最大差异: {diff:.2e}")
        if diff > 1e-6:
            print("  ⚠️ 检测到随机性! 每次处理结果不同,说明注入了随机噪声!")
            return True
    
    print("  ✓ 无随机性检测")
    return False


def test_air_texture_high_frequency_noise():
    """测试2: air_texture是否在高频段注入噪声"""
    print("\n" + "=" * 70)
    print("测试2: air_texture高频噪声频谱分析")
    print("=" * 70)
    
    sr = 48000
    # 使用低频信号(200Hz),这样任何高频噪声都是人为注入的
    y_clean = generate_clean_tone(freq=200, sr=sr, duration=1.0)
    y_processed = y_clean.copy()
    
    y_test = y_processed.reshape(1, -1)
    y_processed = apply_air_texture_lite(y_test, sr, amount=0.8)[0]
    
    # 频谱分析
    n_fft = 4096
    S_clean = stft(y_clean, n_fft=n_fft, hop_length=512)
    S_proc = stft(y_processed, n_fft=n_fft, hop_length=512)
    
    mag_clean = np.abs(S_clean)
    mag_proc = np.abs(S_proc)
    
    # 检查高频段(8kHz-20kHz)的能量变化
    nyq = sr / 2
    hf_bins = int(8000 / (nyq / (n_fft / 2)))
    total_hf_energy_clean = np.mean(mag_clean[hf_bins:, :] ** 2)
    total_hf_energy_proc = np.mean(mag_proc[hf_bins:, :] ** 2)
    
    print(f"  纯净信号高频能量(8k-20kHz): {total_hf_energy_clean:.2e}")
    print(f"  处理后高频能量(8k-20kHz):   {total_hf_energy_proc:.2e}")
    
    if total_hf_energy_proc > total_hf_energy_clean * 10:
        print("  ⚠️ 高频能量暴增! 检测到人工噪声注入!")
        return True
    else:
        print("  ✓ 高频能量正常")
        return False


def test_v32a_full_pipeline():
    """测试3: v3.2a完整处理流程"""
    print("\n" + "=" * 70)
    print("测试3: v3.2a完整修复流程 - 导出音频质量检查")
    print("=" * 70)
    
    from services.repair.repair_v3_2a.core import repair_single_track
    
    sr = 44100
    y_clean = generate_clean_tone(freq=440, sr=sr, duration=2.0)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = str(Path(tmpdir) / "input.wav")
        output_path = str(Path(tmpdir) / "output.wav")
        
        # 写入干净音频
        sf.write(input_path, y_clean, sr, subtype='PCM_16')
        
        # 使用v3.2a处理
        params = {
            "air_texture": 0.3,
            "bass_enhance": 0.2,
            "declip": 0.1,
            "depop": 0.1,
            "de_ess": 0.1,
            "mastering_style": "standard",
            "bit_depth": 24,
        }
        
        result = repair_single_track(input_path, output_path, params)
        
        # 读取处理后的音频
        y_out, sr_out = sf.read(output_path, dtype='float32')
        
        # 对齐长度
        min_len = min(len(y_clean), len(y_out))
        y_clean_trimmed = y_clean[:min_len]
        y_out_trimmed = y_out[:min_len]
        
        snr = compute_snr(y_clean_trimmed, y_out_trimmed)
        print(f"  输入->输出 SNR: {snr:.1f} dB")
        
        if snr < 30:
            print(f"  ⚠️ SNR过低! 输出包含大量噪声!")
            return False
        else:
            print(f"  ✓ SNR正常")
            return True


def test_v40a_full_pipeline():
    """测试4: v4.0a完整处理流程"""
    print("\n" + "=" * 70)
    print("测试4: v4.0a完整修复流程 - 导出音频质量检查")
    print("=" * 70)
    
    from services.repair.repair_v4_0a.core import repair_single_track
    
    sr = 44100
    y_clean = generate_clean_tone(freq=440, sr=sr, duration=2.0)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = str(Path(tmpdir) / "input.wav")
        output_path = str(Path(tmpdir) / "output.wav")
        
        sf.write(input_path, y_clean, sr, subtype='PCM_16')
        
        params = {
            "air_texture": 0.3,
            "bass_enhance": 0.2,
            "declip": 0.1,
            "depop": 0.1,
            "de_ess": 0.1,
            "bit_depth": 24,
        }
        
        result = repair_single_track(input_path, output_path, params)
        
        y_out, sr_out = sf.read(output_path, dtype='float32')
        
        # 对齐长度
        min_len = min(len(y_clean), len(y_out))
        y_clean_trimmed = y_clean[:min_len]
        y_out_trimmed = y_out[:min_len]
        
        snr = compute_snr(y_clean_trimmed, y_out_trimmed)
        print(f"  输入->输出 SNR: {snr:.1f} dB")
        
        if snr < 30:
            print(f"  ⚠️ SNR过低! 输出包含大量噪声!")
            return False
        else:
            print(f"  ✓ SNR正常")
            return True


def main():
    print("\n" + "🔍 开始检测空气感模块噪声问题\n")
    
    issue1 = test_air_texture_adds_noise()
    issue2 = test_air_texture_high_frequency_noise()
    test_v32a_full_pipeline()
    test_v40a_full_pipeline()
    
    print("\n" + "=" * 70)
    print("总结:")
    print("=" * 70)
    if issue1 or issue2:
        print("❌ 确认问题: apply_air_texture_lite() 函数通过 np.random.randn() 注入随机噪声")
        print("   这导致了'电滋滋'的白噪音/电流声")
        print("\n   问题代码位置:")
        print("   backend/services/repair/repair_v3_2a/core.py:688")
        print("   noise = np.random.randn(len(high_band)) * noise_level")
        print("\n   这个设计目的是模拟'空气感',但实际上是注入了可闻的白噪声!")
    else:
        print("✓ 未发现明显问题")
    
    print()


if __name__ == "__main__":
    main()
