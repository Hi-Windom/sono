import os
import json
import asyncio
import logging
import stat
import subprocess
import time
from datetime import datetime, timezone
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, MOBILE_MODE, OUTPUT_DIR, UPLOAD_DIR, DECODED_DIR, DEPLOY_TIME_FILE
from database import create_task, find_task_by_hash, get_queue_status, get_task, update_task, _format_timestamp
from services.task_manager import generate_task_id, submit_detect_task, submit_repair_task, cancel_task, executor, can_accept_task, get_active_task_count, get_active_tasks
from services.audio_repair import get_available_versions
from services.ai_detector import get_detector_versions
from services.memory_guard import get_available_memory_bytes, estimate_repair_memory_bytes, should_use_float32, get_total_memory_bytes
from services.param_maps import VOCAL_KEY_MAP, INST_KEY_MAP, flatten_vocal_params, flatten_inst_params

logger = logging.getLogger(__name__)

def _get_audio_info(path: str) -> dict | None:
    try:
        import soundfile as sf
        info = sf.info(path)
        return {
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "duration": info.duration,
            "num_frames": info.frames,
            "format": info.format,
            "subtype": info.subtype,
        }
    except Exception:
        pass
    try:
        import miniaudio
        info = miniaudio.get_file_info(path)
        return {
            "sample_rate": info.sample_rate,
            "channels": info.nchannels,
            "duration": info.duration,
            "num_frames": info.num_frames,
            "format": str(info.file_format),
            "sample_width": info.sample_width,
        }
    except Exception:
        return None

def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    from services.mp3_encoder import encode_mp3
    encode_mp3(wav_path, mp3_path, bitrate)

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
    # 智能识别流式分块处理：v2.2 及以上版本都支持流式处理
    # 通过版本号解析，避免硬编码列表，支持未来新版本自动识别
    def _supports_streaming(version: str) -> bool:
        """检查算法版本是否支持流式分块处理"""
        try:
            # 解析版本号，如 "v2.4a" -> major=2, minor=4
            if version.startswith('v'):
                version = version[1:]
            # 移除后缀（如 'a', 'b', 'beta' 等）
            import re
            match = re.match(r'(\d+)\.(\d+)', version)
            if match:
                major = int(match.group(1))
                minor = int(match.group(2))
                # v2.2 及以上支持流式处理
                return (major > 2) or (major == 2 and minor >= 2)
        except (ValueError, AttributeError):
            pass
        return False

    has_streaming = _supports_streaming(request.algorithm_version)
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

@router.get("/system/load")
async def system_load():
    active_count = get_active_task_count()
    active_tasks = get_active_tasks()
    available_mem = get_available_memory_bytes()
    from config import MAX_CONCURRENT_TASKS
    return {
        "active_tasks": active_count,
        "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
        "available_memory_mb": round(available_mem / 1024 / 1024, 1) if available_mem else None,
        "can_accept": active_count < MAX_CONCURRENT_TASKS,
        "load_percent": round(active_count / MAX_CONCURRENT_TASKS * 100, 1) if MAX_CONCURRENT_TASKS > 0 else 0,
        "active_task_ids": active_tasks,
    }

