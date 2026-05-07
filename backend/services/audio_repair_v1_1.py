import numpy as np
import librosa
import soundfile as sf
try:
    from pedalboard import Pedalboard, Compressor, Gain, LowShelfFilter, HighShelfFilter, PeakFilter, Reverb, Limiter, HighpassFilter, LowpassFilter, Chorus, Clipping
    from pedalboard.io import AudioFile as PedalboardAudioFile
    HAS_PEDALBOARD = True
except ImportError:
    HAS_PEDALBOARD = False
from scipy.signal import medfilt, butter, filtfilt, resample_poly
from scipy.fftpack import fft, ifft


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = librosa.load(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    target_sr = params.get("sample_rate", sr)
    original_duration = round(y.shape[1] / sr, 2)
    n_fft = 4096
    hop_length = 1024

    if progress_callback:
        progress_callback(0.03, "v1.1 分析音频特征...")

    issues_found = []

    if params.get("de_clipping", 0) > 0:
        if progress_callback:
            progress_callback(0.07, "v1.1 去削波...")
        y = _apply_de_clipping(y, sr, params["de_clipping"])
        issues_found.append("削波修复v2")

    if params.get("de_crackle", 0) > 0:
        if progress_callback:
            progress_callback(0.14, "v1.1 去毛刺(频谱中值掩蔽)...")
        y = _apply_de_crackle_v2(y, sr, params["de_crackle"], n_fft, hop_length)
        issues_found.append("毛刺修复v2")

    if params.get("de_pop", 0) > 0:
        if progress_callback:
            progress_callback(0.21, "v1.1 去爆音(多尺度能量检测)...")
        y = _apply_de_pop_v2(y, sr, params["de_pop"])
        issues_found.append("爆音修复v2")

    if params.get("de_essing", 0) > 0:
        if progress_callback:
            progress_callback(0.28, "v1.1 去齿音(多频段自适应压缩)...")
        y = _apply_de_essing_v2(y, sr, params["de_essing"], n_fft, hop_length)
        issues_found.append("齿音抑制v2")

    if params.get("noise_reduction", 0) > 0:
        if progress_callback:
            progress_callback(0.36, "v1.1 降噪(频谱门控)...")
        y = _apply_noise_reduction(y, sr, params["noise_reduction"])
        issues_found.append("智能降噪v2")

    if params.get("transient_repair", 0) > 0:
        if progress_callback:
            progress_callback(0.44, "v1.1 瞬态修复(包络重塑)...")
        y = _apply_transient_repair_v2(y, sr, params["transient_repair"])
        issues_found.append("瞬态修复v2")

    if params.get("harmonic_enhance", 0) > 0:
        if progress_callback:
            progress_callback(0.52, "v1.1 谐波增强(母带级饱和)...")
        y = _apply_harmonic_enhance_v3(y, sr, params["harmonic_enhance"], n_fft, hop_length)
        issues_found.append("谐波增强v3")

    if params.get("spatial_enhance", 0) > 0:
        if progress_callback:
            progress_callback(0.60, "v1.1 空间感增强(自适应宽度控制)...")
        y = _apply_spatial_enhance_v3(y, sr, params["spatial_enhance"])
        issues_found.append("空间感增强v3")

    if params.get("presence_boost", 0) > 0:
        if progress_callback:
            progress_callback(0.68, "v1.1 临场感增强...")
        y = _apply_presence_boost(y, sr, params["presence_boost"])
        issues_found.append("临场增强v2")

    if params.get("bass_enhance", 0) > 0:
        if progress_callback:
            progress_callback(0.74, "v1.1 低音增强...")
        y = _apply_bass_enhance(y, sr, params["bass_enhance"])
        issues_found.append("低音增强v2")

    if params.get("dynamic_range", 0) > 0:
        if progress_callback:
            progress_callback(0.82, "v1.1 动态范围优化(多段压缩)...")
        y = _apply_multiband_compression(y, sr, params["dynamic_range"])
        issues_found.append("多段压缩v3")

    if params.get("softness", 0) > 0:
        if progress_callback:
            progress_callback(0.88, "v1.1 柔化处理...")
        y = _apply_softness(y, sr, params["softness"])
        issues_found.append("柔化处理v2")

    if target_sr != sr:
        if progress_callback:
            progress_callback(0.92, f"v1.1 重采样到 {target_sr//1000} kHz...")
        if target_sr < sr:
            nyquist = target_sr / 2
            cutoff = nyquist * 0.95
            b, a = butter(8, cutoff / (sr / 2), btype='low')
            for ch in range(y.shape[0]):
                y[ch] = filtfilt(b, a, y[ch])

        y_resampled = np.zeros((y.shape[0], int(y.shape[1] * target_sr / sr)))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], target_sr, sr)
            y_resampled[ch, :len(resampled)] = resampled[:y_resampled.shape[1]]
        y = y_resampled
        sr = target_sr

    if progress_callback:
        progress_callback(0.95, "v1.1 响度归一化+峰值限制...")

    y = _apply_loudness_normalize(y, sr, -16.0)
    y = _apply_peak_limit(y, sr)

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.97, "导出WAV...")

    bit_depth = params.get("bit_depth", 24)
    if bit_depth < 32:
        y = _apply_dither(y, bit_depth)

    subtype = "PCM_16" if bit_depth == 16 else "PCM_24" if bit_depth == 24 else "FLOAT"
    sf.write(output_path, y.T if y.ndim == 1 else y.T, sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v1.1 修复完成!")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": 1 if was_mono else 2,
    }


