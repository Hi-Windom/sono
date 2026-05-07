import os
import logging
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, MOBILE_MODE, OUTPUT_DIR, UPLOAD_DIR
from database import create_task, find_task_by_hash, get_queue_status, get_task
from services.task_manager import generate_task_id, submit_detect_task, submit_repair_task, cancel_task
from services.audio_repair import get_available_versions
from services.ai_detector import get_detector_versions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

class LogRequest(BaseModel):
    message: str
    level: str = "info"

@router.post("/log")
async def log_message(request: LogRequest):
    level = request.level.lower()
    if level == "error":
        logger.error(request.message)
    elif level == "warning":
        logger.warning(request.message)
    elif level == "debug":
        logger.debug(request.message)
    else:
        logger.info(request.message)
    return {"status": "ok"}


# 同时支持 /api/log 路径，用于兼容前端
@router.post("", include_in_schema=False)
async def log_message_root(request: LogRequest):
    level = request.level.lower()
    if level == "error":
        logger.error(request.message)
    elif level == "warning":
        logger.warning(request.message)
    elif level == "debug":
        logger.debug(request.message)
    else:
        logger.info(request.message)
    return {"status": "ok"}

@router.get("/algorithm-versions")
async def list_algorithm_versions():
    return {"versions": get_available_versions(mobile_mode=MOBILE_MODE)}

@router.get("/detector-versions")
async def list_detector_versions():
    return {"versions": get_detector_versions()}

class CheckHashRequest(BaseModel):
    file_hash: str

@router.post("/check-hash")
async def check_file_hash(request: CheckHashRequest):
    existing = find_task_by_hash(request.file_hash)
    if existing:
        return {
            "exists": True,
            "task_id": existing["id"],
            "output_path": existing.get("output_path", ""),
            "status": existing.get("status", ""),
            "params": existing.get("params", {}),
        }
    return {"exists": False}

@router.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
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
    
    create_task(task_id, file.filename or "audio", upload_path, {})
    
    return {
        "task_id": task_id,
        "filename": file.filename,
        "size": len(content),
    }

class DetectRequest(BaseModel):
    task_id: str
    type: str = "original"
    detector_version: str = "v1.1"

@router.post("/detect")
async def detect_audio(request: DetectRequest):
    logger.info(f"[/detect] 收到请求: task_id={request.task_id}, type={request.type}, detector_version={request.detector_version}")
    
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

class RepairRequest(BaseModel):
    task_id: str
    params: dict

@router.post("/repair")
async def repair_audio_endpoint(request: RepairRequest):
    task = get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    audio_path = task.get("original_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=400, detail="原始音频不存在")
    
    submit_repair_task(request.task_id, audio_path, request.params)
    
    return {"task_id": request.task_id, "status": "pending"}

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task

@router.get("/queue-status")
async def get_queue():
    return get_queue_status()

@router.websocket("/ws/{task_id}")
async def websocket_task_status(websocket: WebSocket, task_id: str):
    await websocket.accept()
    
    task = get_task(task_id)
    if not task:
        await websocket.send_json({"error": "任务不存在"})
        await websocket.close()
        return
    from services.ws_manager import ws_manager
    await ws_manager.connect(task_id, websocket)
    try:
        current = {
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "step": task["step"],
        }
        if task.get("detection_result"):
            current["detection_result"] = task["detection_result"]
        if task.get("repaired_detection_result"):
            current["repaired_detection_result"] = task["repaired_detection_result"]
        if task.get("repair_result"):
            current["repair_result"] = task["repair_result"]
        if task.get("error"):
            current["error"] = task["error"]
        await websocket.send_json(current)
        if task["status"] in ("completed", "detected", "error"):
            await websocket.close()
            return
        
        import asyncio
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            except asyncio.TimeoutError:
                current_task = get_task(task_id)
                if not current_task:
                    await websocket.send_json({"error": "任务不存在"})
                    await websocket.close()
                    return
                heartbeat_msg = {
                    "task_id": task_id,
                    "status": current_task["status"],
                    "progress": current_task["progress"],
                    "step": current_task["step"],
                    "heartbeat": True,
                }
                if current_task.get("detection_result"):
                    heartbeat_msg["detection_result"] = current_task["detection_result"]
                if current_task.get("repaired_detection_result"):
                    heartbeat_msg["repaired_detection_result"] = current_task["repaired_detection_result"]
                if current_task.get("repair_result"):
                    heartbeat_msg["repair_result"] = current_task["repair_result"]
                if current_task.get("error"):
                    heartbeat_msg["error"] = current_task["error"]
                await websocket.send_json(heartbeat_msg)
                if current_task["status"] in ("completed", "detected", "error"):
                    await websocket.close()
                    return
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(task_id, websocket)

@router.get("/download/{task_id}")
async def download_audio(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    output_path = task.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="修复后的音频不存在")
    
    original_name = task.get("original_filename", "audio")
    base_name = os.path.splitext(original_name)[0]
    download_name = f"{base_name}_repaired.wav"
    
    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename=download_name,
    )

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