@router.get("/diag")
async def diagnostics():
    import sys
    import platform
    import shutil
    from datetime import datetime, timezone

    try:
        import psutil
        _has_psutil = True
    except ImportError:
        _has_psutil = False

    result = {"backend": True, "timestamp": datetime.now(timezone.utc).isoformat()}

    result["python"] = True
    result["python_version"] = f"Python {sys.version.split()[0]}"

    ffmpeg_ok = False
    ffmpeg_ver = None
    try:
        proc = await asyncio.create_subprocess_shell(
            "ffmpeg -version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        first_line = output.split("\n")[0] if output else ""
        if "ffmpeg" in first_line.lower():
            ffmpeg_ok = True
            parts = first_line.split()
            if len(parts) >= 3:
                ffmpeg_ver = f"{parts[2]} {parts[3]}" if len(parts) > 3 else parts[2]
    except Exception:
        pass
    result["ffmpeg"] = ffmpeg_ok
    result["ffmpeg_version"] = ffmpeg_ver or "Not found"

    if _has_psutil:
        try:
            mem = psutil.virtual_memory()
            total_gb = round(mem.total / (1024**3), 1)
            avail_gb = round(mem.available / (1024**3), 1)
            used_pct = mem.percent
            result["memory"] = avail_gb >= 0.5
            result["memory_info"] = {
                "total_gb": total_gb,
                "available_gb": avail_gb,
                "used_percent": used_pct,
            }
        except Exception:
            result["memory"] = False
    else:
        result["memory"] = False

    try:
        disk = shutil.disk_usage("/")
        total_gb = round(disk.total / (1024**3), 1)
        free_gb = round(disk.free / (1024**3), 1)
        used_pct = round(disk.used / disk.total * 100, 1)
        result["storage"] = free_gb >= 0.5
        result["storage_info"] = {
            "total_gb": total_gb,
            "available_gb": free_gb,
            "used_percent": used_pct,
        }
    except Exception:
        result["storage"] = False

    gpu_ok = False
    gpu_info = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu_ok = True
            props = torch.cuda.get_device_properties(0)
            vram_total = round(props.total_mem / (1024**3), 1)
            vram_free = round(torch.cuda.mem_get_info(0)[0] / (1024**3), 1)
            gpu_info = f"{props.name} ({vram_free}/{vram_total}GB VRAM)"
        else:
            gpu_info = "N/A (CUDA not available)"
    except ImportError:
        gpu_info = "N/A (PyTorch not installed)"
    except Exception as e:
        gpu_info = f"N/A ({str(e)[:40]})"
    result["gpu"] = gpu_ok
    result["gpu_info"] = gpu_info

    result["system"] = {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "platform": platform.platform(),
        "hostname": platform.node(),
    }

    uptime_seconds = None
    if _has_psutil:
        try:
            uptime_seconds = int(time.time() - psutil.boot_time())
        except Exception:
            pass
    result["runtime"] = {
        "pid": os.getpid(),
        "mobile_mode": MOBILE_MODE,
        "uptime_seconds": uptime_seconds,
        "algorithm_versions": get_available_versions(mobile_mode=MOBILE_MODE),
    }

    try:
        upload_count = len(os.listdir(UPLOAD_DIR)) if os.path.isdir(UPLOAD_DIR) else -1
        output_count = len(os.listdir(OUTPUT_DIR)) if os.path.isdir(OUTPUT_DIR) else -1
        decoded_count = len(os.listdir(DECODED_DIR)) if os.path.isdir(DECODED_DIR) else -1
        result["directories"] = {
            "upload_files": upload_count,
            "output_files": output_count,
            "decoded_files": decoded_count,
        }
    except Exception:
        result["directories"] = None

    if _has_psutil:
        try:
            p = psutil.Process(os.getpid())
            result["process"] = {
                "cpu_percent": round(p.cpu_percent(), 1),
                "memory_mb": round(p.memory_info().rss / (1024 * 1024), 1),
                "threads": p.num_threads(),
                "fd_count": p.num_fds() if hasattr(p, 'num_fds') else None,
            }
        except Exception:
            result["process"] = None
    else:
        result["process"] = None

    return result

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

    audio_info = _get_audio_info(upload_path)

    return {
        "task_id": task_id,
        "filename": file.filename,
        "size": file_size,
        "audio_info": audio_info,
    }

@router.post("/upload-dual")
async def upload_dual_audio(
    vocal_file: UploadFile = File(...),
    accompaniment_file: UploadFile = File(...),
    file_hash: str = Form(""),
    vocal_file_hash: str = Form(""),
    accompaniment_file_hash: str = Form(""),
):
    vocal_ext = os.path.splitext(vocal_file.filename or '')[1].lower()
    accompaniment_ext = os.path.splitext(accompaniment_file.filename or '')[1].lower()
    if vocal_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的人声文件格式: {vocal_ext}")
    if accompaniment_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的伴奏文件格式: {accompaniment_ext}")

    vocal_task_id = generate_task_id()
    accompaniment_task_id = generate_task_id()
    main_task_id = generate_task_id()

    vocal_upload_path = os.path.join(UPLOAD_DIR, f"{vocal_task_id}{vocal_ext}")
    accompaniment_upload_path = os.path.join(UPLOAD_DIR, f"{accompaniment_task_id}{accompaniment_ext}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    vocal_content = await vocal_file.read()
    accompaniment_content = await accompaniment_file.read()

    if len(vocal_content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"人声文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
    if len(accompaniment_content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"伴奏文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")

    with open(vocal_upload_path, "wb") as f:
        f.write(vocal_content)
    with open(accompaniment_upload_path, "wb") as f:
        f.write(accompaniment_content)

    vocal_hash = vocal_file_hash or file_hash
    accompaniment_hash = accompaniment_file_hash or file_hash

    vocal_audio_info = _get_audio_info(vocal_upload_path)
    acc_audio_info = _get_audio_info(accompaniment_upload_path)

    create_task(vocal_task_id, f"vocal_{vocal_file.filename or 'audio'}", vocal_upload_path,
                {"audio_info": vocal_audio_info} if vocal_audio_info else {},
                vocal_hash, len(vocal_content))
    create_task(accompaniment_task_id, f"acc_{accompaniment_file.filename or 'audio'}", accompaniment_upload_path,
                {"audio_info": acc_audio_info} if acc_audio_info else {},
                accompaniment_hash, len(accompaniment_content))
    create_task(main_task_id, f"dual_{vocal_file.filename or 'audio'}", vocal_upload_path, {
        "vocal_task_id": vocal_task_id,
        "accompaniment_task_id": accompaniment_task_id,
        "vocal_file_hash": vocal_hash,
        "accompaniment_file_hash": accompaniment_hash,
        "vocal_filename": vocal_file.filename or "",
        "accompaniment_filename": accompaniment_file.filename or "",
    }, file_hash, len(vocal_content) + len(accompaniment_content))

    logger.info(f"[/upload-dual] main_task_id={main_task_id} vocal={vocal_task_id} acc={accompaniment_task_id} vocal_hash={vocal_hash[:12] if vocal_hash else 'none'} acc_hash={accompaniment_hash[:12] if accompaniment_hash else 'none'}")

    vocal_info = _get_audio_info(vocal_upload_path)
    acc_info = _get_audio_info(accompaniment_upload_path)

    return {
        "task_id": main_task_id,
        "vocal_task_id": vocal_task_id,
        "accompaniment_task_id": accompaniment_task_id,
        "vocal_filename": vocal_file.filename,
        "accompaniment_filename": accompaniment_file.filename,
        "vocal_size": len(vocal_content),
        "accompaniment_size": len(accompaniment_content),
        "vocal_info": _get_audio_info(vocal_upload_path),
        "accompaniment_info": _get_audio_info(accompaniment_upload_path),
    }


class DetectRequest(BaseModel):
    task_id: str
    type: str = "original"
    detector_version: str = "v1.1"
    skip_cache: bool = False

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

_audio_files_cache: dict = {"data": None, "ts": 0}

@router.get("/audio-files")
async def list_audio_files():
    import hashlib
    import time

    now = time.time()
    if _audio_files_cache["data"] is not None and now - _audio_files_cache["ts"] < 5:
        return _audio_files_cache["data"]

    files = []
    seen_paths = set()

    for directory, ftype in [(UPLOAD_DIR, "upload"), (OUTPUT_DIR, "output")]:
        if not os.path.exists(directory):
            continue
        for fname in os.listdir(directory):
            fp = os.path.join(directory, fname)
            if not os.path.isfile(fp):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            real = os.path.realpath(fp)
            if real in seen_paths:
                continue
            seen_paths.add(real)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            file_id = hashlib.sha256(fp.encode()).hexdigest()[:16]
            render_type = "render" if "_rendered_" in fname else ftype
            files.append({
                "file_id": file_id,
                "filename": fname,
                "size": st.st_size,
                "type": render_type,
                "modified_at": st.st_mtime,
            })

    files.sort(key=lambda x: x["modified_at"], reverse=True)

    result = {"files": files, "count": len(files)}
    _audio_files_cache["data"] = result
    _audio_files_cache["ts"] = now
    return result

class DetectPathRequest(BaseModel):
    file_id: str
    detector_version: str = "v1.1"

@router.post("/detect-path")
async def detect_by_path(request: DetectPathRequest):
    can_accept, reject_reason = can_accept_task()
    if not can_accept:
        raise HTTPException(status_code=503, detail=reject_reason)

    import hashlib

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

class RepairRequest(BaseModel):
    task_id: str
    params: dict

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


class DualRepairRequest(BaseModel):
    task_id: str
    vocal_task_id: str
    accompaniment_task_id: str
    params: dict
    vocal_params: dict | None = None
    accompaniment_params: dict | None = None
    mix_ratio: float | None = None
    speed: float | None = None


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

    import shutil
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


class RenderRequest(BaseModel):
    task_id: str
    sample_rate: int = 44100
    bit_depth: int = 24
    merge: bool = False
    track_type: str = "both"

@router.post("/render")
async def render_audio_endpoint(request: RenderRequest):
    task = get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_params = task.get("params", {})
    if isinstance(task_params, str):
        import json as _json
        try:
            task_params = _json.loads(task_params)
        except Exception:
            task_params = {}
    
    is_dual_track = task_params.get("processing_mode") == "dual"
    
    if is_dual_track:
        vocal_output_path = task_params.get("vocal_output_path")
        accompaniment_output_path = task_params.get("accompaniment_output_path")
        
        if not vocal_output_path or not os.path.exists(vocal_output_path):
            raise HTTPException(status_code=400, detail="人声修复结果不存在")
        if not accompaniment_output_path or not os.path.exists(accompaniment_output_path):
            raise HTTPException(status_code=400, detail="伴奏修复结果不存在")
    else:
        output_path = task.get("output_path")
        if not output_path or not os.path.exists(output_path):
            raise HTTPException(status_code=400, detail="修复结果不存在，请先完成修复")

    algo_ver = task_params.get("algorithm_version", "v2.0").replace(".", "p")
    speed = task_params.get("speed", 1.0)
    speed_tag = f"_{speed}x" if speed and speed != 1.0 else ""

    if is_dual_track and request.track_type != "both":
        render_filename = f"{request.task_id}_rendered_{algo_ver}{speed_tag}_{request.sample_rate}_{request.bit_depth}_{request.track_type}.wav"
    else:
        merge_suffix = "_merged" if request.merge else ""
        render_filename = f"{request.task_id}_rendered_{algo_ver}{speed_tag}_{request.sample_rate}_{request.bit_depth}{merge_suffix}.wav"
    render_path = os.path.join(OUTPUT_DIR, render_filename)

    update_task(request.task_id, status="rendering", step="渲染交付规格...", progress=0)

    if is_dual_track:
        executor.submit(_run_render_dual, request.task_id, vocal_output_path, accompaniment_output_path, render_path, request.sample_rate, request.bit_depth, render_filename, request.merge, request.track_type)
    else:
        executor.submit(_run_render, request.task_id, output_path, render_path, request.sample_rate, request.bit_depth, render_filename)

    return {"task_id": request.task_id, "status": "rendering"}


def _run_render(task_id, input_path, output_path, target_sr, bit_depth, render_filename):
    from services.render import render_output
    from services.task_manager import _ws_send_progress, _ws_send_final

    source_bit_depth = None
    try:
        from services.audio_loader import load_audio_with_fallback
        _, _, src_bd = load_audio_with_fallback(input_path, sr=None, mono=False, return_bit_depth=True)
        source_bit_depth = src_bd
    except Exception:
        pass

    def progress_callback(pct, step):
        update_task(task_id, progress=pct, step=step)
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "rendering",
            "progress": pct,
            "step": step,
        })

    try:
        result = render_output(input_path, output_path, target_sr, bit_depth, progress_callback=progress_callback, source_bit_depth=source_bit_depth)
        update_task(task_id,
            status="render_completed",
            progress=1.0,
            step="渲染完成",
            render_filename=render_filename,
            render_result=result,
        )
        _ws_send_final(task_id, {
            "task_id": task_id,
            "status": "render_completed",
            "progress": 1.0,
            "step": "渲染完成",
            "render_filename": render_filename,
            "render_result": result,
        })
        from services.ws_manager import ws_manager
        files = [{"filename": render_filename, "sample_rate": target_sr, "bit_depth": bit_depth, "track_type": "both"}]
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast_render_cache_update(task_id, files),
                asyncio.get_event_loop()
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[render] 渲染失败 task_id={task_id}: {e}")
        update_task(task_id, status="error", error=str(e), step="渲染失败")
        _ws_send_final(task_id, {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
            "step": "渲染失败",
        })


def _run_render_dual(task_id, vocal_path, accompaniment_path, output_path, target_sr, bit_depth, render_filename, merge=False, track_type="both"):
    from services.render import render_output
    from services.task_manager import _ws_send_progress, _ws_send_final
    import numpy as np
    import soundfile as sf

    vocal_rendered = False
    accompaniment_rendered = False
    vocal_render_filename = None
    accompaniment_render_filename = None

    def progress_callback(pct, step):
        update_task(task_id, progress=pct, step=step)
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "rendering",
            "progress": pct,
            "step": step,
        })

    try:
        from services.audio_loader import load_audio_with_fallback
        
        if track_type == "vocal":
            progress_callback(0.2, "渲染人声轨...")
            y, sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
            source_bit_depth = None
            try:
                _, _, src_bd = load_audio_with_fallback(vocal_path, sr=None, mono=False, return_bit_depth=True)
                source_bit_depth = src_bd
            except Exception:
                pass
            result = render_output(vocal_path, output_path, target_sr, bit_depth, progress_callback=progress_callback, source_bit_depth=source_bit_depth)
        elif track_type == "accompaniment":
            progress_callback(0.2, "渲染伴奏轨...")
            y, sr = load_audio_with_fallback(accompaniment_path, sr=None, mono=False)
            source_bit_depth = None
            try:
                _, _, src_bd = load_audio_with_fallback(accompaniment_path, sr=None, mono=False, return_bit_depth=True)
                source_bit_depth = src_bd
            except Exception:
                pass
            result = render_output(accompaniment_path, output_path, target_sr, bit_depth, progress_callback=progress_callback, source_bit_depth=source_bit_depth)
        else:
            progress_callback(0.1, "加载人声轨...")
            vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
            progress_callback(0.2, "加载伴奏轨...")
            accompaniment_y, accompaniment_sr = load_audio_with_fallback(accompaniment_path, sr=None, mono=False)
            
            progress_callback(0.3, "混音...")
            max_len = max(vocal_y.shape[1], accompaniment_y.shape[1])
            if vocal_y.shape[1] < max_len:
                vocal_y = np.pad(vocal_y, ((0, 0), (0, max_len - vocal_y.shape[1])), mode='constant')
            if accompaniment_y.shape[1] < max_len:
                accompaniment_y = np.pad(accompaniment_y, ((0, 0), (0, max_len - accompaniment_y.shape[1])), mode='constant')
            
            mixed = (vocal_y + accompaniment_y) / 2
            
            progress_callback(0.5, "渲染输出...")
            mixed = np.clip(mixed, -1.0, 1.0)
            if vocal_sr != target_sr:
                from scipy.signal import resample_poly
                target_len = int(mixed.shape[1] * target_sr / vocal_sr)
                mixed_resampled = np.zeros((mixed.shape[0], target_len), dtype=mixed.dtype)
                for ch in range(mixed.shape[0]):
                    resampled = resample_poly(mixed[ch], target_sr, vocal_sr)
                    mixed_resampled[ch, :len(resampled)] = resampled[:target_len]
                mixed = mixed_resampled
            subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
            subtype = subtype_map.get(bit_depth, "PCM_24")
            sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, target_sr, subtype=subtype)
            
            result = {
                "input_sample_rate": vocal_sr,
                "output_sample_rate": target_sr,
                "output_bit_depth": bit_depth,
                "channels": mixed.shape[0] if mixed.ndim > 1 else 1,
            }

            base_name = render_filename.rsplit(".", 1)[0]
            if base_name.endswith("_merged"):
                base_name = base_name[:-7]

            progress_callback(0.6, "渲染人声独立轨...")
            vocal_render_filename = f"{base_name}_vocal.wav"
            vocal_render_path = os.path.join(os.path.dirname(output_path), vocal_render_filename)
            vocal_source_bit_depth = None
            try:
                _, _, src_bd = load_audio_with_fallback(vocal_path, sr=None, mono=False, return_bit_depth=True)
                vocal_source_bit_depth = src_bd
            except Exception:
                pass
            try:
                render_output(vocal_path, vocal_render_path, target_sr, bit_depth, progress_callback=progress_callback, source_bit_depth=vocal_source_bit_depth)
                vocal_rendered = True
                logger.info(f"[render_dual] 人声独立轨渲染完成: {vocal_render_filename}")
            except Exception as e:
                logger.warning(f"[render_dual] 人声独立轨渲染失败: {e}")

            progress_callback(0.8, "渲染伴奏独立轨...")
            accompaniment_render_filename = f"{base_name}_accompaniment.wav"
            accompaniment_render_path = os.path.join(os.path.dirname(output_path), accompaniment_render_filename)
            accompaniment_source_bit_depth = None
            try:
                _, _, src_bd = load_audio_with_fallback(accompaniment_path, sr=None, mono=False, return_bit_depth=True)
                accompaniment_source_bit_depth = src_bd
            except Exception:
                pass
            try:
                render_output(accompaniment_path, accompaniment_render_path, target_sr, bit_depth, progress_callback=progress_callback, source_bit_depth=accompaniment_source_bit_depth)
                accompaniment_rendered = True
                logger.info(f"[render_dual] 伴奏独立轨渲染完成: {accompaniment_render_filename}")
            except Exception as e:
                logger.warning(f"[render_dual] 伴奏独立轨渲染失败: {e}")

        progress_callback(0.9, "完成")
        update_task(task_id,
            status="render_completed",
            progress=1.0,
            step="渲染完成",
            render_filename=render_filename,
            render_result=result,
        )
        _ws_send_final(task_id, {
            "task_id": task_id,
            "status": "render_completed",
            "progress": 1.0,
            "step": "渲染完成",
            "render_filename": render_filename,
            "render_result": result,
        })
        from services.ws_manager import ws_manager
        files = [{"filename": render_filename, "sample_rate": target_sr, "bit_depth": bit_depth, "track_type": "both"}]
        if vocal_rendered and vocal_render_filename:
            files.append({"filename": vocal_render_filename, "sample_rate": target_sr, "bit_depth": bit_depth, "track_type": "vocal"})
        if accompaniment_rendered and accompaniment_render_filename:
            files.append({"filename": accompaniment_render_filename, "sample_rate": target_sr, "bit_depth": bit_depth, "track_type": "accompaniment"})
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast_render_cache_update(task_id, files),
                asyncio.get_event_loop()
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[render_dual] 渲染失败 task_id={task_id}: {e}")
        update_task(task_id, status="error", error=str(e), step="渲染失败")
        _ws_send_final(task_id, {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
            "step": "渲染失败",
        })

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
        if task.get("status") in ("completed", "detected", "error", "render_completed"):
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
                if current_task["status"] in ("completed", "detected", "error", "render_completed"):
                    await websocket.close()
                    return
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(task_id, websocket)


