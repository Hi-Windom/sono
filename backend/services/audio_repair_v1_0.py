import numpy as np
import librosa
import soundfile as sf
from scipy.interpolate import CubicSpline
from scipy.signal import medfilt, butter, sosfilt, resample_poly


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    y, sr = librosa.load(input_path, sr=None, mono=False)
    was_mono = False
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True

    original_sr = sr
    target_sr = params.get("sample_rate", sr)
    original_duration = round(y.shape[1] / sr, 2)

    if progress_callback:
        progress_callback(0.05, "分析音频问题...")

    issues_found = []
    n_fft = 4096
    hop_length = 1024

    if params.get("de_clipping", 0) > 0:
        if progress_callback:
            progress_callback(0.08, "去削波处理(三次样条插值)...")
        y = _apply_de_clipping(y, params["de_clipping"])
        issues_found.append("削波修复")

    if params.get("de_crackle", 0) > 0:
        if progress_callback:
            progress_callback(0.16, "去毛刺处理(频谱插值)...")
        y = _apply_de_crackle(y, sr, params["de_crackle"], n_fft, hop_length)
        issues_found.append("毛刺修复")

    if params.get("de_pop", 0) > 0:
        if progress_callback:
            progress_callback(0.24, "去爆音处理(能量检测)...")
        y = _apply_de_pop(y, sr, params["de_pop"])
        issues_found.append("爆音修复")

    if params.get("de_essing", 0) > 0:
        if progress_callback:
            progress_callback(0.32, "去齿音处理(自适应宽频)...")
        y = _apply_de_essing(y, sr, params["de_essing"], n_fft, hop_length)
        issues_found.append("齿音抑制")

    if params.get("noise_reduction", 0) > 0:
        if progress_callback:
            progress_callback(0.40, "频谱门限降噪...")
        y = _apply_noise_reduction(y, sr, params["noise_reduction"], n_fft, hop_length)
        issues_found.append("降噪处理")

    if params.get("transient_repair", 0) > 0:
        if progress_callback:
            progress_callback(0.50, "瞬态修复(包络平滑)...")
        y = _apply_transient_repair(y, sr, params["transient_repair"])
        issues_found.append("瞬态修复")

    if params.get("harmonic_enhance", 0) > 0:
        if progress_callback:
            progress_callback(0.58, "谐波增强(STFT谐波生成)...")
        y = _apply_harmonic_enhance(y, sr, params["harmonic_enhance"], n_fft, hop_length)
        issues_found.append("谐波增强")

    if params.get("spatial_enhance", 0) > 0 and y.shape[0] == 2:
        if progress_callback:
            progress_callback(0.66, "空间感增强(Mid/Side)...")
        y = _apply_spatial_enhance(y, params["spatial_enhance"])
        issues_found.append("空间感增强")

    if params.get("presence_boost", 0) > 0:
        if progress_callback:
            progress_callback(0.74, "临场感增强(参数EQ)...")
        y = _apply_presence_boost(y, sr, params["presence_boost"])
        issues_found.append("临场增强")

    if params.get("bass_enhance", 0) > 0:
        if progress_callback:
            progress_callback(0.80, "低音增强(参数EQ)...")
        y = _apply_bass_enhance(y, sr, params["bass_enhance"])
        issues_found.append("低音增强")

    if params.get("dynamic_range", 0) > 0:
        if progress_callback:
            progress_callback(0.86, "动态范围优化(多频段压缩)...")
        y = _apply_dynamic_range(y, sr, params["dynamic_range"])
        issues_found.append("动态优化")

    if params.get("softness", 0) > 0:
        if progress_callback:
            progress_callback(0.90, "柔和处理(高频衰减)...")
        y = _apply_softness(y, sr, params["softness"])
        issues_found.append("柔和处理")

    if target_sr != sr:
        if progress_callback:
            progress_callback(0.93, f"重采样到 {target_sr//1000} kHz...")
        y_resampled = np.zeros((y.shape[0], int(y.shape[1] * target_sr / sr)))
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], target_sr, sr)
            y_resampled[ch, :len(resampled)] = resampled[:y_resampled.shape[1]]
        y = y_resampled
        sr = target_sr

    y = _apply_peak_limit(y, -0.3)

    if was_mono:
        y = y[0]

    if progress_callback:
        progress_callback(0.96, "导出WAV...")

    bit_depth = params.get("bit_depth", 24)
    subtype = "PCM_16" if bit_depth == 16 else "PCM_24" if bit_depth == 24 else "FLOAT"
    sf.write(output_path, y.T if y.ndim == 1 else y.T, sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "修复完成!")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": 1 if was_mono else 2,
    }


def _apply_peak_limit(y: np.ndarray, ceiling_db: float) -> np.ndarray:
    ceiling = 10 ** (ceiling_db / 20)
    for ch in range(y.shape[0]):
        peak = np.max(np.abs(y[ch]))
        if peak > ceiling:
            y[ch] *= ceiling / peak
    return y


