#!/usr/bin/env python3
"""
逐个测试 v1.2 检测算法，强制释放内存
"""

import os
import sys
import gc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import json

def test_single():
    training_dir = Path("/workspace/backend/storage/training")
    
    # 获取所有音频文件
    audio_files = sorted([f for f in training_dir.glob("*") 
                         if f.suffix.lower() in ['.mp3', '.wav', '.flac', '.m4a']])
    
    # 检查缓存
    cache_file = Path("/workspace/backend/training/v12_results.json")
    if cache_file.exists():
        with open(cache_file, 'r') as f:
            results = json.load(f)
    else:
        results = {}
    
    # 找出未检测的文件
    remaining = [f for f in audio_files if f.name not in results]
    
    if not remaining:
        print("所有文件已检测完成！")
        print_summary(results)
        return True
    
    # 只处理第一个文件
    audio_file = remaining[0]
    print(f"检测: {audio_file.name}")
    
    try:
        # 延迟导入以释放内存
        from services.detectors.ai_detector_v1_2 import detect_ai_audio
        
        result = detect_ai_audio(str(audio_file))
        
        results[audio_file.name] = {
            'ai_prob': result['ai_probability'],
            'human_prob': result['human_probability'],
            'signature': result['signature'],
            'confidence': result['confidence'],
            'reasons': result['reasons'][:3]
        }
        
        print(f"  AI={result['ai_probability']:.2%}, 人类={result['human_probability']:.2%}, 判定={result['signature']}")
        print(f"  原因: {', '.join(result['reasons'][:3])}")
        
        # 保存进度
        with open(cache_file, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n进度: {len(results)}/{len(audio_files)}")
        
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 强制释放内存
    gc.collect()
    
    return len(results) == len(audio_files)

def print_summary(results):
    print("\n" + "=" * 80)
    print("统计汇总")
    print("=" * 80)
    
    total = len(results)
    ai_detected = sum(1 for r in results.values() if r['ai_prob'] > 0.5)
    high_confidence_ai = sum(1 for r in results.values() if r['ai_prob'] > 0.7)
    low_human = sum(1 for r in results.values() if r['human_prob'] < 0.3)
    
    print(f"\n总样本数: {total}")
    print(f"判定为 AI (AI > 50%): {ai_detected} ({ai_detected/total*100:.1f}%)")
    print(f"高置信度 AI (AI > 70%): {high_confidence_ai} ({high_confidence_ai/total*100:.1f}%)")
    print(f"人类概率 < 30%: {low_human} ({low_human/total*100:.1f}%)")
    
    print("\n【AI 概率 < 70% 的样本】")
    for name, r in sorted(results.items()):
        if r['ai_prob'] < 0.7:
            print(f"  {name}: AI={r['ai_prob']:.2%}, 人类={r['human_prob']:.2%}")
    
    print("\n【AI 概率 >= 70% 的样本】")
    for name, r in sorted(results.items()):
        if r['ai_prob'] >= 0.7:
            print(f"  {name}: AI={r['ai_prob']:.2%}")
    
    avg_ai_prob = sum(r['ai_prob'] for r in results.values()) / total
    print(f"\n平均 AI 概率: {avg_ai_prob:.2%}")

if __name__ == "__main__":
    done = test_single()
    if done:
        print("\n✅ 所有文件检测完成！")
