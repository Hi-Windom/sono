"""
悲观测试 - 模拟各种边界情况，探测10MB MP3修复可能的失败点
测试目标：找出v3.2a修复失败的根因
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import time
import tempfile
import numpy as np
import json

def test_audio_loader_10mb_mp3():
    """测试1: 10MB MP3文件加载是否正常"""
    print("\n" + "="*60)
    print("测试1: 10MB MP3文件加载")
    print("="*60)
    
    from services.audio_loader import load_audio_with_fallback
    
    test_file = "/workspace/scripts/test_real_10mb.mp3"
    file_size = os.path.getsize(test_file)
    print(f"文件: {test_file}")
    print(f"大小: {file_size / 1024 / 1024:.2f} MB")
    
    try:
        y, sr = load_audio_with_fallback(test_file)
        print(f"✅ 加载成功")
        print(f"  采样率: {sr}")
        print(f"  声道数: {y.ndim == 1 and 1 or y.shape[0]}")
        print(f"  采样点数: {y.shape[-1]}")
        print(f"  时长: {y.shape[-1] / sr:.2f}s")
        print(f"  dtype: {y.dtype}")
        print(f"  内存占用: {y.nbytes / 1024 / 1024:.2f} MB")
        return True
    except Exception as e:
        print(f"❌ 加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_v32a_repair_core():
    """测试2: v3.2a核心修复算法直接调用"""
    print("\n" + "="*60)
    print("测试2: v3.2a核心修复算法直接调用")
    print("="*60)
    
    from services.audio_loader import load_audio_with_fallback
    from services.repair.repair_v3_2a.core import repair_audio
    
    test_file = "/workspace/scripts/test_real_10mb.mp3"
    
    try:
        y, sr = load_audio_with_fallback(test_file)
        print(f"输入: {y.shape}, sr={sr}, dtype={y.dtype}")
        
        params = {
            "sample_rate": 44100,
            "bit_depth": 16,
            "mastering_mode": "standard",
            "output_gain": 0,
            "denoise_strength": 0.5,
            "dehum_strength": 0.5,
            "declick_strength": 0.5,
            "dereverb_strength": 0.3,
            "brightness": 0.5,
            "warmth": 0.5,
            "presence": 0.5,
            "stereo_width": 0.5,
        }
        
        start_time = time.time()
        result = repair_audio(y, sr, params, progress_callback=lambda p, s: print(f"  [{p*100:5.1f}%] {s}"))
        elapsed = time.time() - start_time
        
        print(f"✅ 修复完成，耗时: {elapsed:.1f}s")
        if result:
            print(f"  输出形状: {result.get('output', y).shape}")
            print(f"  结果键: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
        return True
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_guard():
    """测试3: 内存守卫是否正确估算"""
    print("\n" + "="*60)
    print("测试3: 内存守卫估算")
    print("="*60)
    
    from services.audio_loader import load_audio_with_fallback
    from services.memory_guard import estimate_memory_usage, check_memory_safe
    
    test_file = "/workspace/scripts/test_real_10mb.mp3"
    
    try:
        y, sr = load_audio_with_fallback(test_file)
        duration = y.shape[-1] / sr
        channels = 1 if y.ndim == 1 else y.shape[0]
        
        print(f"音频时长: {duration:.1f}s, 声道: {channels}, 采样率: {sr}")
        
        for algo in ["v2.2", "v2.3", "v3.2", "v3.2a"]:
            est = estimate_memory_usage(duration, channels, sr, algo)
            safe = check_memory_safe(duration, channels, sr, algo)
            print(f"  {algo}: 估算 {est / 1024 / 1024:.1f} MB, 安全: {safe}")
        
        return True
    except Exception as e:
        print(f"❌ 内存估算失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_task_manager_submit():
    """测试4: 任务管理器提交并执行v3.2a修复"""
    print("\n" + "="*60)
    print("测试4: 任务管理器提交v3.2a修复")
    print("="*60)
    
    from services.audio_loader import load_audio_with_fallback
    from services.task_manager import submit_repair_task, get_task_status
    
    test_file = "/workspace/scripts/test_real_10mb.mp3"
    file_size = os.path.getsize(test_file)
    
    try:
        # 创建一个任务
        import uuid
        task_id = str(uuid.uuid4())[:16]
        
        params = {
            "algorithm_version": "v3.2a",
            "sample_rate": 44100,
            "bit_depth": 16,
            "mastering_mode": "standard",
            "output_gain": 0,
            "processing_mode": "single",
            "denoise_strength": 0.5,
            "dehum_strength": 0.5,
            "declick_strength": 0.5,
            "dereverb_strength": 0.3,
            "brightness": 0.5,
            "warmth": 0.5,
            "presence": 0.5,
            "stereo_width": 0.5,
        }
        
        print(f"提交任务: {task_id}")
        print(f"文件: {test_file} ({file_size / 1024 / 1024:.2f} MB)")
        print(f"算法: v3.2a")
        
        submit_repair_task(task_id, test_file, params)
        
        # 等待完成
        max_wait = 300
        start_time = time.time()
        last_status = ""
        
        while time.time() - start_time < max_wait:
            status = get_task_status(task_id)
            if status:
                current = f"{status.get('status')} - {status.get('progress', 0)*100:.1f}% - {status.get('step', '')}"
                if current != last_status:
                    print(f"  [{time.time() - start_time:6.1f}s] {current}")
                    last_status = current
                
                if status.get('status') in ('completed', 'error', 'failed', 'cancelled'):
                    if status.get('status') == 'completed':
                        print(f"✅ 任务完成")
                        output_path = status.get('output_path', '')
                        if output_path and os.path.exists(output_path):
                            print(f"  输出文件: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
                        return True
                    else:
                        print(f"❌ 任务失败: {status.get('error', '未知错误')}")
                        return False
            
            time.sleep(2)
        
        print(f"⏰ 超时 ({max_wait}s)")
        return False
        
    except Exception as e:
        print(f"❌ 任务管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_repair_registry_v32a():
    """测试5: v3.2a是否在修复注册表中正确注册"""
    print("\n" + "="*60)
    print("测试5: v3.2a算法注册状态")
    print("="*60)
    
    try:
        from services.repair_registry import ALGORITHM_VERSIONS
        
        print(f"已注册算法数量: {len(ALGORITHM_VERSIONS)}")
        for algo in ALGORITHM_VERSIONS:
            print(f"  - {algo.get('name')}: {algo.get('description', '')[:50]}")
        
        v32a = next((a for a in ALGORITHM_VERSIONS if a.get('name') == 'v3.2a'), None)
        if v32a:
            print(f"\n✅ v3.2a 已注册")
            print(f"  兼容: {v32a.get('compatible', True)}")
            print(f"  默认参数: {list(v32a.get('defaultParams', {}).keys())[:10]}...")
            return True
        else:
            print(f"\n❌ v3.2a 未在注册表中找到!")
            return False
            
    except Exception as e:
        print(f"❌ 注册表检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_audio_repair_router():
    """测试6: audio_repair.py路由是否正确分派v3.2a"""
    print("\n" + "="*60)
    print("测试6: 修复路由v3.2a分派")
    print("="*60)
    
    from services.audio_loader import load_audio_with_fallback
    
    test_file = "/workspace/scripts/test_real_10mb.mp3"
    
    try:
        y, sr = load_audio_with_fallback(test_file)
        
        from services.audio_repair import repair_audio
        
        params = {
            "algorithm_version": "v3.2a",
            "sample_rate": 44100,
            "bit_depth": 16,
            "mastering_mode": "standard",
            "output_gain": 0,
            "processing_mode": "single",
            "denoise_strength": 0.5,
        }
        
        print(f"调用 repair_audio, algorithm_version=v3.2a")
        start_time = time.time()
        result = repair_audio(y, sr, params)
        elapsed = time.time() - start_time
        
        if result:
            print(f"✅ 路由分派成功，耗时: {elapsed:.1f}s")
            return True
        else:
            print(f"❌ 路由分派失败，返回 None")
            return False
            
    except Exception as e:
        print(f"❌ 路由测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("="*60)
    print("10MB MP3 v3.2a 修复失败 - 悲观测试套件")
    print("="*60)
    
    results = {}
    
    tests = [
        ("音频加载", test_audio_loader_10mb_mp3),
        ("算法注册", test_repair_registry_v32a),
        ("内存估算", test_memory_guard),
        ("核心修复", test_v32a_repair_core),
        ("修复路由", test_audio_repair_router),
        ("任务管理器", test_task_manager_submit),
    ]
    
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n❌ {name} 异常: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
    
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    print(f"\n总计: {'全部通过' if all_passed else '有失败项'}")
    sys.exit(0 if all_passed else 1)
