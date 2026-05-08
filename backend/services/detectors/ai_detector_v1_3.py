"""
AI 检测器 v1.3 - 基于拼接痕迹和频谱指纹分析
无需训练数据，基于音频物理原理检测

核心策略：
1. 拼接痕迹检测 - AI 生成音频往往在固定间隔（4s/8s）有拼接痕迹
2. 频谱指纹分析 - 检测频谱的过度平滑和周期性
"""

import numpy as np
from services.audio_loader import load_audio_with_fallback
from services.librosa_compat import (
    stft,
    mel_spectrogram,
    power_to_db,
    onset_strength,
    onset_detect,
)

# AI 常见拼接周期（秒）
AI_COMMON_PERIODS = [4.0, 8.0, 12.0, 16.0]


def _detect_splicing_artifacts(y, sr):
    """
    检测音频中的拼接痕迹
    AI 生成音频往往在固定长度处有周期性拼接痕迹

    Returns:
        dict: 包含周期性分数、相位不连续度等指标
    """
    hop_length = 512
    frame_length = 2048

    # 1. 计算短时能量包络
    S = np.abs(stft(y, n_fft=frame_length, hop_length=hop_length))
    rms = np.sqrt(np.mean(S**2, axis=0))

    # 2. 检测周期性突变 - 检查 AI 常见周期
    if len(rms) < 10:
        return {'periodicity_score': 0, 'phase_discontinuity': 0, 'splicing_score': 0}

    # 计算自相关
    rms_normalized = rms - np.mean(rms)
    correlation = np.correlate(rms_normalized, rms_normalized, mode='full')
    correlation = correlation[len(correlation)//2:]

    # 归一化
    if correlation[0] > 0:
        correlation = correlation / correlation[0]

    # 3. 在 AI 常见周期位置检测峰值
    period_scores = []
    for period_sec in AI_COMMON_PERIODS:
        period_frames = int(period_sec * sr / hop_length)
        if period_frames < len(correlation) and period_frames > 0:
            # 获取周期位置的相关系数
            score = correlation[period_frames]
            # 同时检查相邻位置（允许 ±10% 误差）
            nearby_scores = []
            for offset in range(-2, 3):
                idx = period_frames + offset
                if 0 < idx < len(correlation):
                    nearby_scores.append(correlation[idx])
            max_nearby = max(nearby_scores) if nearby_scores else score
            period_scores.append({
                'period': period_sec,
                'score': max_nearby,
                'frames': period_frames
            })

    # 4. 找出最强的周期性
    best_period = max(period_scores, key=lambda x: x['score']) if period_scores else {'score': 0}
    periodicity_score = max(0, best_period['score'])

    # 5. 相位连续性检测 - 检测频谱相位的跳变
    phase = np.angle(S)
    phase_diff = np.diff(phase, axis=1)
    # 归一化到 [-pi, pi]
    phase_diff = np.mod(phase_diff + np.pi, 2 * np.pi) - np.pi
    # 计算跳变强度（超过 pi/2 视为跳变）
    phase_jumps = np.abs(phase_diff) > np.pi / 2
    phase_discontinuity = np.mean(phase_jumps)

    # 6. 能量突变检测 - 拼接处往往有能量不连续
    rms_diff = np.diff(rms)
    # 检测异常大的变化
    rms_mean = np.mean(np.abs(rms_diff))
    rms_std = np.std(np.abs(rms_diff))
    if rms_std > 0:
        abnormal_jumps = np.abs(rms_diff) > (rms_mean + 2 * rms_std)
        energy_discontinuity = np.mean(abnormal_jumps)
    else:
        energy_discontinuity = 0

    # 7. 综合拼接痕迹分数
    # 高周期性 + 高相位不连续 + 高能量不连续 = AI 特征
    splicing_score = (
        periodicity_score * 0.4 +
        min(1.0, phase_discontinuity * 5) * 0.3 +  # 放大相位不连续的影响
        energy_discontinuity * 0.3
    )

    return {
        'periodicity_score': round(periodicity_score, 4),
        'phase_discontinuity': round(phase_discontinuity, 4),
        'energy_discontinuity': round(energy_discontinuity, 4),
        'best_period': best_period.get('period', 0),
        'splicing_score': round(splicing_score, 4),
    }


def _analyze_spectral_fingerprint(y, sr):
    """
    分析频谱"指纹" - 检测 AI 生成音频的频谱特征

    AI 生成音频的频谱特点：
    1. 时间轴上过度平滑（相邻帧过于相似）
    2. 频率轴上有固定模式
    3. 缺乏自然音频的微观随机性

    Returns:
        dict: 包含频谱平滑度、稳定性等指标
    """
    n_mels = 128
    hop_length = 512
    n_fft = 2048

    # 1. 计算 mel 频谱
    mel_spec = mel_spectrogram(y=y, sr=sr, n_mels=n_mels, hop_length=hop_length, n_fft=n_fft)
    log_mel = power_to_db(mel_spec, ref=np.max(mel_spec))

    if log_mel.shape[1] < 10:
        return {'smoothness_score': 0.5, 'stability_score': 0.5, 'fingerprint_score': 0.5}

    # 2. 时间轴平滑度分析
    # 计算相邻帧的相似度
    adjacent_similarities = []
    for i in range(min(200, log_mel.shape[1] - 1)):
        # 使用余弦相似度
        vec1 = log_mel[:, i]
        vec2 = log_mel[:, i + 1]
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 > 0 and norm2 > 0:
            sim = np.dot(vec1, vec2) / (norm1 * norm2)
            adjacent_similarities.append(sim)

    if not adjacent_similarities:
        adjacent_similarities = [0.5]

    mean_similarity = np.mean(adjacent_similarities)
    similarity_std = np.std(adjacent_similarities)

    # 高相似度 + 低方差 = 过度平滑（AI 特征）
    smoothness_score = mean_similarity * (1 - min(1.0, similarity_std * 5))

    # 3. 频谱稳定性分析 - 检查频谱是否随时间有自然变化
    # 计算每帧频谱的质心变化
    mel_mean = np.mean(log_mel, axis=0)
    mel_variance = np.var(log_mel, axis=1)

    # 时间轴上的方差变化（应该有自然的起伏）
    temporal_changes = np.abs(np.diff(mel_mean))
    mean_change = np.mean(temporal_changes)
    change_std = np.std(temporal_changes)

    # AI 往往变化过于均匀（低方差）或过于稳定（低均值变化）
    if mean_change > 0:
        stability_ratio = change_std / mean_change
        # 高 ratio = 变化不均匀 = 人类特征
        stability_score = 1.0 - min(1.0, stability_ratio)
    else:
        stability_score = 1.0  # 完全稳定 = AI 特征

    # 4. 频谱熵分析 - 检测频谱的随机性
    # 对每帧计算频谱熵
    frame_entropies = []
    for i in range(log_mel.shape[1]):
        frame = log_mel[:, i]
        # 归一化为概率分布
        frame_norm = frame - np.min(frame)
        if np.sum(frame_norm) > 0:
            frame_prob = frame_norm / np.sum(frame_norm)
            # 计算熵
            entropy = -np.sum(frame_prob * np.log2(frame_prob + 1e-10))
            frame_entropies.append(entropy)

    if frame_entropies:
        entropy_mean = np.mean(frame_entropies)
        entropy_std = np.std(frame_entropies)
        # 熵值过于稳定 = AI 特征
        entropy_consistency = 1.0 - min(1.0, entropy_std / (entropy_mean + 1e-10))
    else:
        entropy_consistency = 0.5

    # 5. 综合频谱指纹分数
    # 高平滑度 + 高稳定性 + 高熵一致性 = AI 特征
    fingerprint_score = (
        smoothness_score * 0.4 +
        stability_score * 0.3 +
        entropy_consistency * 0.3
    )

    return {
        'adjacent_similarity': round(mean_similarity, 4),
        'similarity_std': round(similarity_std, 4),
        'smoothness_score': round(smoothness_score, 4),
        'stability_score': round(stability_score, 4),
        'entropy_consistency': round(entropy_consistency, 4),
        'fingerprint_score': round(fingerprint_score, 4),
    }


def _analyze_rhythm_patterns(y, sr):
    """
    分析节奏模式 - AI 生成音频的节奏往往过于完美

    Returns:
        dict: 节奏规律性指标
    """
    hop_length = 512

    # 1. 计算 onset 强度
    onset_env = onset_strength(y=y, sr=sr, hop_length=hop_length)
    onset_frames = onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop_length)

    if len(onset_frames) < 3:
        return {'rhythm_regularity': 0.5, 'rhythm_score': 0.5}

    # 2. 计算 onset 间隔
    intervals = np.diff(onset_frames)

    # 3. 分析间隔的规律性
    interval_mean = np.mean(intervals)
    interval_std = np.std(intervals)

    if interval_mean > 0:
        # 变异系数 - 越低越规律
        cv = interval_std / interval_mean
        # 归一化到 0-1，高规律性 = AI 特征
        rhythm_regularity = 1.0 - min(1.0, cv)
    else:
        rhythm_regularity = 1.0

    # 4. 检测节拍对齐
    # AI 往往有完美的节拍对齐
    if len(intervals) > 1:
        # 计算间隔的间隔（二阶差分）
        interval_diff = np.diff(intervals)
        # 二阶差分应该小（规律变化）或大（人类的不规律）
        second_order_variance = np.var(interval_diff) / (np.mean(intervals) ** 2 + 1e-10)
        # 非常小的二阶方差 = 过于规律 = AI
        beat_alignment = 1.0 - min(1.0, second_order_variance * 10)
    else:
        beat_alignment = 0.5

    # 5. 综合节奏分数
    rhythm_score = (rhythm_regularity * 0.6 + beat_alignment * 0.4)

    return {
        'rhythm_regularity': round(rhythm_regularity, 4),
        'beat_alignment': round(beat_alignment, 4),
        'rhythm_score': round(rhythm_score, 4),
    }


