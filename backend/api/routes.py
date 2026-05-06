import os
import hashlib
import json
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from config import UPLOAD_DIR, OUTPUT_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE
from database import create_task, get_task, find_task_by_hash, get_queue_status, mark_stuck_tasks
from services.task_manager import generate_task_id, submit_detect_task, submit_repair_task
from services.file_cache import evict_old_files
from services.audio_repair import get_available_versions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

@router.get("/algorithm-versions")
async def list_algorithm_versions():
    return {"versions": get_available_versions()}

class RepairRequest(BaseModel):
    task_id: str
    params: dict

class DetectRequest(BaseModel):
    task_id: str
    type: str = "original"
    detector_version: str = "v1.1"

class CheckHashRequest(BaseModel):
    file_hash: str

@router.post("/check-hash")
async def check_file_hash(request: CheckHashRequest):
    if not request.file_hash:
        raise HTTPException(400, "file_hash不能为空")
    existing = find_task_by_hash(request.file_hash)
    if existing:
        return {"exists": True, "task_id": existing["id"], "filename": existing["original_filename"]}
    return {"exists": False}

@router.post("/upload")
async def upload_audio(file: UploadFile = File(...), file_hash: str = Form("")):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}")

    if file_hash:
        existing = find_task_by_hash(file_hash)
        if existing:
            logger.info(f"文件哈希命中缓存: hash={file_hash} task_id={existing['id']}")
            return {
                "task_id": existing["id"],
                "filename": existing["original_filename"],
                "size": existing.get("file_size", 0),
                "message": "文件已存在，跳过上传",
                "cached": True,
            }

    task_id = generate_task_id()
    filepath = os.path.join(UPLOAD_DIR, f"{task_id}{ext}")

    total_size = 0
    hasher = hashlib.sha256()
    with open(filepath, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                os.remove(filepath)
                raise HTTPException(400, f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
            hasher.update(chunk)
            f.write(chunk)

    computed_hash = file_hash or hasher.hexdigest()

    create_task(task_id, file.filename, filepath, {}, file_hash=computed_hash, file_size=total_size)

    evict_old_files()

    return {
        "task_id": task_id,
        "filename": file.filename,
        "size": total_size,
        "message": "上传成功",
        "cached": False,
    }

@router.post("/detect")
async def detect_audio(request: DetectRequest):
    logger.info(f"[/detect] 收到请求: task_id={request.task_id}, type={request.type}, detector_version={request.detector_version}")
    task = get_task(request.task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    if request.type == "repaired":
        audio_path = task.get("output_path", "")
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(400, "修复文件不存在，请先完成修复")
    else:
        audio_path = task["original_path"]
        if not os.path.exists(audio_path):
            raise HTTPException(400, "音频文件不存在")

    # 重置检测相关状态，避免显示缓存结果
    from database import update_task
    label = "修复后" if request.type == "repaired" else "原始"
    update_task(
        request.task_id,
        status="detecting",
        progress=0,
        step=f"AI检测{label}音频({request.detector_version})...",
        detection_result=None if request.type == "original" else task.get("detection_result"),
        repaired_detection_result=None if request.type == "repaired" else task.get("repaired_detection_result"),
        error=None
    )

    logger.info(f"[/detect] 提交检测任务: task_id={request.task_id}, detector_version={request.detector_version}")
    submit_detect_task(request.task_id, audio_path, request.type, request.detector_version)

    return {
        "task_id": request.task_id,
        "message": "检测任务已提交"
    }

@router.post("/repair")
async def repair_audio(request: RepairRequest):
    task = get_task(request.task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    if not os.path.exists(task["original_path"]):
        raise HTTPException(400, "音频文件不存在")

    from database import update_task
    update_task(request.task_id, params=request.params, status="pending", progress=0, step="准备修复...", output_path="", repair_result=None, error=None)

    submit_repair_task(request.task_id, task["original_path"], request.params)

    return {
        "task_id": request.task_id,
        "message": "修复任务已提交"
    }

@router.get("/status/{task_id}")
async def task_status(task_id: str):
    # 先检查并标记卡住的任务
    mark_stuck_tasks(timeout_seconds=300)
    
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    return {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "step": task["step"],
        "detection_result": task.get("detection_result"),
        "repaired_detection_result": task.get("repaired_detection_result"),
        "repair_result": task.get("repair_result"),
        "error": task.get("error"),
    }


@router.get("/queue-status")
async def queue_status():
    """获取任务队列状态"""
    mark_stuck_tasks(timeout_seconds=300)
    return get_queue_status()

@router.get("/stream/{task_id}")
async def stream_progress(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    async def event_generator():
        while True:
            t = get_task(task_id)
            if t is None:
                break
            data = {
                "task_id": task_id,
                "status": t["status"],
                "progress": t["progress"],
                "step": t["step"],
            }
            if t.get("detection_result"):
                data["detection_result"] = t["detection_result"]
            if t.get("repaired_detection_result"):
                data["repaired_detection_result"] = t["repaired_detection_result"]
            if t.get("repair_result"):
                data["repair_result"] = t["repair_result"]
            if t.get("error"):
                data["error"] = t["error"]

            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            if t["status"] in ("completed", "detected", "error"):
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/download/{task_id}")
async def download_audio(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    output_path = task.get("output_path", "")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(400, "修复文件不存在，请先完成修复")

    filename = os.path.basename(task["original_filename"])
    base_name = os.path.splitext(filename)[0]
    download_name = f"{base_name}_repaired.wav"

    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename=download_name,
        headers={
            "Content-Length": str(os.path.getsize(output_path)),
        },
    )

@router.get("/preview/{task_id}")
async def preview_audio(task_id: str, type: str = Query("original")):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    if type == "original":
        filepath = task["original_path"]
    elif type == "repaired":
        filepath = task.get("output_path", "")
        if not filepath or not os.path.exists(filepath):
            raise HTTPException(400, "修复文件不存在，请先完成修复")
    else:
        raise HTTPException(400, "type必须是original或repaired")

    if not os.path.exists(filepath):
        raise HTTPException(404, "文件不存在")

    return FileResponse(
        filepath,
        media_type="audio/wav",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(os.path.getsize(filepath)),
        },
    )

# 训练素材哈希检查接口
class TrainingCheckHashRequest(BaseModel):
    file_hash: str

@router.post("/training/check-hash")
async def check_training_hash(request: TrainingCheckHashRequest):
    from database import find_training_by_hash
    if not request.file_hash:
        raise HTTPException(400, "file_hash不能为空")
    existing = find_training_by_hash(request.file_hash)
    if existing:
        return {"exists": True, "filename": existing["filename"], "size": existing["file_size"]}
    return {"exists": False}

# 训练素材上传接口
@router.post("/training/upload")
async def upload_training_audio(file: UploadFile = File(...), file_hash: str = Form("")):
    from config import TRAINING_DIR
    from database import find_training_by_hash, create_training_record
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}")

    # 如果提供了哈希，先检查是否已存在
    if file_hash:
        existing = find_training_by_hash(file_hash)
        if existing:
            logger.info(f"训练素材哈希命中缓存: hash={file_hash} filename={existing['filename']}")
            return {
                "filename": existing["filename"],
                "size": existing["file_size"],
                "path": existing["filepath"],
                "message": "文件已存在，跳过上传",
                "cached": True,
            }

    # 生成唯一文件名
    import uuid
    file_id = str(uuid.uuid4())[:8]
    filename = f"{file_id}_{file.filename}"
    filepath = os.path.join(TRAINING_DIR, filename)

    # 计算哈希（如果没有提供）
    import hashlib
    hasher = hashlib.sha256() if not file_hash else None
    
    total_size = 0
    with open(filepath, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                os.remove(filepath)
                raise HTTPException(400, f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
            if hasher:
                hasher.update(chunk)
            f.write(chunk)

    computed_hash = file_hash or hasher.hexdigest()
    
    # 保存到数据库
    create_training_record(file_id, file.filename, filepath, computed_hash, total_size)
    
    logger.info(f"训练素材上传成功: {filename}, size={total_size}, hash={computed_hash[:16]}...")

    return {
        "filename": filename,
        "size": total_size,
        "path": filepath,
        "message": "训练素材上传成功",
        "cached": False,
    }

@router.get("/training/list")
async def list_training_files():
    from config import TRAINING_DIR
    
    files = []
    try:
        for filename in os.listdir(TRAINING_DIR):
            filepath = os.path.join(TRAINING_DIR, filename)
            if os.path.isfile(filepath):
                files.append({
                    "filename": filename,
                    "size": os.path.getsize(filepath),
                    "modified": os.path.getmtime(filepath),
                })
    except Exception as e:
        logger.error(f"读取训练素材目录失败: {e}")
    
    return {"files": sorted(files, key=lambda x: x["modified"], reverse=True)}