def _apply_de_clipping(y: np.ndarray, intensity: float) -> np.ndarray:
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
            margin = max(4, int((end - start) * 0.3))
            left = max(0, start - margin)
            right = min(len(data), end + margin)

            anchor_indices = list(range(left, start)) + list(range(end, right))
            anchor_values = data[anchor_indices]

            if len(anchor_indices) >= 4:
                try:
                    cs = CubicSpline(anchor_indices, anchor_values)
                    clip_indices = np.arange(start, end)
                    reconstructed = cs(clip_indices)
                    blend = intensity * 0.85
                    result[ch, start:end] = reconstructed * blend + data[start:end] * (1 - blend)
                except Exception:
                    sign = np.sign(data[start:end])
                    result[ch, start:end] = sign * threshold * intensity * 0.8 + data[start:end] * (1 - intensity * 0.8)
            elif len(anchor_indices) >= 2:
                slope = (anchor_values[-1] - anchor_values[0]) / (anchor_indices[-1] - anchor_indices[0] + 1e-10)
                for i in range(start, end):
                    t = (i - anchor_indices[0]) / (anchor_indices[-1] - anchor_indices[0] + 1e-10)
                    interp = anchor_values[0] + slope * (i - anchor_indices[0])
                    result[ch, i] = interp * intensity * 0.7 + data[i] * (1 - intensity * 0.7)

    return result


def _apply_de_crackle(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        phase = np.exp(1j * np.angle(S))

        frame_energy = np.sum(mag ** 2, axis=0)
        med_energy = medfilt(frame_energy, kernel_size=5)
        energy_ratio = frame_energy / (med_energy + 1e-10)
        crackle_frames = energy_ratio > (1.5 + (1 - intensity) * 2)

        if np.any(crackle_frames):
            smooth_mag = medfilt(mag, kernel_size=(1, 3))
            for j in np.where(crackle_frames)[0]:
                blend = min(1.0, intensity * 0.7 * (energy_ratio[j] - 1) / 2)
                S[:, j] = (smooth_mag[:, j] * blend + mag[:, j] * (1 - blend)) * phase[:, j]

        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))
    return result


