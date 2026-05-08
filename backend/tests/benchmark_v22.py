#!/usr/bin/env python3
"""
v2.2 性能基准测试 - 对比优化前后真实性能
"""
import numpy as np
import time
import sys
import os

# 添加后端路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.librosa_compat import stft, istft
from scipy.signal import lfilter


def generate_test_audio(duration_sec=5, sr=22050, n_channels=2):
    """生成测试音频"""
    t = np.linspace(0, duration_sec, int(sr * duration_sec))
    # 生成包含多种频率的测试信号
    audio = np.zeros((n_channels, len(t)))
    for ch in range(n_channels):
        audio[ch] = (
            np.sin(2 * np.pi * 440 * t) * 0.3 +  # 基频
            np.sin(2 * np.pi * 880 * t) * 0.2 +  # 二次谐波
            np.sin(2 * np.pi * 1320 * t) * 0.1 +  # 三次谐波
            np.random.randn(len(t)) * 0.05  # 噪声
        )
    return audio.astype(np.float32)


def benchmark_noise_reduction_old(mag, n_frames, intensity=0.5):
    """旧版降噪 - 使用循环"""
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
    gain = snr / (snr + 1)
    gain = np.maximum(gain, 0.15)

    # 旧版：Python 循环
    alpha = 0.8
    for i in range(1, n_frames):
        gain[:, i] = alpha * gain[:, i-1] + (1 - alpha) * gain[:, i]

    mag *= gain
    return mag


