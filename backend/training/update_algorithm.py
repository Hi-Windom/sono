#!/usr/bin/env python3
"""
根据训练数据更新 v1.1 算法阈值
"""

import os
import sys
import sqlite3
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from feature_extractor import FEATURE_DB_PATH, get_feature_db

# v1.1 算法文件路径
V11_DETECTOR_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                  'services', 'ai_detector_v11.py')


def get_training_thresholds():
    """从训练数据获取阈值建议"""
    conn = get_feature_db()
    
    # 获取所有统计
    rows = conn.execute(
        """SELECT file_type, feature_name, mean, p10, p90, std 
           FROM feature_statistics"""
    ).fetchall()
    
    thresholds = {}
    for row in rows:
        key = f"{row['file_type']}.{row['feature_name']}"
        thresholds[key] = {
            'mean': row['mean'],
            'p10': row['p10'],
            'p90': row['p90'],
            'std': row['std']
        }
    
    conn.close()
    return thresholds


def update_v11_thresholds():
    """更新 v1.1 算法的阈值"""
    thresholds = get_training_thresholds()
    
    if not thresholds:
        print("没有找到训练数据，请先运行 feature_extractor.py 和 analyze_features.py")
        return
    
    print("=" * 60)
    print("更新 v1.1 算法阈值")
    print("=" * 60)
    print()
    
    # 读取当前 v1.1 代码
    with open(V11_DETECTOR_PATH, 'r') as f:
        content = f.read()
    
    # 显示关键阈值建议
    print("【关键阈值建议】")
    print("-" * 60)
    
    # 合并 vocal 和 instrumental 的统计（取更保守的值）
    merged_thresholds = {}
    
    for feature in ['spectral_flatness', 'spectral_entropy', 'mfcc_variability', 
                    'pitch_variability', 'log_spectral_variance', 'dynamic_range',
                    'temporal_regularity', 'micro_rhythm_consistency']:
        vocal_key = f"vocal.{feature}"
        inst_key = f"instrumental.{feature}"
        
        if vocal_key in thresholds and inst_key in thresholds:
            v = thresholds[vocal_key]
            i = thresholds[inst_key]
            
            # 对于 AI 检测，取更保守的阈值（更容易触发 AI 判定）
            merged_thresholds[feature] = {
                'p10': min(v['p10'], i['p10']),
                'p90': max(v['p90'], i['p90']),
                'mean': (v['mean'] + i['mean']) / 2
            }
            
            print(f"  {feature}:")
            print(f"    mean: {merged_thresholds[feature]['mean']:.4f}")
            print(f"    p10:  {merged_thresholds[feature]['p10']:.4f}")
            print(f"    p90:  {merged_thresholds[feature]['p90']:.4f}")
    
    print()
    print("=" * 60)
    print("阈值建议已生成，请根据上述数据手动更新 ai_detector_v11.py")
    print(f"文件路径: {V11_DETECTOR_PATH}")
    print("=" * 60)
    
    # 保存阈值建议到文件
    threshold_file = os.path.join(os.path.dirname(FEATURE_DB_PATH), 'threshold_recommendations.txt')
    with open(threshold_file, 'w') as f:
        f.write("# v1.1 算法阈值建议（基于训练数据）\n\n")
        for feature, values in merged_thresholds.items():
            f.write(f"{feature}:\n")
            f.write(f"  mean: {values['mean']:.6f}\n")
            f.write(f"  p10:  {values['p10']:.6f}\n")
            f.write(f"  p90:  {values['p90']:.6f}\n\n")
    
    print(f"\n阈值建议已保存到: {threshold_file}")


if __name__ == "__main__":
    update_v11_thresholds()
