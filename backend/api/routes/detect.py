import os
import logging
import hashlib
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, UPLOAD_DIR, OUTPUT_DIR
from database import create_task, get_task, update_task
from services.task_manager import generate_task_id, submit_detect_task, can_accept_task

logger = logging.getLogger(__name__)

router = APIRouter()


class DetectRequest(BaseModel):
    task_id: str
    type: str = "original"
    detector_version: str = "v1.1"
    skip_cache: bool = False


class DetectPathRequest(BaseModel):
    file_id: str
    detector_version: str = "v1.1"


@router.post("/detect")
async def detect_audio(request: DetectRequest):
    logger.info(f"[/detect] 收到请求: task_id={request.task_id}, type={request.type}, detector_version={request.detector_version}, skip_cache={request.skip_cache}")

    can_accept, reject_reason = can_accept_task()
    if not can_accept:
        raise HTTPException(status_code=503, detail=reject_reason)

    task = get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if request.type == "repaired":
        audio_path = task.get("output_path")
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(status_code=400, detail="修复后的音频不存在，请先完成修复")
    else:
        audio_path = task.get("original_path")
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(status_code=400, detail="原始音频不存在")

    label = "修复后" if request.type == "repaired" else "原始"

    if not request.skip_cache:
        cached_result_key = "repaired_detection_result" if request.type == "repaired" else "detection_result"
        cached_result = task.get(cached_result_key)
        if cached_result and isinstance(cached_result, dict):
            cached_version = cached_result.get("detector_version", "")
            if cached_version == request.detector_version:
                logger.info(f"[/detect] 缓存命中: task_id={request.task_id} type={request.type} version={request.detector_version}")
                return {
                    "task_id": request.task_id,
                    "status": "detected",
                    "cached": True,
                    "detection_result": cached_result,
                }
    else:
        logger.info(f"[/detect] 跳过缓存检查: task_id={request.task_id} type={request.type}")

    from database import update_task
    update_task(
        request.task_id,
        status="detecting",
        progress=0,
        step=f"AI检测{label}音频({request.detector_version})...",
    )

    logger.info(f"[/detect] 提交检测任务: task_id={request.task_id}, detector_version={request.detector_version}")
    submit_detect_task(request.task_id, audio_path, request.type, request.detector_version)

    return {"task_id": request.task_id, "status": "detecting"}


@router.post("/detect-file")
async def detect_file(file: UploadFile = File(...), detector_version: str = Form("v1.1")):
    can_accept, reject_reason = can_accept_task()
    if not can_accept:
        raise HTTPException(status_code=503, detail=reject_reason)

    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    task_id = generate_task_id()
    upload_path = os.path.join(UPLOAD_DIR, f"{task_id}{ext}")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    with open(upload_path, "wb") as f:
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            os.remove(upload_path)
            raise HTTPException(status_code=413, detail=f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
        f.write(content)

    create_task(task_id, file.filename or "audio", upload_path, {}, "", len(content))
    logger.info(f"[/detect-file] task_id={task_id} file={file.filename} detector_version={detector_version}")

    submit_detect_task(task_id, upload_path, "original", detector_version)

    return {"task_id": task_id, "status": "detecting"}


@router.post("/detect-path")
async def detect_by_path(request: DetectPathRequest):
    can_accept, reject_reason = can_accept_task()
    if not can_accept:
        raise HTTPException(status_code=503, detail=reject_reason)

    target_id = request.file_id
    found_path = None
    found_name = None

    for directory in [UPLOAD_DIR, OUTPUT_DIR]:
        if not os.path.exists(directory):
            continue
        for fname in os.listdir(directory):
            fp = os.path.join(directory, fname)
            if not os.path.isfile(fp):
                continue
            fid = hashlib.sha256(fp.encode()).hexdigest()[:16]
            if fid == target_id:
                found_path = fp
                found_name = fname
                break
        if found_path:
            break

    if not found_path or not os.path.exists(found_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    task_id = generate_task_id()
    create_task(task_id, found_name, found_path, {}, "", os.path.getsize(found_path))
    logger.info(f"[/detect-path] task_id={task_id} file_id={target_id} path={found_path} detector_version={request.detector_version}")

    submit_detect_task(task_id, found_path, "original", request.detector_version)

    return {"task_id": task_id, "status": "detecting"}
