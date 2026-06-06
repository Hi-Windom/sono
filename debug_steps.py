#!/usr/bin/env python3
import sys
import numpy as np
import tempfile
from pathlib import Path
import soundfile as sf

sys.path.insert(0, '/workspace/backend')
from services.audio_loader import load_audio_with_fallback
from services.repair.repair_v2_4.hifi_ai_repair import apply_hifi_ai_repair
from services.repair.repair_v3_0.core import (
    _tanh_declip, _diff_clamp_depop, _vocal_formant_repair,
    _apply_vocal_de_ess, _vocal_breath_enhance,
    _harmonic_bass_enhance, _air_texture_reconstruct,
    _adaptive_loudness_normalize, _soft_peak_limit,
    _spectral_hf_gate, _hf_protect, _mastering_standard,
    mix_tracks, process_vocal_track, process_instrument_track
)
from tests.conftest import generate_speech_like, SR, compute_hf_noise


def main():
    print("=== Debugging v3.0 HF noise ===\n")
    
    # 生成测试信号
    y = generate_speech_like(sr=SR, duration=2.0)
    input_hf = compute_hf_noise(y, SR, 5000, 16000)
    print(f"Input HF: {input_hf:.2e}")
    
    # 模拟处理流程
    y_process = y.reshape(1, -1) if y.ndim == 1 else y.copy()
    sr_process = SR
    
    print("\n=== Step by step processing ===")
    steps = [
        ("_tanh_declip", lambda y: _tanh_declip(y, 0.3)),
        ("_diff_clamp_depop", lambda y: _diff_clamp_depop(y, sr_process, 0.18)),
        ("_vocal_formant_repair", lambda y: _vocal_formant_repair(y, sr_process, 0.5)),
        ("_apply_vocal_de_ess", lambda y: _apply_vocal_de_ess(y, sr_process, 0.25)),
        ("_vocal_breath_enhance", lambda y: _vocal_breath_enhance(y, sr_process, 0.3)),
        ("apply_hifi_ai_repair", lambda y: apply_hifi_ai_repair(y, sr_process, 0.2, {})),
        ("_harmonic_bass_enhance", lambda y: _harmonic_bass_enhance(y, sr_process, 0.1, "vocal")),
        ("_air_texture_reconstruct", lambda y: _air_texture_reconstruct(y, sr_process, 0.2, "vocal")),
        ("_adaptive_loudness_normalize", lambda y: _adaptive_loudness_normalize(y, sr_process, -14.0)),
        ("_soft_peak_limit", lambda y: _soft_peak_limit(y, 0.9)),
        ("_spectral_hf_gate", lambda y: _spectral_hf_gate(y, sr_process)),
        ("_hf_protect", lambda y: _hf_protect(y, sr_process)),
    ]
    
    for name, step in steps:
        y_process = step(y_process)
        hf = compute_hf_noise(y_process, sr_process, 5000, 16000)
        ratio = hf / input_hf if input_hf > 1e-10 else hf / 1e-10
        print(f"{name}: {hf:.2e} ({ratio:.1f}x)")
    
    print("\n=== Processing full pipeline ===")
    y_full = y.reshape(1, -1) if y.ndim == 1 else y.copy()
    params = {
        'vocal_declip': 0.3,
        'vocal_depop': 0.18,
        'vocal_formant_repair': 0.5,
        'vocal_de_ess': 0.25,
        'vocal_breath_enhance': 0.3,
        'vocal_ai_repair': 0.2,
        'vocal_bass_enhance': 0.1,
        'vocal_air_texture': 0.2,
        'vocal_loudness': 0.5,
        '_issues': []
    }
    y_vocal = process_vocal_track(y_full, SR, params)
    y_acc = process_instrument_track(y_full, SR, {
        'inst_declip':0.3, 'inst_depop':0.18, 'inst_timbre_protect':0.5, 
        'inst_dynamic':0.2, 'inst_noise_reduction':0.15, 'inst_spatial':0.15,
        'inst_warmth':0.25, 'inst_loudness':0.5, '_issues': []
    })
    y_mixed = mix_tracks(y_vocal, y_acc, 1.0, 1.0)
    y_mixed = _soft_peak_limit(y_mixed, 0.95)
    y_mixed = _mastering_standard(y_mixed, SR)
    y_mixed = _soft_peak_limit(y_mixed, 0.9)
    y_mixed = _spectral_hf_gate(y_mixed, SR)
    y_mixed = _hf_protect(y_mixed, SR)
    
    final_hf = compute_hf_noise(y_mixed, SR, 5000, 16000)
    final_ratio = final_hf / input_hf if input_hf > 1e-10 else final_hf / 1e-10
    print(f"Final: {final_hf:.2e} ({final_ratio:.1f}x)")
    
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
