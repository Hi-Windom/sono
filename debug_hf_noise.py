#!/usr/bin/env python3
import numpy as np
import sys
sys.path.insert(0, '/workspace/backend')

from services.repair.repair_v3_0 import repair_audio as repair_v30
from services.repair.repair_v3_1 import repair_audio as repair_v31
from tests.conftest import generate_speech_like, SR, compute_hf_noise
import tempfile
from pathlib import Path
import soundfile as sf

print("=== 调试 v3.0 高频噪声 ===\n")

# 生成测试信号
y = generate_speech_like(sr=SR, duration=2.0)
input_hf = compute_hf_noise(y, SR, 5000, 16000)
print(f"输入信号高频能量: {input_hf:.2e}")

# 测试 v3.0
with tempfile.TemporaryDirectory() as tmpdir:
    input_path = str(Path(tmpdir) / "input.wav")
    output_path = str(Path(tmpdir) / "output_v30.wav")
    
    sf.write(input_path, y, SR)
    
    params = {
        'accompaniment_ratio': 1.0,
        'de_clipping': 0.3,
        'de_pop': 0.18,
        'inst_declip': 0.3,
        'inst_depop': 0.18,
        'inst_dynamic': 0.3,
        'inst_loudness': 1.0,
        'inst_noise_reduction': 0.2,
        'inst_spatial': 0.4,
        'inst_timbre_protect': 0.6,
        'inst_warmth': 0.5,
        'loudness': 1.0,
        'vocal_ai_repair': 0.5,
        'vocal_bass_enhance': 0.5,
        'vocal_breath_enhance': 0.3,
        'vocal_de_ess': 0.25,
        'vocal_declip': 0.3,
        'vocal_depop': 0.18,
        'vocal_formant_repair': 0.5,
        'vocal_loudness': 1.0,
        'vocal_ratio': 1.0,
        'vocal_air_texture': 0.5,
    }
    
    print("\n=== 运行 v3.0 修复 ===")
    repair_v30(input_path, output_path, params)
    y_out_v30, sr_out_v30 = sf.read(output_path)
    output_hf_v30 = compute_hf_noise(y_out_v30, sr_out_v30, 5000, 16000)
    hf_ratio_v30 = output_hf_v30 / input_hf if input_hf > 1e-10 else output_hf_v30 / 1e-10
    print(f"v3.0 输出高频能量: {output_hf_v30:.2e}")
    print(f"v3.0 高频比值: {hf_ratio_v30:.1f}x")

# 测试 v3.1
with tempfile.TemporaryDirectory() as tmpdir:
    input_path = str(Path(tmpdir) / "input.wav")
    output_path = str(Path(tmpdir) / "output_v31.wav")
    
    sf.write(input_path, y, SR)
    
    params = {
        'accompaniment_ratio': 1.0,
        'de_clipping': 0.3,
        'de_pop': 0.18,
        'inst_declip': 0.3,
        'inst_depop': 0.18,
        'inst_dynamic': 0.3,
        'inst_loudness': 1.0,
        'inst_noise_reduction': 0.2,
        'inst_spatial': 0.4,
        'inst_stereo_enhance': 0.3,
        'inst_timbre_protect': 0.6,
        'inst_warmth': 0.5,
        'loudness': 1.0,
        'mastering': 0.5,
        'vocal_ai_repair': 0.5,
        'vocal_ai_repair_enhanced': 0.3,
        'vocal_bass_enhance': 0.5,
        'vocal_breath_enhance': 0.3,
        'vocal_compressor': 0.3,
        'vocal_de_ess': 0.25,
        'vocal_declip': 0.3,
        'vocal_depop': 0.18,
        'vocal_exciter': 0.4,
        'vocal_formant_repair': 0.5,
        'vocal_loudness': 1.0,
        'vocal_ratio': 1.0,
        'vocal_spatial': 0.3,
        'vocal_warmth': 0.4,
        'vocal_air_texture': 0.5,
    }
    
    print("\n=== 运行 v3.1 修复 ===")
    repair_v31(input_path, output_path, params)
    y_out_v31, sr_out_v31 = sf.read(output_path)
    output_hf_v31 = compute_hf_noise(y_out_v31, sr_out_v31, 5000, 16000)
    hf_ratio_v31 = output_hf_v31 / input_hf if input_hf > 1e-10 else output_hf_v31 / 1e-10
    print(f"v3.1 输出高频能量: {output_hf_v31:.2e}")
    print(f"v3.1 高频比值: {hf_ratio_v31:.1f}x")

print(f"\n=== 对比 ===")
print(f"v3.0 比值: {hf_ratio_v30:.1f}x")
print(f"v3.1 比值: {hf_ratio_v31:.1f}x")