def _apply_de_pop(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    block_size = int(sr * 0.01)
    if block_size < 2:
        return result

    for ch in range(y.shape[0]):
        data = result[ch]
        n_blocks = len(data) // block_size
        if n_blocks < 3:
            continue

        block_energy = np.zeros(n_blocks)
        for i in range(n_blocks):
            block = data[i * block_size:(i + 1) * block_size]
            block_energy[i] = np.sqrt(np.mean(block ** 2))

        med_energy = medfilt(block_energy, kernel_size=min(5, n_blocks | 1))
        pop_threshold = med_energy * (3 + (1 - intensity) * 5)

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
                blend = intensity * 0.6
                gain = ratio * blend + 1.0 * (1 - blend)
                result[ch, start:end] = data[start:end] * gain

    return result


def _apply_de_essing(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        sibilant_bands = [
            (3000, 5000),
            (5000, 7000),
            (7000, 10000),
        ]

        for low, high in sibilant_bands:
            band_mask = (freqs >= low) & (freqs <= high)
            if not np.any(band_mask):
                continue

            band_energy = np.mean(mag[band_mask, :], axis=0)
            total_energy = np.mean(mag, axis=0) + 1e-10
            sibilant_ratio = band_energy / total_energy

            threshold = np.mean(sibilant_ratio) + np.std(sibilant_ratio) * 1.5
            sibilant_frames = sibilant_ratio > threshold

            for j in np.where(sibilant_frames)[0]:
                excess = (sibilant_ratio[j] - threshold) / (threshold + 1e-10)
                reduction = 1.0 - intensity * 0.4 * min(1.0, excess)
                reduction = max(reduction, 0.3)
                S[band_mask, j] *= reduction

        result[ch] = librosa.istft(S, hop_length=hop_length, length=len(data))
    return result


def _apply_noise_reduction(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    try:
        import noisereduce as nr
        result = y.copy()
        for ch in range(y.shape[0]):
            result[ch] = nr.reduce_noise(
                y=y[ch],
                sr=sr,
                prop_decrease=min(0.95, intensity * 0.85),
                stationary=False,
                n_fft=n_fft,
                hop_length=hop_length,
            )
        return result
    except ImportError:
        return _apply_noise_reduction_fallback(y, sr, intensity, n_fft, hop_length)


def _apply_noise_reduction_fallback(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        S = librosa.stft(result[ch], n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)

        noise_frames = max(1, mag.shape[1] // 20)
        noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)

        threshold = noise_profile * (1 + intensity * 4)
        mask = mag > threshold

        smooth_mask = mask.astype(float)
        for i in range(1, smooth_mask.shape[1] - 1):
            smooth_mask[:, i] = smooth_mask[:, i] * 0.6 + (smooth_mask[:, i-1] + smooth_mask[:, i+1]) * 0.2

        S_clean = S * smooth_mask + S * (1 - smooth_mask) * (1 - intensity * 0.7)
        result[ch] = librosa.istft(S_clean, hop_length=hop_length, length=y.shape[1])
    return result


def _apply_transient_repair(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
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
        deviation = np.abs(frame_rms - smooth_rms) / (smooth_rms + 1e-10)
        anomaly_threshold = 0.4 + (1 - intensity) * 0.6
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
                blend = intensity * 0.5
                gain = ratio * blend + 1.0 * (1 - blend)
                result[ch, start:end] = data[start:end] * gain

    return result


def _apply_harmonic_enhance(y: np.ndarray, sr: int, intensity: float, n_fft: int, hop_length: int) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        S = librosa.stft(data, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        fundamental_mask = freqs < 4000
        harmonic_boost = np.ones_like(mag)

        for i, f in enumerate(freqs):
            if f < 50 or f > sr / 2 - 100:
                continue
            h2_idx = np.argmin(np.abs(freqs - f * 2))
            h3_idx = np.argmin(np.abs(freqs - f * 3))

            if h2_idx < mag.shape[0]:
                harmonic_boost[h2_idx, :] += mag[i, :] * intensity * 0.008
            if h3_idx < mag.shape[0]:
                harmonic_boost[h3_idx, :] += mag[i, :] * intensity * 0.003

        harmonic_boost = np.clip(harmonic_boost, 1.0, 1.0 + intensity * 0.5)
        S_enhanced = S * harmonic_boost
        result[ch] = librosa.istft(S_enhanced, hop_length=hop_length, length=len(data))
    return result


def _apply_spatial_enhance(y: np.ndarray, intensity: float) -> np.ndarray:
    if y.shape[0] != 2:
        return y
    mid = (y[0] + y[1]) / 2
    side = (y[0] - y[1]) / 2
    side *= (1 + intensity * 0.4)
    result = np.zeros_like(y)
    result[0] = mid + side
    result[1] = mid - side
    return result


def _apply_presence_boost(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    boost_db = intensity * 3.0
    gain = 10 ** (boost_db / 20)

    freqs_centers = [2500, 3500, 5000]
    bandwidths = [400, 600, 800]

    for ch in range(y.shape[0]):
        data = result[ch]
        for fc, bw in zip(freqs_centers, bandwidths):
            nyq = sr / 2
            if fc >= nyq:
                continue
            low = max(20, (fc - bw / 2)) / nyq
            high = min(nyq - 1, (fc + bw / 2)) / nyq
            if high <= low:
                continue
            try:
                sos = butter(2, [low, high], btype='band', output='sos')
                band = sosfilt(sos, data)
                data = data + band * (gain - 1) * 0.5
            except Exception:
                pass
        result[ch] = data
    return result


def _apply_bass_enhance(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    boost_db = intensity * 4.0
    gain = 10 ** (boost_db / 20)

    for ch in range(y.shape[0]):
        data = result[ch]
        nyq = sr / 2

        sub_cutoff = min(60, nyq * 0.9) / nyq
        if sub_cutoff > 0 and sub_cutoff < 1:
            try:
                sos = butter(2, sub_cutoff, btype='low', output='sos')
                sub = sosfilt(sos, data)
                data = data + sub * (gain - 1) * 0.4
            except Exception:
                pass

        bass_low = max(20, 60) / nyq
        bass_high = min(nyq * 0.9, 150) / nyq
        if bass_high > bass_low and bass_high < 1:
            try:
                sos = butter(2, [bass_low, bass_high], btype='band', output='sos')
                bass = sosfilt(sos, data)
                data = data + bass * (10 ** (boost_db * 0.6 / 20) - 1) * 0.3
            except Exception:
                pass

        result[ch] = data
    return result


def _apply_dynamic_range(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        frame_size = int(sr * 0.05)
        n_frames = max(1, len(data) // frame_size)

        rms_values = []
        for i in range(n_frames):
            start = i * frame_size
            end = min(len(data), start + frame_size)
            rms = np.sqrt(np.mean(data[start:end] ** 2))
            rms_values.append(rms)

        rms_arr = np.array(rms_values)
        global_rms = np.sqrt(np.mean(data ** 2))

        if global_rms < 1e-6:
            continue

        target_rms = 0.08 + 0.04 * (1 - intensity)
        ratio = target_rms / global_rms

        makeup_gain = 1.0 + (ratio - 1.0) * intensity * 0.6
        makeup_gain = max(0.5, min(2.0, makeup_gain))

        result[ch] = data * makeup_gain

        peak = np.max(np.abs(result[ch]))
        if peak > 0.95:
            result[ch] *= 0.95 / peak

    return result


def _apply_softness(y: np.ndarray, sr: int, intensity: float) -> np.ndarray:
    result = y.copy()
    cutoff = max(6000, 16000 - intensity * 6000)
    nyq = sr / 2
    normalized_cutoff = min(cutoff / nyq, 0.99)

    if normalized_cutoff <= 0:
        return result

    try:
        sos = butter(4, normalized_cutoff, btype='low', output='sos')
        for ch in range(y.shape[0]):
            filtered = sosfilt(sos, result[ch])
            blend = intensity * 0.3
            result[ch] = filtered * blend + result[ch] * (1 - blend)
    except Exception:
        pass

    return result
