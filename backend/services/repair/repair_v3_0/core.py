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

    result = data.astype(np.float64)
    for i in range(n_frames):
        start = i * hop
        end = start + frame_len
        if end > len(result):
            break
        s_gain = sibilance_smooth[i] if i < len(sibilance_smooth) else 1.0
        p_gain = pop_smooth[i] if i < len(pop_smooth) else 1.0
        combined_gain = (s_gain + p_gain) / 2
        result[start:end] *= combined_gain

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


def process_vocal_track(y, sr, params):
    if params.get("declip", 0) > 0:
        y = _tanh_declip(y, params["declip"])

    if params.get("depop", 0) > 0:
        y = _diff_clamp_depop(y, sr, params["depop"])

    if params.get("formant_repair", 0) > 0:
        y = _vocal_formant_repair(y, sr, params["formant_repair"])

    if params.get("de_ess", 0) > 0:
        y = _apply_vocal_de_ess(y, sr, params["de_ess"])

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

    if params.get("bass_enhance", 0) > 0:
        from services.repair.repair_v2_4.core import _harmonic_bass_enhance
        try:
            y = _harmonic_bass_enhance(y, sr, params["bass_enhance"], "vocal")
        except Exception:
            pass

    if params.get("air_texture", 0) > 0:
        from services.repair.repair_v2_4.core import _air_texture_reconstruct
        try:
            y = _air_texture_reconstruct(y, sr, params["air_texture"], "vocal")
        except Exception:
            pass

    if params.get("loudness", 0) > 0:
        y = _adaptive_loudness_normalize(y, sr, -14.0)

    y = _soft_peak_limit(y, threshold=0.9)
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


def process_instrument_track(y, sr, params):
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


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    vocal_path = params.get("vocal_path", input_path)
    accompaniment_path = params.get("accompaniment_path", input_path)

    if progress_callback:
        progress_callback(0.05, "v3.0 加载人声轨...")

    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    if vocal_y.ndim == 1:
        vocal_y = vocal_y.reshape(1, -1)

    if progress_callback:
        progress_callback(0.10, "v3.0 加载伴奏轨...")

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
        algorithm_version="v3.0",
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

    vocal_params = {k.replace("vocal_", ""): v for k, v in params.items() if k.startswith("vocal_")}
    vocal_params["_issues"] = issues_found

    inst_params = {k.replace("inst_", ""): v for k, v in params.items() if k.startswith("inst_")}
    inst_params["_issues"] = issues_found

    if progress_callback:
        progress_callback(0.20, "v3.0 处理人声轨...")

    vocal_y = process_vocal_track(vocal_y, vocal_sr, vocal_params)
    issues_found.append("人声处理完成")

    if progress_callback:
        progress_callback(0.50, "v3.0 处理伴奏轨...")

    accompaniment_y = process_instrument_track(accompaniment_y, accompaniment_sr, inst_params)
    issues_found.append("伴奏处理完成")

    gc.collect()

    bit_depth = params.get("bit_depth", 24)
    subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
    subtype = subtype_map.get(bit_depth, "PCM_24")

    if progress_callback:
        progress_callback(0.70, "v3.0 保存人声修复结果...")

    vocal_output_path = params.get("vocal_output_path")
    if vocal_output_path:
        vocal_out = _soft_peak_limit(vocal_y, threshold=0.9)
        if vocal_out.dtype == np.float32:
            vocal_out = vocal_out.astype(np.float64)
        sf.write(vocal_output_path, vocal_out.T if vocal_out.ndim > 1 else vocal_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.75, "v3.0 保存伴奏修复结果...")

    accompaniment_output_path = params.get("accompaniment_output_path")
    if accompaniment_output_path:
        acc_out = _soft_peak_limit(accompaniment_y, threshold=0.9)
        if acc_out.dtype == np.float32:
            acc_out = acc_out.astype(np.float64)
        sf.write(accompaniment_output_path, acc_out.T if acc_out.ndim > 1 else acc_out, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(0.80, "v3.0 混音...")

    vocal_ratio = params.get("vocal_ratio", 1.0)
    accompaniment_ratio = params.get("accompaniment_ratio", 1.0)
    mixed = mix_tracks(vocal_y, accompaniment_y, vocal_ratio, accompaniment_ratio)

    issues_found.append("混音完成")

    if progress_callback:
        progress_callback(0.90, "v3.0 导出...")

    mixed = _soft_peak_limit(mixed, threshold=0.9)

    if mixed.dtype == np.float32:
        mixed = mixed.astype(np.float64)

    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, working_sr, subtype=subtype)

    if progress_callback:
        progress_callback(1.0, "v3.0 修复完成")

    result = {
        "issues_found": issues_found,
        "original_sample_rate": vocal_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": bit_depth,
        "duration": original_duration,
        "channels": mixed.shape[0] if mixed.ndim > 1 else 1,
        "algorithm_version": "v3.0",
        "processing_mode": "dual",
    }
    if vocal_output_path:
        result["vocal_output_path"] = vocal_output_path
    if accompaniment_output_path:
        result["accompaniment_output_path"] = accompaniment_output_path
    return result
