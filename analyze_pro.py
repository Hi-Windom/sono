#!/usr/bin/env python3
import sys
sys.path.insert(0, '/workspace/backend')
import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt, spectrogram

def professional_analysis(name, path):
    """专业的声学分析"""
    y, sr = sf.read(path, dtype='float32')
    
    print(f"\n{'='*80}")
    print(f"{name}")
    print(f"{'='*80}")
    print(f"采样率: {sr} Hz")
    print(f"声道数: {y.shape[1] if y.ndim > 1 else 1}")
    print(f"时长: {len(y)/sr:.2f} 秒")
    
    # 1. 基本电平指标
    rms = np.sqrt(np.mean(y.astype(np.float64)**2))
    peak = np.max(np.abs(y))
    crest_factor = 20 * np.log10(peak/rms) if rms > 0 else 0
    
    print(f"\n【电平指标】")
    print(f"  RMS电平: {20*np.log10(rms+1e-10):.1f} dBFS")
    print(f"  峰值: {20*np.log10(peak+1e-10):.1f} dBFS")
    print(f"  峰值因数( Crest Factor): {crest_factor:.1f} dB")
    
    # 2. 响度感知 (简化版 ITU-R BS.1770)
    # 应用K权重滤波器 (48Hz高通 + 4kHz一阶高通)
    if sr == 48000:
        # 48Hz 高通滤波器
        b, a = butter(4, 48/(sr/2), btype='high')
        y_filtered = filtfilt(b, a, y, axis=0)
        loudness = np.sqrt(np.mean(y_filtered.astype(np.float64)**2))
        loudness_dB = 20 * np.log10(loudness + 1e-10)
        print(f"\n【感知响度】(ITU-R BS.1770简化)")
        print(f"  加权RMS: {loudness_dB:.1f} dBFS")
    
    # 3. 动态范围
    # 计算10秒窗口的RMS分布
    window_size = int(sr * 0.1)  # 100ms窗口
    rms_over_time = []
    for i in range(0, len(y) - window_size, window_size):
        chunk = y[i:i+window_size].flatten()
        rms_chunk = np.sqrt(np.mean(chunk.astype(np.float64)**2))
        rms_over_time.append(20 * np.log10(rms_chunk + 1e-10))
    
    rms_over_time = np.array(rms_over_time)
    dynamic_range = np.max(rms_over_time) - np.min(rms_over_time)
    
    print(f"\n【动态范围】")
    print(f"  时间动态范围: {dynamic_range:.1f} dB")
    print(f"  RMS均值: {np.mean(rms_over_time):.1f} dBFS")
    print(f"  RMS标准差: {np.std(rms_over_time):.1f} dB")
    
    # 4. 频谱特征 - 按频带分析
    bands = [
        ('亚低频 (20-60Hz)', 20, 60),
        ('低频 (60-250Hz)', 60, 250),
        ('中低频 (250-500Hz)', 250, 500),
        ('中频 (500Hz-2kHz)', 500, 2000),
        ('中高频 (2kHz-4kHz)', 2000, 4000),
        ('高频 (4kHz-8kHz)', 4000, 8000),
        ('极高频 (8kHz-20kHz)', 8000, 20000),
    ]
    
    print(f"\n【频带能量分布】")
    y_flat = y.flatten()
    N = len(y_flat)
    from scipy.fft import fft
    Y = fft(y_flat)
    freqs = np.fft.fftfreq(N, 1/sr)
    magnitude = np.abs(Y[:N//2])
    freqs_pos = np.abs(freqs[:N//2])
    
    band_energies = {}
    total_energy = np.sum(magnitude**2)
    
    for band_name, f_low, f_high in bands:
        band_mask = (freqs_pos >= f_low) & (freqs_pos < f_high)
        band_energy = np.sum(magnitude[band_mask]**2)
        band_db = 10 * np.log10(band_energy/total_energy + 1e-10) if total_energy > 0 else -100
        band_energies[band_name] = band_db
        print(f"  {band_name:20s}: {band_db:.1f} dB (相对总能量)")
    
    # 5. 谐波分析 (基频检测)
    print(f"\n【谐波特征】")
    # 计算自相关检测基频
    autocorr = np.correlate(y_flat, y_flat, mode='full')
    autocorr = autocorr[len(autocorr)//2:]
    autocorr /= np.max(autocorr) + 1e-10
    
    # 在50-500Hz范围内寻找第一个显著峰值
    f0_range = (50, 500)
    f0_indices = np.where((freqs_pos >= f0_range[0]) & (freqs_pos <= f0_range[1]))[0]
    if len(f0_indices) > 0:
        f0_candidates = autocorr[f0_indices]
        if len(f0_candidates) > 0:
            best_idx = np.argmax(f0_candidates[1:]) + 1  # 跳过DC
            estimated_f0 = freqs_pos[f0_indices[best_idx]]
            print(f"  估计基频(F0): {estimated_f0:.1f} Hz")
    
    # 6. 瞬态分析
    print(f"\n【瞬态特征】")
    # 计算能量包络
    envelope = np.abs(y_flat)
    envelope_smooth = np.convolve(envelope, np.ones(1000)/1000, mode='same')
    
    # 瞬态 = 实际信号 - 平滑包络
    transients = np.abs(envelope - envelope_smooth)
    transient_ratio = np.sum(transients > 0.1) / len(transients)
    
    print(f"  瞬态占比: {transient_ratio*100:.2f}%")
    print(f"  瞬态能量: {np.mean(transients):.4f}")
    
    # 7. 噪声底分析
    print(f"\n【噪声底分析】")
    # 使用谱减法估算噪声
    # 取信号最安静的1%作为噪声参考
    sorted_energy = np.sort(np.abs(Y))
    noise_floor_idx = int(len(sorted_energy) * 0.01)
    noise_estimate = np.median(np.abs(Y[:noise_floor_idx]))
    noise_dB = 20 * np.log10(noise_estimate + 1e-10)
    print(f"  噪声基底: {noise_dB:.1f} dBFS")
    
    # 信噪比估算
    signal_power = np.mean(Y**2)
    snr = 10 * np.log10(signal_power / (noise_estimate**2 + 1e-10))
    print(f"  估算信噪比(SNR): {snr:.1f} dB")
    
    return {
        'rms_db': 20*np.log10(rms+1e-10),
        'peak_db': 20*np.log10(peak+1e-10),
        'crest_factor': crest_factor,
        'dynamic_range': dynamic_range,
        'band_energies': band_energies,
        'noise_floor': noise_dB,
        'snr': snr,
    }

# 分析两个文件
original_path = '/workspace/backend/storage/training/4f51ca5161ac4f09_新项目 (1).mp3'
distorted_path = '/workspace/backend/storage/training/b114cec8565c4704_新项目 (1)_v3.2a+_48k_24bit_20260630063951.wav'

orig_stats = professional_analysis('原始音频 MP3', original_path)
dist_stats = professional_analysis('处理后音频 v3.2a+', distorted_path)

# 对比分析
print(f"\n{'='*80}")
print(f"【对比分析 - 处理影响评估】")
print(f"{'='*80}")

print(f"\n电平变化:")
print(f"  RMS: {orig_stats['rms_db']:.1f} -> {dist_stats['rms_db']:.1f} dBFS ({dist_stats['rms_db'] - orig_stats['rms_db']:+.1f} dB)")
print(f"  Peak: {orig_stats['peak_db']:.1f} -> {dist_stats['peak_db']:.1f} dBFS ({dist_stats['peak_db'] - orig_stats['peak_db']:+.1f} dB)")
print(f"  Crest Factor: {orig_stats['crest_factor']:.1f} -> {dist_stats['crest_factor']:.1f} dB ({dist_stats['crest_factor'] - orig_stats['crest_factor']:+.1f} dB)")

print(f"\n动态范围:")
print(f"  时间动态: {orig_stats['dynamic_range']:.1f} -> {dist_stats['dynamic_range']:.1f} dB ({dist_stats['dynamic_range'] - orig_stats['dynamic_range']:+.1f} dB)")

print(f"\n频带能量变化:")
for band_name in orig_stats['band_energies'].keys():
    orig_db = orig_stats['band_energies'][band_name]
    dist_db = dist_stats['band_energies'][band_name]
    diff = dist_db - orig_db
    marker = "⚠️ " if abs(diff) > 3 else "  "
    print(f"  {marker}{band_name:20s}: {orig_db:.1f} -> {dist_db:.1f} dB ({diff:+.1f} dB)")

print(f"\n噪声特性:")
print(f"  噪声底: {orig_stats['noise_floor']:.1f} -> {dist_stats['noise_floor']:.1f} dBFS ({dist_stats['noise_floor'] - orig_stats['noise_floor']:+.1f} dB)")
print(f"  SNR: {orig_stats['snr']:.1f} -> {dist_stats['snr']:.1f} dB ({dist_stats['snr'] - orig_stats['snr']:+.1f} dB)")

# 诊断
print(f"\n{'='*80}")
print(f"【诊断结论】")
print(f"{'='*80}")

if dist_stats['dynamic_range'] < orig_stats['dynamic_range'] * 0.7:
    print("❌ 动态范围显著压缩 - 可能过度使用限幅器/压缩器")

if dist_stats['peak_db'] < orig_stats['peak_db'] - 3:
    print("❌ 峰值电平大幅下降 - 处理链中有限幅或增益衰减")

if dist_stats['noise_floor'] > orig_stats['noise_floor']:
    print("⚠️  噪声基底上升 - 可能引入处理伪影")

# 检查特定频带
if '中高频 (2kHz-4kHz)' in orig_stats['band_energies']:
    mid_high_diff = dist_stats['band_energies'].get('中高频 (2kHz-4kHz)', 0) - orig_stats['band_energies']['中高频 (2kHz-4kHz)']
    if mid_high_diff < -3:
        print(f"❌ 中高频(2-4kHz)损失{abs(mid_high_diff):.1f}dB - 人声清晰度下降，可能过度降噪")

if '低频 (60-250Hz)' in orig_stats['band_energies']:
    low_diff = dist_stats['band_energies'].get('低频 (60-250Hz)', 0) - orig_stats['band_energies']['低频 (60-250Hz)']
    if low_diff < -3:
        print(f"❌ 低频(60-250Hz)损失{abs(low_diff):.1f}dB - 丰满度下降，可能低音被切除")

print("\n建议检查处理模块:")
print("  1. loudness_normalize - 检查目标LUFS和增益曲线")
print("  2. compressor - 检查ratio/threshold/knee设置")
print("  3. noise_reduce - 检查降噪强度是否过高")
print("  4. air_texture - 检查高频激励是否反向衰减")
