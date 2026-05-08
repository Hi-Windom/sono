#!/usr/bin/env python3
"""
测试 v1.2 检测算法在训练素材上的表现
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.detectors.ai_detector_v1_2 import detect_ai_audio
from pathlib import Path

def test_training_files():
    training_dir = Path("/workspace/backend/storage/training")
    
    print("=" * 80)
    print("v1.2 检测算法在 AI 训练素材上的表现")
    print("=" * 80)
    print()
    
    results = []
    
    for audio_file in sorted(training_dir.glob("*")):
        if audio_file.suffix.lower() not in ['.mp3', '.wav', '.flac', '.m4a']:
            continue
        
        print(f"\n检测: {audio_file.name}")
        print("-" * 60)
        
        try:
            result = detect_ai_audio(str(audio_file))
            
            ai_prob = result['ai_probability']
            human_prob = result['human_probability']
            signature = result['signature']
            confidence = result['confidence']
            
            print(f"  AI 概率: {ai_prob:.2%}")
            print(f"  人类概率: {human_prob:.2%}")
            print(f"  判定: {signature} (置信度: {confidence:.2%})")
            print(f"  原因: {', '.join(result['reasons'][:3])}")
            
            results.append({
                'name': audio_file.name,
                'ai_prob': ai_prob,
                'human_prob': human_prob,
                'signature': signature,
                'confidence': confidence
            })
            
        except Exception as e:
            print(f"  错误: {e}")
    
    # 统计
    print("\n" + "=" * 80)
    print("统计汇总")
    print("=" * 80)
    
    total = len(results)
    ai_detected = sum(1 for r in results if r['ai_prob'] > 0.5)
    high_confidence_ai = sum(1 for r in results if r['ai_prob'] > 0.7)
    low_human = sum(1 for r in results if r['human_prob'] < 0.3)
    
    print(f"\n总样本数: {total}")
    print(f"判定为 AI (AI > 50%): {ai_detected} ({ai_detected/total*100:.1f}%)")
    print(f"高置信度 AI (AI > 70%): {high_confidence_ai} ({high_confidence_ai/total*100:.1f}%)")
    print(f"人类概率 < 30%: {low_human} ({low_human/total*100:.1f}%)")
    
    print("\n【AI 概率 < 70% 的样本】")
    for r in results:
        if r['ai_prob'] < 0.7:
            print(f"  {r['name']}: AI={r['ai_prob']:.2%}, 人类={r['human_prob']:.2%}")
    
    print("\n【AI 概率 > 70% 的样本】")
    for r in results:
        if r['ai_prob'] >= 0.7:
            print(f"  {r['name']}: AI={r['ai_prob']:.2%}")
    
    avg_ai_prob = sum(r['ai_prob'] for r in results) / total
    print(f"\n平均 AI 概率: {avg_ai_prob:.2%}")
    
    return results

if __name__ == "__main__":
    test_training_files()
