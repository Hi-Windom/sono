"""简单端到端测试：合成信号 -> 修复 -> 检查输出是否仍然像原信号"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import soundfile as sf

# 创建测试信号（简单的正弦波）
sr = 48000
duration = 2  # 秒
t = np.arange(int(sr * duration)) / sr
# 混合几个频率模拟音乐
y = (0.4 * np.sin(2*np.pi*440*t) + 
     0.3 * np.sin(2*np.pi*554*t) + 
     0.2 * np.sin(2*np.pi*659*t) +
     0.1 * np.sin(2*np.pi*880*t))
y = y.reshape(1, -1).astype(np.float32)

# 保存为临时文件
test_input = "/tmp/test_sine.wav"
sf.write(test_input, y.T, sr)

# 现在用不同的版本处理
versions = ["v3.1", "v3.1a", "v3.2", "v3.2a", "v3.2ap", "v4.0a", "v4.0ap"]

for ver in versions:
    test_output = f"/tmp/test_sine_{ver}.wav"
    
    try:
        if ver == "v3.1":
            from services.repair.repair_v3_1.core import repair_audio as repair
        elif ver == "v3.1a":
            from services.repair.repair_v3_1a.core import repair_audio as repair
        elif ver == "v3.2":
            from services.repair.repair_v3_2.core import repair_audio as repair
        elif ver == "v3.2a":
            from services.repair.repair_v3_2a.core import repair_audio as repair
        elif ver == "v3.2ap":
            from services.repair.repair_v3_2ap.core import repair_audio as repair
        elif ver == "v4.0a":
            from services.repair.repair_v4_0a.core import repair_audio as repair
        elif ver == "v4.0ap":
            from services.repair.repair_v4_0ap.core import repair_audio as repair
        else:
            continue
        
        # 使用默认参数（模拟用户正常使用）
        params = {
            "de_clipping": 0.3,
            "de_pop": 0.18,
            "formant_repair": 0.5,
            "de_essing": 0.25,
            "breath_enhance": 0.3,
            "ai_repair": 0.2,
            "bass_enhance": 0.1,
            "air_texture": 0.2,
            "loudness_optimize": 0.5,
            "exciter": 0.5,
            "compressor": 0.5,
            "spatial": 0.5,
            "warmth": 0.5,
            "smart_compressor": 0.5,
            "transient_aware": 0.3,
            "resonance_suppress": 0.3,
            "ai_repair_adaptive": 0.5,
            "exciter_improved": 0.5,
            "de_esser_improved": 0.5,
            "speed": 1.0,
            "mastering_style": "standard",
            "bit_depth": 24,
            "processing_mode": "single",
        }
        
        result = repair(test_input, test_output, params)
        
        # 读取输出并与输入比较
        y_in = y[0]
        y_out_data, out_sr = sf.read(test_output)
        if y_out_data.ndim > 1:
            y_out_data = y_out_data[:, 0]  # 取第一声道
        
        # 对齐长度
        min_len = min(len(y_in), len(y_out_data))
        y_in_aligned = y_in[:min_len]
        y_out_aligned = y_out_data[:min_len]
        
        # 计算相关性
        corr = np.corrcoef(y_in_aligned, y_out_aligned)[0, 1]
        rms_in = np.sqrt(np.mean(y_in_aligned**2))
        rms_out = np.sqrt(np.mean(y_out_aligned**2))
        
        print(f"{ver}: corr={corr:.4f}, RMS in={rms_in:.4f}, out={rms_out:.4f}, "
              f"peak in={np.max(np.abs(y_in_aligned)):.4f}, out={np.max(np.abs(y_out_aligned)):.4f}")
        
        if corr < 0.5:
            print(f"  *** 严重失真! 相关性仅 {corr:.4f} ***")
        
    except Exception as e:
        print(f"{ver}: 错误: {e}")
        import traceback
        traceback.print_exc()

print("\n完成。输出文件在 /tmp/test_sine_*.wav")
