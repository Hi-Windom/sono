"""
调试修复模块：用指定版本的完全一致参数跑一遍完整修复流程，
在每个处理阶段后保存中间结果，用于验证管线各环节逻辑是否正确。
"""
import os
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_debug_repair(input_path: str, output_dir: str, algorithm_version: str | None = None,
                     progress_callback: Any = None) -> dict:
    """
    用相同版本、相同参数跑一遍 repair_audio，每个处理阶段后保存中间 .wav，
    用于逐阶段验证管线逻辑。

    algorithm_version: 要调试的单个算法版本名，如 "v4.0a+"；None=使用默认版本
    """
    from services.audio_repair import ALGORITHM_VERSIONS, _get_repair_fn

    if not algorithm_version or algorithm_version not in ALGORITHM_VERSIONS:
        from services.audio_repair import DEFAULT_VERSION
        algorithm_version = DEFAULT_VERSION

    ver_info = ALGORITHM_VERSIONS[algorithm_version]
    default_params = ver_info.get("default_params", {})

    logger.info(f"[debug] 开始调试修复: {input_path} 版本={algorithm_version}")
    os.makedirs(output_dir, exist_ok=True)

    prefix = os.path.splitext(os.path.basename(input_path))[0]

    # 构造参数：版本+默认参数+debug输出目录（所有参数完全一致，仅注入调试目录）
    params: dict[str, Any] = {
        "algorithm_version": algorithm_version,
        **default_params,
    }
    # 注入调试输出目录（管线各阶段会把中间结果写入此目录）
    params["_debug_output_dir"] = output_dir

    repair_fn = _get_repair_fn(ver_info.get("repair_version", algorithm_version))
    if not repair_fn:
        raise RuntimeError(f"版本 {algorithm_version} 的修复函数加载失败")

    start = time.time()

    # 最终输出文件（正常修复结果）也放到 debug 目录
    final_output = os.path.join(output_dir, f"{prefix}_final.wav")

    try:
        result = repair_fn(input_path, final_output, params, progress_callback)
        elapsed = time.time() - start

        # 扫描调试目录中管线保存的所有中间 .wav 文件（按文件名排序）
        intermediates = sorted(
            [f for f in os.listdir(output_dir) if f.endswith(".wav")],
        )

        # 构造结果列表：每个文件一个条目
        results = []
        for fname in intermediates:
            fpath = os.path.join(output_dir, fname)
            try:
                import soundfile as sf
                info = sf.info(fpath)
                duration = round(info.duration, 2) if info.duration else 0
            except Exception:
                duration = 0

            # 从文件名提取阶段标签
            # 格式: NN_keyname.wav 或 99_mastering.wav 或 prefix_final.wav
            stem = os.path.splitext(fname)[0]
            if fname.startswith(f"{prefix}_"):
                label = "最终输出"
            elif stem.startswith("99_"):
                label = f"母带 ({stem[3:]})"
            else:
                # NN_keyname
                parts = stem.split("_", 1)
                if len(parts) == 2:
                    label = parts[1]
                else:
                    label = stem

            results.append({
                "version": algorithm_version,
                "filename": fname,
                "label": label,
                "ok": True,
                "duration_ms": round(elapsed * 1000),
                "rms": 0,
                "peak": 0,
                "file_duration_sec": duration,
            })

        logger.info(f"[debug] {algorithm_version} 完成 ({elapsed:.1f}s), 中间文件={len(results)}")

        return {
            "algorithm_version": algorithm_version,
            "input": os.path.basename(input_path),
            "output_dir": output_dir,
            "total": len(results),
            "success": len(results),
            "failed": 0,
            "results": results,
        }

    except Exception as e:
        elapsed = time.time() - start
        logger.warning(f"[debug] {algorithm_version} 失败: {e}")
        return {
            "algorithm_version": algorithm_version,
            "input": os.path.basename(input_path),
            "output_dir": output_dir,
            "total": 0,
            "success": 0,
            "failed": 1,
            "results": [{
                "version": algorithm_version,
                "filename": None,
                "label": "失败",
                "ok": False,
                "duration_ms": round(elapsed * 1000),
                "rms": 0,
                "peak": 0,
                "error": str(e),
            }],
        }
