from __future__ import annotations

from typing import Any

from services.repair_registry import (
    _REPAIR_MODULES,
    _REPAIR_FN_CACHE,
    _get_repair_fn,
    PARAM_DEFINITIONS,
    ALGORITHM_VERSIONS,
    DEFAULT_VERSION,
    get_available_versions,
)


def repair_audio(input_path: str, output_path: str, params: dict[str, Any], progress_callback: Any = None, mobile_mode: bool = False) -> dict[str, Any]:
    version = params.get("algorithm_version", DEFAULT_VERSION)
    version_info = ALGORITHM_VERSIONS.get(version)
    if not version_info:
        version_info = ALGORITHM_VERSIONS[DEFAULT_VERSION]
    
    if mobile_mode and not version_info.get("mobile_compatible", True):
        raise ValueError(f"算法版本 {version} 不支持移动端，请使用 v2.0")
    
    repair_fn = _get_repair_fn(version_info["repair_version"])
    if not repair_fn:
        raise ValueError(f"算法版本 {version} 加载失败")
    return repair_fn(input_path, output_path, params, progress_callback)