@router.websocket("/ws/cache-events")
async def websocket_cache_events(websocket: WebSocket):
    await websocket.accept()
    from services.ws_manager import ws_manager
    CACHE_LISTENER_ID = "__cache_events__"
    await ws_manager.connect(CACHE_LISTENER_ID, websocket)
    try:
        import asyncio
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "status": "alive"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(CACHE_LISTENER_ID, websocket)


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
    speed = task.get("params", {}).get("speed", 1.0)
    speed_tag = f"{speed}x_" if speed and speed != 1.0 else ""
    download_name = f"{base_name}_{speed_tag}repaired.wav"

    file_size = os.path.getsize(output_path)
    from urllib.parse import quote
    encoded_name = quote(download_name)
    ascii_name = download_name.encode("ascii", "ignore").decode("ascii") or "audio_repaired.wav"
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'

    def iter_full_file():
        with open(output_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter_full_file(),
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
    )

@router.get("/download-file/{filename}")
async def download_file(filename: str, request: Request):
    logger.info(f"[DOWNLOAD] Request received: filename={filename}, client={request.client.host if request.client else 'unknown'}")
    file_path = os.path.join(OUTPUT_DIR, filename)
    logger.info(f"[DOWNLOAD] File path: {file_path}, exists={os.path.exists(file_path)}")
    if not os.path.exists(file_path):
        logger.warning(f"[DOWNLOAD] File not found: {file_path}")
        raise HTTPException(status_code=404, detail="文件不存在")
    # 生成友好下载文件名: 原始文件名_算法版本_交付规格_时间戳.wav
    download_name = filename
    if "_rendered_" in filename:
        parts = filename.replace(".wav", "").split("_rendered_")
        task_id_prefix = parts[0]
        task = get_task(task_id_prefix)
        original_basename = "audio"
        algo_ver_display = ""
        sr_display = ""
        bd_display = ""
        if task and task.get("original_filename"):
            original_basename = os.path.splitext(task["original_filename"])[0]
        suffix = parts[1] if len(parts) > 1 else ""
        segments = suffix.split("_")
        if len(segments) >= 3:
            # 新格式: algo_ver / sr / bd
            sr_val = int(segments[-2]) if segments[-2].isdigit() else 0
            sr_display = f"{sr_val // 1000}k" if sr_val >= 1000 else f"{sr_val}k"
            bd_display = f"{segments[-1]}bit"
            algo_ver_raw = "_".join(segments[:-2])
            algo_ver_display = algo_ver_raw.replace("p", ".")
        elif len(segments) == 2:
            sr_val = int(segments[0]) if segments[0].isdigit() else 0
            sr_display = f"{sr_val // 1000}k" if sr_val >= 1000 else f"{sr_val}k"
            bd_display = f"{segments[1]}bit"
            algo_ver_display = task.get("params", {}).get("algorithm_version", "") if task else ""
        # 生成时间戳 (文件修改时间)
        from datetime import datetime, timezone
        mtime = os.path.getmtime(file_path)
        ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        # 拼接: 原始文件名_算法版本_交付规格_时间戳.wav
        name_parts = [original_basename]
        if algo_ver_display:
            name_parts.append(algo_ver_display)
        speed = task.get("params", {}).get("speed", 1.0) if task else 1.0
        if speed and speed != 1.0:
            name_parts.append(f"{speed}x")
        if sr_display and bd_display:
            name_parts.append(f"{sr_display}_{bd_display}")
        name_parts.append(ts)
        download_name = "_".join(name_parts) + ".wav"
    # 使用 StreamingResponse 支持 Range 请求（断点续传 + 多线程下载）
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")
    logger.info(f"[DOWNLOAD] File size: {file_size}, Range header: {range_header}")
    # 统一使用 RFC 5987 编码 Content-Disposition，确保中文文件名正确
    from urllib.parse import quote
    encoded_name = quote(download_name)
    ascii_name = download_name.encode("ascii", "ignore").decode("ascii") or "audio.wav"
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'

    if range_header:
        # 解析 Range: bytes=start-end
        range_match = __import__("re").match(r"bytes=(\d+)-(\d*)", range_header)
        logger.info(f"[DOWNLOAD] Range matched: {range_match is not None}")
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            logger.info(f"[DOWNLOAD] Range: start={start}, end={end}")
            if start >= file_size:
                logger.warning(f"[DOWNLOAD] Invalid range: start={start} >= file_size={file_size}")
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
            logger.info(f"[DOWNLOAD] Returning 206 Partial Content: bytes {start}-{end}/{file_size}")
            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type="audio/wav",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(chunk_size),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": disposition,
                },
            )

    # 无 Range 请求，返回完整文件（使用 StreamingResponse 统一 Content-Disposition 格式）
    logger.info(f"[DOWNLOAD] Returning 200 OK with full file, disposition={disposition}")
    def iter_full_file():
        with open(file_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter_full_file(),
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
    )

