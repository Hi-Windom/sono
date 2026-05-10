import os
import logging
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, MOBILE_MODE, OUTPUT_DIR, UPLOAD_DIR, DEPLOY_TIME_FILE
from database import create_task, find_task_by_hash, get_queue_status, get_task, update_task
from services.task_manager import generate_task_id, submit_detect_task, submit_repair_task, cancel_task, executor
from services.audio_repair import get_available_versions
from services.ai_detector import get_detector_versions
from services.memory_guard import get_available_memory_bytes, estimate_repair_memory_bytes, should_use_float32, get_total_memory_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

class LogRequest(BaseModel):
    message: str
    level: str = "info"

class MemoryInfoRequest(BaseModel):
    duration: float
    channels: int = 2
    sample_rate: int = 44100
    algorithm_version: str = "v2.3a"

@router.post("/memory/info")
async def memory_info(request: MemoryInfoRequest):
    if request.duration <= 0:
        return {
            "available_memory_bytes": None,
            "estimated_memory_bytes": 0,
            "is_sufficient": True,
        }
    available = get_available_memory_bytes()
    n_samples = int(request.duration * request.sample_rate)
    if request.algorithm_version == "v1.2":
        working_sr = 96000
    elif request.algorithm_version in ("v1.0", "v1.1", "v2.2a"):
        working_sr = request.sample_rate
    elif request.algorithm_version == "v2.3a":
        working_sr = 48000
    elif MOBILE_MODE:
        working_sr = request.sample_rate
    else:
        working_sr = 48000
    estimated = estimate_repair_memory_bytes(
        n_samples, request.channels, request.sample_rate, working_sr,
        algorithm_version=request.algorithm_version
    )
    is_sufficient = True
    if available is not None:
        is_sufficient = estimated <= available
    use_f32 = should_use_float32(n_samples, request.channels)
    has_streaming = request.algorithm_version in ("v2.2", "v2.3", "v2.3a")
    total_mem = get_total_memory_bytes()
    used_mem = (total_mem - available) if (total_mem is not None and available is not None) else None
    baseline_samples = int(n_samples * working_sr / request.sample_rate) if working_sr > request.sample_rate else n_samples
    baseline_bytes = request.channels * baseline_samples * 8
    baseline_peak = baseline_samples * 8 * 3
    baseline_total = (baseline_bytes + baseline_peak) * 1.3 * 1.2
    memory_saving = max(0, 1 - estimated / baseline_total) if baseline_total > 0 else 0
    return {
        "available_memory_bytes": available,
        "total_memory_bytes": total_mem,
        "used_memory_bytes": used_mem,
        "estimated_memory_bytes": estimated,
        "is_sufficient": is_sufficient,
        "working_sr": working_sr,
        "use_float32": use_f32,
        "has_streaming": has_streaming,
        "memory_saving": round(memory_saving, 2),
    }

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

@router.get("/deploy-info")
async def deploy_info():
    from datetime import datetime, timezone
    deploy_time = None
    deploy_days = None
    try:
        with open(DEPLOY_TIME_FILE, "r") as f:
            content = f.read().strip()
        dt = datetime.fromisoformat(content)
        deploy_time = content
        deploy_days = (datetime.now(timezone.utc) - dt).days
    except (FileNotFoundError, ValueError, OSError):
        pass
    return {"deploy_time": deploy_time, "deploy_days": deploy_days}

class StorageEstimateRequest(BaseModel):
    duration: float
    channels: int = 2
    sample_rate: int = 44100
    bit_depth: int = 24

