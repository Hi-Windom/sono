"""
WASM 运行时单元测试

测试 WASM 运行时的核心功能，包括：
- 运行时初始化和后端检测
- 模块加载和调用
- 注册表功能
- DSP 加速器 fallback 模式
"""

import os
import sys
import tempfile
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.services.wasm_runtime.runtime import (
    WasmRuntime,
    WasmModule,
    WasmRuntimeError,
    WasmModuleInfo,
)
from backend.services.wasm_runtime.registry import (
    WasmModuleRegistry,
    ModuleManifest,
)
from backend.services.wasm_runtime.dsp_accelerator import DspAccelerator


class TestWasmRuntime:
    """WASM 运行时测试"""
    
    def test_runtime_instance_creation(self):
        """测试运行时创建"""
        runtime = WasmRuntime()
        assert runtime.backend in ('disabled', 'wamr', 'wasmtime', 'none')
        assert isinstance(runtime.available, bool)
    
    def test_runtime_singleton(self):
        """测试单例模式"""
        rt1 = WasmRuntime.instance()
        rt2 = WasmRuntime.instance()
        assert rt1 is rt2
    
    def test_runtime_list_modules_empty(self):
        """测试空模块列表"""
        runtime = WasmRuntime()
        modules = runtime.list_modules()
        assert isinstance(modules, list)
    
    def test_load_nonexistent_module_raises(self):
        """测试加载不存在的文件"""
        runtime = WasmRuntime()
        if not runtime.available:
            pytest.skip("WASM runtime not available")
        
        with pytest.raises(WasmRuntimeError):
            runtime.load_module("nonexistent", "/nonexistent/path.wasm")
    
    def test_get_nonexistent_module_returns_none(self):
        """测试获取不存在的模块"""
        runtime = WasmRuntime()
        assert runtime.get_module("nonexistent") is None
    
    def test_unload_nonexistent_module_safe(self):
        """测试卸载不存在的模块不会报错"""
        runtime = WasmRuntime()
        runtime.unload_module("nonexistent")  # 不抛异常


class TestWasmModuleInfo:
    """WASM 模块信息测试"""
    
    def test_module_info_creation(self):
        """测试模块信息创建"""
        info = WasmModuleInfo(
            name="test_module",
            path="/path/to/test.wasm",
            size=1024,
        )
        assert info.name == "test_module"
        assert info.size == 1024
        assert info.memory_pages == 16
        assert isinstance(info.exports, list)
    
    def test_module_info_with_exports(self):
        """测试带导出函数的模块信息"""
        info = WasmModuleInfo(
            name="dsp",
            path="dsp.wasm",
            size=2048,
            exports=["process", "malloc", "free"],
        )
        assert len(info.exports) == 3
        assert "process" in info.exports


class TestWasmModuleRegistry:
    """WASM 模块注册表测试"""
    
    def test_registry_creation(self):
        """测试注册表创建"""
        registry = WasmModuleRegistry()
        assert isinstance(registry.available, bool)
    
    def test_add_search_path(self):
        """测试添加搜索路径"""
        registry = WasmModuleRegistry()
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.add_search_path(tmpdir)
            assert tmpdir in registry._search_paths
    
    def test_scan_empty_directory(self):
        """测试扫描空目录"""
        registry = WasmModuleRegistry()
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.add_search_path(tmpdir)
            discovered = registry.scan_modules()
            assert len(discovered) == 0
    
    def test_list_modules_empty(self):
        """测试空模块列表"""
        registry = WasmModuleRegistry()
        modules = registry.list_modules()
        assert isinstance(modules, list)
    
    def test_get_nonexistent_module_info(self):
        """测试获取不存在的模块信息"""
        registry = WasmModuleRegistry()
        assert registry.get_module_info("nonexistent") is None


class TestModuleManifest:
    """模块清单测试"""
    
    def test_manifest_creation(self):
        """测试清单创建"""
        manifest = ModuleManifest(
            name="test_dsp",
            version="1.0.0",
            description="Test DSP module",
            type="dsp",
        )
        assert manifest.name == "test_dsp"
        assert manifest.version == "1.0.0"
        assert manifest.type == "dsp"
    
    def test_manifest_default_values(self):
        """测试默认值"""
        manifest = ModuleManifest(name="test", version="0.1")
        assert manifest.description == ""
        assert manifest.type == "dsp"
        assert isinstance(manifest.required_exports, list)