def _find_rendered_merged(task_id: str) -> str | None:
    """查找任务的 render 合并缓存 WAV"""
    if not os.path.isdir(OUTPUT_DIR):
        return None
    prefix = f"{task_id}_rendered_"
    for fname in os.listdir(OUTPUT_DIR):
        if fname.startswith(prefix) and fname.endswith("_merged.wav"):
            return os.path.join(OUTPUT_DIR, fname)
    return None


def _merge_wavs(vocal_path: str, acc_path: str, output_path: str):
    """合并人声和伴奏为混合 WAV"""
    import numpy as np
    import soundfile as sf
    from services.audio_loader import load_audio_with_fallback

    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    acc_y, acc_sr = load_audio_with_fallback(acc_path, sr=None, mono=False)

    max_len = max(vocal_y.shape[1], acc_y.shape[1])
    if vocal_y.shape[1] < max_len:
        vocal_y = np.pad(vocal_y, ((0, 0), (0, max_len - vocal_y.shape[1])), mode='constant')
    if acc_y.shape[1] < max_len:
        acc_y = np.pad(acc_y, ((0, 0), (0, max_len - acc_y.shape[1])), mode='constant')

    mixed = np.clip((vocal_y + acc_y) / 2, -1.0, 1.0)
    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, vocal_sr, subtype="PCM_16")