@router.post("/storage/estimate")
async def storage_estimate(request: StorageEstimateRequest):
    bytes_per_sample = request.bit_depth // 8
    data_bytes = int(request.duration * request.sample_rate * request.channels * bytes_per_sample)
    total_bytes = data_bytes + 44
    estimated_mb = round(total_bytes / (1024 * 1024), 1)

    available_bytes = None
    total_disk_bytes = None
    used_disk_bytes = None
    is_sufficient = True
    try:
        disk_usage = os.statvfs(UPLOAD_DIR)
        available_bytes = disk_usage.f_bavail * disk_usage.f_frsize
        total_disk_bytes = disk_usage.f_blocks * disk_usage.f_frsize
        used_disk_bytes = total_disk_bytes - available_bytes
        is_sufficient = total_bytes <= available_bytes
    except OSError:
        pass

    return {
        "estimated_output_bytes": total_bytes,
        "estimated_output_mb": estimated_mb,
        "available_disk_bytes": available_bytes,
        "total_disk_bytes": total_disk_bytes,
        "used_disk_bytes": used_disk_bytes,
        "is_sufficient": is_sufficient,
    }

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
async def upload_audio(file: UploadFile = File(...), file_hash: str = Form("")):
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

    file_size = len(content)

    try:
        disk_usage = os.statvfs(UPLOAD_DIR)
        available_bytes = disk_usage.f_bavail * disk_usage.f_frsize
        min_required = file_size * 2
        if available_bytes < min_required:
            os.remove(upload_path)
            available_mb = available_bytes // 1024 // 1024
            required_mb = min_required // 1024 // 1024
            raise HTTPException(
                status_code=507,
                detail=f"存储空间不足：可用 {available_mb}MB，至少需要 {required_mb}MB（文件大小的2倍）"
            )
    except OSError:
        pass

    create_task(task_id, file.filename or "audio", upload_path, {}, file_hash, file_size)
    logger.info(f"[/upload] task_id={task_id} file_hash={file_hash or 'none'}")

    return {
        "task_id": task_id,
        "filename": file.filename,
        "size": file_size,
    }

class DetectRequest(BaseModel):
    task_id: str
    type: str = "original"
    detector_version: str = "v1.1"
    skip_cache: bool = False

@router.post("/detect")
async def detect_audio(request: DetectRequest):
    logger.info(f"[/detect] 收到请求: task_id={request.task_id}, type={request.type}, detector_version={request.detector_version}, skip_cache={request.skip_cache}")

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

    # 如果 skip_cache=True，跳过缓存检查，强制重新检测
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

class RenderRequest(BaseModel):
    task_id: str
    sample_rate: int = 44100
    bit_depth: int = 24

@router.post("/render")
async def render_audio_endpoint(request: RenderRequest):
    task = get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    output_path = task.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=400, detail="修复结果不存在，请先完成修复")

    algo_ver = task.get("params", {}).get("algorithm_version", "v2.0").replace(".", "p")
    render_filename = f"{request.task_id}_rendered_{algo_ver}_{request.sample_rate}_{request.bit_depth}.wav"
    render_path = os.path.join(OUTPUT_DIR, render_filename)

    update_task(request.task_id, status="rendering", step="渲染交付规格...", progress=0)

    executor.submit(_run_render, request.task_id, output_path, render_path, request.sample_rate, request.bit_depth, render_filename)

    return {"task_id": request.task_id, "status": "rendering"}


def _run_render(task_id, input_path, output_path, target_sr, bit_depth, render_filename):
    from services.render import render_output
    from services.task_manager import _ws_send_progress

    def progress_callback(pct, step):
        update_task(task_id, progress=pct, step=step)
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "rendering",
            "progress": pct,
            "step": step,
        })

    try:
        result = render_output(input_path, output_path, target_sr, bit_depth, progress_callback=progress_callback)
        update_task(task_id,
            status="render_completed",
            progress=1.0,
            step="渲染完成",
            render_filename=render_filename,
            render_result=result,
        )
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "render_completed",
            "progress": 1.0,
            "step": "渲染完成",
            "render_filename": render_filename,
            "render_result": result,
        })
    except Exception as e:
        logger.error(f"[render] 渲染失败 task_id={task_id}: {e}")
        update_task(task_id, status="error", error=str(e), step="渲染失败")
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
            "step": "渲染失败",
        })

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
    
    if task_id.startswith("qt-"):
        qt_task = _quality_test_cache.get(task_id)
        if not qt_task:
            await websocket.send_json({"error": "测试任务不存在"})
            await websocket.close()
            return
        from services.ws_manager import ws_manager
        await ws_manager.connect(task_id, websocket)
        try:
            await websocket.send_json({
                "task_id": task_id,
                "status": qt_task.get("status", "running"),
                "progress": 0 if qt_task.get("status") == "running" else 100,
                "step": "quality_test",
            })
            if qt_task.get("status") == "completed":
                await websocket.send_json({"task_id": task_id, "status": "completed", "progress": 100, "step": "done", **qt_task})
                await websocket.close()
                return
            import asyncio
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
                except asyncio.TimeoutError:
                    current = _quality_test_cache.get(task_id, {})
                    if current.get("status") == "completed":
                        await websocket.send_json({"task_id": task_id, "status": "completed", "progress": 100, "step": "done", **current})
                        await websocket.close()
                        return
                    await websocket.send_json({"task_id": task_id, "status": "running", "progress": 50, "step": "quality_test", "heartbeat": True})
        except WebSocketDisconnect:
            pass
        finally:
            ws_manager.disconnect(task_id, websocket)
        return

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

    file_size = os.path.getsize(output_path)
    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename=download_name,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
    )

