"""系统性失真检测脚本"""
import numpy as np
from scipy.signal import butter, sosfiltfilt, resample_poly

def soft_peak_limit(y, threshold=0.9):
    abs_max = np.max(np.abs(y))
    if abs_max <= threshold:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        soft_peak_limit(y, threshold)
        return y[0]
    for ch in range(y.shape[0]):
        abs_data = np.abs(y[ch])
        mask = abs_data > threshold
        if not np.any(mask):
            continue
        headroom = 1.0 - threshold
        y[ch][mask] = (np.sign(y[ch][mask]) * (threshold + headroom * np.tanh((abs_data[mask] - threshold) / headroom))).astype(y.dtype)
    return y

# Test 1: resample_poly overflow
sr_orig, sr_target = 44100, 48000
y1 = np.sin(2 * np.pi * 1000 * np.arange(sr_orig * 3) / sr_orig) * 0.99
r1 = resample_poly(y1, sr_target, sr_orig)
print(f'Test1 resample: in={np.max(np.abs(y1)):.4f} out={np.max(np.abs(r1)):.4f}')

# Test 2: sosfiltfilt overflow
nyq = 24000
sos = butter(4, [4000/nyq, 8000/nyq], btype='band', output='sos')
y2 = np.random.randn(48000 * 3) * 0.5
f2 = sosfiltfilt(sos, y2)
print(f'Test2 sosfiltfilt: in={np.max(np.abs(y2)):.4f} out={np.max(np.abs(f2)):.4f}')

# Test 3: soft_peak_limit extreme values
y3 = np.array([-100.0, -5.0, -2.0, -1.5, -1.0, 0, 1.0, 1.5, 2.0, 5.0, 100.0], dtype=np.float64)
l3 = soft_peak_limit(y3.copy())
print(f'Test3 limit: max={np.max(np.abs(l3)):.10f}, over1={np.sum(np.abs(l3)>1.0)}')
print(f'  values: {np.round(l3, 8)}')

# Test 4: compressor AM distortion
def compressor(y, sr, amount):
    if amount <= 0:
        return y
    threshold = 0.3 + (1 - amount) * 0.4
    ratio = 1.0 + amount * 3.0
    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        abs_data = np.abs(data)
        peak_env = np.maximum(abs_data, 0.001)
        db = 20 * np.log10(peak_env)
        db_thresh = 20 * np.log10(threshold)
        gain_db = np.zeros_like(db)
        above_thresh = db > db_thresh
        gain_db[above_thresh] = (db_thresh - db[above_thresh]) * (1 - 1 / ratio)
        gain_linear = 10 ** (gain_db / 20.0)
        release_gamma = 0.2 - (0.2 - 0.01) * amount
        env = np.ones_like(gain_linear)
        env[0] = gain_linear[0]
        for i in range(1, len(gain_linear)):
            if gain_linear[i] < env[i-1]:
                env[i] = (1 - release_gamma) * env[i-1] + release_gamma * gain_linear[i]
            else:
                env[i] = gain_linear[i]
        y[ch] = (data * env).astype(y.dtype)
    return y

sr = 48000
t = np.arange(sr * 1) / sr
y4 = (np.sin(2 * np.pi * 440 * t) * 0.5 + np.sin(2 * np.pi * 1000 * t) * 0.3).reshape(1, -1)
c4 = compressor(y4.copy(), sr, 0.5)
print(f'Test4 compressor: in={np.max(np.abs(y4)):.4f} out={np.max(np.abs(c4)):.4f}')
# Check for high-frequency artifacts
from scipy.fft import rfft, rfftfreq
spec_in = np.abs(rfft(y4[0]))
spec_out = np.abs(rfft(c4[0]))
freqs = rfftfreq(len(c4[0]), 1/sr)
# Energy above 5kHz (where the signal has no energy)
mask_hf = freqs > 5000
hf_in = np.sum(spec_in[mask_hf]**2)
hf_out = np.sum(spec_out[mask_hf]**2)
total_out = np.sum(spec_out**2)
print(f'  HF energy ratio: {hf_out/total_out:.6f} (input had {hf_in:.2e})')