@router.get("/download-mp3/{task_id}")
async def download_mp3(task_id: str, request: Request):
    wav_path = os.path.join(OUTPUT_DIR, f"{task_id}_repaired.wav")
    temp_wav = None

    if not os.path.exists(wav_path):
        task = get_task(task_id)
        if task:
            params = task.get("params", {})
            if isinstance(params, str):
                import json as _json
                try:
                    params = _json.loads(params)
                except Exception:
                    params = {}
            if params.get("processing_mode") == "dual":
                merged_wav = _find_rendered_merged(task_id)
                if merged_wav:
                    wav_path = merged_wav
                else:
                    vocal_task_id = params.get("vocal_task_id")
                    acc_task_id = params.get("accompaniment_task_id")
                    vocal_wav = os.path.join(OUTPUT_DIR, f"{vocal_task_id}_repaired.wav") if vocal_task_id else None
                    acc_wav = os.path.join(OUTPUT_DIR, f"{acc_task_id}_repaired.wav") if acc_task_id else None
                    if vocal_wav and os.path.exists(vocal_wav) and acc_wav and os.path.exists(acc_wav):
                        temp_wav = os.path.join(OUTPUT_DIR, f"{task_id}_temp_merged.wav")
                        _merge_wavs(vocal_wav, acc_wav, temp_wav)
                        wav_path = temp_wav
                    elif vocal_wav and os.path.exists(vocal_wav):
                        wav_path = vocal_wav
                    elif acc_wav and os.path.exists(acc_wav):
                        wav_path = acc_wav

    if not os.path.exists(wav_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    mp3_path = os.path.join(OUTPUT_DIR, f"{task_id}_repaired.mp3")
    if not os.path.exists(mp3_path):
        try:
            _wav_to_mp3(wav_path, mp3_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ImportError, RuntimeError) as e:
            raise HTTPException(status_code=500, detail=f"MP3编码库未安装: {e}")
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"音频格式不支持: {e}")
        except Exception as e:
            logger.error(f"[DOWNLOAD-MP3] 转码失败 task_id={task_id}: {e}")
            raise HTTPException(status_code=500, detail=f"MP3转码失败: {e}")

    # Clean up temporary merged WAV (encoding already succeeded or MP3 existed)
    if temp_wav and os.path.exists(temp_wav):
        os.unlink(temp_wav)

    file_size = os.path.getsize(mp3_path)
    from urllib.parse import quote
    download_name = f"{task_id}.mp3"
    task = get_task(task_id)
    if task and task.get("original_filename"):
        original_basename = os.path.splitext(task["original_filename"])[0]
        speed = task.get("params", {}).get("speed", 1.0)
        speed_tag = f"{speed}x_" if speed and speed != 1.0 else ""
        download_name = f"{original_basename}_{speed_tag}repaired.mp3"
    encoded_name = quote(download_name)
    ascii_name = download_name.encode("ascii", "ignore").decode("ascii") or "audio.mp3"
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'
    range_header = request.headers.get("range")
    if range_header:
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
                with open(mp3_path, "rb") as f:
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
                media_type="audio/mpeg",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(chunk_size),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": disposition,
                },
            )
    def iter_full_file_and_cleanup():
        try:
            with open(mp3_path, "rb") as f:
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    yield data
        finally:
            if os.path.exists(mp3_path):
                os.unlink(mp3_path)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter_full_file_and_cleanup(),
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
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
            # 格式: {task_id}_rendered_{algo_ver}_{sr}_{bd}[_{track_type}][_merged]
            parts = base.split("_rendered_")
            if len(parts) != 2:
                continue
            suffix = parts[1]
            segments = suffix.split("_")
            try:
                track_type = "both"
                is_merged = False
                
                if len(segments) >= 4:
                    # 双轨模式格式: algo_ver / sr / bd / track_type 或 algo_ver / sr / bd / merged
                    if segments[-1] == "merged":
                        is_merged = True
                        sr = int(segments[-3])
                        bd = int(segments[-2])
                        file_algo_ver = "_".join(segments[:-3])
                    elif segments[-1] in ("vocal", "accompaniment"):
                        track_type = segments[-1]
                        sr = int(segments[-3])
                        bd = int(segments[-2])
                        file_algo_ver = "_".join(segments[:-3])
                    else:
                        sr = int(segments[-2])
                        bd = int(segments[-1])
                        file_algo_ver = "_".join(segments[:-2])
                elif len(segments) >= 3:
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
                cache_entry = {
                    "sample_rate": sr,
                    "bit_depth": bd,
                    "filename": fname,
                    "size": os.path.getsize(fpath),
                    "mtime": mtime_str,
                    "algorithm_version": file_algo_ver.replace("p", ".") if file_algo_ver else algo_version,
                }
                if track_type != "both":
                    cache_entry["track_type"] = track_type
                if is_merged:
                    cache_entry["is_merged"] = True
                caches.append(cache_entry)
            except ValueError:
                pass
    return {"caches": caches}

