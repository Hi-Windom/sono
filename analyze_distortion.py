#!/usr/bin/env python3
import sys
sys.path.insert(0, '/workspace/backend')
import numpy as np
import soundfile as sf
import json

files = [
    ('原始MP3', '/workspace/backend/storage/training/4f51ca5161ac4f09_新项目 (1).mp3'),
    ('v3.2a失真', '/workspace/backend/storage/training/b114cec8565c4704_新项目 (1)_v3.2a+_48k_24bit_20260630063951.wav'),
]

results = {}

for name, path in files:
    y, sr = sf.read(path, dtype='float32')
    rms = float(np.sqrt(np.mean(y.astype(np.float64)**2)))
    peak = float(np.max(np.abs(y)))
    clipped_count = int(np.sum(np.abs(y) > 0.995))
    clipped_pct = clipped_count / len(y) * 100
    results[name] = {
        'sr': sr,
        'ch': y.shape[1] if y.ndim > 1 else 1,
        'dur': len(y)/sr,
        'rms': rms,
        'peak': peak,
        'clipped_count': clipped_count,
        'clipped_pct': clipped_pct,
    }
    print(f'{name}: sr={sr} ch={results[name]["ch"]} dur={len(y)/sr:.2f}s')
    print(f'  RMS={rms:.4f} Peak={peak:.4f}')
    print(f'  Clipped samples (>0.995): {clipped_count} ({clipped_pct:.2f}%)')

# Compare
print('\n=== 对比分析 ===')
orig = results['原始MP3']
dist = results['v3.2a失真']

print(f'峰值变化: {orig["peak"]:.4f} -> {dist["peak"]:.4f}')
print(f'RMS变化: {orig["rms"]:.4f} -> {dist["rms"]:.4f}')

if dist['clipped_count'] > 0:
    print(f'\n⚠️  检测到截断失真！{dist["clipped_count"]}个样本超过0.995阈值')
else:
    print(f'\n✓ 未检测到截断失真')

# Save results
with open('/workspace/distortion_analysis.json', 'w') as f:
    json.dump(results, f, indent=2)
