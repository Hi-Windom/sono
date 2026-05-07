import os
import hashlib
import json
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from config import UPLOAD_DIR, OUTPUT_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, MOBILE_MODE
from database import create_task, get_task, find_task_by_hash, get_queue_status, mark_stuck_tasks, delete_task
from services.task_manager import generate_task_id, submit_detect_task, submit_repair_task
from services.file_cache import evict_old_files
from services.audio_repair import get_available_versions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

@router.get("/algorithm-versions")
async def list_algorithm_versions():
    return {"versions": get_available_versions(mobile_mode=MOBILE_MODE)}

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

@router.websocket("/ws/progress/{task_id}")
async def websocket_progress(websocket: WebSocket, task_id: str):
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

@router.get("/cache/info")
async def get_cache_info():
    """获取缓存详细信息"""
    from database import get_db, get_all_tasks_ordered
    from services.file_cache import get_dir_size
    from config import UPLOAD_DIR, OUTPUT_DIR
    
    upload_size = get_dir_size(UPLOAD_DIR)
    output_size = get_dir_size(OUTPUT_DIR)
    
    conn = get_db()
    all_tasks = conn.execute(
        """SELECT id, original_filename, status, progress, step, 
                  original_path, output_path, file_size, file_hash,
                  created_at, updated_at, error
           FROM tasks 
           ORDER BY created_at DESC"""
    ).fetchall()
    conn.close()
    
    tasks = []
    invalid_tasks = []
    
    for row in all_tasks:
        task = dict(row)
        orig_path = task.get("original_path", "")
        out_path = task.get("output_path", "")
        
        # 检查文件是否存在
        orig_exists = bool(orig_path) and os.path.exists(orig_path)
        out_exists = bool(out_path) and os.path.exists(out_path)
        
        # 计算文件大小
        orig_size = os.path.getsize(orig_path) if orig_exists else 0
        out_size = os.path.getsize(out_path) if out_exists else 0
        
        task_info = {
            "id": task["id"],
            "filename": task["original_filename"],
            "status": task["status"],
            "progress": task["progress"],
            "step": task["step"],
            "original_path": orig_path,
            "output_path": out_path,
            "original_exists": orig_exists,
            "output_exists": out_exists,
            "original_size": orig_size,
            "output_size": out_size,
            "total_size": orig_size + out_size,
            "file_hash": task.get("file_hash", ""),
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
            "error": task.get("error", ""),
        }
        
        # 判断是否为无效任务
        is_invalid = False
        # 状态异常
        if task["status"] in ["error", "timeout"]:
            is_invalid = True
        # 文件丢失
        elif (task["status"] == "completed" and not out_exists) or not orig_exists:
            is_invalid = True
        
        if is_invalid:
            invalid_tasks.append(task_info)
        tasks.append(task_info)
    
    return {
        "total_size": upload_size + output_size,
        "upload_size": upload_size,
        "output_size": output_size,
        "task_count": len(tasks),
        "invalid_count": len(invalid_tasks),
        "tasks": tasks,
        "invalid_tasks": invalid_tasks,
    }


@router.post("/cache/clean-invalid")
async def clean_invalid_cache():
    """清理无效缓存（损坏文件、失败任务等）"""
    from database import get_db
    from config import UPLOAD_DIR, OUTPUT_DIR
    
    conn = get_db()
    try:
        all_tasks = conn.execute(
            "SELECT id, original_path, output_path, status FROM tasks"
        ).fetchall()
        
        cleaned_count = 0
        released_bytes = 0
        
        for row in all_tasks:
            task_id = row["id"]
            orig_path = row["original_path"] if row["original_path"] else ""
            out_path = row["output_path"] if row["output_path"] else ""
            status = row["status"]
            
            should_delete = False
            # 状态异常的任务
            if status in ["error", "timeout"]:
                should_delete = True
            # 文件丢失的任务
            elif not (bool(orig_path) and os.path.exists(orig_path)):
                should_delete = True
            # 已完成但输出文件丢失的任务
            elif status == "completed" and not (bool(out_path) and os.path.exists(out_path)):
                should_delete = True
            
            if should_delete:
                # 删除文件
                released = 0
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
                
                # 删除数据库记录（直接删除，不调用 delete_task 避免连接冲突）
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                cleaned_count += 1
                released_bytes += released
        
        return {
            "cleaned_count": cleaned_count,
            "released_bytes": released_bytes,
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
    from config import UPLOAD_DIR, OUTPUT_DIR
    
    conn = get_db()
    
    # 删除所有文件
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
    
    # 清空数据库
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()
    
    return {
        "released_bytes": total_released,
    }


@router.post("/cache/clear-output")
async def clear_output_cache():
    """清空输出文件缓存"""
    from database import get_db
    
    conn = get_db()
    
    released_bytes = 0
    
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            filepath = os.path.join(OUTPUT_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    released_bytes += os.path.getsize(filepath)
                    os.remove(filepath)
                except Exception as e:
                    logger.warning(f"删除输出文件失败: {filepath}, {e}")
    
    conn.execute("UPDATE tasks SET output_path = ''")
    conn.commit()
    conn.close()
    
    return {
        "released_bytes": released_bytes,
    }


@router.post("/cache/clear-upload")
async def clear_upload_cache():
    """清空上传文件缓存（保留输出文件）"""
    from database import get_db
    from config import UPLOAD_DIR
    
    conn = get_db()
    
    released_bytes = 0
    
    if os.path.exists(UPLOAD_DIR):
        for filename in os.listdir(UPLOAD_DIR):
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    released_bytes += os.path.getsize(filepath)
                    os.remove(filepath)
                    logger.info(f"删除上传文件: {filepath}")
                except Exception as e:
                    logger.warning(f"删除上传文件失败: {filepath}, {e}")
    
    # 清空数据库中的所有任务记录
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()
    
    return {
        "released_bytes": released_bytes,
    }


@router.post("/cache/delete/{task_id}")
async def delete_cache_task(task_id: str):
    """删除指定缓存任务"""
    from database import get_db, get_task, delete_task
    
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    
    released = 0
    orig_path = task.get("original_path", "")
    out_path = task.get("output_path", "")
    
    if orig_path and os.path.exists(orig_path):
        released += os.path.getsize(orig_path)
        os.remove(orig_path)
    if out_path and os.path.exists(out_path):
        released += os.path.getsize(out_path)
        os.remove(out_path)
    
    delete_task(task_id)
    
    return {
        "task_id": task_id,
        "released_bytes": released,
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