@router.delete("/render-cache/{filename}")
async def delete_render_cache(filename: str):
    """删除单个渲染缓存文件"""
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    if "_rendered_" not in filename:
        raise HTTPException(status_code=400, detail="不是渲染缓存文件")
    released = os.path.getsize(file_path)
    os.remove(file_path)
    return {"released_bytes": released, "filename": filename}


_DELIVERY_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


@router.get("/delivery-files")
async def list_delivery_files():
    if not os.path.isdir(OUTPUT_DIR):
        return {"files": []}

    files = []
    for fname in os.listdir(OUTPUT_DIR):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in _DELIVERY_AUDIO_EXTENSIONS:
            continue
        fp = os.path.join(OUTPUT_DIR, fname)
        if not os.path.isfile(fp):
            continue
        try:
            st = os.stat(fp)
        except OSError:
            continue

        entry = {
            "filename": fname,
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "is_parent": False,
        }

        if "_rendered_" in fname:
            base = fname.replace(".wav", "")
            parts = base.split("_rendered_")
            if len(parts) == 2:
                task_id = parts[0]
                suffix = parts[1]
                segments = suffix.split("_")
                track_type = "both"
                if segments[-1] == "vocal":
                    track_type = "vocal"
                elif segments[-1] == "accompaniment":
                    track_type = "accompaniment"
                elif segments[-1] == "merged":
                    track_type = "both"
                entry["task_id"] = task_id
                if track_type != "both":
                    entry["track_type"] = track_type

        files.append(entry)

    task_groups = {}
    for f in files:
        tid = f.get("task_id")
        if tid:
            task_groups.setdefault(tid, []).append(f)

    for task_id, group in task_groups.items():
        parent = None
        children = []
        for f in group:
            if f.get("track_type") in ("vocal", "accompaniment"):
                children.append(f)
            else:
                parent = f
        if parent and children:
            parent["is_parent"] = True
            parent["children"] = [c["filename"] for c in children]
            for c in children:
                c["parent_filename"] = parent["filename"]

    return {"files": files}


@router.delete("/delivery-files/{filename}")
async def delete_delivery_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="不是文件")
    try:
        os.remove(file_path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="权限不足，无法删除")
    logger.info(f"[/delivery-files] deleted: {filename}")
    return {"status": "ok"}


@router.delete("/delivery-files/parent/{filename}")
async def delete_delivery_parent(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    parent_task_id = None
    if "_rendered_" in filename:
        base = filename.replace(".wav", "")
        parts = base.split("_rendered_")
        if len(parts) == 2:
            parent_task_id = parts[0]

    if not parent_task_id:
        try:
            os.remove(file_path)
        except PermissionError:
            raise HTTPException(status_code=403, detail="权限不足，无法删除")
        return {"status": "ok", "deleted": [filename]}

    deleted = []
    if os.path.isdir(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            if fname.startswith(f"{parent_task_id}_rendered_") and fname.endswith(".wav"):
                fp = os.path.join(OUTPUT_DIR, fname)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                        deleted.append(fname)
                    except PermissionError:
                        logger.warning(f"无法删除文件: {fp}")

    if not deleted:
        raise HTTPException(status_code=404, detail="未找到相关文件")

    logger.info(f"[/delivery-files/parent] deleted: {deleted}")
    return {"status": "ok", "deleted": deleted}


# ===== 分析缓存 API =====

class AnalysisCacheRequest(BaseModel):
    quick_hash: str
    file_name: str = ""
    file_size: int = 0
    wav_info: str = ""
    analysis: str = ""

@router.get("/analysis-cache/{quick_hash}")
async def get_analysis_cache_endpoint(quick_hash: str):
    """获取单条分析缓存"""
    from database import get_analysis_cache as db_get
    cached = db_get(quick_hash)
    if not cached:
        return {"found": False}
    return {"found": True, "data": cached}

@router.post("/analysis-cache")
async def save_analysis_cache_endpoint(request: AnalysisCacheRequest):
    """保存分析缓存"""
    from database import save_analysis_cache as db_save
    db_save(request.quick_hash, request.file_name, request.file_size, request.wav_info, request.analysis)
    return {"status": "ok"}

@router.get("/analysis-cache-list")
async def list_analysis_cache():
    """获取所有分析缓存列表"""
    from database import get_all_analysis_cache
    entries = get_all_analysis_cache()
    return {"entries": entries, "count": len(entries)}

@router.delete("/analysis-cache/{quick_hash}")
async def delete_analysis_cache_endpoint(quick_hash: str):
    """删除单条分析缓存"""
    from database import delete_analysis_cache as db_delete
    db_delete(quick_hash)
    return {"status": "ok"}

@router.post("/analysis-cache-clear")
async def clear_analysis_cache():
    """清空所有分析缓存"""
    from database import clear_all_analysis_cache
    count = clear_all_analysis_cache()
    return {"deleted_count": count}


@router.get("/decoded-wav/{file_hash}")
async def get_decoded_wav(file_hash: str, request: Request):
    """获取非WAV文件的解码WAV缓存，支持Range断点续传"""
    decoded_path = os.path.join(DECODED_DIR, f"{file_hash}.wav")
    if not os.path.exists(decoded_path):
        raise HTTPException(status_code=404, detail="解码缓存不存在")

    file_size = os.path.getsize(decoded_path)
    range_header = request.headers.get("range")

    if range_header:
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
                with open(decoded_path, "rb") as f:
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
                },
            )

    def iter_full_file():
        with open(decoded_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter_full_file(),
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


@router.head("/decoded-wav/{file_hash}")
async def head_decoded_wav(file_hash: str):
    """检查解码WAV缓存是否存在"""
    decoded_path = os.path.join(DECODED_DIR, f"{file_hash}.wav")
    if not os.path.exists(decoded_path):
        raise HTTPException(status_code=404, detail="解码缓存不存在")
    from fastapi.responses import Response
    file_size = os.path.getsize(decoded_path)
    return Response(
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Type": "audio/wav",
        },
    )


