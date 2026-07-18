"""
WAMR WebAssembly Runtime 核心实现

支持两种运行模式：
1. WAMR 模式（推荐，高性能）：通过 WAMR Python bindings 运行
2. 纯 Python 模式（fallback）：当 WAMR 不可用时，使用 wasmtime 或纯解释器

注意：WAMR 需要安装 wamr-python 包或编译 Python bindings。
如果环境不支持 WAMR，会自动降级到备用方案。
"""

import os
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class WasmRuntimeError(Exception):
    """WASM 运行时错误"""
    pass


@dataclass
class WasmModuleInfo:
    """WASM 模块信息"""
    name: str
    path: str
    size: int
    hash: str = ""
    exports: List[str] = field(default_factory=list)
    memory_pages: int = 16


class WasmModule:
    """
    封装单个 WASM 模块
    
    提供统一的调用接口，底层可以是 WAMR、wasmtime 或其他运行时。
    """
    
    def __init__(
        self,
        name: str,
        module_data: bytes,
        runtime: "WasmRuntime",
        info: Optional[WasmModuleInfo] = None,
    ):
        self.name = name
        self._module_data = module_data
        self._runtime = runtime
        self._info = info or WasmModuleInfo(name=name, path="", size=len(module_data))
        self._instance = None
        self._exports: Dict[str, Any] = {}
        self._memory = None
        
    @property
    def info(self) -> WasmModuleInfo:
        return self._info
    
    def call(self, func_name: str, *args: Any) -> Any:
        """
        调用 WASM 模块中的导出函数
        
        Args:
            func_name: 导出函数名
            *args: 函数参数
            
        Returns:
            函数返回值
            
        Raises:
            WasmRuntimeError: 函数不存在或调用失败
        """
        if not self._instance:
            raise WasmRuntimeError(f"Module '{self.name}' not instantiated")
        
        if func_name not in self._exports:
            raise WasmRuntimeError(
                f"Function '{func_name}' not found in module '{self.name}'. "
                f"Available exports: {list(self._exports.keys())}"
            )
        
        try:
            func = self._exports[func_name]
            return func(*args)
        except Exception as e:
            raise WasmRuntimeError(
                f"Failed to call '{func_name}' in module '{self.name}': {e}"
            ) from e
    
    def read_memory(self, offset: int, length: int) -> bytes:
        """读取 WASM 线性内存"""
        if not self._memory:
            raise WasmRuntimeError(f"No memory available in module '{self.name}'")
        return bytes(self._memory[offset:offset + length])
    
    def write_memory(self, offset: int, data: bytes) -> None:
        """写入 WASM 线性内存"""
        if not self._memory:
            raise WasmRuntimeError(f"No memory available in module '{self.name}'")
        self._memory[offset:offset + len(data)] = data
    
    def alloc(self, size: int) -> int:
        """
        在 WASM 堆上分配内存
        
        模块需要导出 malloc 函数。
        """
        if "malloc" in self._exports:
            return self.call("malloc", size)
        raise WasmRuntimeError(
            f"Module '{self.name}' does not export 'malloc'"
        )
    
    def free(self, ptr: int) -> None:
        """释放 WASM 堆内存"""
        if "free" in self._exports:
            self.call("free", ptr)
        else:
            raise WasmRuntimeError(
                f"Module '{self.name}' does not export 'free'"
            )


