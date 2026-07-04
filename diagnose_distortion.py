"""诊断脚本：逐步骤应用处理函数，定位导致输出完全变样的根本原因。

用法: python diagnose_distortion.py <input_wav> [version]
  version: v3.1, v3.1a, v3.2, v3.2a, v3.2ap, v4.0a, v4.0ap
  默认: v3.2a
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))


def test_version(version, input_path):
    """测试指定版本的每个处理步骤"""
    from services.audio_loader import load_audio_with_fallback
    
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)
    
    # 重采样到 48kHz
    from scipy.signal import resample_poly
    working_sr = 48000
    if sr != working_sr:
        target_len = int(y.shape[1] * working_sr / sr)
        new_y = np.zeros((y.shape[0], target_len), dtype=y.dtype)
        for ch in range(y.shape[0]):
            resampled = resample_poly(y[ch], working_sr, sr)
            copy_len = min(target_len, len(resampled))
            new_y[ch, :copy_len] = resampled[:copy_len]
        y = new_y
        sr = working_sr
    
    print(f"原始音频: shape={y.shape}, sr={sr}, dtype={y.dtype}")
    print(f"原始 RMS: {np.sqrt(np.mean(y.astype(np.float64)**2)):.6f}")
    print(f"原始 peak: {np.max(np.abs(y)):.6f}")
    
    # 测试各个处理函数
    if version == "v3.2a":
        from services.repair.repair_v3_2a.core import (
            simple_declip, simple_depop, de_ess, spectral_denoise,
            vocal_ai_repair_adaptive_lite, vocal_exciter_lite,
            vocal_smart_compressor_lite, transient_aware_process_lite,
            resonance_suppress_lite, apply_bass_enhance_lite,
            apply_air_texture_lite, transparent_compress, loudness_normalize,
            soft_peak_limit, mastering_standard_lite, mastering_powerful_lite,
            mastering_warm_lite
        )
        
        tests = [
            ("simple_declip(0.5)", lambda y: simple_declip(y, 0.5)),
            ("simple_depop(0.5)", lambda y: simple_depop(y, sr, 0.5)),
            ("de_ess(0.5)", lambda y: de_ess(y, sr, 0.5)),
            ("spectral_denoise(0.3)", lambda y: spectral_denoise(y, sr, 0.3)),
            ("vocal_ai_repair_adaptive_lite(0.5)", lambda y: vocal_ai_repair_adaptive_lite(y, sr, 0.5)),
            ("vocal_exciter_lite(0.3)", lambda y: vocal_exciter_lite(y, sr, 0.3)),
            ("vocal_smart_compressor_lite(0.5)", lambda y: vocal_smart_compressor_lite(y, sr, 0.5)),
            ("transient_aware_process_lite(0.3)", lambda y: transient_aware_process_lite(y, sr, 0.3)),
            ("resonance_suppress_lite(0.3)", lambda y: resonance_suppress_lite(y, sr, 0.3)),
            ("apply_bass_enhance_lite(0.3)", lambda y: apply_bass_enhance_lite(y, sr, 0.3)),
            ("apply_air_texture_lite(0.3)", lambda y: apply_air_texture_lite(y, sr, 0.3)),
            ("transparent_compress(0.3)", lambda y: transparent_compress(y, sr, 0.3)),
            ("loudness_normalize(-14)", lambda y: loudness_normalize(y, sr, -14)),
            ("soft_peak_limit(0.9)", lambda y: soft_peak_limit(y, 0.9)),
            ("mastering_standard_lite", lambda y: mastering_standard_lite(y, sr)),
        ]
    elif version == "v3.1":
        from services.repair.repair_v3_1.core import (
            _tanh_declip, _diff_clamp_depop, _vocal_formant_repair,
            _apply_vocal_de_ess, _vocal_breath_enhance,
            _vocal_ai_repair_enhanced, _vocal_exciter, _vocal_compressor,
            _vocal_warmth, _vocal_spatial, _instrument_stereo_enhance,
            _adaptive_loudness_normalize, _soft_peak_limit,
            _mastering_standard, _mastering_powerful, _mastering_warm
        )
        
        tests = [
            ("_tanh_declip(0.5)", lambda y: _tanh_declip(y, 0.5)),
            ("_diff_clamp_depop(0.5)", lambda y: _diff_clamp_depop(y, sr, 0.5)),
            ("_vocal_formant_repair(0.3)", lambda y: _vocal_formant_repair(y, sr, 0.3)),
            ("_apply_vocal_de_ess(0.5)", lambda y: _apply_vocal_de_ess(y, sr, 0.5)),
            ("_vocal_breath_enhance(0.3)", lambda y: _vocal_breath_enhance(y, sr, 0.3)),
            ("_vocal_ai_repair_enhanced(0.5)", lambda y: _vocal_ai_repair_enhanced(y, sr, 0.5)),
            ("_vocal_exciter(0.3)", lambda y: _vocal_exciter(y, sr, 0.3)),
            ("_vocal_compressor(0.5)", lambda y: _vocal_compressor(y, sr, 0.5)),
            ("_vocal_warmth(0.3)", lambda y: _vocal_warmth(y, sr, 0.3)),
            ("_vocal_spatial(0.3)", lambda y: _vocal_spatial(y, sr, 0.3)),
            ("_adaptive_loudness_normalize(-14)", lambda y: _adaptive_loudness_normalize(y, sr, -14)),
            ("_soft_peak_limit(0.9)", lambda y: _soft_peak_limit(y, 0.9)),
            ("_mastering_standard", lambda y: _mastering_standard(y, sr)),
        ]
    else:
        print(f"不支持的版本: {version}")
        return
    
    # 对每个测试：保存输出并检查是否变样
    y_current = y.copy()
    for name, fn in tests:
        try:
            y_prev = y_current.copy()
            y_current = fn(y_current)
            
            # 检查数值变化
            rms_before = np.sqrt(np.mean(y_prev.astype(np.float64)**2))
            rms_after = np.sqrt(np.mean(y_current.astype(np.float64)**2))
            peak_before = np.max(np.abs(y_prev))
            peak_after = np.max(np.abs(y_current))
            
            # 计算相关性（如果形状一致）
            if y_prev.shape == y_current.shape:
                corr = np.corrcoef(y_prev.flatten()[:10000], y_current.flatten()[:10000])[0,1]
            else:
                corr = float('nan')
            
            # 检查是否有 NaN 或 Inf
            has_nan = np.any(np.isnan(y_current))
            has_inf = np.any(np.isinf(y_current))
            
            status = "OK"
            if has_nan:
                status = "NaN!"
            if has_inf:
                status = "Inf!"
            if abs(corr) < 0.5 and not (has_nan or has_inf):
                status = "LOW_CORR"
            if rms_after > 10:
                status = "BLAST"
            if rms_after < 1e-8 and rms_before > 1e-6:
                status = "SILENCE"
            
            print(f"  {name}: RMS {rms_before:.6f}→{rms_after:.6f}, peak {peak_before:.4f}→{peak_after:.4f}, corr={corr:.4f} [{status}]")
            
            if status != "OK":
                print(f"    *** 严重问题! 此步骤破坏了信号! ***")
                # 保存对比文件
                import soundfile as sf
                sf.write(f"/tmp/diag_before_{name.replace('(','_').replace(')','').replace('.','_')}.wav", 
                        y_prev.T if y_prev.ndim > 1 else y_prev, sr)
                sf.write(f"/tmp/diag_after_{name.replace('(','_').replace(')','').replace('.','_')}.wav",
                        y_current.T if y_current.ndim > 1 else y_current, sr)
                
        except Exception as e:
            print(f"  {name}: 异常: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python diagnose_distortion.py <input_wav> [version]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    version = sys.argv[2] if len(sys.argv) > 2 else "v3.2a"
    
    if not os.path.exists(input_path):
        print(f"文件不存在: {input_path}")
        sys.exit(1)
    
    test_version(version, input_path)
