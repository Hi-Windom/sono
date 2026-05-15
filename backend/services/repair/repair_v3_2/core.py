import numpy as np
import soundfile as sf
import gc
from scipy.signal import butter, sosfiltfilt, resample_poly

from services.audio_loader import load_audio_with_fallback
from services.dsp_utils import stft, istft

DESKTOP_WORKING_SR = 48000
N_FFT = 2048
HOP_LENGTH = 512


def _vocal_formant_repair(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_formant_repair(y, sr, amount)
        return y[0]
    for ch in range(y.shape[0]):
        y[ch] = _vocal_formant_repair_1d(y[ch], sr, amount)
    return y


def _vocal_formant_repair_1d(data, sr, amount):
    nyq = sr / 2
    sibilance_low = int(6000 / nyq * (N_FFT // 2))
    sibilance_high = int(12000 / nyq * (N_FFT // 2))
    pop_low = int(50 / nyq * (N_FFT // 2))
    pop_high = int(200 / nyq * (N_FFT // 2))
    formant_low = int(500 / nyq * (N_FFT // 2))
    formant_high = int(3000 / nyq * (N_FFT // 2))

    frame_len = N_FFT
    hop = HOP_LENGTH
    n_frames = (len(data) - frame_len) // hop + 1
    if n_frames < 2:
        return data

    sibilance_gain = np.ones(n_frames)
    pop_gain = np.ones(n_frames)

    for i in range(n_frames):
        start = i * hop
        end = start + frame_len
        if end > len(data):
            break
        frame = data[start:end]

        hf_energy = np.mean(frame[sibilance_low:sibilance_high]**2) if sibilance_high < len(frame) else 0
        lf_energy = np.mean(frame[pop_low:pop_high]**2) if pop_high < len(frame) else 0
        formant_energy = np.mean(frame[formant_low:formant_high]**2) if formant_high < len(frame) else 0

        total_energy = np.mean(frame**2) + 1e-10
        hf_ratio = hf_energy / total_energy
        lf_ratio = lf_energy / total_energy

        if hf_ratio > 0.15 + amount * 0.2:
            sibilance_gain[i] = 1.0 - amount * 0.3
        if lf_ratio > 0.3 + amount * 0.2:
            pop_gain[i] = 1.0 - amount * 0.4

    sibilance_smooth = np.convolve(sibilance_gain, np.ones(3)/3, mode='same')
    pop_smooth = np.convolve(pop_gain, np.ones(5)/5, mode='same')

    gain_per_frame = np.ones(n_frames)
    for i in range(n_frames):
        s_gain = sibilance_smooth[i] if i < len(sibilance_smooth) else 1.0
        p_gain = pop_smooth[i] if i < len(pop_smooth) else 1.0
        gain_per_frame[i] = (s_gain + p_gain) / 2

    sample_positions = np.arange(len(data))
    frame_centers = np.arange(n_frames) * hop + frame_len // 2
    frame_centers = np.clip(frame_centers, 0, len(data) - 1)
    gain_per_sample = np.interp(sample_positions, frame_centers, gain_per_frame)

    result = data.astype(np.float64) * gain_per_sample
    return result.astype(data.dtype)


def _vocal_breath_enhance(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_breath_enhance(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        breath_mask = _detect_breath_regions(y[ch], sr)
        if breath_mask is None:
            continue
        breath_gain = 1.0 + amount * 0.3
        y[ch][breath_mask] *= breath_gain
        noise_floor = np.std(y[ch][breath_mask]) * 0.1 * amount
        y[ch][breath_mask] += np.random.randn(np.sum(breath_mask)) * noise_floor

    return y


def _detect_breath_regions(data, sr):
    frame_len = int(sr * 0.05)
    hop = int(sr * 0.025)
    n_frames = (len(data) - frame_len) // hop + 1
    if n_frames < 2:
        return None

    frame_energies = []
    for i in range(n_frames):
        start = i * hop
        end = start + frame_len
        if end > len(data):
            break
        frame = data[start:end]
        rms = np.sqrt(np.mean(frame**2))
        frame_energies.append(rms)

    frame_energies = np.array(frame_energies)
    if len(frame_energies) == 0:
        return None

    threshold = np.percentile(frame_energies, 30)
    breath_frames = frame_energies < threshold

    breath_mask = np.zeros(len(data), dtype=bool)
    for i, is_breath in enumerate(breath_frames):
        if is_breath:
            start = i * hop
            end = min(start + frame_len, len(data))
            breath_mask[start:end] = True

    return breath_mask


def _instrument_timbre_protect(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _instrument_timbre_protect(y, sr, amount)
        return y[0]
    for ch in range(y.shape[0]):
        protected = _protect_timbre_1d(y[ch], sr, amount)
        y[ch] = protected
    return y


def _protect_timbre_1d(data, sr, amount):
    nyq = sr / 2
    bass_low, bass_high = 60, 250
    mid_low, mid_high = 250, 4000
    high_low, high_high = 4000, 16000

    sos_bass = butter(4, [bass_low/nyq, bass_high/nyq], btype='band', output='sos') if bass_low < bass_high < nyq else None
    sos_mid = butter(4, [mid_low/nyq, mid_high/nyq], btype='band', output='sos') if mid_low < mid_high < nyq else None
    sos_high = butter(4, [high_low/nyq, min(high_high, nyq*0.95)/nyq], btype='band', output='sos') if high_low < high_high < nyq else None

    bands = []
    if sos_bass is not None:
        bands.append(sosfiltfilt(sos_bass, data))
    if sos_mid is not None:
        bands.append(sosfiltfilt(sos_mid, data))
    if sos_high is not None:
        bands.append(sosfiltfilt(sos_high, data))

    if not bands:
        return data

    result = np.zeros_like(data)
    for band in bands:
        band_rms = np.sqrt(np.mean(band**2))
        if band_rms > 1e-6:
            target_rms = band_rms * (1 + amount * 0.1)
            gain = target_rms / band_rms
            gain = min(gain, 1.5)
            result += band * gain
        else:
            result += band

    return result


def _tanh_declip(y, amount):
    if amount <= 0:
        return y
    threshold = 0.90
    mask = np.abs(y) > threshold
    if not np.any(mask):
        return y
    abs_y = np.abs(y[mask]).astype(np.float64)
    over = abs_y - threshold
    headroom = 1.0 - threshold
    y[mask] = (np.sign(y[mask]) * (threshold + headroom * np.tanh(over / headroom))).astype(y.dtype)
    return y


def _diff_clamp_depop(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _diff_clamp_depop(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        diff = np.diff(data)
        abs_diff = np.abs(diff)
        median_diff = np.median(abs_diff)
        if median_diff < 1e-10:
            continue
        threshold_val = median_diff * (80 + 120 * amount)
        pop_mask = np.concatenate(([False], abs_diff > threshold_val))
        if not np.any(pop_mask):
            continue
        indices = np.where(pop_mask)[0]
        for idx in indices:
            if 0 < idx < len(data) - 1:
                prev = data[idx - 1]
                next_val = data[idx + 1]
                actual_diff = data[idx] - prev
                if abs(actual_diff) > threshold_val:
                    clamped = prev + np.sign(actual_diff) * threshold_val
                    data[idx] = 0.5 * (clamped + next_val)
        y[ch] = data.astype(y.dtype)
    return y


def _soft_peak_limit(y, threshold=0.9):
    abs_max = np.max(np.abs(y))
    if abs_max <= threshold:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _soft_peak_limit(y, threshold)
        return y[0]
    for ch in range(y.shape[0]):
        abs_data = np.abs(y[ch])
        mask = abs_data > threshold
        if not np.any(mask):
            continue
        headroom = 1.0 - threshold
        y[ch][mask] = (np.sign(y[ch][mask]) * (threshold + headroom * np.tanh((abs_data[mask] - threshold) / headroom))).astype(y.dtype)
    return y


def _adaptive_loudness_normalize(y, sr, target_loudness_lu=-14.0):
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _adaptive_loudness_normalize(y, sr, target_loudness_lu)
        return y[0]

    for ch in range(y.shape[0]):
        rms_val = np.sqrt(np.mean(y[ch].astype(np.float64)**2))
        if rms_val < 1e-10:
            continue
        target_rms = 10 ** (target_loudness_lu / 20.0)
        gain = target_rms / rms_val
        gain = np.clip(gain, 0.2, 5.0)
        y[ch] = (y[ch].astype(np.float64) * gain).astype(y.dtype)

    return y


def _apply_vocal_de_ess(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _apply_vocal_de_ess(y, sr, amount)
        return y[0]

    nyq = sr / 2
    low_hz, high_hz = 4000, 8000
    if high_hz >= nyq:
        high_hz = nyq * 0.95
    if low_hz >= high_hz:
        return y

    sos = butter(4, [low_hz/nyq, high_hz/nyq], btype='band', output='sos')
    high_band = sosfiltfilt(sos, y, axis=-1)
    low_band = y.astype(np.float64) - high_band.astype(np.float64)

    gain = 1 - amount * 0.35
    gain = max(gain, 0.1)

    y = (low_band + high_band * gain).astype(y.dtype)
    return y


def _vocal_ai_repair_adaptive(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_ai_repair_adaptive(y, sr, strength)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        S = stft(data, n_fft=N_FFT, hop_length=HOP_LENGTH)
        magnitude = np.abs(S)
        phase = np.angle(S)

        n_bins, n_frames = magnitude.shape

        nyq = sr / 2
        low_cut = int(2000 / nyq * n_bins)
        mid_cut = int(8000 / nyq * n_bins)
        low_cut = min(low_cut, n_bins)
        mid_cut = min(mid_cut, n_bins)

        min_stats_frames = 10
        noise_floor_min = np.zeros_like(magnitude)
        for b in range(n_bins):
            for f in range(n_frames):
                start_f = max(0, f - min_stats_frames + 1)
                noise_floor_min[b, f] = np.min(magnitude[b, start_f:f+1])

        threshold = np.zeros_like(magnitude)
        for f in range(n_frames):
            threshold[:low_cut, f] = noise_floor_min[:low_cut, f] * (1.0 + strength * 2.0)
            threshold[low_cut:mid_cut, f] = noise_floor_min[low_cut:mid_cut, f] * (1.0 + strength * 2.5)
            threshold[mid_cut:, f] = noise_floor_min[mid_cut:, f] * (1.0 + strength * 3.0)

        gain_map = np.where(magnitude < threshold, magnitude / (threshold + 1e-10), 1.0)
        gain_map = np.maximum(gain_map, 1.0 - strength * 0.3)

        smoothing_frames = max(2, int(0.02 * sr / HOP_LENGTH))
        kernel = np.ones(smoothing_frames) / smoothing_frames
        gain_map_smooth = np.zeros_like(gain_map)
        for b in range(n_bins):
            gain_map_smooth[b] = np.convolve(gain_map[b], kernel, mode='same')

        spectral_kernel_size = max(3, n_bins // 16)
        spectral_kernel = np.ones(spectral_kernel_size) / spectral_kernel_size
        gain_map_spectral = np.zeros_like(gain_map_smooth)
        for f in range(n_frames):
            gain_map_spectral[:, f] = np.convolve(gain_map_smooth[:, f], spectral_kernel, mode='same')

        S_repaired = magnitude * gain_map_spectral * np.exp(1j * phase)
        y_out = istft(S_repaired, hop_length=HOP_LENGTH, length=len(data))
        if len(y_out) > len(data):
            y_out = y_out[:len(data)]
        elif len(y_out) < len(data):
            y_out = np.pad(y_out, (0, len(data) - len(y_out)))

        y[ch] = y_out.astype(y.dtype)

    return y


def _vocal_exciter_improved(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_exciter_improved(y, sr, amount)
        return y[0]

    nyq = sr / 2
    crossover_hz = 2000
    if crossover_hz >= nyq:
        crossover_hz = nyq * 0.95
    sos_low = butter(4, crossover_hz / nyq, btype='low', output='sos')

    for ch in range(y.shape[0]):
        dry = y[ch].astype(np.float64)

        low_band = sosfiltfilt(sos_low, dry)
        high_band = dry - low_band

        harmonic2 = np.tanh(high_band * 1.5) * 0.3
        harmonic3 = np.tanh(high_band * 0.8) * 0.15

        pos_sat = np.where(high_band > 0, np.tanh(high_band * 1.2), high_band * 0.8)
        neg_sat = np.where(high_band < 0, np.tanh(high_band * 1.0), high_band * 0.9)
        harmonics = harmonic2 + harmonic3 + (pos_sat - high_band * 0.5 + neg_sat - high_band * 0.5) * 0.25
        harmonics = harmonics / (np.max(np.abs(harmonics)) + 1e-10)

        wet_high = high_band + harmonics * amount * 0.4
        peak_wet = np.max(np.abs(wet_high))
        if peak_wet > 0.99:
            wet_high *= 0.99 / peak_wet

        mix = low_band + wet_high
        peak = np.max(np.abs(mix))
        if peak > 0.99:
            mix *= 0.99 / peak

        y[ch] = mix.astype(y.dtype)

    return y


def _vocal_smart_compressor(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_smart_compressor(y, sr, amount)
        return y[0]

    attack_ms = 10.0
    attack_gamma = np.exp(-1000.0 / (attack_ms * sr / HOP_LENGTH + 1e-10))

    ratio = 1.0 + amount * 3.0
    threshold_db = -24.0 + (1.0 - amount) * 12.0
    knee_width = 6.0

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)

        frame_len = HOP_LENGTH
        n_frames = (len(data) - frame_len) // (frame_len // 2) + 1
        if n_frames < 2:
            continue

        rms_envelope = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))
            frame = data[start:end]
            rms_envelope[i] = np.sqrt(np.mean(frame**2) + 1e-10)

        rms_db = 20 * np.log10(rms_envelope + 1e-10)

        sliding_window = HOP_LENGTH * 2
        sliding_frames = max(1, int(sliding_window / (HOP_LENGTH // 2)))
        rms_activity = np.zeros_like(rms_envelope)
        for i in range(n_frames):
            start_f = max(0, i - sliding_frames // 2)
            end_f = min(n_frames, i + sliding_frames // 2 + 1)
            window = rms_envelope[start_f:end_f]
            rms_activity[i] = np.mean(window)

        peak_rms = np.max(rms_envelope)

        release_ms_low = 30.0
        release_ms_high = 300.0
        release_gamma_low = np.exp(-1000.0 / (release_ms_low * sr / HOP_LENGTH + 1e-10))
        release_gamma_high = np.exp(-1000.0 / (release_ms_high * sr / HOP_LENGTH + 1e-10))

        gain_db = np.zeros(n_frames)
        smoothed_gain_db = 0.0
        for i in range(n_frames):
            level = rms_db[i]
            over_db = level - threshold_db

            if over_db > knee_width / 2:
                reduction = over_db * (1.0 - 1.0 / ratio)
            elif over_db > -knee_width / 2:
                reduction = ((over_db + knee_width / 2) ** 2) / (2 * knee_width) * (1.0 - 1.0 / ratio)
            else:
                reduction = 0.0

            gain_db[i] = -reduction

            activity_norm = rms_activity[i] / (peak_rms + 1e-10)
            activity_norm = np.clip(activity_norm, 0.0, 1.0)
            release_gamma = release_gamma_low * (1.0 - activity_norm) + release_gamma_high * activity_norm

            if gain_db[i] < smoothed_gain_db:
                smoothed_gain_db = smoothed_gain_db * attack_gamma + gain_db[i] * (1 - attack_gamma)
            else:
                smoothed_gain_db = smoothed_gain_db * release_gamma + gain_db[i] * (1 - release_gamma)
            gain_db[i] = smoothed_gain_db

        gain_linear = 10 ** (gain_db / 20.0)

        result = np.zeros_like(data)
        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))
            result[start:end] += data[start:end] * gain_linear[i]

        overlap_count = np.zeros(len(data))
        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))
            overlap_count[start:end] += 1.0
        overlap_count[overlap_count < 1] = 1.0
        result /= overlap_count

        y[ch] = result.astype(y.dtype)

    return y


def _de_esser_improved(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _de_esser_improved(y, sr, amount)
        return y[0]

    nyq = sr / 2
    low_sib_hz, high_sib_hz = 4000, 8000
    if high_sib_hz >= nyq:
        high_sib_hz = nyq * 0.95
    sos_sibilance = butter(4, [low_sib_hz/nyq, high_sib_hz/nyq], btype='band', output='sos')
    sos_full = butter(4, [80/nyq, min(16000, nyq*0.95)/nyq], btype='band', output='sos')

    attack_gamma = np.exp(-1000.0 / (5.0 * sr / HOP_LENGTH + 1e-10))
    release_gamma = np.exp(-1000.0 / (50.0 * sr / HOP_LENGTH + 1e-10))

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)

        sibilance_band = sosfiltfilt(sos_sibilance, data)
        full_band = sosfiltfilt(sos_full, data)

        frame_len = HOP_LENGTH
        n_frames = (len(data) - frame_len) // (frame_len // 2) + 1
        if n_frames < 2:
            continue

        smoothed_gain = 0.0
        gain_envelope = np.ones(n_frames)
        sib_energy_history = np.zeros(20)
        history_idx = 0

        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))

            sib_rms = np.sqrt(np.mean(sibilance_band[start:end]**2) + 1e-10)
            full_rms = np.sqrt(np.mean(full_band[start:end]**2) + 1e-10)
            ratio_val = sib_rms / (full_rms + 1e-10)

            sib_energy_history[history_idx] = sib_rms
            history_idx = (history_idx + 1) % 20
            running_avg = np.mean(sib_energy_history) + 1e-10
            adaptive_threshold = (0.2 + running_avg * 1.5) * (1.0 - amount * 0.3)

            segment = sibilance_band[start:end]
            segment_fft = np.fft.rfft(segment)
            segment_freqs = np.fft.rfftfreq(len(segment), 1.0/sr)
            sib_mask = (segment_freqs >= low_sib_hz) & (segment_freqs <= high_sib_hz)
            sib_mag = np.abs(segment_fft)
            if np.any(sib_mask):
                peak_sib_idx = np.argmax(sib_mag * sib_mask)
                peak_sib_freq = segment_freqs[peak_sib_idx]
                bp_low = max(low_sib_hz, peak_sib_freq - 500)
                bp_high = min(high_sib_hz, peak_sib_freq + 500)
                sos_narrow = butter(4, [bp_low/nyq, bp_high/nyq], btype='band', output='sos')
                sib_band_narrow = sosfiltfilt(sos_narrow, data)
                sib_rms_narrow = np.sqrt(np.mean(sib_band_narrow[start:end]**2) + 1e-10)
                ratio_val = sib_rms_narrow / (full_rms + 1e-10)

            if ratio_val > adaptive_threshold:
                attenuation = 1.0 - (ratio_val - adaptive_threshold) * amount * 1.5
                attenuation = max(attenuation, 1.0 - amount * 0.6)
            else:
                attenuation = 1.0

            if attenuation < smoothed_gain:
                smoothed_gain = smoothed_gain * attack_gamma + attenuation * (1 - attack_gamma)
            else:
                smoothed_gain = smoothed_gain * release_gamma + attenuation * (1 - release_gamma)
            gain_envelope[i] = smoothed_gain

        result = np.zeros_like(data)
        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))
            result[start:end] += data[start:end] * gain_envelope[i]

        overlap_count = np.zeros(len(data))
        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))
            overlap_count[start:end] += 1.0
        overlap_count[overlap_count < 1] = 1.0
        result /= overlap_count

        y[ch] = result.astype(y.dtype)

    return y


def _vocal_spatial(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_spatial(y, sr, amount)
        return y[0]

    delay_samples = int(0.015 * sr)
    decay = 0.3 * amount

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)

        delayed = np.zeros_like(data)
        if delay_samples < len(data):
            delayed[delay_samples:] = data[:-delay_samples] * decay

        reverb_len = min(int(0.1 * sr), len(data))
        reverb_tail = np.zeros(reverb_len)
        for i in range(1, reverb_len):
            reverb_tail[i] = data[i] * 0.3 + reverb_tail[i-1] * 0.7
        reverb_tail *= decay * 0.5

        wet = delayed
        wet[:reverb_len] += reverb_tail * amount

        mix = data * (1.0 - amount * 0.4) + wet * amount * 0.4
        peak = np.max(np.abs(mix))
        if peak > 0.99:
            mix *= 0.99 / peak

        y[ch] = mix.astype(y.dtype)

    return y


def _vocal_warmth(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _vocal_warmth(y, sr, amount)
        return y[0]

    nyq = sr / 2
    sos_warm = butter(4, [200/nyq, min(800, nyq*0.95)/nyq], btype='band', output='sos')

    for ch in range(y.shape[0]):
        dry = y[ch].astype(np.float64)

        warm_band = sosfiltfilt(sos_warm, dry)

        drive = 1.0 + amount * 2.0
        saturated = np.tanh(warm_band * drive) / np.tanh(drive)

        harmonic = saturated - warm_band * 0.3
        harmonic = np.tanh(harmonic * 1.5) * 0.5

        mix = dry + harmonic * amount * 0.3
        peak = np.max(np.abs(mix))
        if peak > 0.99:
            mix *= 0.99 / peak

        y[ch] = mix.astype(y.dtype)

    return y


def _instrument_stereo_enhance(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        return y
    if y.shape[0] < 2:
        return y

    mid = (y[0].astype(np.float64) + y[1].astype(np.float64)) * 0.5
    side = (y[0].astype(np.float64) - y[1].astype(np.float64)) * 0.5

    side_gain = 1.0 + amount * 1.5
    side *= side_gain

    new_left = mid + side
    new_right = mid - side

    peak_l = np.max(np.abs(new_left))
    peak_r = np.max(np.abs(new_right))
    peak = max(peak_l, peak_r)
    if peak > 0.99:
        new_left *= 0.99 / peak
        new_right *= 0.99 / peak

    y[0] = new_left.astype(y.dtype)
    y[1] = new_right.astype(y.dtype)

    return y


def _mastering_standard(y, sr):
    nyq = sr / 2

    sos_hp = butter(4, 20 / nyq, btype='high', output='sos')
    y = sosfiltfilt(sos_hp, y, axis=-1)

    sos_presence = butter(4, [3000/nyq, min(4000, nyq*0.95)/nyq], btype='band', output='sos')
    presence_band = sosfiltfilt(sos_presence, y, axis=-1)
    y = y.astype(np.float64) + presence_band * 0.06

    peak = np.max(np.abs(y))
    if peak > 0.99:
        y *= 0.99 / peak

    return y


def _mastering_powerful(y, sr):
    nyq = sr / 2

    sos_hp = butter(4, 20 / nyq, btype='high', output='sos')
    y = sosfiltfilt(sos_hp, y, axis=-1)

    sos_bass = butter(4, [60/nyq, min(100, nyq*0.95)/nyq], btype='band', output='sos')
    bass_band = sosfiltfilt(sos_bass, y, axis=-1)
    y = y.astype(np.float64) + bass_band * 0.25

    sos_low_mid = butter(4, [200/nyq, min(500, nyq*0.95)/nyq], btype='band', output='sos')
    low_mid_band = sosfiltfilt(sos_low_mid, y, axis=-1)
    y = y.astype(np.float64) + low_mid_band * 0.1

    sos_presence = butter(4, [3000/nyq, min(6000, nyq*0.95)/nyq], btype='band', output='sos')
    presence_band = sosfiltfilt(sos_presence, y, axis=-1)
    y = y.astype(np.float64) + presence_band * 0.1

    if y.ndim > 1 and y.shape[0] >= 2:
        mid = (y[0] + y[1]) * 0.5
        side = (y[0] - y[1]) * 0.5
        side *= 1.2
        new_left = mid + side
        new_right = mid - side
        peak = max(np.max(np.abs(new_left)), np.max(np.abs(new_right)))
        if peak > 0.99:
            new_left *= 0.99 / peak
            new_right *= 0.99 / peak
        y[0] = new_left.astype(y.dtype)
        y[1] = new_right.astype(y.dtype)

    peak = np.max(np.abs(y))
    if peak > 0.99:
        y *= 0.99 / peak

    return y


def _mastering_warm(y, sr):
    nyq = sr / 2

    sos_hp = butter(4, 20 / nyq, btype='high', output='sos')
    y = sosfiltfilt(sos_hp, y, axis=-1)

    sos_low_mid = butter(4, [200/nyq, min(500, nyq*0.95)/nyq], btype='band', output='sos')
    low_mid_band = sosfiltfilt(sos_low_mid, y, axis=-1)
    saturated = np.tanh(low_mid_band * 1.5) * 0.4
    y = y.astype(np.float64) + saturated * 0.2

    peak = np.max(np.abs(y))
    if peak > 0.99:
        y *= 0.99 / peak

    return y


def _mastering_adaptive(y, sr):
    nyq = sr / 2

    sos_hp = butter(4, 20 / nyq, btype='high', output='sos')
    y = sosfiltfilt(sos_hp, y, axis=-1)

    S = stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)
    magnitude = np.abs(S)
    n_bins = magnitude.shape[0]

    low_bin_end = int(250 / nyq * n_bins)
    mid_bin_end = int(4000 / nyq * n_bins)
    low_bin_end = min(low_bin_end, n_bins)
    mid_bin_end = min(mid_bin_end, n_bins)

    total_energy = np.sum(magnitude) + 1e-10
    low_energy = np.sum(magnitude[:low_bin_end, :]) / total_energy
    mid_energy = np.sum(magnitude[low_bin_end:mid_bin_end, :]) / total_energy
    high_energy = np.sum(magnitude[mid_bin_end:, :]) / total_energy

    if low_energy < 0.20:
        sos_low_shelf = butter(4, 250 / nyq, btype='low', output='sos')
        y = sosfiltfilt(sos_low_shelf, y, axis=-1)
        boost_gain = 1.0 + (0.20 - low_energy) * 0.5
        y = y.astype(np.float64) * boost_gain

    if high_energy < 0.15:
        sos_high_shelf = butter(4, 4000 / nyq, btype='high', output='sos')
        high_shelf = sosfiltfilt(sos_high_shelf, y, axis=-1)
        y = y.astype(np.float64) + high_shelf * (0.15 - high_energy) * 0.3

    if mid_energy > 0.60:
        sos_mid_cut = butter(4, [250/nyq, 4000/nyq], btype='band', output='sos')
        mid_band = sosfiltfilt(sos_mid_cut, y, axis=-1)
        y = y.astype(np.float64) - mid_band * (mid_energy - 0.60) * 0.2

    peak = np.max(np.abs(y))
    if peak > 0.99:
        y *= 0.99 / peak

    rms_val = np.sqrt(np.mean(y.astype(np.float64)**2))
    if rms_val > 1e-10:
        target_rms = 10 ** (-14.0 / 20.0)
        gain = target_rms / rms_val
        gain = np.clip(gain, 0.2, 5.0)
        y = (y.astype(np.float64) * gain).astype(y.dtype)

    return y


def _resonance_suppress(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _resonance_suppress(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        S = stft(data, n_fft=N_FFT, hop_length=HOP_LENGTH)
        magnitude = np.abs(S)
        phase = np.angle(S)
        n_bins, n_frames = magnitude.shape

        gain_map = np.ones_like(magnitude)
        for f in range(n_frames):
            for b in range(2, n_bins - 2):
                local_median = np.median(magnitude[b-2:b+3, f])
                if local_median > 1e-10 and magnitude[b, f] > 2.0 * local_median:
                    gain_map[b, f] = 1.0 - amount * 0.5

        smoothing_frames = max(2, int(0.02 * sr / HOP_LENGTH))
        kernel = np.ones(smoothing_frames) / smoothing_frames
        gain_map_smooth = np.zeros_like(gain_map)
        for b in range(n_bins):
            gain_map_smooth[b] = np.convolve(gain_map[b], kernel, mode='same')

        S_processed = magnitude * gain_map_smooth * np.exp(1j * phase)
        y_out = istft(S_processed, hop_length=HOP_LENGTH, length=len(data))
        if len(y_out) > len(data):
            y_out = y_out[:len(data)]
        elif len(y_out) < len(data):
            y_out = np.pad(y_out, (0, len(data) - len(y_out)))

        y[ch] = y_out.astype(y.dtype)

    return y


def _transient_aware_process(y, sr, amount):
    if amount <= 0:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        _transient_aware_process(y, sr, amount)
        return y[0]

    for ch in range(y.shape[0]):
        data = y[ch].astype(np.float64)
        S = stft(data, n_fft=N_FFT, hop_length=HOP_LENGTH)
        magnitude = np.abs(S)
        n_bins, n_frames = magnitude.shape

        if n_frames < 3:
            continue

        spectral_flux = np.zeros(n_frames)
        for f in range(1, n_frames):
            diff = magnitude[:, f] - magnitude[:, f-1]
            spectral_flux[f] = np.sum(np.maximum(diff, 0))

        flux_median = np.median(spectral_flux)
        flux_std = np.std(spectral_flux)
        flux_threshold = flux_median + 2.0 * flux_std

        transient_mask = spectral_flux > flux_threshold

        gain_envelope = np.ones(n_frames)
        for f in range(n_frames):
            if transient_mask[f]:
                gain_envelope[f] = 1.0 - amount * 0.5

        smoothing_kernel = np.ones(3) / 3
        gain_envelope = np.convolve(gain_envelope, smoothing_kernel, mode='same')

        result = np.zeros_like(data)
        frame_len = HOP_LENGTH
        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))
            result[start:end] += data[start:end] * gain_envelope[i]

        overlap_count = np.zeros(len(data))
        for i in range(n_frames):
            start = i * (frame_len // 2)
            end = min(start + frame_len, len(data))
            overlap_count[start:end] += 1.0
        overlap_count[overlap_count < 1] = 1.0
        result /= overlap_count

        y[ch] = result.astype(y.dtype)

    return y


def process_vocal_track(y, sr, params):
    speed = params.get('speed', 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)
    if params.get("declip", 0) > 0:
        y = _tanh_declip(y, params["declip"])

    if params.get("depop", 0) > 0:
        y = _diff_clamp_depop(y, sr, params["depop"])

    if params.get("formant_repair", 0) > 0:
        y = _vocal_formant_repair(y, sr, params["formant_repair"])

    if params.get("de_ess", 0) > 0:
        y = _apply_vocal_de_ess(y, sr, params["de_ess"])

    if params.get("de_esser_improved", 0) > 0:
        y = _de_esser_improved(y, sr, params["de_esser_improved"])

    if params.get("breath_enhance", 0) > 0:
        y = _vocal_breath_enhance(y, sr, params["breath_enhance"])

    if params.get("ai_repair", 0) > 0:
        from services.repair.repair_v2_4.hifi_ai_repair import apply_hifi_ai_repair
        from services.repair.repair_v2_2.music_type_detector import detect_music_type
        try:
            music_type, _, _ = detect_music_type(y, sr)
            y = apply_hifi_ai_repair(y, sr, params["ai_repair"], {})
            if "AI频谱修复" not in params.get("_issues", []):
                params["_issues"].append("AI频谱修复")
        except Exception:
            pass

    if params.get("ai_repair_adaptive", 0) > 0:
        y = _vocal_ai_repair_adaptive(y, sr, params["ai_repair_adaptive"])

    if params.get("bass_enhance", 0) > 0:
        from services.repair.repair_v3_0.core import _harmonic_bass_enhance
        try:
            y = _harmonic_bass_enhance(y, sr, params["bass_enhance"], "vocal")
        except Exception:
            pass

    if params.get("air_texture", 0) > 0:
        from services.repair.repair_v3_0.core import _air_texture_reconstruct
        try:
            y = _air_texture_reconstruct(y, sr, params["air_texture"], "vocal")
        except Exception:
            pass

    if params.get("resonance_suppress", 0) > 0:
        y = _resonance_suppress(y, sr, params["resonance_suppress"])

    if params.get("exciter_improved", 0) > 0:
        y = _vocal_exciter_improved(y, sr, params["exciter_improved"])

    if params.get("compressor", 0) > 0:
        y = _vocal_smart_compressor(y, sr, params["compressor"])

    if params.get("transient_aware", 0) > 0:
        y = _transient_aware_process(y, sr, params["transient_aware"])

    if params.get("warmth", 0) > 0:
        y = _vocal_warmth(y, sr, params["warmth"])

    if params.get("spatial", 0) > 0:
        y = _vocal_spatial(y, sr, params["spatial"])

    if params.get("loudness", 0) > 0:
        y = _adaptive_loudness_normalize(y, sr, -14.0)

    y = _soft_peak_limit(y, threshold=0.9)
    return y


def process_instrument_track(y, sr, params):
    speed = params.get('speed', 1.0)
    if speed != 1.0:
        from services.time_stretch import time_stretch_hifi
        y = time_stretch_hifi(y, sr, speed)
    if params.get("declip", 0) > 0:
        y = _tanh_declip(y, params["declip"])

    if params.get("depop", 0) > 0:
        y = _diff_clamp_depop(y, sr, params["depop"])

    if params.get("timbre_protect", 0) > 0:
        y = _instrument_timbre_protect(y, sr, params["timbre_protect"])

    if params.get("dynamic", 0) > 0:
        from services.repair.repair_v2_2.dynamics import apply_softness_v5
        try:
            y = apply_softness_v5(y, sr, params["dynamic"])
        except Exception:
            pass

    if params.get("noise_reduction", 0) > 0:
        from services.repair.repair_v2_2.spectral_group_a import apply_spectral_group_a
        try:
            y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, [], "instrumental")
        except Exception:
            pass

    if params.get("spatial", 0) > 0:
        from services.repair.repair_v2_2.spatial import apply_spatial_enhance_v6
        try:
            y = apply_spatial_enhance_v6(y, sr, params["spatial"], "instrumental")
        except Exception:
            pass

    if params.get("warmth", 0) > 0:
        from services.repair.repair_v2_2.filters import apply_warmth_v2
        try:
            y = apply_warmth_v2(y, sr, params["warmth"], "instrumental")
        except Exception:
            pass

    if params.get("stereo_enhance", 0) > 0:
        y = _instrument_stereo_enhance(y, sr, params["stereo_enhance"])

    if params.get("loudness", 0) > 0:
        y = _adaptive_loudness_normalize(y, sr, -14.0)

    y = _soft_peak_limit(y, threshold=0.9)
    return y


def mix_tracks(vocal, accompaniment, vocal_ratio=1.0, accompaniment_ratio=1.0):
    if vocal.ndim == 1:
        vocal = vocal.reshape(1, -1)
    if accompaniment.ndim == 1:
        accompaniment = accompaniment.reshape(1, -1)

    min_len = min(vocal.shape[1], accompaniment.shape[1])
    vocal = vocal[:, :min_len]
    accompaniment = accompaniment[:, :min_len]

    if vocal.shape[0] != accompaniment.shape[0]:
        if vocal.shape[0] == 1 and accompaniment.shape[0] == 2:
            vocal = np.repeat(vocal, 2, axis=0)
        elif vocal.shape[0] == 2 and accompaniment.shape[0] == 1:
            accompaniment = np.repeat(accompaniment, 2, axis=0)

    mixed = vocal * vocal_ratio + accompaniment * accompaniment_ratio
    peak = np.max(np.abs(mixed))
    if peak > 0.99:
        mixed *= 0.99 / peak

    return mixed


def _repair_single_track(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    if progress_callback:
        progress_callback(0.05, "v3.2 加载音频...")

    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)
    issues_found = ["单轨处理"]

    working_sr = DESKTOP_WORKING_SR

    from services.memory_guard import check_memory_before_repair, should_use_float32
    working_sr = check_memory_before_repair(
        n_samples=y.shape[1],
        n_channels=y.shape[0],
        sr=sr,
        working_sr=working_sr,
        algorithm_version="v3.2",
    )

    if should_use_float32(y.shape[1], y.shape[0]):
        y = y.astype(np.float32)

    if sr != working_sr:
        target_len = int(y.shape[1] * working_sr / sr)
        new_y = np.zeros((y.shape[0], target_len), dtype=y.dtype)
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            copy_len = min(target_len, len(resampled))
            new_y[ch, :copy_len] = resampled[:copy_len]
        y = new_y
        sr = working_sr

    gc.collect()

    single_params = dict(params)
    _SINGLE_KEY_MAP = {
        "de_clipping": "declip", "de_pop": "depop", "de_essing": "de_ess",
        "dynamic_range": "dynamic", "spatial_enhance": "spatial",
        "loudness_optimize": "loudness",
    }
    for _sk, _dk in _SINGLE_KEY_MAP.items():
        if _sk in single_params and _dk not in single_params:
            single_params[_dk] = single_params[_sk]
    single_params["_issues"] = issues_found

    if progress_callback:
        progress_callback(0.10, "v3.2 处理音频...")

    if single_params.get("declip", 0) > 0:
        y = _tanh_declip(y, single_params["declip"])

    if single_params.get("depop", 0) > 0:
        y = _diff_clamp_depop(y, sr, single_params["depop"])

    if single_params.get("formant_repair", 0) > 0:
        y = _vocal_formant_repair(y, sr, single_params["formant_repair"])

    if single_params.get("de_ess", 0) > 0:
        y = _apply_vocal_de_ess(y, sr, single_params["de_ess"])

    if single_params.get("de_esser_improved", 0) > 0:
        y = _de_esser_improved(y, sr, single_params["de_esser_improved"])

    if single_params.get("noise_reduction", 0) > 0:
        from services.repair.repair_v2_2.spectral_group_a import apply_spectral_group_a
        try:
            y = apply_spectral_group_a(y, sr, single_params, N_FFT, HOP_LENGTH, issues_found, "generic")
        except Exception:
            pass

    if single_params.get("ai_repair", 0) > 0:
        from services.repair.repair_v2_4.hifi_ai_repair import apply_hifi_ai_repair
        from services.repair.repair_v2_2.music_type_detector import detect_music_type
        try:
            music_type, _, _ = detect_music_type(y, sr)
            y = apply_hifi_ai_repair(y, sr, single_params["ai_repair"], {})
            if "AI频谱修复" not in issues_found:
                issues_found.append("AI频谱修复")
        except Exception:
            pass

    if single_params.get("ai_repair_adaptive", 0) > 0:
        y = _vocal_ai_repair_adaptive(y, sr, single_params["ai_repair_adaptive"])

    if single_params.get("breath_enhance", 0) > 0:
        y = _vocal_breath_enhance(y, sr, single_params["breath_enhance"])

    if single_params.get("bass_enhance", 0) > 0:
        from services.repair.repair_v3_0.core import _harmonic_bass_enhance
        try:
            y = _harmonic_bass_enhance(y, sr, single_params["bass_enhance"], "generic")
        except Exception:
            pass

    if single_params.get("air_texture", 0) > 0:
        from services.repair.repair_v3_0.core import _air_texture_reconstruct
        try:
            y = _air_texture_reconstruct(y, sr, single_params["air_texture"], "generic")
        except Exception:
            pass

    if single_params.get("resonance_suppress", 0) > 0:
        y = _resonance_suppress(y, sr, single_params["resonance_suppress"])

    if single_params.get("exciter_improved", 0) > 0:
        y = _vocal_exciter_improved(y, sr, single_params["exciter_improved"])

    if single_params.get("dynamic", 0) > 0:
        from services.repair.repair_v2_2.dynamics import apply_softness_v5
        try:
            y = apply_softness_v5(y, sr, single_params["dynamic"])
        except Exception:
            pass

    if single_params.get("compressor", 0) > 0:
        y = _vocal_smart_compressor(y, sr, single_params["compressor"])

    if single_params.get("transient_aware", 0) > 0:
        y = _transient_aware_process(y, sr, single_params["transient_aware"])

    if single_params.get("warmth", 0) > 0:
        y = _vocal_warmth(y, sr, single_params["warmth"])

    if single_params.get("spatial", 0) > 0:
        y = _vocal_spatial(y, sr, single_params["spatial"])

    if single_params.get("stereo_enhance", 0) > 0 and y.shape[0] >= 2:
        y = _instrument_stereo_enhance(y, sr, single_params["stereo_enhance"])

    if single_params.get("loudness", 0) > 0:
        y = _adaptive_loudness_normalize(y, sr, -14.0)

    if progress_callback:
        progress_callback(0.80, "v3.2 母带处理...")

    mastering_style = single_params.get("mastering_style", "standard")
    y = _soft_peak_limit(y, threshold=0.95)
    if mastering_style == "powerful":
        y = _mastering_powerful(y, working_sr)
        issues_found.append("强力母带")
    elif mastering_style == "warm":
        y = _mastering_warm(y, working_sr)
        issues_found.append("温暖母带")
    elif mastering_style == "adaptive":
        y = _mastering_adaptive(y, working_sr)
        issues_found.append("自适应母带")
    else:
        y = _mastering_standard(y, working_sr)
        issues_found.append("标准母带")

    if progress_callback:
        progress_callback(0.90, "v3.2 导出...")

    y = _soft_peak_limit(y, threshold=0.9)

    bit_depth = single_params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if y.dtype == np.float32:
        y = y.astype(np.float64)

    sf.write(output_path, y.T if y.ndim > 1 else y, working_sr, subtype=subtype)

    channels = y.shape[0] if y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, "v3.2 修复完成")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.2",
        "processing_mode": "single",
    }


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    processing_mode = params.get("processing_mode", "single")

    if processing_mode == "single":
        return _repair_single_track(input_path, output_path, params, progress_callback)

    vocal_path = params.get("vocal_path", input_path)
    accompaniment_path = params.get("accompaniment_path", input_path)

    if progress_callback:
        progress_callback(0.05, "v3.2 加载人声轨...")

    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    if vocal_y.ndim == 1:
        vocal_y = vocal_y.reshape(1, -1)

    if progress_callback:
        progress_callback(0.10, "v3.2 加载伴奏轨...")

    accompaniment_y, accompaniment_sr = load_audio_with_fallback(accompaniment_path, sr=None, mono=False)
    if accompaniment_y.ndim == 1:
        accompaniment_y = accompaniment_y.reshape(1, -1)

    original_duration = round(max(vocal_y.shape[1] / vocal_sr, accompaniment_y.shape[1] / accompaniment_sr), 2)
    issues_found = ["双轨处理"]

    working_sr = DESKTOP_WORKING_SR

    from services.memory_guard import check_memory_before_repair, should_use_float32
    vocal_samples = vocal_y.shape[1]
    vocal_channels = vocal_y.shape[0]
    working_sr = check_memory_before_repair(
        n_samples=vocal_samples,
        n_channels=vocal_channels,
        sr=vocal_sr,
        working_sr=working_sr,
        algorithm_version="v3.2",
    )

    if should_use_float32(vocal_samples, vocal_channels):
        vocal_y = vocal_y.astype(np.float32)
        accompaniment_y = accompaniment_y.astype(np.float32)

    if vocal_sr != working_sr:
        target_len = int(vocal_y.shape[1] * working_sr / vocal_sr)
        new_vocal_y = np.zeros((vocal_y.shape[0], target_len), dtype=vocal_y.dtype)
        for ch in range(vocal_y.shape[0]):
            resampled = resample_poly(vocal_y[ch], working_sr, vocal_sr)
            copy_len = min(target_len, len(resampled))
            new_vocal_y[ch, :copy_len] = resampled[:copy_len]
        vocal_y = new_vocal_y
        vocal_sr = working_sr

    if accompaniment_sr != working_sr:
        target_len = int(accompaniment_y.shape[1] * working_sr / accompaniment_sr)
        new_acc_y = np.zeros((accompaniment_y.shape[0], target_len), dtype=accompaniment_y.dtype)
        for ch in range(accompaniment_y.shape[0]):
            resampled = resample_poly(accompaniment_y[ch], working_sr, accompaniment_sr)
            copy_len = min(target_len, len(resampled))
            new_acc_y[ch, :copy_len] = resampled[:copy_len]
        accompaniment_y = new_acc_y
        accompaniment_sr = working_sr

    gc.collect()

    vocal_params = params.get("vocal_params", {}).copy()
    vocal_params["_issues"] = issues_found

    inst_params = params.get("inst_params", {}).copy()
    inst_params["_issues"] = issues_found

    for shared_key in ("speed",):
        if shared_key in params:
            vocal_params[shared_key] = params[shared_key]
            inst_params[shared_key] = params[shared_key]

    if progress_callback:
        progress_callback(0.20, "v3.2 处理人声轨...")

    vocal_y = process_vocal_track(vocal_y, vocal_sr, vocal_params)
    issues_found.append("人声处理完成")

    if progress_callback:
        progress_callback(0.50, "v3.2 处理伴奏轨...")

    accompaniment_y = process_instrument_track(accompaniment_y, accompaniment_sr, inst_params)
    issues_found.append("伴奏处理完成")

    gc.collect()

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if progress_callback:
        progress_callback(0.70, "v3.2 保存人声修复结果...")

    vocal_output_path = params.get("vocal_output_path")
    if vocal_output_path:
        vocal_out = _soft_peak_limit(vocal_y, threshold=0.9)
        if vocal_out.dtype == np.float32:
            vocal_out = vocal_out.astype(np.float64)
        sf.write(vocal_output_path, vocal_out.T if vocal_out.ndim > 1 else vocal_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.75, "v3.2 保存伴奏修复结果...")

    accompaniment_output_path = params.get("accompaniment_output_path")
    if accompaniment_output_path:
        acc_out = _soft_peak_limit(accompaniment_y, threshold=0.9)
        if acc_out.dtype == np.float32:
            acc_out = acc_out.astype(np.float64)
        sf.write(accompaniment_output_path, acc_out.T if acc_out.ndim > 1 else acc_out, working_sr, subtype=subtype)

    auto_mix = params.get("auto_mix", True)

    if auto_mix:
        if progress_callback:
            progress_callback(0.80, "v3.2 混音...")

        vocal_ratio = params.get("vocal_ratio", 1.0)
        accompaniment_ratio = params.get("accompaniment_ratio", 1.0)
        mixed = mix_tracks(vocal_y, accompaniment_y, vocal_ratio, accompaniment_ratio)

        issues_found.append("混音完成")

        if progress_callback:
            progress_callback(0.85, "v3.2 母带处理...")

        mastering_style = params.get("mastering_style", "standard")
        mixed = _soft_peak_limit(mixed, threshold=0.95)
        if mastering_style == "powerful":
            mixed = _mastering_powerful(mixed, working_sr)
            issues_found.append("强力母带")
        elif mastering_style == "warm":
            mixed = _mastering_warm(mixed, working_sr)
            issues_found.append("温暖母带")
        elif mastering_style == "adaptive":
            mixed = _mastering_adaptive(mixed, working_sr)
            issues_found.append("自适应母带")
        else:
            mixed = _mastering_standard(mixed, working_sr)
            issues_found.append("标准母带")

        if progress_callback:
            progress_callback(0.90, "v3.2 导出...")

        mixed = _soft_peak_limit(mixed, threshold=0.9)

        if mixed.dtype == np.float32:
            mixed = mixed.astype(np.float64)

        sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, working_sr, subtype=subtype)

        channels = mixed.shape[0] if mixed.ndim > 1 else 1
    else:
        if progress_callback:
            progress_callback(0.90, "v3.2 导出...")
        sf.write(output_path, vocal_y.T if vocal_y.ndim > 1 else vocal_y, working_sr, subtype=subtype)
        channels = vocal_y.shape[0] if vocal_y.ndim > 1 else 1

    if progress_callback:
        progress_callback(1.0, "v3.2 修复完成")

    result = {
        "issues_found": issues_found,
        "original_sample_rate": vocal_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": channels,
        "algorithm_version": "v3.2",
        "processing_mode": "dual",
    }
    if vocal_output_path:
        result["vocal_output_path"] = vocal_output_path
    if accompaniment_output_path:
        result["accompaniment_output_path"] = accompaniment_output_path
    return result