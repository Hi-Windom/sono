"""
WASM 模块管理 API

提供 WASM 算法模块的上传、列表查询、加载和卸载接口。
支持运行时热更新 DSP 算法，无需重启服务。
"""

import os
import hashlib
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel

from services.wasm_runtime import WasmRuntime, WasmModuleRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wasm", tags=["wasm"])

MODULE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "services",
    "wasm_runtime",
    "modules",
)

_runtime: WasmRuntime | None = None
_registry: WasmModuleRegistry | None = None


def _get_runtime() -> WasmRuntime:
    global _runtime
    if _runtime is None:
        _runtime = WasmRuntime.instance()
    return _runtime


def _get_registry() -> WasmModuleRegistry:
    global _registry
    if _registry is None:
        _registry = WasmModuleRegistry()
        os.makedirs(MODULE_DIR, exist_ok=True)
        _registry.add_search_path(MODULE_DIR)
        _registry.scan_modules()
    return _registry


class WasmModuleInfo(BaseModel):
    name: str
    version: str
    description: str = ""
    wasm_file: str = ""
    type: str = "dsp"
    size: int = 0
    hash: str = ""
    loaded: bool = False
    exports: List[str] = []


class WasmStatusResponse(BaseModel):
    available: bool
    backend: str
    backend_version: str = ""
    modules: List[WasmModuleInfo]


@router.get("/status", response_model=WasmStatusResponse)
async def get_wasm_status():
    """获取 WASM 运行时状态"""
    runtime = _get_runtime()
    registry = _get_registry()
    
    modules = []
    for manifest in registry.list_modules():
        loaded = runtime.get_module(manifest.name) is not None
        exports = []
        if loaded:
            mod = runtime.get_module(manifest.name)
            if mod:
                exports = mod.info.exports
        
        modules.append(WasmModuleInfo(
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            wasm_file=manifest.wasm_file,
            type=manifest.type,
            size=os.path.getsize(manifest.wasm_file) if os.path.exists(manifest.wasm_file) else 0,
            hash=manifest.hash,
            loaded=loaded,
            exports=exports,
        ))
    
    return WasmStatusResponse(
        available=runtime.available,
        backend=runtime.backend,
        backend_version="",
        modules=modules,
    )


@router.get("/modules")
async def list_modules():
    """列出所有 WASM 模块"""
    registry = _get_registry()
    runtime = _get_runtime()
    
    result = []
    for manifest in registry.list_modules():
        loaded = runtime.get_module(manifest.name) is not None
        result.append({
            "name": manifest.name,
            "version": manifest.version,
            "type": manifest.type,
            "size": os.path.getsize(manifest.wasm_file) if os.path.exists(manifest.wasm_file) else 0,
            "hash": manifest.hash,
            "loaded": loaded,
        })
    
    return {"modules": result}


@router.post("/upload")
async def upload_wasm_module(
    file: UploadFile = File(...),
    module_name: str = Form(None),
):
    """
    上传 WASM 模块
    
    上传后模块会被保存到 modules 目录，并自动注册。
    """
    if not file.filename or not file.filename.endswith('.wasm'):
        raise HTTPException(status_code=400, detail="Only .wasm files are allowed")
    
    os.makedirs(MODULE_DIR, exist_ok=True)
    
    raw_name = module_name or os.path.splitext(file.filename)[0]
    safe_name = os.path.basename(raw_name)
    if not safe_name or safe_name != raw_name:
        raise HTTPException(status_code=400, detail="Invalid module name")
    if not safe_name.replace('_', '').replace('-', '').isalnum():
        raise HTTPException(status_code=400, detail="Module name must contain only letters, numbers, underscores, and hyphens")
    
    file_path = os.path.join(MODULE_DIR, f"{safe_name}.wasm")
    real_path = os.path.realpath(file_path)
    real_module_dir = os.path.realpath(MODULE_DIR)
    if not real_path.startswith(real_module_dir + os.sep):
        raise HTTPException(status_code=400, detail="Path traversal detected")
    
    content = await file.read()
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    file_hash = hashlib.sha256(content).hexdigest()[:16]
    
    registry = _get_registry()
    registry.scan_modules()
    
    logger.info(f"WASM module uploaded: {safe_name} ({len(content)} bytes, hash={file_hash})")
    
    return {
        "success": True,
        "name": safe_name,
        "size": len(content),
        "hash": file_hash,
        "path": file_path,
    }


@router.post("/modules/{name}/load")
async def load_module(name: str):
    """加载指定的 WASM 模块"""
    registry = _get_registry()
    
    try:
        module = registry.load_module(name)
        return {
            "success": True,
            "name": name,
            "exports": module.info.exports,
            "message": f"Module '{name}' loaded successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load module: {e}")


@router.post("/modules/{name}/unload")
async def unload_module(name: str):
    """卸载指定的 WASM 模块"""
    registry = _get_registry()
    registry.unload_module(name)
    
    return {
        "success": True,
        "name": name,
        "message": f"Module '{name}' unloaded successfully",
    }


@router.post("/modules/{name}/reload")
async def reload_module(name: str):
    """
    热重载 WASM 模块
    
    用于运行时更新算法，无需重启服务。
    """
    registry = _get_registry()
    
    try:
        module = registry.reload_module(name)
        return {
            "success": True,
            "name": name,
            "exports": module.info.exports,
            "message": f"Module '{name}' reloaded successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload module: {e}")


@router.delete("/modules/{name}")
async def delete_module(name: str):
    """删除 WASM 模块文件"""
    registry = _get_registry()
    
    manifest = registry.get_module_info(name)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Module '{name}' not found")
    
    try:
        registry.unload_module(name)
    except Exception:
        pass
    
    try:
        if os.path.exists(manifest.wasm_file):
            os.remove(manifest.wasm_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete module file: {e}")
    
    return {
        "success": True,
        "name": name,
        "message": f"Module '{name}' deleted successfully",
    }
