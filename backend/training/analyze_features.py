#!/usr/bin/env python3
"""
训练特征分析器
- 计算纯音乐和歌唱作品的统计分布
- 生成阈值建议
"""

import os
import sys
import json
import sqlite3
import numpy as np
from typing import Dict, List
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TRAINING_DIR
from feature_extractor import FEATURE_DB_PATH, FEATURE_CACHE_DIR, get_feature_db


def load_all_features() -> Dict[str, List[Dict]]:
    """加载所有特征数据，按类型分类"""
    conn = get_feature_db()
    rows = conn.execute(
        "SELECT file_type, feature_cache_path FROM file_features"
    ).fetchall()
    conn.close()
    
    features_by_type = defaultdict(list)
    
    for row in rows:
        file_type = row['file_type']
        cache_path = row['feature_cache_path']
        
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                data = json.load(f)
                features_by_type[file_type].append(data['features'])
    
    return dict(features_by_type)


def calculate_statistics(values: List[float]) -> Dict:
    """计算统计指标"""
    arr = np.array(values)
    return {
        'mean': float(np.mean(arr)),
        'std': float(np.std(arr)),
        'median': float(np.median(arr)),
        'p10': float(np.percentile(arr, 10)),
        'p90': float(np.percentile(arr, 90)),
        'min': float(np.min(arr)),
        'max': float(np.max(arr)),
        'count': len(values)
    }


def analyze_features():
    """分析特征并生成报告"""
    features_by_type = load_all_features()
    
    if not features_by_type:
        print("没有找到特征数据，请先运行 feature_extractor.py")
        return
    
    print("=" * 60)
    print("AI音乐训练数据分析报告")
    print("=" * 60)
    print()
    
    for file_type, features_list in features_by_type.items():
        print(f"\n【{file_type.upper()}】样本数: {len(features_list)}")
        print("-" * 60)
        
        # 收集所有特征值
        feature_values = defaultdict(list)
        for features in features_list:
            for key, value in features.items():
                feature_values[key].append(value)
        
        # 计算每个特征的统计
        stats_by_feature = {}
        for feature_name, values in feature_values.items():
            stats_by_feature[feature_name] = calculate_statistics(values)
        
        # 显示关键特征
        key_features = [
            'spectral_flatness', 'spectral_entropy',
            'mfcc_variability', 'pitch_variability',
            'log_spectral_variance', 'dynamic_range',
            'temporal_regularity', 'micro_rhythm_consistency',
            'harmonic_ratio', 'voiced_ratio'
        ]
        
        for feature in key_features:
            if feature in stats_by_feature:
                s = stats_by_feature[feature]
                print(f"  {feature:30s} mean={s['mean']:8.4f}  p10={s['p10']:8.4f}  p90={s['p90']:8.4f}  std={s['std']:8.4f}")
        
        # 保存到数据库
        conn = get_feature_db()
        for feature_name, stats in stats_by_feature.items():
            conn.execute("""
                INSERT OR REPLACE INTO feature_statistics 
                (file_type, feature_name, mean, std, median, p10, p90, min_val, max_val, sample_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_type, feature_name,
                stats['mean'], stats['std'], stats['median'],
                stats['p10'], stats['p90'], stats['min'], stats['max'],
                stats['count']
            ))
        conn.commit()
        conn.close()
    
    print("\n" + "=" * 60)
    print("分析完成！统计数据已保存到数据库")


def generate_threshold_recommendations():
    """生成阈值建议"""
    conn = get_feature_db()
    
    print("\n" + "=" * 60)
    print("v1.1 算法阈值建议")
    print("=" * 60)
    print()
    
    # 获取所有统计
    rows = conn.execute(
        "SELECT file_type, feature_name, mean, p10, p90 FROM feature_statistics ORDER BY file_type, feature_name"
    ).fetchall()
    
    # 按类型分组
    stats_by_type = defaultdict(dict)
    for row in rows:
        stats_by_type[row['file_type']][row['feature_name']] = {
            'mean': row['mean'],
            'p10': row['p10'],
            'p90': row['p90']
        }
    
    for file_type in ['vocal', 'instrumental']:
        if file_type not in stats_by_type:
            continue
        
        print(f"\n【{file_type.upper()} 类型阈值建议】")
        print("-" * 60)
        
        stats = stats_by_type[file_type]
        
        # 关键特征阈值建议
        recommendations = []
        
        if 'spectral_flatness' in stats:
            s = stats['spectral_flatness']
            recommendations.append(f"spectral_flatness: 当前 mean={s['mean']:.4f}, 建议 AI 阈值 < {s['p10']:.4f}")
        
        if 'pitch_variability' in stats:
            s = stats['pitch_variability']
            recommendations.append(f"pitch_variability: 当前 mean={s['mean']:.4f}, 建议 AI 阈值 > {s['p90']:.4f}")
        
        if 'log_spectral_variance' in stats:
            s = stats['log_spectral_variance']
            recommendations.append(f"log_spectral_variance: 当前 mean={s['mean']:.4f}, 建议 AI 阈值 > {s['p90']:.4f}")
        
        if 'dynamic_range' in stats:
            s = stats['dynamic_range']
            recommendations.append(f"dynamic_range: 当前 mean={s['mean']:.4f}, 建议 AI 阈值 > {s['p90']:.4f}")
        
        if 'mfcc_variability' in stats:
            s = stats['mfcc_variability']
            recommendations.append(f"mfcc_variability: 当前 mean={s['mean']:.4f}, 建议 AI 阈值 > {s['p90']:.4f}")
        
        for rec in recommendations:
            print(f"  {rec}")
    
    conn.close()


if __name__ == "__main__":
    analyze_features()
    generate_threshold_recommendations()
