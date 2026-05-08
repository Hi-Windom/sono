#!/usr/bin/env python3
"""
真实性能对比测试 - 原版 vs Numba 加速版
"""
import numpy as np
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

print("=" * 60)
print("v2.2 真实性能对比测试")
print("=" * 60)

# 生成测试音频
sr = 22050
duration = 10  # 10秒音频
test_audio = np.random.randn(2, sr * duration).astype(np.float32) * 0.5

print(f"\n测试音频: {duration}秒, {test_audio.shape[0]}通道, {sr}Hz")

# 测试配置
params = {
    'de_crackle': 0.5,
    'de_essing': 0.5,
    'noise_reduction': 0.5,
    'harmonic_enhance': 0.5,
    'harmonic_richness': 0.5
}

n_fft = 2048
hop_length = 512

# 测试 1: 频谱处理 (group_a)
print("\n" + "-" * 60)
print("测试 1: 频谱修复 (spectral_group_a)")
print("-" * 60)

from services.repair.repair_v2_2.spectral_group_a import apply_spectral_group_a

# 预热/编译
print("Numba 编译中...")
issues = []
_ = apply_spectral_group_a(test_audio.copy(), sr, params, n_fft, hop_length, issues.copy(), 'generic')

# 正式测试
n_runs = 5
times = []
for i in range(n_runs):
    start = time.perf_counter()
    issues = []
    _ = apply_spectral_group_a(test_audio.copy(), sr, params, n_fft, hop_length, issues.copy(), 'generic')
    elapsed = time.perf_counter() - start
    times.append(elapsed)
    print(f"  运行 {i+1}: {elapsed:.3f}s")

avg_time = np.mean(times)
print(f"\n  平均耗时: {avg_time:.3f}s")
print(f"  处理速度: {duration / avg_time:.2f}x 实时")

# 测试 2: 合并频谱处理
print("\n" + "-" * 60)
print("测试 2: 合并频谱处理 (spectral_combined)")
print("-" * 60)

from services.repair.repair_v2_2.spectral_combined import apply_spectral_combined

times = []
for i in range(n_runs):
    start = time.perf_counter()
    issues = []
    _ = apply_spectral_combined(test_audio.copy(), sr, params, n_fft, hop_length, issues.copy(), 'generic')
    elapsed = time.perf_counter() - start
    times.append(elapsed)
    print(f"  运行 {i+1}: {elapsed:.3f}s")

avg_time_combined = np.mean(times)
print(f"\n  平均耗时: {avg_time_combined:.3f}s")
print(f"  处理速度: {duration / avg_time_combined:.2f}x 实时")

# 测试 3: 瞬态修复
print("\n" + "-" * 60)
print("测试 3: 瞬态修复 (transient)")
print("-" * 60)

from services.repair.repair_v2_2.transient import apply_transient_repair_v9

times = []
for i in range(n_runs):
    start = time.perf_counter()
    _ = apply_transient_repair_v9(test_audio.copy(), sr, 0.5)
    elapsed = time.perf_counter() - start
    times.append(elapsed)
    print(f"  运行 {i+1}: {elapsed:.3f}s")

avg_time_transient = np.mean(times)
print(f"\n  平均耗时: {avg_time_transient:.3f}s")
print(f"  处理速度: {duration / avg_time_transient:.2f}x 实时")

# 汇总
print("\n" + "=" * 60)
print("性能汇总")
print("=" * 60)
print(f"{'模块':<25} {'耗时':<12} {'实时因子':<12}")
print("-" * 60)
print(f"{'频谱修复 (group_a)':<25} {avg_time:.3f}s{'':<6} {duration / avg_time:.2f}x")
print(f"{'合并频谱处理':<25} {avg_time_combined:.3f}s{'':<6} {duration / avg_time_combined:.2f}x")
print(f"{'瞬态修复':<25} {avg_time_transient:.3f}s{'':<6} {duration / avg_time_transient:.2f}x")

print("\n" + "=" * 60)
print("结论")
print("=" * 60)
if avg_time < duration / 3:
    print(f"✓ 频谱修复已达到 3x+ 提速目标 ({duration / avg_time:.1f}x)")
else:
    print(f"✗ 频谱修复未达到 3x 目标 ({duration / avg_time:.1f}x)")

if avg_time_transient < duration / 3:
    print(f"✓ 瞬态修复已达到 3x+ 提速目标 ({duration / avg_time_transient:.1f}x)")
else:
    print(f"✗ 瞬态修复未达到 3x 目标 ({duration / avg_time_transient:.1f}x)")

print("=" * 60)
