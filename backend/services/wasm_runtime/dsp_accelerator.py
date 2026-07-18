"""
WASM DSP 加速层

提供与 dsp_utils.py 兼容的 API，底层使用 WASM 模块加速。
当 WASM 运行时不可用时，自动回退到纯 Python (numpy) 实现。

使用方式：
    from services.wasm_runtime.dsp_accelerator import DspAccelerator

    dsp = DspAccelerator()
    output = dsp.apply_gain(audio_data, 3.0)  # +3dB
    print(f"Backend: {dsp.backend}")
"""

import logging
import numpy as np
from typing import Optional

from .runtime import WasmRuntime, WasmModule, WasmRuntimeError

logger = logging.getLogger(__name__)


class DspAccelerator:
    """
    DSP WASM 加速器。

    封装 WASM DSP 模块，提供与 Python 实现一致的接口。
    WASM 不可用时自动回退到纯 numpy 实现。
    """

    def __init__(self, runtime: Optional[WasmRuntime] = None):
        self._runtime = runtime or WasmRuntime.instance()
        self._module: Optional[WasmModule] = None
        self._fallback = not self._runtime.available

        if self._runtime.available:
            self._try_load_module()

    def _try_load_module(self) -> None:
        import os

        module_dir = os.path.join(os.path.dirname(__file__), "modules")
        candidates = [
            os.path.join(module_dir, "dsp_core.wasm"),
            os.path.join(module_dir, "dsp_example.wasm"),
        ]

        for path in candidates:
            if os.path.exists(path):
                try:
                    self._module = self._runtime.load_module("dsp_core", path)
                    logger.info(f"DSP WASM accelerator loaded: {path}")
                    self._fallback = False
                    return
                except Exception as e:
                    logger.warning(f"Failed to load DSP WASM from {path}: {e}")

        logger.info("DSP WASM module not found, using fallback (pure Python)")
        self._fallback = True

    @property
    def available(self) -> bool:
        return self._module is not None and not self._fallback

    @property
    def backend(self) -> str:
        if self.available:
            return f"wasm ({self._runtime.backend})"
        return "python (fallback)"

    def _wasm_call(self, func_name: str, *args) -> any:
        assert self._module is not None
        return self._module.call(func_name, *args)

    def _alloc_and_write(self, audio: np.ndarray) -> tuple:
        assert self._module is not None
        audio_f32 = np.ascontiguousarray(audio, dtype=np.float32).ravel()
        n_bytes = audio_f32.size * 4
        ptr = self._module.alloc(n_bytes)
        if ptr == 0:
            raise WasmRuntimeError("WASM memory allocation failed")
        self._module.write_memory(ptr, audio_f32.tobytes())
        return ptr, audio_f32.size

    def _read_floats(self, ptr: int, count: int) -> np.ndarray:
        assert self._module is not None
        data = self._module.read_memory(ptr, count * 4)
        return np.frombuffer(data, dtype=np.float32)

    def apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        if not self.available or self._module is None:
            return self._fallback_apply_gain(audio, gain_db)
        try:
            return self._wasm_apply_gain(audio, gain_db)
        except Exception as e:
            logger.warning(f"WASM apply_gain failed: {e}, fallback")
            return self._fallback_apply_gain(audio, gain_db)

    def _wasm_apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        ptr, n = self._alloc_and_write(audio)
        try:
            self._wasm_call("apply_gain", ptr, n, gain_db)
            result = self._read_floats(ptr, n)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)

    def _fallback_apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        return audio * (10.0 ** (gain_db / 20.0))

    def compute_rms(self, audio: np.ndarray) -> float:
        if not self.available or self._module is None:
            return self._fallback_compute_rms(audio)
        try:
            return self._wasm_compute_rms(audio)
        except Exception as e:
            logger.warning(f"WASM compute_rms failed: {e}, fallback")
            return self._fallback_compute_rms(audio)

    def _wasm_compute_rms(self, audio: np.ndarray) -> float:
        ptr, n = self._alloc_and_write(audio)
        try:
            return float(self._wasm_call("compute_rms", ptr, n))
        finally:
            self._module.free(ptr)

    def _fallback_compute_rms(self, audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio))))

    def compute_peak(self, audio: np.ndarray) -> float:
        if not self.available or self._module is None:
            return self._fallback_compute_peak(audio)
        try:
            return self._wasm_compute_peak(audio)
        except Exception as e:
            logger.warning(f"WASM compute_peak failed: {e}, fallback")
            return self._fallback_compute_peak(audio)

    def _wasm_compute_peak(self, audio: np.ndarray) -> float:
        ptr, n = self._alloc_and_write(audio)
        try:
            return float(self._wasm_call("compute_peak", ptr, n))
        finally:
            self._module.free(ptr)

    def _fallback_compute_peak(self, audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        return float(np.max(np.abs(audio)))

    def normalize(self, audio: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
        if not self.available or self._module is None:
            return self._fallback_normalize(audio, target_peak)
        try:
            return self._wasm_normalize(audio, target_peak)
        except Exception as e:
            logger.warning(f"WASM normalize failed: {e}, fallback")
            return self._fallback_normalize(audio, target_peak)

    def _wasm_normalize(self, audio: np.ndarray, target_peak: float) -> np.ndarray:
        ptr, n = self._alloc_and_write(audio)
        try:
            self._wasm_call("normalize", ptr, n, target_peak)
            result = self._read_floats(ptr, n)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)

    def _fallback_normalize(self, audio: np.ndarray, target_peak: float) -> np.ndarray:
        peak = np.max(np.abs(audio))
        if peak > 0:
            return audio * (target_peak / peak)
        return audio.copy()

    def soft_clip(self, audio: np.ndarray, threshold: float = 0.95) -> np.ndarray:
        if not self.available or self._module is None:
            return self._fallback_soft_clip(audio, threshold)
        try:
            return self._wasm_soft_clip(audio, threshold)
        except Exception as e:
            logger.warning(f"WASM soft_clip failed: {e}, fallback")
            return self._fallback_soft_clip(audio, threshold)

    def _wasm_soft_clip(self, audio: np.ndarray, threshold: float) -> np.ndarray:
        ptr, n = self._alloc_and_write(audio)
        try:
            self._wasm_call("soft_clip", ptr, n, threshold)
            result = self._read_floats(ptr, n)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)

    def _fallback_soft_clip(self, audio: np.ndarray, threshold: float) -> np.ndarray:
        result = audio.copy()
        mask = np.abs(result) > threshold
        result[mask] = np.sign(result[mask]) * (
            threshold + (np.abs(result[mask]) - threshold) * 0.3
        )
        return result

    def remove_dc(self, audio: np.ndarray) -> np.ndarray:
        if not self.available or self._module is None:
            return self._fallback_remove_dc(audio)
        try:
            return self._wasm_remove_dc(audio)
        except Exception as e:
            logger.warning(f"WASM remove_dc failed: {e}, fallback")
            return self._fallback_remove_dc(audio)

    def _wasm_remove_dc(self, audio: np.ndarray) -> np.ndarray:
        ptr, n = self._alloc_and_write(audio)
        try:
            self._wasm_call("remove_dc", ptr, n)
            result = self._read_floats(ptr, n)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)

    def _fallback_remove_dc(self, audio: np.ndarray) -> np.ndarray:
        return audio - np.mean(audio)

    def fade_in(self, audio: np.ndarray, fade_samples: int) -> np.ndarray:
        if not self.available or self._module is None:
            return self._fallback_fade_in(audio, fade_samples)
        try:
            return self._wasm_fade_in(audio, fade_samples)
        except Exception as e:
            logger.warning(f"WASM fade_in failed: {e}, fallback")
            return self._fallback_fade_in(audio, fade_samples)

    def _wasm_fade_in(self, audio: np.ndarray, fade_samples: int) -> np.ndarray:
        ptr, n = self._alloc_and_write(audio)
        try:
            self._wasm_call("fade_in", ptr, n, fade_samples)
            result = self._read_floats(ptr, n)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)

    def _fallback_fade_in(self, audio: np.ndarray, fade_samples: int) -> np.ndarray:
        result = audio.copy()
        n = min(fade_samples, result.shape[-1])
        fade = np.linspace(0, 1, n, dtype=result.dtype)
        if result.ndim == 1:
            result[:n] *= fade
        else:
            result[:, :n] *= fade
        return result

    def fade_out(self, audio: np.ndarray, fade_samples: int) -> np.ndarray:
        if not self.available or self._module is None:
            return self._fallback_fade_out(audio, fade_samples)
        try:
            return self._wasm_fade_out(audio, fade_samples)
        except Exception as e:
            logger.warning(f"WASM fade_out failed: {e}, fallback")
            return self._fallback_fade_out(audio, fade_samples)

    def _wasm_fade_out(self, audio: np.ndarray, fade_samples: int) -> np.ndarray:
        ptr, n = self._alloc_and_write(audio)
        try:
            self._wasm_call("fade_out", ptr, n, fade_samples)
            result = self._read_floats(ptr, n)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)

    def _fallback_fade_out(self, audio: np.ndarray, fade_samples: int) -> np.ndarray:
        result = audio.copy()
        n = min(fade_samples, result.shape[-1])
        fade = np.linspace(1, 0, n, dtype=result.dtype)
        if result.ndim == 1:
            result[-n:] *= fade
        else:
            result[:, -n:] *= fade
        return result

    def low_pass_filter(
        self, audio: np.ndarray, sample_rate: float, cutoff_freq: float
    ) -> np.ndarray:
        if not self.available or self._module is None:
            return self._fallback_low_pass(audio, sample_rate, cutoff_freq)
        try:
            return self._wasm_low_pass(audio, sample_rate, cutoff_freq)
        except Exception as e:
            logger.warning(f"WASM low_pass_filter failed: {e}, fallback")
            return self._fallback_low_pass(audio, sample_rate, cutoff_freq)

    def _wasm_low_pass(
        self, audio: np.ndarray, sample_rate: float, cutoff_freq: float
    ) -> np.ndarray:
        ptr, n = self._alloc_and_write(audio)
        lpf_ptr = self._module.alloc(8)
        try:
            self._wasm_call("lpf_init", lpf_ptr, sample_rate, cutoff_freq)
            self._wasm_call("lpf_process", lpf_ptr, ptr, n)
            result = self._read_floats(ptr, n)
            return result.reshape(audio.shape).astype(audio.dtype)
        finally:
            self._module.free(ptr)
            self._module.free(lpf_ptr)

    def _fallback_low_pass(
        self, audio: np.ndarray, sample_rate: float, cutoff_freq: float
    ) -> np.ndarray:
        dt = 1.0 / sample_rate
        rc = 1.0 / (2.0 * np.pi * cutoff_freq)
        alpha = dt / (rc + dt)
        result = np.zeros_like(audio)
        y = 0.0
        flat = audio.ravel()
        out_flat = result.ravel()
        for i in range(len(flat)):
            y = y + alpha * (flat[i] - y)
            out_flat[i] = y
        return result
