"""
WASM Runtime - WebAssembly Micro Runtime (WAMR) 集成模块

提供基于 WAMR 的 WebAssembly 运行时，用于加载和执行编译为 Wasm 的 DSP 算法。

架构设计：
- 后端 Python 通过 WAMR Python bindings 运行 Wasm 模块
- 浏览器端直接使用原生 WebAssembly API
- 同一套 Wasm 算法可在多平台运行（桌面/Android/浏览器）
- 支持热加载算法模块，无需重启服务

使用方式：
    from backend.services.wasm_runtime import WasmRuntime, WasmModule
    
    runtime = WasmRuntime()
    module = runtime.load_module("path/to/algorithm.wasm")
    result = module.call("process", input_data)
"""

from .runtime import WasmRuntime, WasmModule, WasmRuntimeError
from .registry import WasmModuleRegistry
from .dsp_accelerator import DspAccelerator

__all__ = [
    "WasmRuntime",
    "WasmModule",
    "WasmRuntimeError",
    "WasmModuleRegistry",
    "DspAccelerator",
]
