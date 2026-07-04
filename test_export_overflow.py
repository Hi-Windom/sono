#!/usr/bin/env python3
"""测试导出时的溢出问题"""
import sys
sys.path.insert(0, '/workspace/backend')
import numpy as np
import soundfile as sf
from services.repair.repair_v3_2a.core import soft_peak_limit

# 模拟真实音频（有高峰值）
y = np.random.randn(44100 * 10).astype(np.float32) * 0.85

print("处理前:")
print(f"  dtype: {y.dtype}")
print(f"  min/max: [{y.min():.4f}, {y.max():.4f}]")

y_peaked = soft_peak_limit(y)

print("\nsoft_peak_limit后:")
print(f"  dtype: {y_peaked.dtype}")
print(f"  min/max: [{y_peaked.min():.4f}, {y_peaked.max():.4f}]")
print(f"  是否有溢出: {np.any(np.abs(y_peaked) > 1.0)}")

# 模拟导出流程
y_for_export = y_peaked
if y_for_export.dtype == np.float32:
    y_for_export = y_for_export.astype(np.float64)

print(f"\n导出前dtype: {y_for_export.dtype}")
print(f"导出前min/max: [{y_for_export.min():.4f}, {y_for_export.max():.4f}]")

sf.write('/tmp/test_overflow.wav', y_for_export, 44100, subtype='PCM_24')
y_read, _ = sf.read('/tmp/test_overflow.wav', dtype='float32')

print(f"\nPCM_24导出后:")
print(f"  min/max: [{y_read.min():.4f}, {y_read.max():.4f}]")
print(f"  往返误差: {np.max(np.abs(y_for_export - y_read)):.8f}")
