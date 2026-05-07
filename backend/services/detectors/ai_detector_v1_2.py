import numpy as np
from services.audio_loader import load_audio_with_fallback
from services.librosa_compat import (
    stft,
    spectral_flatness,
    spectral_centroid,
    spectral_bandwidth,
    spectral_rolloff,
    chroma_stft,
    zero_crossing_rate,
    rms,
    mfcc,
    delta,
    onset_strength,
    onset_detect,
    harmonic,
    frame,
    pyin,
    note_to_hz,
    hpss,
)

MAX_PITCH_DURATION = 30

def _extract_spectral(y, sr):
    S = np.abs(stft(y, n_fft=4096, hop_length=1024))
    S_power = S ** 2
    S_norm = S_power / (np.sum(S_power, axis=0, keepdims=True) + 1e-10)
    log_S = np.log(S_power + 1e-10)

    spectral_flatness_val = float(np.mean(spectral_flatness(y=y, S=S)))
    spectral_centroids = spectral_centroid(y=y, sr=sr, S=S)
    centroid_mean = float(np.mean(spectral_centroids))
    centroid_std = float(np.std(spectral_centroids))
    centroid_cv = float(np.std(spectral_centroids) / (np.mean(spectral_centroids) + 1e-10))

    spectral_bandwidths = spectral_bandwidth(y=y, sr=sr, S=S)
    bandwidth_mean = float(np.mean(spectral_bandwidths))
    bandwidth_var = float(np.var(spectral_bandwidths))
    bandwidth_cv = float(np.std(spectral_bandwidths) / (np.mean(spectral_bandwidths) + 1e-10))

    spectral_entropy = float(np.mean(-np.sum(S_norm * np.log2(S_norm + 1e-10), axis=0)) / np.log2(S.shape[0]))
    log_S_var = float(np.mean(np.var(log_S, axis=1)))

    spec_rolloff = spectral_rolloff(y=y, sr=sr, S=S)
    high_freq_attenuation = float(np.mean(spec_rolloff) / (sr / 2))
    rolloff_cv = float(np.std(spec_rolloff) / (np.mean(spec_rolloff) + 1e-10))

    chroma = chroma_stft(y=y, sr=sr, S=S)
    chroma_var = float(np.mean(np.std(chroma, axis=1)))
    chroma_mean = float(np.mean(chroma))

    zero_crossings = zero_crossing_rate(y)
    zcr_mean = float(np.mean(zero_crossings))
    zcr_std = float(np.std(zero_crossings))

    rms_val = rms(y=y)
    rms_mean = float(np.mean(rms_val))
    rms_std = float(np.std(rms_val))
    rms_cv = float(rms_std / (rms_mean + 1e-10))

    S_sample = S[:, ::max(1, S.shape[1]//100)]
    if S_sample.shape[1] > 1:
        spec_corr_matrix = np.corrcoef(S_sample.T)
        spec_corr = float(np.mean(spec_corr_matrix[np.triu_indices_from(spec_corr_matrix, k=1)]))
    else:
        spec_corr = 1.0

    return {
        "S": S,
        "S_power": S_power,
        "spectral_flatness": spectral_flatness_val,
        "spectral_entropy": spectral_entropy,
        "centroid_mean": centroid_mean,
        "centroid_std": centroid_std,
        "centroid_cv": centroid_cv,
        "bandwidth_mean": bandwidth_mean,
        "bandwidth_var": bandwidth_var,
        "bandwidth_cv": bandwidth_cv,
        "high_freq_attenuation": high_freq_attenuation,
        "rolloff_cv": rolloff_cv,
        "chroma_var": chroma_var,
        "chroma_mean": chroma_mean,
        "zcr_mean": zcr_mean,
        "zcr_std": zcr_std,
        "rms_mean": rms_mean,
        "rms_std": rms_std,
        "rms_cv": rms_cv,
        "log_S_var": log_S_var,
        "spectral_correlation": spec_corr,
    }


def _extract_mfcc(y, sr, S=None):
    if S is None:
        S = np.abs(stft(y, n_fft=4096, hop_length=1024))
    mfccs = mfcc(y=y, sr=sr, S=S, n_mfcc=20)
    mfcc_delta = delta(mfccs)
    mfcc_delta2 = delta(mfccs, order=2)
    mfcc_variability = float(np.mean(np.std(mfcc_delta, axis=1)))
    mfcc_accel = float(np.mean(np.std(mfcc_delta2, axis=1)))
    mfcc_mean = float(np.mean(np.abs(mfccs)))
    return {
        "mfcc_variability": mfcc_variability,
        "mfcc_acceleration": mfcc_accel,
        "mfcc_mean": mfcc_mean,
    }


def _extract_rhythm(y, sr):
    onset_env = onset_strength(y=y, sr=sr)
    onset_frames = onset_detect(onset_envelope=onset_env, sr=sr)
    if len(onset_frames) > 2:
        onset_intervals = np.diff(onset_frames)
        micro_rhythm_consistency = float(1.0 - np.std(onset_intervals) / (np.mean(onset_intervals) + 1e-10))
        onset_cv = float(np.std(onset_intervals) / (np.mean(onset_intervals) + 1e-10))
    else:
        micro_rhythm_consistency = 0.5
        onset_cv = 1.0

    env = np.abs(harmonic(y))
    env_frames = frame(env, frame_length=4096, hop_length=1024)
    env_means = np.mean(env_frames, axis=0)
    temporal_regularity = float(1.0 - np.std(np.diff(env_means)) / (np.mean(np.abs(np.diff(env_means))) + 1e-10))

    rms_val = rms(y=y)
    dynamic_range = float(np.percentile(rms_val, 95) - np.percentile(rms_val, 5))

    return {
        "micro_rhythm_consistency": micro_rhythm_consistency,
        "onset_cv": onset_cv,
        "temporal_regularity": temporal_regularity,
        "dynamic_range": dynamic_range,
    }


def _extract_pitch(y, sr):
    duration = len(y) / sr
    if duration > MAX_PITCH_DURATION:
        seg_len = int(MAX_PITCH_DURATION / 3 * sr)
        total_len = len(y)
        y_pitch = np.concatenate([y[:seg_len], y[total_len//3:total_len//3+seg_len], y[-seg_len:]])
    else:
        y_pitch = y

    f0, voiced_flag, _ = pyin(y_pitch, fmin=note_to_hz('C2'), fmax=note_to_hz('C7'), sr=sr)
    voiced_f0 = f0[voiced_flag] if f0 is not None else np.array([])
    pitch_variability = float(np.std(voiced_f0) / (np.mean(voiced_f0) + 1e-10)) if len(voiced_f0) > 0 else 0
    voiced_ratio = float(len(voiced_f0) / len(f0)) if f0 is not None and len(f0) > 0 else 0

    return {
        "pitch_variability": pitch_variability,
        "voiced_ratio": voiced_ratio,
    }


def _extract_harmonic(y):
    harmonic_out, percussive = hpss(y)
    harmonic_ratio = float(np.mean(np.abs(harmonic_out)) / (np.mean(np.abs(percussive)) + 1e-10))
    return {"harmonic_ratio": harmonic_ratio}


def detect_ai_audio(audio_path: str, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(audio_path, sr=None, mono=True)

    if progress_callback:
        progress_callback(0.05, "v1.2 分析频谱特征...")
    spectral = _extract_spectral(y, sr)
    if progress_callback:
        progress_callback(0.25, "v1.2 频谱特征分析完成...")

    if progress_callback:
        progress_callback(0.30, "v1.2 分析MFCC...")
    mfcc = _extract_mfcc(y, sr, spectral.get("S"))
    if progress_callback:
        progress_callback(0.45, "v1.2 MFCC深度分析完成...")

    if progress_callback:
        progress_callback(0.50, "v1.2 分析节奏...")
    rhythm = _extract_rhythm(y, sr)
    if progress_callback:
        progress_callback(0.65, "v1.2 节奏与时域分析完成...")

    if progress_callback:
        progress_callback(0.70, "v1.2 分析音高...")
    pitch = _extract_pitch(y, sr)
    if progress_callback:
        progress_callback(0.80, "v1.2 音高分析完成...")

    if progress_callback:
        progress_callback(0.82, "v1.2 分析谐波...")
    harmonic = _extract_harmonic(y)

    if progress_callback:
        progress_callback(0.85, "v1.2 计算综合评分...")

    features = {
        "spectral_flatness": round(spectral["spectral_flatness"], 4),
        "spectral_entropy": round(spectral["spectral_entropy"], 4),
        "mfcc_variability": round(mfcc["mfcc_variability"], 4),
        "micro_rhythm_consistency": round(rhythm["micro_rhythm_consistency"], 4),
        "pitch_variability": round(pitch["pitch_variability"], 4),
        "high_freq_attenuation": round(spectral["high_freq_attenuation"], 4),
        "temporal_regularity": round(rhythm["temporal_regularity"], 4),
        "dynamic_range": round(rhythm["dynamic_range"], 4),
        "spectral_centroid_mean": round(spectral["centroid_mean"], 2),
        "spectral_centroid_std": round(spectral["centroid_std"], 2),
        "spectral_bandwidth_mean": round(spectral["bandwidth_mean"], 2),
        "mfcc_acceleration": round(mfcc["mfcc_acceleration"], 4),
        "chroma_variability": round(spectral["chroma_var"], 4),
        "log_spectral_variance": round(spectral["log_S_var"], 4),
        "rms_mean": round(spectral["rms_mean"], 4),
        "harmonic_ratio": round(harmonic["harmonic_ratio"], 4),
        "zero_crossing_rate": round(spectral["zcr_mean"], 4),
        "spectral_correlation": round(spectral["spectral_correlation"], 4),
        "centroid_cv": round(spectral["centroid_cv"], 4),
        "rms_cv": round(spectral["rms_cv"], 4),
    }

    ai_score = 0.0
    human_score = 0.0
    ai_reasons = []
    human_reasons = []

    spec_corr = spectral["spectral_correlation"]
    if spec_corr > 0.92:
        human_score += 22
        human_reasons.append("频谱结构高度稳定")
    elif spec_corr < 0.45:
        ai_score += 20
        ai_reasons.append("频谱结构突变明显")
    else:
        human_score += 12 * spec_corr
        ai_score += 12 * (1 - spec_corr)

    centroid_cv = spectral["centroid_cv"]
    if centroid_cv < 0.25:
        human_score += 16
        human_reasons.append("频谱质心非常稳定")
    elif centroid_cv > 0.75:
        ai_score += 16
        ai_reasons.append("频谱质心突变")
    else:
        norm = (centroid_cv - 0.25) / 0.50
        ai_score += 14 * norm
        human_score += 14 * (1 - norm)

    rhythm_consistency = rhythm["micro_rhythm_consistency"]
    if rhythm_consistency > 0.88:
        human_score += 20
        human_reasons.append("节奏高度规律")
    elif rhythm_consistency < 0.35:
        ai_score += 18
        ai_reasons.append("节奏混乱")
    else:
        norm = max(0, (rhythm_consistency - 0.35) / 0.53)
        human_score += 16 * norm
        ai_score += 16 * (1 - norm)

    flatness = spectral["spectral_flatness"]
    if flatness < 0.0008:
        ai_score += 14
        ai_reasons.append("频谱异常平坦")
    elif flatness > 0.012:
        human_score += 10
        human_reasons.append("频谱自然起伏")
    else:
        norm = (0.012 - flatness) / 0.0112
        ai_score += 10 * norm
        human_score += 10 * (1 - norm)

    rms_cv = spectral["rms_cv"]
    if rms_cv < 0.35:
        human_score += 12
        human_reasons.append("响度稳定")
    elif rms_cv > 0.75:
        ai_score += 12
        ai_reasons.append("响度波动剧烈")
    else:
        norm = (rms_cv - 0.35) / 0.40
        ai_score += 10 * norm
        human_score += 10 * (1 - norm)

    temporal_reg = rhythm["temporal_regularity"]
    if temporal_reg > 0.65:
        human_score += 12
        human_reasons.append("时域包络平滑")
    elif temporal_reg < 0.15:
        ai_score += 10
        ai_reasons.append("时域包络突变")
    else:
        norm = max(0, (temporal_reg - 0.15) / 0.50)
        human_score += 10 * norm
        ai_score += 10 * (1 - norm)

    dyn_range = rhythm["dynamic_range"]
    if dyn_range < 0.04:
        ai_score += 10
        ai_reasons.append("动态范围过窄")
    elif dyn_range > 0.28:
        ai_score += 10
        ai_reasons.append("动态范围异常")
    elif 0.07 < dyn_range < 0.20:
        human_score += 10
        human_reasons.append("动态范围自然")
    else:
        if dyn_range <= 0.07:
            norm = dyn_range / 0.07
        else:
            norm = (0.28 - dyn_range) / 0.08
        human_score += 8 * norm
        ai_score += 8 * (1 - norm)

    entropy = spectral["spectral_entropy"]
    if entropy > 0.78:
        ai_score += 10
        ai_reasons.append("频谱熵过高")
    elif entropy < 0.42:
        human_score += 8
        human_reasons.append("频谱熵自然")
    else:
        norm = (entropy - 0.42) / 0.36
        ai_score += 8 * norm
        human_score += 8 * (1 - norm)

    mfcc_var = mfcc["mfcc_variability"]
    if mfcc_var > 2.8:
        ai_score += 10
        ai_reasons.append("MFCC突变")
    elif mfcc_var < 0.8:
        human_score += 8
        human_reasons.append("MFCC稳定")
    else:
        norm = (mfcc_var - 0.8) / 2.0
        ai_score += 8 * norm
        human_score += 8 * (1 - norm)

    hr_log = np.log1p(harmonic["harmonic_ratio"])
    if hr_log > 3.8:
        ai_score += 8
        ai_reasons.append("谐波比例异常")
    elif hr_log < 0.8:
        ai_score += 6
        ai_reasons.append("谐波比例过低")
    else:
        human_score += 6

    zcr_std = spectral["zcr_std"]
    if zcr_std > 0.055:
        ai_score += 6
        ai_reasons.append("过零率波动过大")
    elif zcr_std < 0.012:
        human_score += 5
        human_reasons.append("过零率稳定")
    else:
        norm = (zcr_std - 0.012) / 0.043
        ai_score += 5 * norm
        human_score += 5 * (1 - norm)

    total_points = ai_score + human_score
    if total_points > 0:
        ai_probability = ai_score / total_points
    else:
        ai_probability = 0.5

    human_probability = 1.0 - ai_probability
    ai_probability = max(0.05, min(0.95, ai_probability))
    human_probability = 1.0 - ai_probability

    if human_probability > 0.82:
        signature = "human"
        confidence = min(0.96, 0.6 + (human_probability - 0.82) * 1.5)
    elif ai_probability > 0.82:
        signature = "ai"
        confidence = min(0.96, 0.6 + (ai_probability - 0.82) * 1.5)
    elif human_probability > 0.50:
        signature = "mixed"
        confidence = min(0.72, 0.4 + total_points / 200)
        human_reasons.append("呈现混合特征")
    else:
        signature = "ai"
        confidence = min(0.76, 0.5 + (ai_probability - 0.50))

    is_ai = ai_probability > human_probability

    all_reasons = []
    if ai_reasons:
        all_reasons.extend(ai_reasons[:3])
    if human_reasons:
        all_reasons.extend(human_reasons[:3])

    if progress_callback:
        progress_callback(1.0, "v1.2 检测完成")

    return {
        "is_ai_generated": is_ai,
        "confidence": round(confidence, 4),
        "ai_probability": round(ai_probability, 4),
        "human_probability": round(human_probability, 4),
        "signature": signature,
        "reasons": all_reasons[:6],
        "features": features,
        "sample_rate": sr,
        "duration": round(len(y) / sr, 2),
    }