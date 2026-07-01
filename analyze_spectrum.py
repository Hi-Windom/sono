#!/usr/bin/env python3
import sys
sys.path.insert(0, '/workspace/backend')
import numpy as np
import soundfile as sf
from scipy.fft import fft

files = [
    ('原始MP3', '/workspace/backend/storage/training/4f51ca5161ac4f09_新项目 (1).mp3'),
    ('v3.2a失真', '/workspace/backend/storage/training/b114cec8565c4704_新项目 (1)_v3.2a+_48k_24bit_20260630063951.wav'),
]

results = {}

for name, path in files:
    y, sr = sf.read(path, dtype='float32')
    
    # Take first 10 seconds for analysis
    y_short = y[:int(sr * 10)]
    
    # FFT analysis
    N = len(y_short)
    y_flat = y_short.flatten()
    Y = fft(y_flat)
    freqs_full = np.fft.fftfreq(N, 1/sr)
    freqs_pos = freqs_full[:N//2]
    magnitude = np.abs(Y[:N//2])
    
    # Frequency bands
    low = np.mean(magnitude[(freqs_pos >= 20) & (freqs_pos < 200)])  # Bass
    mid = np.mean(magnitude[(freqs_pos >= 200) & (freqs_pos < 2000)])  # Mid
    high = np.mean(magnitude[(freqs_pos >= 2000) & (freqs_pos < 20000)])  # Treble
    
    results[name] = {
        'sr': sr,
        'rms': float(np.sqrt(np.mean(y_short.astype(np.float64)**2))),
        'peak': float(np.max(np.abs(y_short))),
        'low_band': float(low),
        'mid_band': float(mid),
        'high_band': float(high),
        'low_mid_ratio': float(low/mid) if mid > 0 else 0,
        'high_mid_ratio': float(high/mid) if mid > 0 else 0,
    }
    
    print(f'{name}:')
    print(f'  RMS: {results[name]["rms"]:.4f}')
    print(f'  Peak: {results[name]["peak"]:.4f}')
    print(f'  Low band (20-200Hz): {low:.2f}')
    print(f'  Mid band (200-2kHz): {mid:.2f}')
    print(f'  High band (2k-20kHz): {high:.2f}')
    print(f'  Low/Mid ratio: {results[name]["low_mid_ratio"]:.4f}')
    print(f'  High/Mid ratio: {results[name]["high_mid_ratio"]:.4f}')

# Compare
print('\n=== 频谱对比 ===')
orig = results['原始MP3']
dist = results['v3.2a失真']

print(f'\nRMS变化: {orig["rms"]:.4f} -> {dist["rms"]:.4f} ({(dist["rms"]/orig["rms"]-1)*100:+.1f}%)')
print(f'Low/Mid变化: {orig["low_mid_ratio"]:.4f} -> {dist["low_mid_ratio"]:.4f} ({(dist["low_mid_ratio"]/orig["low_mid_ratio"]-1)*100:+.1f}%)')
print(f'High/Mid变化: {orig["high_mid_ratio"]:.4f} -> {dist["high_mid_ratio"]:.4f} ({(dist["high_mid_ratio"]/orig["high_mid_ratio"]-1)*100:+.1f}%)')

if dist['high_mid_ratio'] < orig['high_mid_ratio'] * 0.8:
    print('\n⚠️  高频成分显著减少 - 可能过度降噪或滤波')
if dist['low_mid_ratio'] < orig['low_mid_ratio'] * 0.8:
    print('\n⚠️  低频成分显著减少 - 可能低音被抑制')