@router.post("/decoded-wav/{file_hash}")
async def create_decoded_wav(file_hash: str):
    """为非WAV文件创建解码WAV缓存（后台异步）"""
    decoded_path = os.path.join(DECODED_DIR, f"{file_hash}.wav")
    if os.path.exists(decoded_path):
        return {"status": "ok", "message": "缓存已存在"}

    task = find_task_by_hash(file_hash)
    if not task:
        raise HTTPException(status_code=404, detail="未找到对应的上传文件")

    original_path = task.get("original_path", "")
    if not original_path or not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="原始文件不存在")

    ext = os.path.splitext(original_path)[1].lower()
    if ext == ".wav":
        return {"status": "ok", "message": "WAV文件无需解码缓存"}

    task_id = task.get("id", "")

    def _convert_to_wav():
        try:
            import numpy as np
            from services.audio_loader import load_audio_with_fallback
            y, sr = load_audio_with_fallback(original_path)
            if y.ndim == 2:
                y = y.T
            os.makedirs(DECODED_DIR, exist_ok=True)
            import soundfile as sf
            sf.write(decoded_path, y, sr)
            logger.info(f"解码WAV缓存创建完成: {decoded_path} size={os.path.getsize(decoded_path)}")
            from database import update_task
            update_task(task_id, original_path=decoded_path)
            if original_path != decoded_path and os.path.exists(original_path):
                os.remove(original_path)
                logger.info(f"已删除原始文件: {original_path}")
        except Exception as e:
            logger.warning(f"解码WAV缓存创建失败: {e}")

    executor.submit(_convert_to_wav)
    return {"status": "ok", "message": "正在后台创建解码缓存"}

@router.get("/audio-info/{file_hash}")
async def get_audio_info(file_hash: str):
    task = find_task_by_hash(file_hash)
    if not task:
        raise HTTPException(status_code=404, detail="未找到对应的上传文件")

    original_path = task.get("original_path", "")
    if not original_path or not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    try:
        audio_info = _get_audio_info(original_path)
        if audio_info is None:
            raise HTTPException(status_code=500, detail="获取音频信息失败")
        return audio_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取音频信息失败: {e}")

@router.get("/waveform/{file_hash}")
async def get_waveform(file_hash: str):
    task = find_task_by_hash(file_hash)
    if not task:
        raise HTTPException(status_code=404, detail="未找到对应的上传文件")

    from database import get_analysis_cache as db_get, save_analysis_cache as db_save
    cached = db_get(file_hash)
    if cached and cached.get("waveform_peaks"):
        try:
            return {"peaks": json.loads(cached["waveform_peaks"])}
        except Exception:
            pass

    original_path = task.get("original_path", "")
    if not original_path or not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    from services.task_manager import _generate_waveform_peaks
    peaks = _generate_waveform_peaks(original_path)
    if not peaks:
        raise HTTPException(status_code=500, detail="波形生成失败")

    if cached:
        from database import get_db
        conn = get_db()
        conn.execute("UPDATE analysis_cache SET waveform_peaks = ? WHERE quick_hash = ?", (json.dumps(peaks), file_hash))
        conn.commit()
        conn.close()
    else:
        db_save(file_hash, task.get("original_filename", ""), task.get("file_size", 0), "", "", waveform_peaks=json.dumps(peaks))

    return {"peaks": peaks}

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
async def preview_audio(task_id: str, type: str = 'repaired'):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if type == 'original':
        original_path = task.get("original_path", "")
        if not original_path or not os.path.exists(original_path):
            raise HTTPException(status_code=404, detail="原始音频不存在")
        return FileResponse(
            original_path,
            media_type="audio/wav",
        )

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
    render_size = 0
    repair_size = 0
    upload_count = 0
    output_count = 0
    render_count = 0
    repair_count = 0
    invalid_count = 0
    invalid_size = 0

    conn = get_db()
    db_files = set()
    try:
        all_tasks = conn.execute(
            "SELECT id, original_filename, original_path, output_path, status, created_at FROM tasks ORDER BY created_at DESC"
        ).fetchall()
        for row in all_tasks:
            if row["original_path"]:
                db_files.add(row["original_path"])
            if row["output_path"]:
                db_files.add(row["output_path"])
    finally:
        conn.close()

    def _check_invalid(filepath):
        nonlocal invalid_count, invalid_size
        is_valid, _ = _is_valid_audio_file(filepath)
        is_orphaned = filepath not in db_files
        if not is_valid or is_orphaned:
            invalid_count += 1
            invalid_size += os.path.getsize(filepath) if os.path.exists(filepath) else 0

    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            fp = os.path.join(UPLOAD_DIR, f)
            if os.path.isfile(fp):
                upload_size += os.path.getsize(fp)
                upload_count += 1
                _check_invalid(fp)

    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            fp = os.path.join(OUTPUT_DIR, f)
            if os.path.isfile(fp):
                output_size += os.path.getsize(fp)
                output_count += 1
                if "_rendered_" in f:
                    render_size += os.path.getsize(fp)
                    render_count += 1
                else:
                    repair_count += 1
                _check_invalid(fp)

    repair_size = output_size - render_size

    tasks = []
    for row in all_tasks:
        orig_path = row["original_path"] if row["original_path"] else ""
        out_path = row["output_path"] if row["output_path"] else ""

        orig_exists = bool(orig_path) and os.path.exists(orig_path)
        out_exists = bool(out_path) and os.path.exists(out_path)

        orig_size = os.path.getsize(orig_path) if orig_exists else 0
        out_size = os.path.getsize(out_path) if out_exists else 0

        # 收集该任务的渲染缓存
        task_render_caches = []
        if os.path.isdir(OUTPUT_DIR):
            task_id_prefix = row["id"]
            for fname in os.listdir(OUTPUT_DIR):
                if fname.startswith(f"{task_id_prefix}_rendered_") and fname.endswith(".wav"):
                    fp = os.path.join(OUTPUT_DIR, fname)
                    task_render_caches.append({
                        "filename": fname,
                        "size": os.path.getsize(fp),
                    })

        task_info = {
            "id": row["id"],
            "filename": row["original_filename"] or "unknown",
            "status": row["status"],
            "created_at": _format_timestamp(row["created_at"]),
            "original_exists": orig_exists,
            "output_exists": out_exists,
            "original_size": orig_size,
            "output_size": out_size,
            "total_size": orig_size + out_size,
            "render_caches": task_render_caches,
        }
        tasks.append(task_info)

    return {
        "total_size": upload_size + output_size,
        "upload_size": upload_size,
        "output_size": output_size,
        "repair_size": repair_size,
        "render_size": render_size,
        "upload_count": upload_count,
        "output_count": output_count,
        "repair_count": repair_count,
        "render_count": render_count,
        "task_count": len(tasks),
        "invalid_count": invalid_count,
        "invalid_size": invalid_size,
        "tasks": tasks,
    }

