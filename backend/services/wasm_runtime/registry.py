"""
WASM 模块注册表

管理所有 WASM 算法模块的注册、发现和生命周期。
支持从指定目录自动扫描和加载 WASM 模块。
"""

import os
import glob
import hashlib
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .runtime import WasmRuntime, WasmModule, WasmModuleInfo, WasmRuntimeError

logger = logging.getLogger(__name__)


@dataclass
class ModuleManifest:
    """WASM 模块清单"""
    name: str
    version: str
    description: str = ""
    wasm_file: str = ""
    entry_point: str = "process"
    type: str = "dsp"  # dsp, detector, encoder, etc.
    required_exports: List[str] = field(default_factory=list)
    hash: str = ""


class WasmModuleRegistry:
    """
    WASM 模块注册表
    
    功能：
    - 从目录扫描 WASM 模块
    - 管理模块生命周期（加载/卸载/热更新）
    - 按类型查询模块
    """
    
    def __init__(self, runtime: Optional[WasmRuntime] = None):
        self._runtime = runtime or WasmRuntime.instance()
        self._modules: Dict[str, ModuleManifest] = {}
        self._search_paths: List[str] = []
    
    @property
    def available(self) -> bool:
        """WASM 运行时是否可用"""
        return self._runtime.available
    
    def add_search_path(self, path: str) -> None:
        """添加模块搜索路径"""
        if os.path.isdir(path) and path not in self._search_paths:
            self._search_paths.append(path)
            logger.info(f"Added WASM module search path: {path}")
    
    def scan_modules(self) -> List[ModuleManifest]:
        """
        扫描所有搜索路径，发现可用的 WASM 模块
        
        Returns:
            发现的模块列表
        """
        discovered = []
        
        for search_path in self._search_paths:
            if not os.path.isdir(search_path):
                continue
            
            for wasm_file in glob.glob(os.path.join(search_path, "*.wasm")):
                try:
                    manifest = self._parse_module(wasm_file)
                    if manifest:
                        if manifest.name not in self._modules:
                            self._modules[manifest.name] = manifest
                            discovered.append(manifest)
                            logger.info(f"Discovered WASM module: {manifest.name} v{manifest.version}")
                except Exception as e:
                    logger.warning(f"Failed to parse {wasm_file}: {e}")
        
        return discovered
    
    def _parse_module(self, wasm_file: str) -> Optional[ModuleManifest]:
        """解析 WASM 文件，提取模块信息"""
        file_name = os.path.basename(wasm_file)
        name = os.path.splitext(file_name)[0]
        
        file_size = os.path.getsize(wasm_file)
        
        with open(wasm_file, "rb") as f:
            data = f.read()
            file_hash = hashlib.sha256(data).hexdigest()[:16]
        
        manifest = ModuleManifest(
            name=name,
            version="0.1.0",
            wasm_file=wasm_file,
            type="dsp",
            hash=file_hash,
        )
        
        return manifest
    
    def load_module(self, name: str) -> WasmModule:
        """
        加载指定模块
        
        Args:
            name: 模块名称
            
        Returns:
            加载后的 WasmModule
            
        Raises:
            WasmRuntimeError: 模块不存在或加载失败
        """
        if not self.available:
            raise WasmRuntimeError("WASM runtime not available")
        
        manifest = self._modules.get(name)
        if not manifest:
            raise WasmRuntimeError(f"Module '{name}' not found in registry")
        
        existing = self._runtime.get_module(name)
        if existing and existing.info.hash == manifest.hash:
            return existing
        
        return self._runtime.load_module(
            name,
            manifest.wasm_file,
        )
    
    def unload_module(self, name: str) -> None:
        """卸载模块"""
        self._runtime.unload_module(name)
        if name in self._modules:
            del self._modules[name]
    
    def list_modules(self) -> List[ModuleManifest]:
        """列出所有已注册的模块"""
        return list(self._modules.values())
    
    def get_module_info(self, name: str) -> Optional[ModuleManifest]:
        """获取模块信息"""
        return self._modules.get(name)
    
    def reload_module(self, name: str) -> WasmModule:
        """
        热重载模块（支持运行时更新算法）
        
        先卸载旧模块，再重新加载新模块。
        """
        manifest = self._modules.get(name)
        if not manifest:
            raise WasmRuntimeError(f"Module '{name}' not found")
        
        self.unload_module(name)
        
        if os.path.exists(manifest.wasm_file):
            file_size = os.path.getsize(manifest.wasm_file)
            with open(manifest.wasm_file, "rb") as f:
                data = f.read()
                manifest.hash = hashlib.sha256(data).hexdigest()[:16]
        
        return self.load_module(name)
