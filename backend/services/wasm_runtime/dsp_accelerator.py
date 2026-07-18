"""
WASM DSP 加速层

提供与 dsp_utils.py 兼容的 API，但底层使用 WASM 模块加速。
当 WASM 运行时不可用时，自动回退到纯 Python 实现。

使用方式：
    from backend.services.wasm_runtime.dsp_accelerator import DspAccelerator
    
    dsp = DspAccelerator()
    if dsp.available:
        output = dsp.apply_gain(audio_data, 3.0)  # +3dB
"""

import logging
import numpy as np
from typing import Optional

from .runtime import WasmRuntime, WasmModule, WasmRuntimeError

logger = logging.getLogger(__name__)


class DspAccelerator:
    """
    DSP WASM 加速器
    
    封装 WASM DSP 模块，提供与 Python 实现一致的接口。
    当 WASM 不可用时，自动回退到纯 numpy 实现。
    """
    
    def __init__(self, runtime: Optional[WasmRuntime] = None):
        self._runtime = runtime or WasmRuntime.instance()
        self._module: Optional[WasmModule] = None
        self._fallback = not self._runtime.available
        
        if self._runtime.available:
            self._try_load_module()
    
    def _try_load_module(self) -> None:
        """尝试加载 DSP WASM 模块"""
        import os
        
        module_paths = [
            os.path.join(os.path.dirname(__file__), "modules", "dsp_example.wasm"),
            os.path.join(os.path.dirname(__file__), "..", "dsp_native", "dsp_example.wasm"),
        ]
        
        for path in module_paths:
            if os.path.exists(path):
                try:
                    self._module = self._runtime.load_module("dsp_example", path)
                    logger.info(f"DSP WASM accelerator loaded from {path}")
                    return
                except Exception as e:
                    logger.warning(f"Failed to load DSP WASM module from {path}: {e}")
        
        logger.info("DSP WASM module not found, using fallback (pure Python)")
        self._fallback = True
    
    @property
    def available(self) -> bool:
        """WASM 加速是否可用"""
        return self._module is not None and not self._fallback
    
    @property
    def backend(self) -> str:
        """当前使用的后端"""
        if self.available:
            return f"wasm ({self._runtime.backend})"
        return "python (fallback)"
    
    def apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        """
        应用增益
        
        Args:
            audio: 音频数据 (float32/float64)
            gain_db: 增益 (dB)
            
        Returns:
            处理后的音频数据
        """
        if not self.available or self._module is None:
            return self._fallback_apply_gain(audio, gain_db)
        
        try:
            return self._wasm_apply_gain(audio, gain_db)
        except Exception as e:
            logger.warning(f"WASM apply_gain failed: {e}, falling back")
            return self._fallback_apply_gain(audio, gain_db)
    
    def _wasm_apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        """WASM 实现的增益处理"""
        assert self._module is not None
        
        audio_float32 = audio.astype(np.float32)
        length = audio_float32.size
        
        ptr = self._module.alloc(length * 4)
        if ptr == 0:
            raise WasmRuntimeError("Failed to allocate WASM memory")
        
        try:
            self._module.write_memory(ptr, audio_float32.tobytes())
            self._module.call("apply_gain", ptr, length, gain_db)
            result_bytes = self._module.read_memory(ptr, length * 4)
            result = np.frombuffer(result_bytes, dtype=np.float32)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)
    
    def _fallback_apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        """纯 Python 实现的增益处理"""
        gain_linear = 10 ** (gain_db / 20.0)
        return audio * gain_linear
    
    def compute_rms(self, audio: np.ndarray) -> float:
        """计算 RMS 值"""
        if not self.available or self._module is None:
            return self._fallback_compute_rms(audio)
        
        try:
            return self._wasm_compute_rms(audio)
        except Exception as e:
            logger.warning(f"WASM compute_rms failed: {e}, falling back")
            return self._fallback_compute_rms(audio)
    
    def _wasm_compute_rms(self, audio: np.ndarray) -> float:
        """WASM 实现的 RMS 计算"""
        assert self._module is not None
        
        audio_float32 = audio.astype(np.float32).ravel()
        length = audio_float32.size
        
        ptr = self._module.alloc(length * 4)
        if ptr == 0:
            raise WasmRuntimeError("Failed to allocate WASM memory")
        
        try:
            self._module.write_memory(ptr, audio_float32.tobytes())
            rms = self._module.call("compute_rms", ptr, length)
            return float(rms)
        finally:
            self._module.free(ptr)
    
    def _fallback_compute_rms(self, audio: np.ndarray) -> float:
        """纯 Python 实现的 RMS 计算"""
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(audio ** 2)))
    
    def normalize(self, audio: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
        """归一化音频"""
        if not self.available or self._module is None:
            return self._fallback_normalize(audio, target_peak)
        
        try:
            return self._wasm_normalize(audio, target_peak)
        except Exception as e:
            logger.warning(f"WASM normalize failed: {e}, falling back")
            return self._fallback_normalize(audio, target_peak)
    
    def _wasm_normalize(self, audio: np.ndarray, target_peak: float) -> np.ndarray:
        """WASM 实现的归一化"""
        assert self._module is not None
        
        audio_float32 = audio.astype(np.float32).ravel()
        length = audio_float32.size
        
        ptr = self._module.alloc(length * 4)
        if ptr == 0:
            raise WasmRuntimeError("Failed to allocate WASM memory")
        
        try:
            self._module.write_memory(ptr, audio_float32.tobytes())
            self._module.call("normalize", ptr, length, target_peak)
            result_bytes = self._module.read_memory(ptr, length * 4)
            result = np.frombuffer(result_bytes, dtype=np.float32)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)
    
    def _fallback_normalize(self, audio: np.ndarray, target_peak: float) -> np.ndarray:
        """纯 Python 实现的归一化"""
        peak = np.max(np.abs(audio))
        if peak > 0:
            return audio * (target_peak / peak)
        return audio
    
    def soft_clip(self, audio: np.ndarray, threshold: float = 0.95) -> np.ndarray:
        """软削波"""
        if not self.available or self._module is None:
            return self._fallback_soft_clip(audio, threshold)
        
        try:
            return self._wasm_soft_clip(audio, threshold)
        except Exception as e:
            logger.warning(f"WASM soft_clip failed: {e}, falling back")
            return self._fallback_soft_clip(audio, threshold)
    
    def _wasm_soft_clip(self, audio: np.ndarray, threshold: float) -> np.ndarray:
        """WASM 实现的软削波"""
        assert self._module is not None
        
        audio_float32 = audio.astype(np.float32).ravel()
        length = audio_float32.size
        
        ptr = self._module.alloc(length * 4)
        if ptr == 0:
            raise WasmRuntimeError("Failed to allocate WASM memory")
        
        try:
            self._module.write_memory(ptr, audio_float32.tobytes())
            self._module.call("soft_clip", ptr, length, threshold)
            result_bytes = self._module.read_memory(ptr, length * 4)
            result = np.frombuffer(result_bytes, dtype=np.float32)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)
    
    def _fallback_soft_clip(self, audio: np.ndarray, threshold: float) -> np.ndarray:
        """纯 Python 实现的软削波"""
        result = audio.copy()
        clip_region = np.abs(result) > threshold
        result[clip_region] = np.sign(result[clip_region]) * (
            threshold + (np.abs(result[clip_region]) - threshold) * 0.3
        )
        return result