@router.get("/download-file/{filename}")
async def download_file(filename: str, request: Request):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    # 生成更友好的下载文件名
    download_name = filename
    if "_rendered_" in filename:
        # 新格式: {task_id}_rendered_{algo_ver}_{sr}_{bd}.wav
        # 旧格式: {task_id}_rendered_{sr}_{bd}.wav
        parts = filename.replace(".wav", "").split("_rendered_")
        task_id_prefix = parts[0]
        task = get_task(task_id_prefix)
        if task and task.get("filename"):
            original_name = task["filename"].rsplit(".", 1)[0]
            suffix = parts[1] if len(parts) > 1 else ""
            segments = suffix.split("_")
            # 取最后两段作为 sr_bd
            sr_bd = "_".join(segments[-2:]) if len(segments) >= 2 else suffix
            download_name = f"{original_name}_repaired_{sr_bd}.wav"
    # 使用 StreamingResponse 支持 Range 请求（断点续传 + 多线程下载）
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    if range_header:
        # 解析 Range: bytes=start-end
        range_match = __import__("re").match(r"bytes=(\d+)-(\d*)", range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            if start >= file_size:
                from fastapi.responses import Response
                return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
            end = min(end, file_size - 1)
            chunk_size = end - start + 1

            def iter_file():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_size = min(8192, remaining)
                        data = f.read(read_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            from fastapi.responses import StreamingResponse
            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type="audio/wav",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(chunk_size),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": f'attachment; filename="{download_name}"',
                },
            )

    # 无 Range 请求，返回完整文件
    return FileResponse(
        file_path,
        media_type="audio/wav",
        filename=download_name,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
    )