# Test 5: Full chain simulation
y5 = (np.sin(2 * np.pi * 440 * t) * 0.85).reshape(1, -1)
# simple_declip
mask = np.abs(y5) > 0.9
y5[mask] = np.sign(y5[mask]) * (0.9 + 0.1 * np.tanh((np.abs(y5[mask]) - 0.9) / 0.1))
print(f'Test5 declip: max={np.max(np.abs(y5)):.4f}')
# compressor
c5 = compressor(y5.copy(), sr, 0.7)
print(f'Test5 compressor: max={np.max(np.abs(c5)):.4f}')
# mastering_standard_lite RMS gain
rms = np.sqrt(np.mean(c5**2))
target = 0.12
gain = np.clip(target / rms, 0.2, 3.0)
boosted = c5 * gain
print(f'Test5 mastering gain: {gain:.2f}x, max={np.max(np.abs(boosted)):.4f}')
# output_volume +3dB
gain2 = 10 ** (3/20)
boosted2 = boosted * gain2
print(f'Test5 +3dB: max={np.max(np.abs(boosted2)):.4f}')
# soft_peak_limit
limited = soft_peak_limit(boosted2, threshold=0.9)
print(f'Test5 limit: max={np.max(np.abs(limited)):.10f}')
print(f'Test5 > 1.0: {np.sum(np.abs(limited) > 1.0)}')

# Test 6: The mastering_standard_lite gain=3.0 extreme case
y6 = (np.sin(2 * np.pi * 440 * t) * 0.1).reshape(1, -1)
rms6 = np.sqrt(np.mean(y6**2))
gain6 = np.clip(0.12 / rms6, 0.2, 3.0)
boosted6 = y6 * gain6
limited6 = soft_peak_limit(boosted6, threshold=0.9)
print(f'\nTest6 quiet signal: rms={rms6:.4f}, gain={gain6:.2f}x, max={np.max(np.abs(limited6)):.6f}')

# Test 7: actual mastering_standard_lite simulation with all processing
def mastering_standard_lite_sim(y, sr):
    nyq = sr / 2
    sos_low = butter(2, 60 / nyq, btype='high', output='sos')
    sos_presence = butter(2, [3000 / nyq, 4000 / nyq], btype='band', output='sos')
    low_cross = min(300, nyq * 0.9)
    sos_lowband = butter(2, low_cross / nyq, btype='low', output='sos')
    sos_highband = butter(2, low_cross / nyq, btype='high', output='sos')
    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        data = sosfiltfilt(sos_low, data)
        presence = sosfiltfilt(sos_presence, data)
        data = data + presence * 0.10
        low_band = sosfiltfilt(sos_lowband, data)
        high_band = sosfiltfilt(sos_highband, data)
        low_e = np.sqrt(np.dot(low_band, low_band) + 1e-20)
        high_e = np.sqrt(np.dot(high_band, high_band) + 1e-20)
        total = low_e + high_e
        low_ratio = low_e / total
        if low_ratio < 0.20:
            data = low_band * (1.0 + (0.20 - low_ratio) * 0.5) + high_band
        elif low_ratio > 0.50:
            data = low_band * (1.0 - (low_ratio - 0.50) * 0.3) + high_band
        else:
            data = low_band + high_band
        rms = np.sqrt(np.dot(data, data) / data.size)
        if rms > 1e-10:
            target = 0.12
            gain = target / rms
            gain = np.clip(gain, 0.2, 3.0)
            data = data * gain
        y[ch] = data.astype(y.dtype)
    return soft_peak_limit(y, threshold=0.95)

y7 = (np.sin(2 * np.pi * 440 * t) * 0.3).reshape(1, -1)
m7 = mastering_standard_lite_sim(y7, sr)
print(f'\nTest7 mastering_standard: in_max={np.max(np.abs(y7)):.4f} out_max={np.max(np.abs(m7)):.10f} over1={np.sum(np.abs(m7)>1.0)}')
