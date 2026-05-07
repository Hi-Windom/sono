import numpy as np
import librosa
import soundfile as sf
from services.audio_loader import load_audio_with_fallback

def detect_ai_audio(audio_path: str, progress_callback=None) -> dict:
    y, sr = load_audio_with_fallback(audio_path, sr=None, mono=True)

    # 不再立即更新步骤，让 API 端点设置的初始步骤保持更长时间
    # 第一个有意义的更新在 0.15 进度时

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    S_power = S ** 2

    if progress_callback:
        progress_callback(0.15, "v1.0 计算频谱平坦度...")

    spectral_flatness = float(np.mean(librosa.feature.spectral_flatness(y=y, S=S)))

    if progress_callback:
        progress_callback(0.25, "v1.0 计算频谱质心...")

    spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr, S=S)
    centroid_mean = float(np.mean(spectral_centroids))
    centroid_std = float(np.std(spectral_centroids))

    if progress_callback:
        progress_callback(0.35, "v1.0 计算MFCC特征...")

    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_delta = librosa.feature.delta(mfccs)
    mfcc_variability = float(np.mean(np.std(mfcc_delta, axis=1)))

    if progress_callback:
        progress_callback(0.45, "v1.0 计算频谱熵...")

    S_norm = S_power / (np.sum(S_power, axis=0, keepdims=True) + 1e-10)
    spectral_entropy = float(np.mean(-np.sum(S_norm * np.log2(S_norm + 1e-10), axis=0)) / np.log2(S.shape[0]))

    if progress_callback:
        progress_callback(0.55, "v1.0 分析动态范围...")

    rms = librosa.feature.rms(y=y)
    dynamic_range = float(np.percentile(rms, 95) - np.percentile(rms, 5))

    if progress_callback:
        progress_callback(0.65, "v1.0 计算音高变化...")

    f0, voiced_flag, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'), sr=sr)
    voiced_f0 = f0[voiced_flag] if f0 is not None else np.array([])
    pitch_variability = float(np.std(voiced_f0) / (np.mean(voiced_f0) + 1e-10)) if len(voiced_f0) > 0 else 0

    if progress_callback:
        progress_callback(0.75, "v1.0 分析微节奏一致性...")

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    if len(onset_frames) > 2:
        onset_intervals = np.diff(onset_frames)
        micro_rhythm_consistency = float(1.0 - np.std(onset_intervals) / (np.mean(onset_intervals) + 1e-10))
    else:
        micro_rhythm_consistency = 0.5

    if progress_callback:
        progress_callback(0.85, "v1.0 分析高频衰减特征...")

    spec_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, S=S)
    high_freq_attenuation = float(np.mean(spec_rolloff) / (sr / 2))

    if progress_callback:
        progress_callback(0.90, "v1.0 分析时域规律性...")

    env = np.abs(librosa.effects.harmonic(y))
    env_frames = librosa.util.frame(env, frame_length=2048, hop_length=512)
    env_means = np.mean(env_frames, axis=0)
    temporal_regularity = float(1.0 - np.std(np.diff(env_means)) / (np.mean(np.abs(np.diff(env_means))) + 1e-10))

    if progress_callback:
        progress_callback(0.95, "v1.0 计算综合评分...")

    score = 0.0
    reasons = []

    if spectral_flatness > 0.15:
        score += 0.12
        reasons.append("频谱过于平坦")
    if spectral_entropy > 0.7:
        score += 0.10
        reasons.append("频谱熵异常高")
    if mfcc_variability < 1.5:
        score += 0.10
        reasons.append("MFCC变化过小")
    if micro_rhythm_consistency > 0.8:
        score += 0.10
        reasons.append("微节奏过于一致")
    if pitch_variability < 0.05:
        score += 0.08
        reasons.append("音高变化过小")
    if high_freq_attenuation < 0.3:
        score += 0.08
        reasons.append("高频衰减不自然")
    if temporal_regularity > 0.75:
        score += 0.08
        reasons.append("时域过于规律")
    if dynamic_range < 0.02:
        score += 0.06
        reasons.append("动态范围过窄")
    if centroid_std < 500:
        score += 0.05
        reasons.append("频谱质心变化过小")

    confidence = min(0.95, score / 0.77)
    is_ai = confidence > 0.5

    if progress_callback:
        progress_callback(1.0, "v1.0 检测完成")

    return {
        "is_ai_generated": is_ai,
        "confidence": round(confidence, 4),
        "ai_probability": round(confidence, 4),
        "reasons": reasons[:6],
        "features": {
            "spectral_flatness": round(spectral_flatness, 4),
            "spectral_entropy": round(spectral_entropy, 4),
            "mfcc_variability": round(mfcc_variability, 4),
            "micro_rhythm_consistency": round(micro_rhythm_consistency, 4),
            "pitch_variability": round(pitch_variability, 4),
            "high_freq_attenuation": round(high_freq_attenuation, 4),
            "temporal_regularity": round(temporal_regularity, 4),
            "dynamic_range": round(dynamic_range, 4),
            "spectral_centroid_mean": round(centroid_mean, 2),
            "spectral_centroid_std": round(centroid_std, 2),
        },
        "sample_rate": sr,
        "duration": round(len(y) / sr, 2),
    }