@router.get("/render-cache/{task_id}")
async def get_render_cache(task_id: str):
    """查询某个任务已有的渲染交付规格缓存"""
    task = get_task(task_id)
    if not task:
        return {"caches": []}

    # 获取修复时使用的算法版本
    algo_version = task.get("params", {}).get("algorithm_version", "")

    caches = []
    # 检查 OUTPUT_DIR 中是否有该 task 的渲染文件
    if os.path.isdir(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            if not fname.startswith(f"{task_id}_rendered_") or not fname.endswith(".wav"):
                continue
            base = fname.replace(".wav", "")
            # 新格式: {task_id}_rendered_{algo_ver}_{sr}_{bd}
            # 旧格式: {task_id}_rendered_{sr}_{bd}
            parts = base.split("_rendered_")
            if len(parts) != 2:
                continue
            suffix = parts[1]
            segments = suffix.split("_")
            try:
                if len(segments) >= 3:
                    # 新格式: algo_ver / sr / bd
                    sr = int(segments[-2])
                    bd = int(segments[-1])
                    file_algo_ver = "_".join(segments[:-2])
                elif len(segments) == 2:
                    # 旧格式: sr / bd (无算法版本)
                    sr = int(segments[0])
                    bd = int(segments[1])
                    file_algo_ver = ""
                else:
                    continue
                fpath = os.path.join(OUTPUT_DIR, fname)
                mtime = os.path.getmtime(fpath)
                from datetime import datetime, timezone
                mtime_str = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                caches.append({
                    "sample_rate": sr,
                    "bit_depth": bd,
                    "filename": fname,
                    "size": os.path.getsize(fpath),
                    "mtime": mtime_str,
                    "algorithm_version": file_algo_ver.replace("p", ".") if file_algo_ver else algo_version,
                })
            except ValueError:
                pass
    return {"caches": caches}

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

class RepairCacheLookupRequest(BaseModel):
    file_hash: str
    params: dict

@router.post("/cache/lookup")
async def lookup_repair_cache(req: RepairCacheLookupRequest):
    from database import find_repair_cache

    cached = find_repair_cache(req.file_hash, req.params)
    if not cached:
        return {"found": False}

    repair_result = cached.get("repair_result")

    if repair_result and not repair_result.get("waveform_peaks"):
        output_path = cached.get("output_path", "")
        if output_path and os.path.exists(output_path):
            from services.task_manager import _generate_waveform_peaks
            peaks = _generate_waveform_peaks(output_path)
            if peaks:
                repair_result["waveform_peaks"] = peaks
                from database import update_task
                update_task(cached["id"], repair_result=repair_result)

    return {
        "found": True,
        "task_id": cached["id"],
        "output_path": cached.get("output_path", ""),
        "output_size": cached.get("output_size", 0),
        "repair_result": repair_result,
        "detection_result": cached.get("detection_result"),
        "repaired_detection_result": cached.get("repaired_detection_result"),
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


_quality_test_cache: dict = {}


def _parse_pytest_output(output: str) -> dict:
    import re
    lines = output.strip().split("\n")
    tests = []
    summary_line = ""
    for line in lines:
        stripped = line.strip()
        if " PASSED" in stripped:
            test_name = stripped.split(" PASSED")[0].strip()
            full_name = test_name
            if "::" in test_name:
                test_name = test_name.split("::")[-1]
            tests.append({"name": test_name, "full_name": full_name, "status": "passed"})
        elif " FAILED" in stripped:
            test_name = stripped.split(" FAILED")[0].strip()
            full_name = test_name
            if "::" in test_name:
                test_name = test_name.split("::")[-1]
            tests.append({"name": test_name, "full_name": full_name, "status": "failed", "error": ""})
        elif " SKIPPED" in stripped:
            test_name = stripped.split(" SKIPPED")[0].strip()
            full_name = test_name
            if "::" in test_name:
                test_name = test_name.split("::")[-1]
            tests.append({"name": test_name, "full_name": full_name, "status": "skipped"})
        elif "passed" in stripped and ("failed" in stripped or "skipped" in stripped or stripped.endswith("passed")):
            summary_line = stripped

    for t in tests:
        name = t["name"]
        full_name = t.get("full_name", name)
        if "[" in name:
            m = re.search(r'\[(v[\d.]+[\w]*)\]', name)
            t["version"] = m.group(1) if m else ""
        elif "V23a" in full_name or "v23a" in full_name.lower():
            t["version"] = "v2.3a"
        elif "V23" in full_name or "v23" in full_name.lower():
            t["version"] = "v2.3"
        elif "V22a" in full_name or "v22a" in full_name.lower():
            t["version"] = "v2.2a"
        else:
            t["version"] = ""

        category_map = {
            "test_pure_sine": ("baseline", "THD", "纯正弦波输入，输出总谐波失真 < -20 dB"),
            "test_no_hard_clipping": ("baseline", "Flat-top", "输出无 flat-top 样本（硬削波指标）"),
            "test_no_high_frequency_noise": ("baseline", "HF Noise", "5-16kHz 频段噪声增长 < 10x"),
            "test_scale_adjusted_snr": ("baseline", "SNR", "全流程 scale-adjusted SNR > 5 dB"),
            "test_output_finite": ("baseline", "Finite", "输出无 NaN/Inf 值"),
            "test_peak_level_valid": ("baseline", "Peak", "输出峰值 ≤ 1.0"),
            "test_dc_offset_small": ("baseline", "DC", "DC 偏移 < 0.01"),
            "test_output_length_preserved": ("baseline", "Length", "输出长度与输入一致（±5%）"),
            "test_declip_snr": ("per_step", "SNR", "Declip 步骤 SNR > 20 dB"),
            "test_depop_snr": ("per_step", "SNR", "Depop 步骤 SNR > 10 dB"),
            "test_compress_snr": ("per_step", "SNR", "Compress 步骤 SNR > 40 dB（全局常量增益）"),
            "test_peak_limit_snr": ("per_step", "SNR", "Peak Limit 步骤 SNR > 30 dB"),
            "test_loudness_norm_snr": ("per_step", "SNR", "Loudness Norm 步骤 SNR > 60 dB（纯增益）"),
            "test_dc_remove_snr": ("per_step", "SNR", "DC Remove 步骤 SNR > 60 dB"),
            "test_depop_no_large": ("iron_rule", "Window", "Depop 不替换超过 5 个连续样本"),
            "test_compress_is_global": ("iron_rule", "Gain CV", "Compress 增益变异系数 < 1%（无 AM 伪影）"),
            "test_declip_uses_soft": ("iron_rule", "Flat-top", "Declip 不增加 flat-top 样本（使用软削波）"),
            "test_peak_limit_uses_soft": ("iron_rule", "Flat-top", "Peak Limit 不增加 flat-top 样本（使用软削波）"),
            "test_loudness_norm_is_constant": ("iron_rule", "Gain CV", "Loudness Norm 是纯常量增益（CV < 0.1%）"),
            "test_dc_remove_reduces": ("per_step", "DC", "DC Remove 有效降低直流偏移"),
            "test_transient_snr": ("per_step", "SNR", "瞬态修复 SNR > 15 dB"),
            "test_transient_uses_constant": ("iron_rule", "Gain CV", "瞬态修复使用全局常量增益（CV < 5%）"),
            "test_spectral_denoise_snr": ("per_step", "SNR", "频谱降噪 SNR > 10 dB"),
            "test_de_ess_snr": ("per_step", "SNR", "齿音抑制 SNR > 15 dB"),
            "test_de_ess_is_constant": ("iron_rule", "Gain CV", "齿音抑制使用全局常量衰减"),
        }
        matched = False
        for key, val in category_map.items():
            if key in name:
                t["category"], t["metric"], t["description"] = val
                matched = True
                break
        if not matched:
            t["category"] = "other"
            t["metric"] = ""
            t["description"] = ""
        t.pop("full_name", None)

    passed = sum(1 for t in tests if t["status"] == "passed")
    failed = sum(1 for t in tests if t["status"] == "failed")
    skipped = sum(1 for t in tests if t["status"] == "skipped")
    baseline = [t for t in tests if t.get("category") == "baseline"]
    per_step = [t for t in tests if t.get("category") == "per_step"]
    iron_rule = [t for t in tests if t.get("category") == "iron_rule"]

    return {
        "total": len(tests), "passed": passed, "failed": failed, "skipped": skipped,
        "summary": summary_line, "tests": tests,
        "baseline": baseline, "per_step": per_step, "iron_rule": iron_rule,
        "raw_output": output[-4000:] if len(output) > 4000 else output,
    }


def _run_quality_tests_background(task_id: str, loop):
    import subprocess
    import asyncio
    from services.ws_manager import ws_manager
    global _quality_test_cache
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        result = subprocess.run(
            ["python", "-m", "pytest", "backend/tests/test_repair_quality.py", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=180, cwd=project_root,
        )
        output = result.stdout + result.stderr

        for line in output.strip().split("\n"):
            if " PASSED" in line or " FAILED" in line or " SKIPPED" in line:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.send_progress(task_id, {
                            "task_id": task_id, "status": "running",
                            "progress": 50, "step": "quality_test",
                            "quality_test_line": line.strip(),
                        }),
                        loop,
                    )
                except Exception:
                    pass

        parsed = _parse_pytest_output(output)
        parsed["exit_code"] = result.returncode
        parsed["status"] = "completed"
        _quality_test_cache[task_id] = parsed

        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_final(task_id, {
                    "task_id": task_id, "status": "completed",
                    "progress": 100, "step": "done",
                    **parsed,
                }),
                loop,
            )
        except Exception:
            pass
    except subprocess.TimeoutExpired:
        err_data = {
            "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "summary": "测试超时（180秒）", "tests": [], "baseline": [], "per_step": [], "iron_rule": [],
            "raw_output": "", "exit_code": -1, "status": "completed",
        }
        _quality_test_cache[task_id] = err_data
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_final(task_id, {"task_id": task_id, "status": "completed", "progress": 100, "step": "timeout", **err_data}),
                loop,
            )
        except Exception:
            pass
    except Exception as e:
        err_data = {
            "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "summary": f"运行失败: {str(e)}", "tests": [], "baseline": [], "per_step": [], "iron_rule": [],
            "raw_output": "", "exit_code": -1, "status": "completed",
        }
        _quality_test_cache[task_id] = err_data
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_final(task_id, {"task_id": task_id, "status": "completed", "progress": 100, "step": "error", **err_data}),
                loop,
            )
        except Exception:
            pass


@router.post("/quality-tests/start")
async def start_quality_tests():
    import threading
    import uuid
    import asyncio
    global _quality_test_cache
    task_id = f"qt-{uuid.uuid4().hex[:8]}"
    _quality_test_cache[task_id] = {"status": "running", "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                                     "tests": [], "baseline": [], "per_step": [], "iron_rule": [],
                                     "summary": "", "raw_output": "", "exit_code": -1}
    loop = asyncio.get_event_loop()
    thread = threading.Thread(target=_run_quality_tests_background, args=(task_id, loop), daemon=True)
    thread.start()
    return {"task_id": task_id, "status": "running"}


@router.get("/quality-tests/result/{task_id}")
async def get_quality_test_result(task_id: str):
    global _quality_test_cache
    if task_id not in _quality_test_cache:
        return {"status": "not_found", "error": f"Task {task_id} not found"}
    return _quality_test_cache[task_id]
