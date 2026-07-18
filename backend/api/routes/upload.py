import os
import json
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, UPLOAD_DIR, BASE_DIR
from database import create_task, find_task_by_hash
from services.task_manager import generate_task_id
from ._common import _get_audio_info

logger = logging.getLogger(__name__)

router = APIRouter()


class StorageEstimateRequest(BaseModel):
    duration: float
    channels: int = 2
    sample_rate: int = 44100
    bit_depth: int = 24


class CheckHashRequest(BaseModel):
    file_hash: str


CHUNK_SIZE = 5 * 1024 * 1024

UPLOAD_SESSIONS_DIR = os.path.join(UPLOAD_DIR, "_sessions")
os.makedirs(UPLOAD_SESSIONS_DIR, exist_ok=True)


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


@router.post("/upload-init")
async def upload_init(
    filename: str = Form(...),
    total_size: int = Form(...),
    total_chunks: int = Form(...),
    file_hash: str = Form(""),
):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    if total_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(UPLOAD_SESSIONS_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    session_info = {
        "filename": filename,
        "ext": ext,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "file_hash": file_hash,
        "session_dir": session_dir,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    session_file = os.path.join(session_dir, "session.json")
    with open(session_file, "w") as f:
        json.dump(session_info, f, indent=2)

    logger.info(f"[upload-init] session_id={session_id} file={filename} size={total_size} chunks={total_chunks}")

    return {
        "session_id": session_id,
        "chunk_size": CHUNK_SIZE,
    }


@router.post("/upload-chunk")
async def upload_chunk(
    session_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
):
    session_dir = os.path.join(UPLOAD_SESSIONS_DIR, session_id)
    session_file = os.path.join(session_dir, "session.json")

    if not os.path.exists(session_file):
        raise HTTPException(status_code=404, detail="上传会话不存在或已过期")

    with open(session_file, "r") as f:
        session_info = json.load(f)

    total_chunks = session_info["total_chunks"]

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail=f"无效的分片索引: {chunk_index}")

    chunk_content = await chunk.read()

    chunk_path = os.path.join(session_dir, f"chunk_{chunk_index:06d}")
    with open(chunk_path, "wb") as f:
        f.write(chunk_content)

    logger.debug(f"[upload-chunk] session={session_id} chunk={chunk_index}/{total_chunks} size={len(chunk_content)}")

    return {
        "success": True,
        "chunk_index": chunk_index,
        "size": len(chunk_content),
    }


@router.get("/upload-status")
async def upload_status(session_id: str = ...):
    session_dir = os.path.join(UPLOAD_SESSIONS_DIR, session_id)
    session_file = os.path.join(session_dir, "session.json")

    if not os.path.exists(session_file):
        raise HTTPException(status_code=404, detail="上传会话不存在或已过期")

    with open(session_file, "r") as f:
        session_info = json.load(f)

    total_chunks = session_info["total_chunks"]
    session_dir_path = session_info["session_dir"]

    uploaded_chunks = []
    for i in range(total_chunks):
        chunk_path = os.path.join(session_dir_path, f"chunk_{i:06d}")
        if os.path.exists(chunk_path):
            uploaded_chunks.append(i)

    return {
        "session_id": session_id,
        "uploaded_chunks": uploaded_chunks,
        "uploaded_count": len(uploaded_chunks),
        "total_chunks": total_chunks,
        "progress": len(uploaded_chunks) / total_chunks * 100,
    }


@router.post("/upload-finalize")
async def upload_finalize(session_id: str = Form(...)):
    session_dir = os.path.join(UPLOAD_SESSIONS_DIR, session_id)
    session_file = os.path.join(session_dir, "session.json")

    if not os.path.exists(session_file):
        raise HTTPException(status_code=404, detail="上传会话不存在或已过期")

    with open(session_file, "r") as f:
        session_info = json.load(f)

    total_chunks = session_info["total_chunks"]
    session_dir_path = session_info["session_dir"]
    filename = session_info["filename"]
    ext = session_info["ext"]
    file_hash = session_info["file_hash"]

    missing_chunks = []
    for i in range(total_chunks):
        chunk_path = os.path.join(session_dir_path, f"chunk_{i:06d}")
        if not os.path.exists(chunk_path):
            missing_chunks.append(i)

    if missing_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"缺少分片: {missing_chunks}"
        )

    task_id = generate_task_id()
    final_path = os.path.join(UPLOAD_DIR, f"{task_id}{ext}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    logger.info(f"[upload-finalize] Merging {total_chunks} chunks into {final_path}")

    with open(final_path, "wb") as final_file:
        for i in range(total_chunks):
            chunk_path = os.path.join(session_dir_path, f"chunk_{i:06d}")
            with open(chunk_path, "rb") as chunk_file:
                final_file.write(chunk_file.read())

    file_size = os.path.getsize(final_path)

    create_task(task_id, filename, final_path, {}, file_hash, file_size)

    import shutil
    shutil.rmtree(session_dir, ignore_errors=True)

    logger.info(f"[upload-finalize] task_id={task_id} file_size={file_size}")

    audio_info = _get_audio_info(final_path)

    return {
        "success": True,
        "task_id": task_id,
        "filename": filename,
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


_audio_files_cache: dict = {"data": None, "ts": 0}


@router.get("/audio-files")
async def list_audio_files():
    import hashlib
    import time
    from config import OUTPUT_DIR

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


@router.post("/training/check-hash")
async def training_check_hash(request: CheckHashRequest):
    training_dir = os.path.join(BASE_DIR, "storage", "training")
    if not os.path.exists(training_dir):
        return {"exists": False}

    for filename in os.listdir(training_dir):
        if request.file_hash in filename:
            return {"exists": True, "filename": filename}
    return {"exists": False}


@router.post("/training/upload")
async def training_upload(
    file: UploadFile = File(...),
    file_hash: str = Form(""),
    label: str = Form("ai_generated"),
):
    from services.training_manager import save_training_file

    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".wav"
    content = await file.read()
    file_size = len(content)

    import io
    file.file = io.BytesIO(content)
    saved_path = await save_training_file(file, file_hash, label, ext)

    return {
        "status": "ok",
        "path": saved_path,
        "filename": file.filename,
        "size": file_size,
    }


@router.post("/training/upload-init")
async def training_upload_init(
    filename: str = Form(...),
    total_size: int = Form(...),
    total_chunks: int = Form(...),
    file_hash: str = Form(""),
    label: str = Form("ai_generated"),
):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(UPLOAD_SESSIONS_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    session_info = {
        "filename": filename,
        "ext": ext,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "file_hash": file_hash,
        "label": label,
        "session_dir": session_dir,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(os.path.join(session_dir, "session.json"), "w") as f:
        json.dump(session_info, f, indent=2)

    return {"session_id": session_id}


@router.post("/training/upload-finalize")
async def training_upload_finalize(
    session_id: str = Form(...),
):
    session_dir = os.path.join(UPLOAD_SESSIONS_DIR, session_id)
    session_file = os.path.join(session_dir, "session.json")

    if not os.path.exists(session_file):
        raise HTTPException(status_code=404, detail="上传会话不存在")

    with open(session_file, "r") as f:
        session_info = json.load(f)

    total_chunks = session_info["total_chunks"]
    session_dir_path = session_info["session_dir"]
    filename = session_info["filename"]
    ext = session_info["ext"]
    file_hash = session_info["file_hash"]
    label = session_info["label"]

    for i in range(total_chunks):
        chunk_path = os.path.join(session_dir_path, f"chunk_{i:06d}")
        if not os.path.exists(chunk_path):
            raise HTTPException(status_code=400, detail=f"缺少分片 {i}")

    task_id = generate_task_id()
    final_path = os.path.join(UPLOAD_DIR, f"{task_id}{ext}")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    with open(final_path, "wb") as final_file:
        for i in range(total_chunks):
            chunk_path = os.path.join(session_dir_path, f"chunk_{i:06d}")
            with open(chunk_path, "rb") as chunk_file:
                final_file.write(chunk_file.read())

    file_size = os.path.getsize(final_path)

    training_dir = os.path.join(BASE_DIR, "storage", "training")
    os.makedirs(training_dir, exist_ok=True)
    training_filename = f"{task_id}_{filename}"
    training_path = os.path.join(training_dir, training_filename)

    import shutil
    shutil.move(final_path, training_path)

    shutil.rmtree(session_dir, ignore_errors=True)

    return {"status": "ok", "path": training_path, "size": file_size}


@router.get("/training/list")
async def list_training_data():
    from services.training_manager import list_training_files
    return list_training_files()