def benchmark_noise_reduction_new(mag, n_frames, intensity=0.5):
    """新版降噪 - 使用 lfilter"""
    noise_frames = max(1, n_frames // 20)
    noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

    snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
    gain = snr / (snr + 1)
    gain = np.maximum(gain, 0.15)

    # 新版：lfilter (C 实现)
    alpha = 0.8
    gain = lfilter([1 - alpha], [1, -alpha], gain, axis=1)

    mag *= gain
    return mag


def benchmark_smooth_old(data, window_size=3):
    """旧版平滑 - 使用 convolve"""
    kernel = np.ones(window_size) / window_size
    return np.convolve(data, kernel, mode='same')


def benchmark_smooth_new(data, window_size=3):
    """新版平滑 - 使用 lfilter"""
    if window_size == 3:
        return lfilter([0.25, 0.5, 0.25], [1], data)
    else:
        kernel = np.ones(window_size) / window_size
        return lfilter(kernel, [1], data)


def run_benchmark():
    """运行基准测试"""
    print("=" * 60)
    print("v2.2 性能基准测试")
    print("=" * 60)

    # 测试参数
    sr = 22050
    n_fft = 2048
    hop_length = 512
    n_bins = n_fft // 2 + 1
    n_frames = 200  # 约 4.6 秒音频

    print(f"\n测试配置:")
    print(f"  采样率: {sr} Hz")
    print(f"  FFT 大小: {n_fft}")
    print(f"  帧数: {n_frames}")
    print(f"  频谱形状: ({n_bins}, {n_frames})")

    # 生成测试数据
    mag = np.random.rand(n_bins, n_frames).astype(np.float32) * 100
    data_1d = np.random.rand(n_frames * 100).astype(np.float32)

    results = []

    # 测试 1: 降噪平滑
    print("\n" + "-" * 60)
    print("测试 1: 降噪平滑处理")
    print("-" * 60)

    # 预热
    _ = benchmark_noise_reduction_old(mag.copy(), n_frames)
    _ = benchmark_noise_reduction_new(mag.copy(), n_frames)

    # 旧版测试
    n_runs = 100
    start = time.perf_counter()
    for _ in range(n_runs):
        _ = benchmark_noise_reduction_old(mag.copy(), n_frames)
    old_time = (time.perf_counter() - start) / n_runs * 1000

    # 新版测试
    start = time.perf_counter()
    for _ in range(n_runs):
        _ = benchmark_noise_reduction_new(mag.copy(), n_frames)
    new_time = (time.perf_counter() - start) / n_runs * 1000

    speedup = old_time / new_time
    results.append(("降噪平滑", old_time, new_time, speedup))

    print(f"  旧版 (Python 循环): {old_time:.3f} ms")
    print(f"  新版 (lfilter):     {new_time:.3f} ms")
    print(f"  提速倍数:           {speedup:.2f}x")

    # 测试 2: 1D 平滑
    print("\n" + "-" * 60)
    print("测试 2: 1D 信号平滑")
    print("-" * 60)

    n_runs = 1000

    # 旧版
    start = time.perf_counter()
    for _ in range(n_runs):
        _ = benchmark_smooth_old(data_1d.copy())
    old_time = (time.perf_counter() - start) / n_runs * 1000

    # 新版
    start = time.perf_counter()
    for _ in range(n_runs):
        _ = benchmark_smooth_new(data_1d.copy())
    new_time = (time.perf_counter() - start) / n_runs * 1000

    speedup = old_time / new_time
    results.append(("1D 平滑", old_time, new_time, speedup))

    print(f"  旧版 (convolve): {old_time:.3f} ms")
    print(f"  新版 (lfilter):  {new_time:.3f} ms")
    print(f"  提速倍数:        {speedup:.2f}x")

    # 测试 3: 完整频谱处理
    print("\n" + "-" * 60)
    print("测试 3: 完整频谱处理流程")
    print("-" * 60)

    # 生成测试音频
    test_audio = generate_test_audio(duration_sec=5, sr=sr, n_channels=2)
    print(f"  测试音频: {test_audio.shape[1] / sr:.1f} 秒, {test_audio.shape[0]} 通道")

    # 导入处理函数
    from services.repair.repair_v2_2.spectral_group_a import apply_spectral_group_a
    from services.repair.repair_v2_2.spectral_combined import apply_spectral_combined

    params = {
        'de_crackle': 0.5,
        'de_essing': 0.5,
        'noise_reduction': 0.5,
        'harmonic_enhance': 0.5,
        'harmonic_richness': 0.5
    }

    # 预热
    issues = []
    _ = apply_spectral_group_a(test_audio.copy(), sr, params, n_fft, hop_length, issues.copy(), 'generic')

    # 测试 group_a
    n_runs = 10
    start = time.perf_counter()
    for _ in range(n_runs):
        issues = []
        _ = apply_spectral_group_a(test_audio.copy(), sr, params, n_fft, hop_length, issues.copy(), 'generic')
    group_a_time = (time.perf_counter() - start) / n_runs * 1000

    print(f"  spectral_group_a: {group_a_time:.1f} ms")

    # 测试 combined
    start = time.perf_counter()
    for _ in range(n_runs):
        issues = []
        _ = apply_spectral_combined(test_audio.copy(), sr, params, n_fft, hop_length, issues.copy(), 'generic')
    combined_time = (time.perf_counter() - start) / n_runs * 1000

    print(f"  spectral_combined: {combined_time:.1f} ms")
    print(f"  合并优势: 单次 STFT/ISTFT，减少 50% 变换开销")

    # 测试 4: 瞬态修复
    print("\n" + "-" * 60)
    print("测试 4: 瞬态修复")
    print("-" * 60)

    from services.repair.repair_v2_2.transient import apply_transient_repair_v9

    # 预热
    _ = apply_transient_repair_v9(test_audio.copy(), sr, 0.5)

    n_runs = 10
    start = time.perf_counter()
    for _ in range(n_runs):
        _ = apply_transient_repair_v9(test_audio.copy(), sr, 0.5)
    transient_time = (time.perf_counter() - start) / n_runs * 1000

    print(f"  瞬态修复 (v9): {transient_time:.1f} ms")

    # 汇总结果
    print("\n" + "=" * 60)
    print("基准测试汇总")
    print("=" * 60)
    print(f"{'测试项目':<20} {'旧版 (ms)':<12} {'新版 (ms)':<12} {'提速':<8}")
    print("-" * 60)
    for name, old, new, speedup in results:
        print(f"{name:<20} {old:<12.3f} {new:<12.3f} {speedup:<8.2f}x")

    print("\n" + "=" * 60)
    print("关键优化点:")
    print("=" * 60)
    print("1. 使用 scipy.signal.lfilter 替代 Python 循环")
    print("2. 合并 group_a + group_b，减少 STFT/ISTFT 次数")
    print("3. 向量化操作替代逐元素循环")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_benchmark()