@router.get("/preview/{task_id}")
async def preview_audio(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    output_path = task.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="修复后的音频不存在")
    
    return FileResponse(
        output_path,
        media_type="audio/wav",
    )

@router.post("/training/check-hash")
async def training_check_hash(request: CheckHashRequest):
    from services.training_manager import check_training_hash
    exists = check_training_hash(request.file_hash)
    return {"exists": exists}

@router.post("/training/upload")
async def training_upload(
    file: UploadFile = File(...),
    file_hash: str = Form(...),
    label: str = Form(...),
):
    from services.training_manager import save_training_file
    
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".wav"
    saved_path = await save_training_file(file, file_hash, label, ext)
    
    return {"status": "ok", "path": saved_path}

@router.get("/cache/info")
async def get_cache_info():
    from database import get_db
    
    upload_size = 0
    output_size = 0
    upload_count = 0
    output_count = 0
    
    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            fp = os.path.join(UPLOAD_DIR, f)
            if os.path.isfile(fp):
                upload_size += os.path.getsize(fp)
                upload_count += 1
    
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            fp = os.path.join(OUTPUT_DIR, f)
            if os.path.isfile(fp):
                output_size += os.path.getsize(fp)
                output_count += 1
    
    conn = get_db()
    try:
        all_tasks = conn.execute(
            "SELECT id, original_filename, original_path, output_path, status, created_at FROM tasks ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    
    tasks = []
    for row in all_tasks:
        orig_path = row["original_path"] if row["original_path"] else ""
        out_path = row["output_path"] if row["output_path"] else ""
        
        orig_exists = bool(orig_path) and os.path.exists(orig_path)
        out_exists = bool(out_path) and os.path.exists(out_path)
        
        orig_size = os.path.getsize(orig_path) if orig_exists else 0
        out_size = os.path.getsize(out_path) if out_exists else 0
        
        task_info = {
            "id": row["id"],
            "filename": row["original_filename"] or "unknown",
            "status": row["status"],
            "created_at": row["created_at"],
            "original_exists": orig_exists,
            "output_exists": out_exists,
            "original_size": orig_size,
            "output_size": out_size,
            "total_size": orig_size + out_size,
        }
        tasks.append(task_info)
    
    return {
        "total_size": upload_size + output_size,
        "upload_size": upload_size,
        "output_size": output_size,
        "upload_count": upload_count,
        "output_count": output_count,
        "task_count": len(tasks),
        "tasks": tasks,
    }


def _is_valid_audio_file(filepath: str) -> tuple[bool, str]:
    """检查音频文件是否有效，返回 (是否有效, 原因)"""
    if not os.path.exists(filepath):
        return False, "文件不存在"
    
    try:
        size = os.path.getsize(filepath)
        if size == 0:
            return False, "空文件"
        
        import soundfile as sf
        info = sf.info(filepath)
        if info.duration < 0.1:
            return False, "音频时长过短"
        
        return True, ""
    except Exception as e:
        return False, f"文件损坏: {str(e)[:50]}"


@router.post("/cache/clean-invalid")
async def clean_invalid_cache():
    """清理无效缓存（损坏文件、空文件、孤立文件）"""
    from database import get_db
    
    conn = get_db()
    try:
        db_files = set()
        all_tasks = conn.execute("SELECT id, original_path, output_path FROM tasks").fetchall()
        for row in all_tasks:
            if row["original_path"]:
                db_files.add(row["original_path"])
            if row["output_path"]:
                db_files.add(row["output_path"])
        
        cleaned_count = 0
        released_bytes = 0
        cleaned_files = []
        
        for dir_path in [UPLOAD_DIR, OUTPUT_DIR]:
            if not os.path.exists(dir_path):
                continue
            
            for filename in os.listdir(dir_path):
                filepath = os.path.join(dir_path, filename)
                if not os.path.isfile(filepath):
                    continue
                
                is_valid, reason = _is_valid_audio_file(filepath)
                is_orphaned = filepath not in db_files
                
                if not is_valid or is_orphaned:
                    file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    clean_reason = reason if not is_valid else ("孤立文件" if is_orphaned else "")
                    
                    try:
                        os.remove(filepath)
                        cleaned_count += 1
                        released_bytes += file_size
                        cleaned_files.append({
                            "path": filepath,
                            "size": file_size,
                            "reason": clean_reason,
                        })
                        logger.info(f"清理无效缓存: {filepath} ({clean_reason})")
                    except Exception as e:
                        logger.warning(f"删除文件失败: {filepath}, {e}")
        
        return {
            "cleaned_count": cleaned_count,
            "released_bytes": released_bytes,
            "cleaned_files": cleaned_files[:10],
        }
    except Exception as e:
        logger.error(f"清理无效缓存出错: {e}", exc_info=True)
        raise
    finally:
        conn.close()


@router.post("/cache/clear-all")
async def clear_all_cache():
    """清空全部缓存"""
    from database import get_db
    
    conn = get_db()
    
    total_released = 0
    
    for dir_path in [UPLOAD_DIR, OUTPUT_DIR]:
        if os.path.exists(dir_path):
            for filename in os.listdir(dir_path):
                filepath = os.path.join(dir_path, filename)
                if os.path.isfile(filepath):
                    try:
                        total_released += os.path.getsize(filepath)
                        os.remove(filepath)
                    except Exception as e:
                        logger.warning(f"删除文件失败: {filepath}, {e}")
    
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()
    
    return {"released_bytes": total_released}

@router.post("/cache/clear-output")
async def clear_output_cache():
    """清理输出缓存"""
    from database import get_db
    
    released = 0
    
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            filepath = os.path.join(OUTPUT_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    released += os.path.getsize(filepath)
                    os.remove(filepath)
                except Exception as e:
                    logger.warning(f"删除文件失败: {filepath}, {e}")
    
    conn = get_db()
    conn.execute("UPDATE tasks SET output_path = ''")
    conn.commit()
    conn.close()
    
    return {"released_bytes": released}

@router.post("/cache/clear-upload")
async def clear_upload_cache():
    """清理上传缓存"""
    from database import get_db
    
    released = 0
    
    if os.path.exists(UPLOAD_DIR):
        for filename in os.listdir(UPLOAD_DIR):
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    released += os.path.getsize(filepath)
                    os.remove(filepath)
                except Exception as e:
                    logger.warning(f"删除文件失败: {filepath}, {e}")
    
    conn = get_db()
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()
    
    return {"released_bytes": released}

@router.post("/cache/delete/{task_id}")
async def delete_task_cache(task_id: str):
    """删除指定任务的缓存"""
    from database import get_db
    
    conn = get_db()
    try:
        row = conn.execute("SELECT original_path, output_path FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        released = 0
        orig_path = row["original_path"] if row["original_path"] else ""
        out_path = row["output_path"] if row["output_path"] else ""
        
        if orig_path and os.path.exists(orig_path):
            released += os.path.getsize(orig_path)
            try:
                os.remove(orig_path)
            except Exception as e:
                logger.warning(f"删除文件失败: {orig_path}, {e}")
        
        if out_path and os.path.exists(out_path):
            released += os.path.getsize(out_path)
            try:
                os.remove(out_path)
            except Exception as e:
                logger.warning(f"删除文件失败: {out_path}, {e}")
        
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        
        return {"released_bytes": released}
    finally:
        conn.close()

@router.get("/training/list")
async def list_training_data():
    from services.training_manager import list_training_files
    return list_training_files()