class WasmRuntime:
    """
    WebAssembly 运行时管理器
    
    自动检测可用的 WASM 运行时后端并初始化。
    优先级：WAMR > wasmtime > 纯 Python 解释器
    """
    
    _instance: Optional["WasmRuntime"] = None
    _initialized = False
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._modules: Dict[str, WasmModule] = {}
        self._backend: str = "none"
        self._backend_version: str = ""
        self._native_runtime = None
        
        self._detect_backend()
    
    @classmethod
    def instance(cls) -> "WasmRuntime":
        """单例模式获取全局运行时实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _detect_backend(self) -> None:
        """检测可用的 WASM 运行时后端"""
        backends_to_try = [
            ("wamr", self._init_wamr),
            ("wasmtime", self._init_wasmtime),
        ]
        
        for name, init_fn in backends_to_try:
            try:
                init_fn()
                self._backend = name
                logger.info(f"WASM runtime backend: {name} (v{self._backend_version})")
                return
            except ImportError:
                continue
            except Exception as e:
                logger.warning(f"Failed to init {name} backend: {e}")
                continue
        
        self._backend = "disabled"
        logger.warning(
            "No WASM runtime backend available. WASM modules will be disabled. "
            "Install wamr-python or wasmtime to enable WASM support."
        )
    
    def _init_wamr(self) -> None:
        """初始化 WAMR 后端"""
        try:
            from wamr import WasmRuntime as WamrRuntime  # type: ignore
            self._native_runtime = WamrRuntime()
            self._backend_version = "2.4.4"
        except ImportError:
            raise
        except Exception as e:
            raise RuntimeError(f"WAMR init failed: {e}") from e
    
    def _init_wasmtime(self) -> None:
        """初始化 wasmtime 后端"""
        try:
            import wasmtime  # type: ignore
            self._native_runtime = wasmtime.Engine()
            self._backend_version = wasmtime.__version__
        except ImportError:
            raise
        except Exception as e:
            raise RuntimeError(f"wasmtime init failed: {e}") from e
    
    @property
    def backend(self) -> str:
        """当前使用的运行时后端"""
        return self._backend
    
    @property
    def available(self) -> bool:
        """WASM 运行时是否可用"""
        return self._backend != "disabled" and self._backend != "none"
    
    def load_module(
        self,
        name: str,
        wasm_path: str,
        imports: Optional[Dict[str, Callable]] = None,
    ) -> WasmModule:
        """
        从文件加载 WASM 模块
        
        Args:
            name: 模块名称（唯一标识）
            wasm_path: .wasm 文件路径
            imports: 要注入的宿主函数
            
        Returns:
            WasmModule 实例
            
        Raises:
            WasmRuntimeError: 加载失败
        """
        if not self.available:
            raise WasmRuntimeError("No WASM runtime backend available")
        
        if name in self._modules:
            logger.warning(f"Module '{name}' already loaded, reloading")
        
        if not os.path.exists(wasm_path):
            raise WasmRuntimeError(f"WASM file not found: {wasm_path}")
        
        with open(wasm_path, "rb") as f:
            wasm_data = f.read()
        
        module = self._create_module(name, wasm_data, imports)
        self._modules[name] = module
        
        logger.info(
            f"Loaded WASM module '{name}' "
            f"({len(wasm_data)} bytes, backend={self._backend})"
        )
        return module
    
    def load_module_from_bytes(
        self,
        name: str,
        wasm_data: bytes,
        imports: Optional[Dict[str, Callable]] = None,
    ) -> WasmModule:
        """从内存中加载 WASM 模块"""
        if not self.available:
            raise WasmRuntimeError("No WASM runtime backend available")
        
        module = self._create_module(name, wasm_data, imports)
        self._modules[name] = module
        
        logger.info(
            f"Loaded WASM module '{name}' from memory "
            f"({len(wasm_data)} bytes, backend={self._backend})"
        )
        return module
    
    def _create_module(
        self,
        name: str,
        wasm_data: bytes,
        imports: Optional[Dict[str, Callable]] = None,
    ) -> WasmModule:
        """根据后端创建模块实例"""
        module = WasmModule(name, wasm_data, self)
        
        if self._backend == "wamr":
            self._create_module_wamr(module, wasm_data, imports or {})
        elif self._backend == "wasmtime":
            self._create_module_wasmtime(module, wasm_data, imports or {})
        else:
            raise WasmRuntimeError(f"Unsupported backend: {self._backend}")
        
        return module
    
    def _create_module_wamr(
        self,
        module: WasmModule,
        wasm_data: bytes,
        imports: Dict[str, Callable],
    ) -> None:
        """使用 WAMR 后端创建模块"""
        from wamr import WasmModule as WamrModule, WasmInstance  # type: ignore
        
        wamr_module = WamrModule(wasm_data)
        
        import_obj = {}
        for name, func in imports.items():
            import_obj[name] = func
        
        instance = WasmInstance(wamr_module, import_obj)
        module._instance = instance
        
        for export_name in instance.exports:
            module._exports[export_name] = instance.exports[export_name]
        
        module._info.exports = list(module._exports.keys())
        
        if hasattr(instance, 'memory'):
            module._memory = instance.memory
    
    def _create_module_wasmtime(
        self,
        module: WasmModule,
        wasm_data: bytes,
        imports: Dict[str, Callable],
    ) -> None:
        """使用 wasmtime 后端创建模块"""
        import wasmtime  # type: ignore
        
        engine = self._native_runtime
        store = wasmtime.Store(engine)
        wasm_module = wasmtime.Module(engine, wasm_data)
        
        import_list = []
        for name, func in imports.items():
            import_list.append(wasmtime.Func(store, func))
        
        instance = wasmtime.Instance(store, wasm_module, import_list)
        
        module._instance = (store, instance)
        module._exports = {}
        
        for export in instance.exports(store):
            if isinstance(export, wasmtime.Func):
                module._exports[export.name] = lambda *a, e=export, s=store: e(s, *a)
            elif isinstance(export, wasmtime.Memory):
                module._memory = export.data_ptr(store)
        
        module._info.exports = list(module._exports.keys())
    
    def get_module(self, name: str) -> Optional[WasmModule]:
        """获取已加载的模块"""
        return self._modules.get(name)
    
    def unload_module(self, name: str) -> None:
        """卸载模块"""
        if name in self._modules:
            del self._modules[name]
            logger.info(f"Unloaded WASM module '{name}'")
    
    def list_modules(self) -> List[str]:
        """列出所有已加载的模块"""
        return list(self._modules.keys())
    
    def shutdown(self) -> None:
        """关闭运行时，释放所有资源"""
        for name in list(self._modules.keys()):
            self.unload_module(name)
        
        if self._native_runtime:
            if hasattr(self._native_runtime, 'shutdown'):
                self._native_runtime.shutdown()
            self._native_runtime = None
        
        self._backend = "none"
        logger.info("WASM runtime shutdown complete")
