import os
import json
import logging
import shutil
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import UPLOAD_DIR, OUTPUT_DIR
from database import create_task, get_task, find_task_by_hash, update_task
from services.task_manager import generate_task_id, submit_repair_task, can_accept_task, cancel_task
from services.param_maps import flatten_vocal_params, flatten_inst_params

logger = logging.getLogger(__name__)

router = APIRouter()


class RepairRequest(BaseModel):
    task_id: str
    params: dict


class DualRepairRequest(BaseModel):
    task_id: str
    vocal_task_id: str
    accompaniment_task_id: str
    params: dict
    vocal_params: dict | None = None
    accompaniment_params: dict | None = None
    mix_ratio: float | None = None
    speed: float | None = None


class DualRepairFromHashRequest(BaseModel):
    vocal_file_hash: str
    accompaniment_file_hash: str
    vocal_filename: str = ""
    accompaniment_filename: str = ""
    params: dict
    vocal_params: dict | None = None
    accompaniment_params: dict | None = None
    mix_ratio: float | None = None
    speed: float | None = None


class DebugRepairRequest(BaseModel):
    task_id: str
    algorithm_version: str | None = None


@router.post("/repair")
async def repair_audio_endpoint(request: RepairRequest):
    can_accept, reject_reason = can_accept_task()
    if not can_accept:
        raise HTTPException(status_code=503, detail=reject_reason)

    task = get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    audio_path = task.get("original_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=400, detail="原始音频不存在")

    submit_repair_task(request.task_id, audio_path, request.params)

    return {"task_id": request.task_id, "status": "pending"}


@router.post("/repair-dual")
async def repair_dual_audio_endpoint(request: DualRepairRequest):
    can_accept, reject_reason = can_accept_task()
    if not can_accept:
        raise HTTPException(status_code=503, detail=reject_reason)

    vocal_task = get_task(request.vocal_task_id)
    accompaniment_task = get_task(request.accompaniment_task_id)

    if not vocal_task:
        raise HTTPException(status_code=404, detail="人声任务不存在")
    if not accompaniment_task:
        raise HTTPException(status_code=404, detail="伴奏任务不存在")

    vocal_path = vocal_task.get("original_path")
    accompaniment_path = accompaniment_task.get("original_path")

    if not vocal_path or not os.path.exists(vocal_path):
        raise HTTPException(status_code=400, detail="人声音频不存在")
    if not accompaniment_path or not os.path.exists(accompaniment_path):
        raise HTTPException(status_code=400, detail="伴奏音频不存在")

    params = request.params.copy()
    params["vocal_path"] = vocal_path
    params["accompaniment_path"] = accompaniment_path
    params["vocal_task_id"] = request.vocal_task_id
    params["accompaniment_task_id"] = request.accompaniment_task_id
    params["processing_mode"] = "dual"

    if request.vocal_params:
        flat_vocal = flatten_vocal_params(request.vocal_params)
        params["vocal_params"] = flat_vocal
        params.update(flat_vocal)

    if request.accompaniment_params:
        flat_inst = flatten_inst_params(request.accompaniment_params)
        params["inst_params"] = flat_inst
        params.update(flat_inst)

    if request.mix_ratio is not None:
        params["vocal_ratio"] = request.mix_ratio
        params["accompaniment_ratio"] = 1.0

    if request.speed is not None:
        params["speed"] = request.speed

    params["vocal_path"] = vocal_path
    params["accompaniment_path"] = accompaniment_path

    vocal_output_filename = f"{request.vocal_task_id}_repaired.wav"
    accompaniment_output_filename = f"{request.accompaniment_task_id}_repaired.wav"
    from services.task_manager import OUTPUT_DIR
    params["vocal_output_path"] = os.path.join(OUTPUT_DIR, vocal_output_filename)
    params["accompaniment_output_path"] = os.path.join(OUTPUT_DIR, accompaniment_output_filename)

    submit_repair_task(request.task_id, vocal_path, params)

    return {"task_id": request.task_id, "status": "pending"}


@router.post("/repair-dual-from-hash")
async def repair_dual_from_hash(request: DualRepairFromHashRequest):
    can_accept, reject_reason = can_accept_task()
    if not can_accept:
        raise HTTPException(status_code=503, detail=reject_reason)

    vocal_task = find_task_by_hash(request.vocal_file_hash)
    if not vocal_task or not vocal_task.get("original_path") or not os.path.exists(vocal_task["original_path"]):
        raise HTTPException(status_code=404, detail="人声音频不存在，请重新上传")

    accompaniment_task = find_task_by_hash(request.accompaniment_file_hash)
    if not accompaniment_task or not accompaniment_task.get("original_path") or not os.path.exists(accompaniment_task["original_path"]):
        raise HTTPException(status_code=404, detail="伴奏音频不存在，请重新上传")

    vocal_path = vocal_task["original_path"]
    accompaniment_path = accompaniment_task["original_path"]

    vocal_task_id = generate_task_id()
    accompaniment_task_id = generate_task_id()
    main_task_id = generate_task_id()

    vocal_ext = os.path.splitext(vocal_path)[1].lower()
    accompaniment_ext = os.path.splitext(accompaniment_path)[1].lower()
    vocal_new_path = os.path.join(UPLOAD_DIR, f"{vocal_task_id}{vocal_ext}")
    accompaniment_new_path = os.path.join(UPLOAD_DIR, f"{accompaniment_task_id}{accompaniment_ext}")
    shutil.copy2(vocal_path, vocal_new_path)
    shutil.copy2(accompaniment_path, accompaniment_new_path)

    create_task(vocal_task_id, f"vocal_{request.vocal_filename or 'audio'}", vocal_new_path, {}, request.vocal_file_hash, os.path.getsize(vocal_new_path))
    create_task(accompaniment_task_id, f"acc_{request.accompaniment_filename or 'audio'}", accompaniment_new_path, {}, request.accompaniment_file_hash, os.path.getsize(accompaniment_new_path))
    create_task(main_task_id, f"dual_{request.vocal_filename or 'audio'}", vocal_new_path, {
        "vocal_task_id": vocal_task_id,
        "accompaniment_task_id": accompaniment_task_id,
        "vocal_file_hash": request.vocal_file_hash,
        "accompaniment_file_hash": request.accompaniment_file_hash,
        "vocal_filename": request.vocal_filename,
        "accompaniment_filename": request.accompaniment_filename,
        "processing_mode": "dual",
    }, "", os.path.getsize(vocal_new_path) + os.path.getsize(accompaniment_new_path))

    params = request.params.copy()
    params["vocal_path"] = vocal_new_path
    params["accompaniment_path"] = accompaniment_new_path
    params["vocal_task_id"] = vocal_task_id
    params["accompaniment_task_id"] = accompaniment_task_id
    params["processing_mode"] = "dual"

    if request.vocal_params:
        flat_vocal = flatten_vocal_params(request.vocal_params)
        params["vocal_params"] = flat_vocal
        params.update(flat_vocal)

    if request.accompaniment_params:
        flat_inst = flatten_inst_params(request.accompaniment_params)
        params["inst_params"] = flat_inst
        params.update(flat_inst)

    if request.mix_ratio is not None:
        params["vocal_ratio"] = request.mix_ratio
        params["accompaniment_ratio"] = 1.0

    if request.speed is not None:
        params["speed"] = request.speed

    vocal_output_filename = f"{vocal_task_id}_repaired.wav"
    accompaniment_output_filename = f"{accompaniment_task_id}_repaired.wav"
    from services.task_manager import OUTPUT_DIR
    params["vocal_output_path"] = os.path.join(OUTPUT_DIR, vocal_output_filename)
    params["accompaniment_output_path"] = os.path.join(OUTPUT_DIR, accompaniment_output_filename)

    submit_repair_task(main_task_id, vocal_new_path, params)

    return {
        "task_id": main_task_id,
        "vocal_task_id": vocal_task_id,
        "accompaniment_task_id": accompaniment_task_id,
        "status": "pending",
    }


@router.post("/repair-debug")
async def repair_debug_endpoint(request: DebugRepairRequest):
    task = get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    audio_path = task.get("original_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=400, detail="原始音频不存在")

    debug_dir = os.path.join(OUTPUT_DIR, f"debug_{request.task_id}")
    from services.repair_debug import run_debug_repair
    result = run_debug_repair(audio_path, debug_dir, request.algorithm_version)
    result["task_id"] = request.task_id
    result["debug_dir"] = debug_dir
    return result


@router.get("/repair-debug/{task_id}/{filename}")
async def download_debug_variant(task_id: str, filename: str):
    debug_dir = os.path.join(OUTPUT_DIR, f"debug_{task_id}")
    file_path = os.path.join(debug_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="调试文件不存在")
    return FileResponse(file_path, media_type="audio/wav")


@router.get("/tracks/{task_id}")
async def get_track_status(task_id: str):
    main_task = get_task(task_id)
    if not main_task:
        raise HTTPException(status_code=404, detail="任务不存在")

    params = main_task.get("params", {})
    if isinstance(params, str):
        import json as _json
        try:
            params = _json.loads(params)
        except Exception:
            params = {}

    vocal_task_id = params.get("vocal_task_id") or main_task.get("vocal_task_id")
    accompaniment_task_id = params.get("accompaniment_task_id") or main_task.get("accompaniment_task_id")

    result = {
        "task_id": task_id,
        "status": main_task.get("status"),
        "progress": main_task.get("progress", 0),
        "step": main_task.get("step"),
    }

    if vocal_task_id:
        vocal_task = get_task(vocal_task_id)
        result["vocal"] = {
            "task_id": vocal_task_id,
            "status": vocal_task.get("status") if vocal_task else "unknown",
            "progress": vocal_task.get("progress", 0) if vocal_task else 0,
        }

    if accompaniment_task_id:
        accompaniment_task = get_task(accompaniment_task_id)
        result["accompaniment"] = {
            "task_id": accompaniment_task_id,
            "status": accompaniment_task.get("status") if accompaniment_task else "unknown",
            "progress": accompaniment_task.get("progress", 0) if accompaniment_task else 0,
        }

    return result


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    try:
        task = get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[/status/{task_id}] 获取任务状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"获取任务状态失败: {str(e)[:100]}")


@router.post("/cancel/{task_id}")
async def cancel_task_endpoint(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    status = task.get("status", "")
    if status in ("completed", "error", "cancelled"):
        return {"task_id": task_id, "status": status, "message": "任务已结束，无需取消"}

    success = cancel_task(task_id)
    if success:
        return {"task_id": task_id, "status": "cancelled", "message": "任务已取消"}
    else:
        return {"task_id": task_id, "status": "cancelling", "message": "任务正在取消中"}
