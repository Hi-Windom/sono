#!/usr/bin/env python3
"""
AI音乐训练素材特征提取器
- 增量处理：只处理新增文件
- 断点续传：支持中断后恢复
- 分类存储：纯音乐(instrumental) vs 歌唱(vocal)
"""

import os
import sys
import json
import sqlite3
import hashlib
import numpy as np
import librosa
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from services.audio_loader import load_audio_with_fallback

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TRAINING_DIR

# 特征数据库路径
FEATURE_DB_PATH = os.path.join(os.path.dirname(TRAINING_DIR), "training_features.db")
FEATURE_CACHE_DIR = os.path.join(os.path.dirname(TRAINING_DIR), "training_features")
os.makedirs(FEATURE_CACHE_DIR, exist_ok=True)


def init_feature_db():
    """初始化特征数据库"""
    conn = sqlite3.connect(FEATURE_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_features (
            file_hash TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,  -- 'instrumental' 或 'vocal'
            file_size INTEGER,
            duration REAL,
            sample_rate INTEGER,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            feature_cache_path TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_type TEXT NOT NULL,
            feature_name TEXT NOT NULL,
            mean REAL,
            std REAL,
            median REAL,
            p10 REAL,  -- 10%分位数
            p90 REAL,  -- 90%分位数
            min_val REAL,
            max_val REAL,
            sample_count INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_type, feature_name)
        )
    """)
    conn.commit()
    conn.close()


def get_feature_db():
    """获取数据库连接"""
    conn = sqlite3.connect(FEATURE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_file_processed(file_hash: str) -> bool:
    """检查文件是否已处理"""
    conn = get_feature_db()
    row = conn.execute(
        "SELECT 1 FROM file_features WHERE file_hash = ?",
        (file_hash,)
    ).fetchone()
    conn.close()
    return row is not None


def detect_vocal_vs_instrumental(y: np.ndarray, sr: int) -> str:
    """
    检测是纯音乐还是歌唱作品
    基于：人声通常有特定的频谱特征和音高变化模式
    """
    # 提取音高
    f0, voiced_flag, _ = librosa.pyin(
        y, 
        fmin=librosa.note_to_hz('C2'),
        fmax=librosa.note_to_hz('C7'),
        sr=sr,
        frame_length=2048,
        hop_length=512
    )
    
    voiced_frames = f0[voiced_flag] if f0 is not None else np.array([])
    voiced_ratio = len(voiced_frames) / len(f0) if f0 is not None and len(f0) > 0 else 0
    
    # 提取频谱质心（人声通常在较高频率）
    spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)
    centroid_mean = np.mean(spectral_centroids)
    
    # 提取谐波比
    harmonic, percussive = librosa.effects.hpss(y)
    harmonic_ratio = np.mean(np.abs(harmonic)) / (np.mean(np.abs(percussive)) + 1e-10)
    
    # 简单启发式规则
    # 歌唱作品通常有：较高的voiced_ratio、适中的频谱质心、较高的谐波比
    vocal_score = 0
    
    if voiced_ratio > 0.4:  # 有较多有声音高帧
        vocal_score += 1
    if 1000 < centroid_mean < 4000:  # 人声典型频谱范围
        vocal_score += 1
    if harmonic_ratio > 2.0:  # 谐波丰富
        vocal_score += 1
    
    return 'vocal' if vocal_score >= 2 else 'instrumental'


def extract_all_features(y: np.ndarray, sr: int) -> Dict:
    """提取所有特征（复用v1.1的特征提取逻辑）"""
    features = {}
    
    # 基础频谱特征
    S = np.abs(librosa.stft(y, n_fft=4096, hop_length=1024))
    S_power = S ** 2
    
    # 1. 频谱平坦度
    features['spectral_flatness'] = float(np.mean(librosa.feature.spectral_flatness(S=S)))
    
    # 2. 频谱熵
    S_norm = S_power / (np.sum(S_power, axis=0, keepdims=True) + 1e-10)
    spectral_entropy = np.mean(-np.sum(S_norm * np.log2(S_norm + 1e-10), axis=0)) / np.log2(S.shape[0])
    features['spectral_entropy'] = float(spectral_entropy)
    
    # 3. 频谱质心
    spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr, S=S)
    features['spectral_centroid_mean'] = float(np.mean(spectral_centroids))
    features['spectral_centroid_std'] = float(np.std(spectral_centroids))
    features['spectral_centroid_cv'] = float(np.std(spectral_centroids) / (np.mean(spectral_centroids) + 1e-10))
    
    # 4. 频谱带宽
    spectral_bandwidths = librosa.feature.spectral_bandwidth(y=y, sr=sr, S=S)
    features['spectral_bandwidth_mean'] = float(np.mean(spectral_bandwidths))
    features['spectral_bandwidth_cv'] = float(np.std(spectral_bandwidths) / (np.mean(spectral_bandwidths) + 1e-10))
    
    # 5. 高频衰减
    spec_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, S=S)
    features['high_freq_attenuation'] = float(np.mean(spec_rolloff) / (sr / 2))
    features['rolloff_cv'] = float(np.std(spec_rolloff) / (np.mean(spec_rolloff) + 1e-10))
    
    # 6. MFCC特征
    mfccs = librosa.feature.mfcc(y=y, sr=sr, S=S, n_mfcc=20)
    mfcc_delta = librosa.feature.delta(mfccs)
    mfcc_delta2 = librosa.feature.delta(mfccs, order=2)
    features['mfcc_variability'] = float(np.mean(np.std(mfcc_delta, axis=1)))
    features['mfcc_acceleration'] = float(np.mean(np.std(mfcc_delta2, axis=1)))
    features['mfcc_mean'] = float(np.mean(np.abs(mfccs)))
    
    # 7. 和弦变化
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, S=S)
    features['chroma_variability'] = float(np.mean(np.std(chroma, axis=1)))
    features['chroma_mean'] = float(np.mean(chroma))
    
    # 8. 过零率
    zero_crossings = librosa.feature.zero_crossing_rate(y)
    features['zcr_mean'] = float(np.mean(zero_crossings))
    features['zcr_std'] = float(np.std(zero_crossings))
    
    # 9. RMS/响度
    rms = librosa.feature.rms(y=y)
    features['rms_mean'] = float(np.mean(rms))
    features['rms_std'] = float(np.std(rms))
    features['rms_cv'] = float(np.std(rms) / (np.mean(rms) + 1e-10))
    
    # 10. 对数谱方差
    log_S = np.log(S_power + 1e-10)
    features['log_spectral_variance'] = float(np.mean(np.var(log_S, axis=1)))
    
    # 11. 节奏特征
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    if len(onset_frames) > 2:
        onset_intervals = np.diff(onset_frames)
        features['micro_rhythm_consistency'] = float(1.0 - np.std(onset_intervals) / (np.mean(onset_intervals) + 1e-10))
        features['onset_cv'] = float(np.std(onset_intervals) / (np.mean(onset_intervals) + 1e-10))
    else:
        features['micro_rhythm_consistency'] = 0.5
        features['onset_cv'] = 1.0
    
    # 12. 时域规律性
    env = np.abs(librosa.effects.harmonic(y))
    env_frames = librosa.util.frame(env, frame_length=4096, hop_length=1024)
    env_means = np.mean(env_frames, axis=0)
    features['temporal_regularity'] = float(1.0 - np.std(np.diff(env_means)) / (np.mean(np.abs(np.diff(env_means))) + 1e-10))
    
    # 13. 动态范围
    features['dynamic_range'] = float(np.percentile(rms, 95) - np.percentile(rms, 5))
    
    # 14. 音高特征（对长音频采样）
    duration = len(y) / sr
    if duration > 30:
        seg_len = int(30 / 3 * sr)
        total_len = len(y)
        y_pitch = np.concatenate([y[:seg_len], y[total_len//3:total_len//3+seg_len], y[-seg_len:]])
    else:
        y_pitch = y
    
    f0, voiced_flag, _ = librosa.pyin(y_pitch, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'), sr=sr)
    voiced_f0 = f0[voiced_flag] if f0 is not None else np.array([])
    features['pitch_variability'] = float(np.std(voiced_f0) / (np.mean(voiced_f0) + 1e-10)) if len(voiced_f0) > 0 else 0
    features['voiced_ratio'] = float(len(voiced_f0) / len(f0)) if f0 is not None and len(f0) > 0 else 0
    
    # 15. 谐波比
    harmonic, percussive = librosa.effects.hpss(y)
    features['harmonic_ratio'] = float(np.mean(np.abs(harmonic)) / (np.mean(np.abs(percussive)) + 1e-10))
    
    return features


def process_single_file(filepath: str) -> Optional[Dict]:
    """处理单个文件，返回特征数据"""
    try:
        print(f"  处理: {os.path.basename(filepath)}")
        
        # 计算文件哈希
        with open(filepath, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        # 检查是否已处理
        if is_file_processed(file_hash):
            print(f"    [跳过] 已处理过")
            return None
        
        # 加载音频
        y, sr = load_audio_with_fallback(filepath, sr=None, mono=True)
        duration = len(y) / sr
        
        # 检测类型（纯音乐 vs 歌唱）
        file_type = detect_vocal_vs_instrumental(y, sr)
        print(f"    类型: {file_type}")
        
        # 提取特征
        features = extract_all_features(y, sr)
        
        # 保存特征到缓存文件
        cache_filename = f"{file_hash[:16]}.json"
        cache_path = os.path.join(FEATURE_CACHE_DIR, cache_filename)
        with open(cache_path, 'w') as f:
            json.dump({
                'file_hash': file_hash,
                'filename': os.path.basename(filepath),
                'file_type': file_type,
                'duration': duration,
                'sample_rate': sr,
                'features': features,
                'extracted_at': datetime.now().isoformat()
            }, f, indent=2)
        
        # 记录到数据库
        conn = get_feature_db()
        conn.execute(
            """INSERT INTO file_features 
               (file_hash, filename, file_type, file_size, duration, sample_rate, feature_cache_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_hash, os.path.basename(filepath), file_type, os.path.getsize(filepath), 
             duration, sr, cache_path)
        )
        conn.commit()
        conn.close()
        
        print(f"    [完成] 特征已提取并保存")
        return {
            'file_hash': file_hash,
            'file_type': file_type,
            'features': features
        }
        
    except Exception as e:
        print(f"    [错误] {e}")
        return None


def process_all_files():
    """处理所有未处理的训练文件"""
    init_feature_db()
    
    # 获取所有训练文件
    training_files = []
    for filename in os.listdir(TRAINING_DIR):
        if filename.lower().endswith(('.wav', '.mp3', '.flac', '.ogg', '.aac', '.m4a')):
            filepath = os.path.join(TRAINING_DIR, filename)
            training_files.append(filepath)
    
    print(f"发现 {len(training_files)} 个训练文件")
    
    # 统计已处理和未处理
    processed_count = 0
    new_count = 0
    
    for filepath in training_files:
        # 快速检查是否已处理
        with open(filepath, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        if is_file_processed(file_hash):
            processed_count += 1
        else:
            new_count += 1
    
    print(f"  已处理: {processed_count}")
    print(f"  待处理: {new_count}")
    print()
    
    if new_count == 0:
        print("所有文件已处理完成，无需增量更新")
        return
    
    # 处理未处理的文件
    results = []
    for i, filepath in enumerate(training_files, 1):
        print(f"[{i}/{len(training_files)}]", end=" ")
        result = process_single_file(filepath)
        if result:
            results.append(result)
    
    print(f"\n完成！新增处理 {len(results)} 个文件")


if __name__ == "__main__":
    process_all_files()