class TestDspAccelerator:
    """DSP 加速器测试（主要测试 fallback 模式）"""
    
    def test_accelerator_creation(self):
        """测试加速器创建"""
        dsp = DspAccelerator()
        assert isinstance(dsp.available, bool)
        assert isinstance(dsp.backend, str)
    
    def test_apply_gain_fallback(self):
        """测试增益处理（fallback 模式）"""
        dsp = DspAccelerator()
        audio = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)
        
        result = dsp.apply_gain(audio, 6.0)
        
        assert len(result) == len(audio)
        assert result.dtype == audio.dtype
        # +6dB 约等于 2x 增益
        expected = audio * (10 ** (6.0 / 20.0))
        np.testing.assert_allclose(result, expected, rtol=1e-5)
    
    def test_apply_gain_zero_db(self):
        """测试 0dB 增益（无变化）"""
        dsp = DspAccelerator()
        audio = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)
        
        result = dsp.apply_gain(audio, 0.0)
        
        np.testing.assert_allclose(result, audio, rtol=1e-5)
    
    def test_apply_gain_negative_db(self):
        """测试负增益（衰减）"""
        dsp = DspAccelerator()
        audio = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        
        result = dsp.apply_gain(audio, -6.0)
        
        assert np.all(result < 0.5)  # 衰减后应该更小
    
    def test_compute_rms_fallback(self):
        """测试 RMS 计算（fallback 模式）"""
        dsp = DspAccelerator()
        audio = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        
        rms = dsp.compute_rms(audio)
        
        assert rms == pytest.approx(1.0, rel=1e-5)
    
    def test_compute_rms_silence(self):
        """测试静音 RMS"""
        dsp = DspAccelerator()
        audio = np.zeros(1000, dtype=np.float32)
        
        rms = dsp.compute_rms(audio)
        
        assert rms == pytest.approx(0.0, abs=1e-10)
    
    def test_compute_rms_empty(self):
        """测试空数组 RMS"""
        dsp = DspAccelerator()
        audio = np.array([], dtype=np.float32)
        
        rms = dsp.compute_rms(audio)
        
        assert rms == 0.0
    
    def test_normalize_fallback(self):
        """测试归一化（fallback 模式）"""
        dsp = DspAccelerator()
        audio = np.array([0.1, 0.2, 0.5, 0.3, 0.2], dtype=np.float32)
        
        result = dsp.normalize(audio, 0.95)
        
        peak = np.max(np.abs(result))
        assert peak == pytest.approx(0.95, rel=1e-5)
    
    def test_normalize_silence(self):
        """测试静音归一化（不崩溃）"""
        dsp = DspAccelerator()
        audio = np.zeros(100, dtype=np.float32)
        
        result = dsp.normalize(audio, 0.95)
        
        assert np.all(result == 0.0)
    
    def test_soft_clip_fallback(self):
        """测试软削波（fallback 模式）"""
        dsp = DspAccelerator()
        audio = np.array([0.5, 0.9, 1.0, 1.5, -0.8, -1.2], dtype=np.float32)
        
        result = dsp.soft_clip(audio, 0.95)
        
        assert len(result) == len(audio)
        # 大于阈值的应该被压缩
        assert np.max(result) < 1.5
        assert np.min(result) > -1.2
    
    def test_soft_clip_below_threshold(self):
        """测试低于阈值的信号不被改变"""
        dsp = DspAccelerator()
        audio = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        
        result = dsp.soft_clip(audio, 0.95)
        
        np.testing.assert_allclose(result, audio, rtol=1e-5)
    
    def test_stereo_audio_apply_gain(self):
        """测试立体声增益处理"""
        dsp = DspAccelerator()
        audio = np.random.randn(2, 100).astype(np.float32) * 0.5
        
        result = dsp.apply_gain(audio, 3.0)
        
        assert result.shape == audio.shape
        assert result.dtype == audio.dtype
