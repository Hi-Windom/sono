"""
WebAssembly Runtime 核心实现

支持三种运行时后端，自动检测并降级：
1. WAMR (Bytecode Alliance) — 推荐用于嵌入式/移动设备
2. wasmtime (Bytecode Alliance) — 桌面/服务器高性能
3. disabled — 无 WASM 运行时，使用纯 Python fallback

所有后端提供统一的 WasmModule 接口。
"""

import os
import logging
from typing import Any, Callable, Dict, List, Optional
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
    memory_pages: int = 0


class WasmModule:
    """
    封装单个 WASM 模块，提供统一调用接口。

    底层可以是 WAMR、wasmtime 或其他运行时。
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
        self._backend: str = runtime.backend
        self._store = None
        self._instance = None
        self._exports: Dict[str, Callable] = {}
        self._memory = None
        self._mem_read: Optional[Callable] = None
        self._mem_write: Optional[Callable] = None

    @property
    def info(self) -> WasmModuleInfo:
        return self._info

    def call(self, func_name: str, *args: Any) -> Any:
        if not self._instance:
            raise WasmRuntimeError(f"Module '{self.name}' not instantiated")

        if func_name not in self._exports:
            raise WasmRuntimeError(
                f"Function '{func_name}' not found in module '{self.name}'. "
                f"Available: {list(self._exports.keys())}"
            )

        try:
            return self._exports[func_name](*args)
        except Exception as e:
            raise WasmRuntimeError(
                f"Failed to call '{func_name}' in '{self.name}': {e}"
            ) from e

    def read_memory(self, offset: int, length: int) -> bytes:
        if not self._mem_read:
            raise WasmRuntimeError(f"No memory in module '{self.name}'")
        return self._mem_read(offset, length)

    def write_memory(self, offset: int, data: bytes) -> None:
        if not self._mem_write:
            raise WasmRuntimeError(f"No memory in module '{self.name}'")
        self._mem_write(offset, data)

    def alloc(self, size: int) -> int:
        if "malloc" in self._exports:
            return int(self.call("malloc", size))
        raise WasmRuntimeError(f"Module '{self.name}' does not export 'malloc'")

    def free(self, ptr: int) -> None:
        if "free" in self._exports:
            self.call("free", ptr)


class WasmRuntime:
    """
    WebAssembly 运行时管理器。

    自动检测可用后端并初始化，优先级：WAMR > wasmtime > disabled
    单例模式，全局共享。
    """

    _instance: Optional["WasmRuntime"] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._modules: Dict[str, WasmModule] = {}
        self._backend: str = "none"
        self._backend_version: str = ""
        self._engine = None
        self._detect_backend()

    @classmethod
    def instance(cls) -> "WasmRuntime":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _detect_backend(self) -> None:
        backends = [
            ("wamr", self._init_wamr),
            ("wasmtime", self._init_wasmtime),
        ]
        for name, init_fn in backends:
            try:
                init_fn()
                self._backend = name
                logger.info(f"WASM runtime: {name} v{self._backend_version}")
                return
            except ImportError:
                continue
            except Exception as e:
                logger.warning(f"Failed to init {name}: {e}")
                continue

        self._backend = "disabled"
        logger.warning("No WASM runtime available (install wamr or wasmtime)")

    def _init_wamr(self) -> None:
        from wamr import WasmRuntime as WamrRuntime  # type: ignore
        self._engine = WamrRuntime()
        self._backend_version = "2.4.4"

    def _init_wasmtime(self) -> None:
        import wasmtime  # type: ignore
        self._engine = wasmtime.Engine()
        try:
            self._backend_version = wasmtime.__version__
        except AttributeError:
            self._backend_version = "unknown"

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def available(self) -> bool:
        return self._backend not in ("disabled", "none")

    def load_module(
        self,
        name: str,
        wasm_path: str,
        imports: Optional[Dict[str, Callable]] = None,
    ) -> WasmModule:
        if not self.available:
            raise WasmRuntimeError("No WASM runtime available")

        if not os.path.exists(wasm_path):
            raise WasmRuntimeError(f"WASM file not found: {wasm_path}")

        with open(wasm_path, "rb") as f:
            wasm_data = f.read()

        return self.load_module_from_bytes(name, wasm_data, imports)

    def load_module_from_bytes(
        self,
        name: str,
        wasm_data: bytes,
        imports: Optional[Dict[str, Callable]] = None,
    ) -> WasmModule:
        if not self.available:
            raise WasmRuntimeError("No WASM runtime available")

        if name in self._modules:
            logger.warning(f"Module '{name}' already loaded, reloading")

        module = self._create_module(name, wasm_data, imports or {})
        self._modules[name] = module

        logger.info(
            f"Loaded WASM module '{name}' "
            f"({len(wasm_data)} bytes, {self._backend})"
        )
        return module

    def _create_module(
        self,
        name: str,
        wasm_data: bytes,
        imports: Dict[str, Callable],
    ) -> WasmModule:
        module = WasmModule(name, wasm_data, self)
        module._info.size = len(wasm_data)

        if self._backend == "wamr":
            self._create_wamr(module, wasm_data, imports)
        elif self._backend == "wasmtime":
            self._create_wasmtime(module, wasm_data, imports)
        else:
            raise WasmRuntimeError(f"Unsupported backend: {self._backend}")

        return module

    def _create_wamr(
        self, module: WasmModule, wasm_data: bytes, imports: Dict[str, Callable]
    ) -> None:
        from wamr import WasmModule as WamrModule, WasmInstance  # type: ignore

        wamr_mod = WamrModule(wasm_data)
        import_obj = dict(imports)
        instance = WasmInstance(wamr_mod, import_obj)
        module._instance = instance

        for export_name in instance.exports:
            module._exports[export_name] = instance.exports[export_name]

        module._info.exports = list(module._exports.keys())

        if hasattr(instance, 'memory'):
            mem = instance.memory
            module._memory = mem
            module._mem_read = lambda off, sz: bytes(mem[off:off + sz])
            module._mem_write = lambda off, data: mem.__setitem__(
                slice(off, off + len(data)), data
            )

    def _create_wasmtime(
        self, module: WasmModule, wasm_data: bytes, imports: Dict[str, Callable]
    ) -> None:
        import wasmtime  # type: ignore

        store = wasmtime.Store(self._engine)
        wasm_mod = wasmtime.Module(self._engine, wasm_data)

        import_funcs = []
        for name, func in imports.items():
            import_funcs.append(wasmtime.Func(store, func))

        instance = wasmtime.Instance(store, wasm_mod, import_funcs)
        module._store = store
        module._instance = instance

        exports = instance.exports(store)

        for exp_type in wasm_mod.exports:
            name = exp_type.name
            try:
                value = exports[name]
            except Exception:
                continue

            if isinstance(value, wasmtime.Func):
                fn = value
                module._exports[name] = lambda *a, _fn=fn, _s=store: _fn(_s, *a)
            elif isinstance(value, wasmtime.Memory):
                module._memory = value
                mem = value
                module._mem_read = lambda off, sz, _m=mem, _s=store: _m.read(_s, off, off + sz)
                module._mem_write = lambda off, data, _m=mem, _s=store: _m.write(_s, data, off)
                module._info.memory_pages = mem.size(store)

        module._info.exports = list(module._exports.keys())

    def get_module(self, name: str) -> Optional[WasmModule]:
        return self._modules.get(name)

    def unload_module(self, name: str) -> None:
        if name in self._modules:
            del self._modules[name]
            logger.info(f"Unloaded WASM module '{name}'")

    def list_modules(self) -> List[str]:
        return list(self._modules.keys())

    def shutdown(self) -> None:
        for name in list(self._modules.keys()):
            self.unload_module(name)
        self._engine = None
        self._backend = "none"
        logger.info("WASM runtime shutdown")