def _apply_peak_limit(y: np.ndarray, sr: int) -> np.ndarray:
    if HAS_PEDALBOARD:
        board = Pedalboard([Limiter(threshold_db=-0.5, release_ms=50)])
        if y.shape[0] == 1:
            out = board(y[0], sr)
            return out.reshape(1, -1)
        else:
            out = board(y, sr)
            return out
    else:
        threshold = 10 ** (-0.5 / 20)
        result = y.copy()
        for ch in range(y.shape[0]):
            data = result[ch]
            over = np.abs(data) > threshold
            if np.any(over):
                sign = np.sign(data[over])
                data[over] = sign * (threshold + (1 - threshold) * np.tanh((np.abs(data[over]) - threshold) / (1 - threshold)) * 0.5)
        return result


def _apply_loudness_normalize(y: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        if y.shape[0] == 1:
            loudness = meter.integrated_loudness(y[0])
        else:
            loudness = meter.integrated_loudness(y.T)
        if loudness > -70:
            gain_db = target_lufs - loudness
            gain_db = np.clip(gain_db, -12, 12)
            y *= 10 ** (gain_db / 20)
    except ImportError:
        for ch in range(y.shape[0]):
            rms = np.sqrt(np.mean(y[ch] ** 2))
            if rms < 1e-8:
                continue
            current_lufs = 20 * np.log10(rms) - 0.691
            gain_db = np.clip(target_lufs - current_lufs, -12, 12)
            y[ch] *= 10 ** (gain_db / 20)
    return y


def _apply_de_clipping(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    threshold = 0.92

    for ch in range(y.shape[0]):
        data = result[ch]
        clip_mask = np.abs(data) > threshold
        if not np.any(clip_mask):
            continue

        labeled = np.diff(clip_mask.astype(int))
        starts = np.where(labeled == 1)[0] + 1
        ends = np.where(labeled == -1)[0] + 1

        if clip_mask[0]:
            starts = np.concatenate([[0], starts])
        if clip_mask[-1]:
            ends = np.concatenate([ends, [len(data)]])

        for start, end in zip(starts, ends):
            margin = max(16, int((end - start) * 0.5))
            left = max(0, start - margin)
            right = min(len(data), end + margin)

            anchor_indices = list(range(left, start)) + list(range(end, right))
            anchor_values = data[anchor_indices]

            if len(anchor_indices) >= 4:
                from scipy.interpolate import CubicSpline
                try:
                    cs = CubicSpline(anchor_indices, anchor_values, bc_type='natural')
                    clip_indices = np.arange(start, end)
                    reconstructed = cs(clip_indices)
                    blend = intensity * 0.7
                    result[ch, start:end] = reconstructed * blend + data[start:end] * (1 - blend)
                except Exception:
                    sign = np.sign(data[start:end])
                    result[ch, start:end] = sign * threshold * intensity * 0.8 + data[start:end] * (1 - intensity * 0.8)

    return result


def _apply_de_crackle_v2(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        phase = np.exp(1j * np.angle(S))

        frame_energy = np.sum(mag ** 2, axis=0)
        med_energy = medfilt(frame_energy, kernel_size=5)
        energy_ratio = frame_energy / (med_energy + 1e-10)
        crackle_frames = energy_ratio > (1.3 + (1 - intensity) * 1.5)

        if np.any(crackle_frames):
            smooth_mag = medfilt(mag, kernel_size=(1, 5))
            for j in np.where(crackle_frames)[0]:
                left_j = max(0, j - 2)
                right_j = min(mag.shape[1], j + 3)
                local_avg = np.mean(mag[:, left_j:right_j], axis=1)
                local_avg = np.maximum(local_avg, smooth_mag[:, j] * 0.5)
                blend = min(1.0, intensity * 0.8 * (energy_ratio[j] - 1) / 1.5)
                S[:, j] = (local_avg * blend + mag[:, j] * (1 - blend)) * phase[:, j]

        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))
    return result


def _apply_de_pop_v2(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        for block_ms in [5, 10, 20]:
            block_size = int(sr * block_ms / 1000)
            if block_size < 2:
                continue
            n_blocks = len(data) // block_size
            if n_blocks < 3:
                continue

            block_energy = np.zeros(n_blocks)
            for i in range(n_blocks):
                block = data[i * block_size:(i + 1) * block_size]
                block_energy[i] = np.sqrt(np.mean(block ** 2))

            med_energy = medfilt(block_energy, kernel_size=min(7, n_blocks | 1))
            pop_threshold = med_energy * (2.5 + (1 - intensity) * 4)
            pop_blocks = np.where(block_energy > pop_threshold)[0]

            for block_idx in pop_blocks:
                start = block_idx * block_size
                end = min(len(data), (block_idx + 1) * block_size)
                left_start = max(0, start - block_size)
                right_end = min(len(data), end + block_size)

                left_rms = np.sqrt(np.mean(data[left_start:start] ** 2)) if start > 0 else 0
                right_rms = np.sqrt(np.mean(data[end:right_end] ** 2)) if end < len(data) else 0
                target_rms = (left_rms + right_rms) / 2

                current_rms = np.sqrt(np.mean(data[start:end] ** 2))
                if current_rms > 0 and target_rms > 0:
                    ratio = target_rms / current_rms
                    blend = intensity * 0.7
                    fade_len = min(block_size // 4, end - start)
                    for i in range(start, end):
                        local_blend = blend
                        if i - start < fade_len:
                            local_blend *= (i - start) / fade_len
                        elif end - i < fade_len:
                            local_blend *= (end - i) / fade_len
                        result[ch, i] = data[i] * (ratio * local_blend + 1.0 * (1 - local_blend))
    return result


def _apply_de_essing_v2(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        sibilant_bands = [
            (2000, 4000, 1.0),
            (4000, 7000, 1.5),
            (7000, 12000, 1.2),
        ]

        for low, high, weight in sibilant_bands:
            band_mask = (freqs >= low) & (freqs <= high)
            if not np.any(band_mask):
                continue

            band_energy = np.mean(mag[band_mask, :], axis=0)
            total_energy = np.mean(mag, axis=0) + 1e-10
            sibilant_ratio = band_energy / total_energy

            threshold = np.mean(sibilant_ratio) + np.std(sibilant_ratio) * 1.2
            sibilant_frames = sibilant_ratio > threshold

            for j in np.where(sibilant_frames)[0]:
                excess = (sibilant_ratio[j] - threshold) / (threshold + 1e-10)
                reduction = 1.0 - intensity * 0.35 * weight * min(1.0, excess)
                reduction = max(reduction, 0.25)
                S[band_mask, j] *= reduction

        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))
    return result


def _apply_noise_reduction(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    try:
        import noisereduce as nr
        result = y.copy()
        for ch in range(y.shape[0]):
            result[ch] = nr.reduce_noise(
                y=y[ch],
                sr=sr,
                prop_decrease=min(0.95, intensity * 0.9),
                stationary=False,
                n_fft=4096,
                hop_length=1024,
                use_torch=False,
            )
        return result
    except (ImportError, Exception):
        return _apply_noise_reduction_spectral_v2(y, sr, intensity, 4096, 1024)


def _apply_noise_reduction_spectral_v2(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        S = librosa.stft(result[ch], n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        noise_frames = max(1, mag.shape[1] // 20)
        noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)
        threshold = noise_profile * (1 + intensity * 5)
        mask = np.where(mag > threshold, 1.0, (mag / threshold) ** 2 * intensity * 0.3)
        for i in range(1, mask.shape[1] - 1):
            mask[:, i] = mask[:, i] * 0.5 + (mask[:, i-1] + mask[:, i+1]) * 0.25
        S_clean = S * mask
        result[ch] = librosa.istft(S_clean, hop_length=hop_length, length=y.shape[1])
    return result


def _apply_transient_repair_v2(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        frame_size = int(sr * 0.02)
        n_frames = len(data) // frame_size
        if n_frames < 4:
            continue

        frame_rms = np.zeros(n_frames)
        for i in range(n_frames):
            frame = data[i * frame_size:(i + 1) * frame_size]
            frame_rms[i] = np.sqrt(np.mean(frame ** 2))

        smooth_rms = medfilt(frame_rms, kernel_size=min(7, n_frames | 1))
        attack_coeff = np.exp(-1 / (0.01 * sr / frame_size))
        release_coeff = np.exp(-1 / (0.1 * sr / frame_size))

        envelope = np.zeros(n_frames)
        envelope[0] = frame_rms[0]
        for i in range(1, n_frames):
            coeff = attack_coeff if frame_rms[i] > envelope[i-1] else release_coeff
            envelope[i] = coeff * envelope[i-1] + (1 - coeff) * frame_rms[i]

        deviation = np.abs(envelope - smooth_rms) / (smooth_rms + 1e-10)
        anomaly_threshold = 0.3 + (1 - intensity) * 0.5
        anomaly_frames = deviation > anomaly_threshold

        for frame_idx in np.where(anomaly_frames)[0]:
            start = frame_idx * frame_size
            end = min(len(data), (frame_idx + 1) * frame_size)
            left_idx = max(0, frame_idx - 1)
            right_idx = min(n_frames - 1, frame_idx + 1)
            target_rms = (smooth_rms[left_idx] + smooth_rms[right_idx]) / 2
            current_rms = frame_rms[frame_idx]
            if current_rms > 0 and target_rms > 0:
                ratio = target_rms / current_rms
                blend = intensity * 0.6
                fade_len = min(frame_size // 4, end - start)
                for i in range(start, end):
                    local_blend = blend
                    if i - start < fade_len:
                        local_blend *= (i - start) / fade_len
                    elif end - i < fade_len:
                        local_blend *= (end - i) / fade_len
                    result[ch, i] = data[i] * (ratio * local_blend + 1.0 * (1 - local_blend))
    return result


def _apply_harmonic_enhance_v3(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        phase = np.angle(S)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        harmonic_content = np.zeros_like(mag)
        for i, f in enumerate(freqs):
            if f < 80 or f > 4000:
                continue
            for h_num, h_gain in [(2, 0.08), (3, 0.04), (4, 0.02)]:
                h_freq = f * h_num
                if h_freq > sr / 2 - 200:
                    break
                h_idx = np.argmin(np.abs(freqs - h_freq))
                if h_idx < mag.shape[0]:
                    harmonic_content[h_idx, :] += np.sqrt(mag[i, :]) * h_gain * intensity

        original_energy = np.sum(mag ** 2, axis=0)
        harmonic_energy = np.sum(harmonic_content ** 2, axis=0)
        mix_ratio = np.clip(harmonic_energy / (original_energy + 1e-10), 0, 0.3)

        enhanced_mag = mag + harmonic_content * (1 - mix_ratio) * intensity * 0.5

        S_enhanced = enhanced_mag * np.exp(1j * phase)
        result[ch] = librosa.istft(S_enhanced, hop_length=hop_length, length=len(data))

        result[ch] = _apply_tube_saturation(result[ch], intensity * 0.3)
    return result


def _apply_tube_saturation(x: np.ndarray, amount: float) -> np.ndarray:
    if amount < 0.01:
        return x
    drive = 1 + amount * 2
    return np.tanh(x * drive) / drive


def _apply_spatial_enhance_v3(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    if y.shape[0] != 2:
        return y

    mid = (y[0] + y[1]) / 2
    side = (y[0] - y[1]) / 2

    correlation = np.sum(y[0] * y[1]) / (np.sqrt(np.sum(y[0]**2) * np.sum(y[1]**2)) + 1e-10)

    if correlation > 0.8:
        side_gain = 1 + intensity * 0.5
    elif correlation > 0.5:
        side_gain = 1 + intensity * 0.35
    else:
        side_gain = 1 + intensity * 0.2

    mid_gain = 1 - intensity * 0.02

    low_cutoff = 120
    if sr > low_cutoff * 2:
        b, a = butter(4, low_cutoff / (sr / 2), btype='low')
        mid_low = filtfilt(b, a, mid)
        side_low = filtfilt(b, a, side)
        side = side_low * 0.3 + (side - side_low)

    enhanced_mid = mid * mid_gain
    enhanced_side = side * side_gain

    result = np.zeros_like(y)
    result[0] = enhanced_mid + enhanced_side
    result[1] = enhanced_mid - enhanced_side

    reverb_amount = intensity * 0.1
    if reverb_amount > 0.02:
        if HAS_PEDALBOARD:
            board = Pedalboard([
                Reverb(room_size=reverb_amount, damping=0.8, wet_level=reverb_amount * 0.2, dry_level=1.0)
            ])
            out = board(result, sr)
            if out.ndim == 1:
                out = out.reshape(1, -1)
            if out.shape[0] == result.shape[0] and out.shape[1] >= result.shape[1]:
                result = out[:, :result.shape[1]]
        else:
            result = _apply_simple_reverb(result, sr, reverb_amount)

    return result


def _apply_simple_reverb(y: np.ndarray, sr: int, amount: float) -> np.ndarray:
    delays_ms = [17, 31, 47, 67, 89]
    gains = [0.3, 0.25, 0.2, 0.15, 0.1]
    wet = np.zeros_like(y)
    for delay_ms, gain in zip(delays_ms, gains):
        delay_samples = int(sr * delay_ms / 1000)
        for ch in range(y.shape[0]):
            delayed = np.zeros_like(y[ch])
            if delay_samples < len(y[ch]):
                delayed[delay_samples:] = y[ch, :-delay_samples] * gain
            wet[ch] += delayed
    wet_gain = amount * 0.3
    return y * (1 - wet_gain) + wet * wet_gain


def _apply_presence_boost(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    boost_db = intensity * 2.5

    if HAS_PEDALBOARD:
        filters = []
        freqs_q = [(2000, 1.2), (3000, 1.0), (4000, 1.4), (6000, 1.6)]
        for freq, q in freqs_q:
            if freq < sr / 2:
                filters.append(PeakFilter(cutoff_frequency_hz=freq, gain_db=boost_db * 0.35, q=q))
        if not filters:
            return y
        board = Pedalboard(filters)
        if y.shape[0] == 1:
            out = board(y[0], sr)
            return out.reshape(1, -1)
        else:
            out = board(y, sr)
            if out.ndim == 1:
                out = out.reshape(2, -1)
            return out[:, :y.shape[1]]
    else:
        result = y.copy()
        freqs_boost = [(2000, 4000, boost_db * 0.35), (4000, 6000, boost_db * 0.25)]
        for low, high, gain_db in freqs_boost:
            if high >= sr / 2:
                continue
            b, a = butter(2, [low / (sr / 2), high / (sr / 2)], btype='band')
            for ch in range(y.shape[0]):
                presence = filtfilt(b, a, result[ch])
                result[ch] += presence * (10 ** (gain_db / 20) - 1)
        return result


def _apply_bass_enhance(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    boost_db = intensity * 3.0

    if HAS_PEDALBOARD:
        filters = []
        if 80 < sr / 2:
            filters.append(LowShelfFilter(cutoff_frequency_hz=80, gain_db=boost_db * 0.4, q=0.7))
        if 150 < sr / 2:
            filters.append(LowShelfFilter(cutoff_frequency_hz=150, gain_db=boost_db * 0.25, q=0.7))
        if not filters:
            return y
        board = Pedalboard(filters)
        if y.shape[0] == 1:
            out = board(y[0], sr)
            return out.reshape(1, -1)
        else:
            out = board(y, sr)
            if out.ndim == 1:
                out = out.reshape(2, -1)
            return out[:, :y.shape[1]]
    else:
        result = y.copy()
        shelf_freqs = [(80, boost_db * 0.4), (150, boost_db * 0.25)]
        for freq, gain_db in shelf_freqs:
            if freq >= sr / 2:
                continue
            b, a = butter(2, freq / (sr / 2), btype='low')
            for ch in range(y.shape[0]):
                bass = filtfilt(b, a, result[ch])
                result[ch] += bass * (10 ** (gain_db / 20) - 1)
        return result


def _apply_multiband_compression(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    if intensity < 0.05:
        return y

    low_crossover = 250
    high_crossover = 4000

    result = np.zeros_like(y)

    for ch in range(y.shape[0]):
        data = y[ch]

        b_low, a_low = butter(4, low_crossover / (sr / 2), btype='low')
        low_band = filtfilt(b_low, a_low, data)

        b_mid_low, a_mid_low = butter(4, low_crossover / (sr / 2), btype='high')
        b_mid_high, a_mid_high = butter(4, high_crossover / (sr / 2), btype='low')
        mid_band = filtfilt(b_mid_low, a_mid_low, data)
        mid_band = filtfilt(b_mid_high, a_mid_high, mid_band)

        b_high, a_high = butter(4, high_crossover / (sr / 2), btype='high')
        high_band = filtfilt(b_high, a_high, data)

        bands = [
            (low_band, -20, 3.0, 10.0, 100.0),
            (mid_band, -18, 2.5 + intensity * 2, 5.0, 80.0),
            (high_band, -16, 2.0 + intensity * 3, 3.0, 60.0),
        ]

        compressed_bands = []
        for band, thresh, ratio, attack, release in bands:
            if HAS_PEDALBOARD:
                board = Pedalboard([
                    Compressor(threshold_db=thresh, ratio=ratio, attack_ms=attack, release_ms=release),
                ])
                compressed = board(band, sr)
                if isinstance(compressed, np.ndarray):
                    compressed_bands.append(compressed[:len(data)])
                else:
                    compressed_bands.append(band)
            else:
                compressed_bands.append(_simple_compress(band, thresh, ratio, attack, release, sr))

        result[ch] = sum(compressed_bands)

    makeup_gain = intensity * 1.5
    result *= 10 ** (makeup_gain / 20)

    return result


def _simple_compress(band: np.ndarray, threshold_db: float, ratio: float, attack_ms: float, release_ms: float, sr: int) -> np.ndarray:
    threshold_lin = 10 ** (threshold_db / 20)
    attack_coeff = np.exp(-1 / (attack_ms * 0.001 * sr))
    release_coeff = np.exp(-1 / (release_ms * 0.001 * sr))

    envelope = np.zeros(len(band))
    envelope[0] = np.abs(band[0])
    for i in range(1, len(band)):
        sample_abs = np.abs(band[i])
        coeff = attack_coeff if sample_abs > envelope[i-1] else release_coeff
        envelope[i] = coeff * envelope[i-1] + (1 - coeff) * sample_abs

    gain = np.ones(len(band))
    over = envelope > threshold_lin
    if np.any(over):
        over_db = 20 * np.log10(envelope[over] / threshold_lin)
        compressed_db = over_db / ratio
        gain[over] = 10 ** ((compressed_db - over_db) / 20)

    return band * gain


def _apply_softness(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    cutoff = max(8000, 18000 - intensity * 8000)
    cutoff = min(cutoff, sr / 2 - 100)

    blend = intensity * 0.25

    if HAS_PEDALBOARD:
        board = Pedalboard([
            LowpassFilter(cutoff_frequency_hz=cutoff),
        ])
        if y.shape[0] == 1:
            filtered = board(y[0], sr)
            return (filtered * blend + y[0] * (1 - blend)).reshape(1, -1)
        else:
            filtered = board(y, sr)
            if filtered.ndim == 1:
                filtered = filtered.reshape(2, -1)
            filtered = filtered[:, :y.shape[1]]
            return filtered * blend + y * (1 - blend)
    else:
        b, a = butter(4, cutoff / (sr / 2), btype='low')
        result = y.copy()
        for ch in range(y.shape[0]):
            filtered = filtfilt(b, a, result[ch])
            result[ch] = filtered * blend + result[ch] * (1 - blend)
        return result


def _apply_dither(y: np.ndarray, bit_depth: int) -> np.ndarray:
    if bit_depth >= 32:
        return y

    quant_step = 2.0 / (2 ** bit_depth)

    noise = (np.random.random(y.shape) - 0.5) + (np.random.random(y.shape) - 0.5)
    noise *= quant_step

    y_dithered = y + noise

    y_quantized = np.round(y_dithered / quant_step) * quant_step

    y_quantized = np.clip(y_quantized, -1.0, 1.0 - quant_step)

    return y_quantized