class RepairCacheLookupRequest(BaseModel):
    file_hash: str
    params: dict

class DualRepairCacheLookupRequest(BaseModel):
    vocal_file_hash: str
    accompaniment_file_hash: str
    params: dict = {}
    vocal_params: dict | None = None
    accompaniment_params: dict | None = None
    mix_ratio: float | None = None
    speed: float | None = None


class FileInfoByHashRequest(BaseModel):
    file_hashes: list[str]


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

@router.post("/cache/lookup-dual")
async def lookup_dual_repair_cache(req: DualRepairCacheLookupRequest):
    from database import find_dual_repair_cache

    flat_params = req.params.copy()
    flat_params.pop("processing_mode", None)

    if req.vocal_params:
        flat_vocal = flatten_vocal_params(req.vocal_params)
        flat_params["vocal_params"] = flat_vocal
        flat_params.update(flat_vocal)

    if req.accompaniment_params:
        flat_inst = flatten_inst_params(req.accompaniment_params)
        flat_params["inst_params"] = flat_inst
        flat_params.update(flat_inst)

    if req.mix_ratio is not None:
        flat_params["vocal_ratio"] = req.mix_ratio
        flat_params["accompaniment_ratio"] = 1.0

    if req.speed is not None:
        flat_params["speed"] = req.speed

    logger.info(f"[cache-lookup-dual] input flat_params keys: {sorted(flat_params.keys())}")
    logger.info(f"[cache-lookup-dual] input flat_params: {json.dumps(flat_params, sort_keys=True)[:500]}")

    cached = find_dual_repair_cache(req.vocal_file_hash, req.accompaniment_file_hash, flat_params)
    if not cached:
        return {"found": False}
    repair_result = cached.get("repair_result")
    return {
        "found": True,
        "task_id": cached["id"],
        "output_path": cached.get("output_path", ""),
        "output_size": cached.get("output_size", 0),
        "repair_result": repair_result,
        "detection_result": cached.get("detection_result"),
        "repaired_detection_result": cached.get("repaired_detection_result"),
    }

@router.post("/file-info-by-hash")
async def get_file_info_by_hash(request: FileInfoByHashRequest):
    from database import find_task_by_hash
    result = {}
    for file_hash in request.file_hashes:
        task = find_task_by_hash(file_hash)
        if not task:
            logger.info(f"[file-info-by-hash] hash={file_hash[:12]} NOT FOUND")
            continue
        params = task.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                params = {}
        audio_info = params.get("audio_info") if isinstance(params, dict) else None
        if audio_info:
            result[file_hash] = audio_info
            logger.info(f"[file-info-by-hash] hash={file_hash[:12]} found audio_info in db: {audio_info}")
        else:
            path = task.get("original_path")
            if path and os.path.exists(path):
                try:
                    audio_info = _get_audio_info(path)
                    if audio_info:
                        result[file_hash] = audio_info
                    logger.info(f"[file-info-by-hash] hash={file_hash[:12]} read from file: {audio_info}")
                except Exception as e:
                    logger.info(f"[file-info-by-hash] hash={file_hash[:12]} read file error: {e}")
    return result


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

@router.post("/cache/clear-render")
async def clear_render_cache():
    """清理交付渲染缓存（仅删除 _rendered_ 文件）"""
    released = 0
    cleaned_count = 0

    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            if "_rendered_" in filename and filename.endswith(".wav"):
                filepath = os.path.join(OUTPUT_DIR, filename)
                if os.path.isfile(filepath):
                    try:
                        released += os.path.getsize(filepath)
                        os.remove(filepath)
                        cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"删除渲染缓存失败: {filepath}, {e}")

    return {"released_bytes": released, "cleaned_count": cleaned_count}

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
            "test_adaptive_loudness_normalize_snr": ("per_step", "SNR", "自适应响度归一化 SNR > 60 dB"),
            "test_adaptive_loudness_normalize_is_constant": ("iron_rule", "Gain CV", "自适应响度归一化是纯常量增益"),
            "test_enhanced_multiband_compress_snr": ("per_step", "SNR", "增强多段压缩 SNR > 25 dB"),
            "test_ai_artifact_repair_snr": ("per_step", "SNR", "AI频谱修复 SNR > 5 dB"),
            "test_ai_artifact_repair_reduces": ("per_step", "Presence", "AI频谱修复降低2-5kHz突刺"),
            "test_harmonic_bass_enhance_snr": ("per_step", "SNR", "次谐波低频增强 SNR > 10 dB"),
            "test_harmonic_bass_enhance_increases": ("per_step", "Bass", "次谐波低频增强增加低频能量"),
            "test_air_texture_reconstruct_snr": ("per_step", "SNR", "空气质感重建 SNR > 10 dB"),
            "test_adaptive_loudness_normalize_lite": ("per_step", "SNR", "移动端自适应响度归一化 SNR > 60 dB"),
            "test_enhanced_compress_lite": ("per_step", "SNR", "移动端增强压缩 SNR > 25 dB"),
            "test_ai_artifact_repair_lite": ("per_step", "SNR", "移动端AI频谱修复 SNR > 5 dB"),
            "test_harmonic_bass_enhance_lite": ("per_step", "SNR", "移动端次谐波低频增强 SNR > 10 dB"),
            "test_air_texture_reconstruct_lite": ("per_step", "SNR", "移动端空气质感重建 SNR > 10 dB"),
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
    import uuid
    import asyncio
    global _quality_test_cache
    task_id = f"qt-{uuid.uuid4().hex[:8]}"
    _quality_test_cache[task_id] = {"status": "running", "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                                     "tests": [], "baseline": [], "per_step": [], "iron_rule": [],
                                     "summary": "", "raw_output": "", "exit_code": -1}
    loop = asyncio.get_event_loop()
    executor.submit(_run_quality_tests_background, task_id, loop)
    return {"task_id": task_id, "status": "running"}


@router.get("/quality-tests/result/{task_id}")
async def get_quality_test_result(task_id: str):
    global _quality_test_cache
    if task_id not in _quality_test_cache:
        return {"status": "not_found", "error": f"Task {task_id} not found"}
    return _quality_test_cache[task_id]