def detect_ai_audio(audio_path: str, progress_callback=None) -> dict:
    """
    v1.3 AI 检测主函数
    结合拼接痕迹检测和频谱指纹分析

    Args:
        audio_path: 音频文件路径
        progress_callback: 进度回调函数

    Returns:
        dict: 检测结果
    """
    # 加载音频
    y, sr = load_audio_with_fallback(audio_path, sr=None, mono=True)

    if progress_callback:
        progress_callback(0.1, "v1.3 分析拼接痕迹...")

    # 1. 拼接痕迹检测
    splicing = _detect_splicing_artifacts(y, sr)

    if progress_callback:
        progress_callback(0.4, "v1.3 分析频谱指纹...")

    # 2. 频谱指纹分析
    fingerprint = _analyze_spectral_fingerprint(y, sr)

    if progress_callback:
        progress_callback(0.7, "v1.3 分析节奏模式...")

    # 3. 节奏模式分析
    rhythm = _analyze_rhythm_patterns(y, sr)

    if progress_callback:
        progress_callback(0.9, "v1.3 综合判断...")

    # 4. 综合判断
    # 三个维度的分数都高 = AI 特征
    splicing_score = splicing['splicing_score']
    fingerprint_score = fingerprint['fingerprint_score']
    rhythm_score = rhythm['rhythm_score']

    # 加权综合（拼接痕迹最重要，因为是最直接的 AI 特征）
    ai_score = (
        splicing_score * 0.45 +
        fingerprint_score * 0.35 +
        rhythm_score * 0.20
    )

    # 转换为概率（使用 sigmoid 进行校准）
    # 阈值 0.5 对应概率 0.5
    ai_probability = 1.0 / (1.0 + np.exp(-(ai_score - 0.5) * 6))
    ai_probability = max(0.05, min(0.95, ai_probability))
    human_probability = 1.0 - ai_probability

    # 判定逻辑
    is_ai = ai_probability > 0.5

    if human_probability > 0.75:
        signature = "human"
        confidence = min(0.95, 0.5 + (human_probability - 0.5) * 1.5)
    elif ai_probability > 0.75:
        signature = "ai"
        confidence = min(0.95, 0.5 + (ai_probability - 0.5) * 1.5)
    elif ai_probability > 0.55:
        signature = "likely_ai"
        confidence = 0.55 + (ai_probability - 0.55)
    elif human_probability > 0.55:
        signature = "likely_human"
        confidence = 0.55 + (human_probability - 0.55)
    else:
        signature = "uncertain"
        confidence = 0.5

    # 生成原因
    reasons = []
    if splicing_score > 0.5:
        reasons.append(f"检测到周期性拼接痕迹({splicing['best_period']}s周期)")
    if fingerprint['smoothness_score'] > 0.7:
        reasons.append("频谱过度平滑")
    if rhythm['rhythm_regularity'] > 0.85:
        reasons.append("节奏过于规律")
    if splicing['phase_discontinuity'] > 0.1:
        reasons.append("相位不连续")

    if not reasons:
        if is_ai:
            reasons.append("综合特征偏向AI生成")
        else:
            reasons.append("综合特征偏向人类创作")

    if progress_callback:
        progress_callback(1.0, "v1.3 检测完成")

    return {
        "is_ai_generated": is_ai,
        "confidence": round(confidence, 4),
        "ai_probability": round(ai_probability, 4),
        "human_probability": round(human_probability, 4),
        "signature": signature,
        "reasons": reasons[:4],
        "features": {
            # 拼接痕迹特征
            "splicing_periodicity": splicing['periodicity_score'],
            "splicing_phase_disc": splicing['phase_discontinuity'],
            "splicing_energy_disc": splicing['energy_discontinuity'],
            "splicing_best_period": splicing['best_period'],
            "splicing_score": splicing['splicing_score'],
            # 频谱指纹特征
            "spectral_similarity": fingerprint['adjacent_similarity'],
            "spectral_smoothness": fingerprint['smoothness_score'],
            "spectral_stability": fingerprint['stability_score'],
            "spectral_entropy_cons": fingerprint['entropy_consistency'],
            "fingerprint_score": fingerprint['fingerprint_score'],
            # 节奏特征
            "rhythm_regularity": rhythm['rhythm_regularity'],
            "beat_alignment": rhythm['beat_alignment'],
            "rhythm_score": rhythm['rhythm_score'],
            # 综合
            "combined_ai_score": round(ai_score, 4),
        },
        "sample_rate": sr,
        "duration": round(len(y) / sr, 2),
        "version": "v1.3",
    }
