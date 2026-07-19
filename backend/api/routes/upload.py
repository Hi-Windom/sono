import os
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, UPLOAD_DIR, BASE_DIR
from database import create_task, find_task_by_hash, find_dual_task_by_hashes
from services.task_manager import generate_task_id
from ._common import _get_audio_info, generate_task_access_token

_SESSION_ID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
_audio_files_cache_lock = threading.Lock()

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
        task_id = existing["id"]
        return {
            "exists": True,
            "task_id": task_id,
            "access_token": generate_task_access_token(task_id),
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

    file_size = 0
    try:
        with open(upload_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail=f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
                f.write(chunk)
    except HTTPException:
        if os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except OSError:
                pass
        raise

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

    if file_size == 0:
        if os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except OSError:
                pass
        raise HTTPException(status_code=400, detail="文件为空")

    audio_info = _get_audio_info(upload_path)
    if audio_info is None:
        if os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except OSError:
                pass
        raise HTTPException(status_code=400, detail="无法解析音频文件，文件可能已损坏")

    create_task(task_id, file.filename or "audio", upload_path, {"audio_info": audio_info}, file_hash, file_size)
    logger.info(f"[/upload] task_id={task_id} file_hash={file_hash or 'none'}")

    return {
        "task_id": task_id,
        "access_token": generate_task_access_token(task_id),
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
    if not _SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(status_code=400, detail="无效的会话ID")
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

    max_chunk_size = 10 * 1024 * 1024
    if len(chunk_content) > max_chunk_size:
        raise HTTPException(status_code=413, detail=f"分片过大，最大支持 {max_chunk_size // 1024 // 1024}MB")

    uploaded_size = 0
    for i in range(total_chunks):
        if i == chunk_index:
            continue
        existing_chunk_path = os.path.join(session_dir, f"chunk_{i:06d}")
        if os.path.exists(existing_chunk_path):
            try:
                uploaded_size += os.path.getsize(existing_chunk_path)
            except OSError:
                pass

    if uploaded_size + len(chunk_content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")

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
    if not _SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(status_code=400, detail="无效的会话ID")
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
    if not _SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(status_code=400, detail="无效的会话ID")
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

    if file_size == 0:
        try:
            os.remove(final_path)
        except OSError:
            pass
        import shutil
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="文件为空，无法处理")

    audio_info = _get_audio_info(final_path)
    if not audio_info:
        try:
            os.remove(final_path)
        except OSError:
            pass
        import shutil
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="无效的音频文件")

    create_task(task_id, filename, final_path, {}, file_hash, file_size)

    import shutil
    shutil.rmtree(session_dir, ignore_errors=True)

    logger.info(f"[upload-finalize] task_id={task_id} file_size={file_size}")

    return {
        "success": True,
        "task_id": task_id,
        "access_token": generate_task_access_token(task_id),
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
    vocal_hash = vocal_file_hash or file_hash
    accompaniment_hash = accompaniment_file_hash or file_hash

    if vocal_hash and accompaniment_hash:
        existing_dual = find_dual_task_by_hashes(vocal_hash, accompaniment_hash)
        if existing_dual:
            main_task_id = existing_dual["id"]
            return {
                "cached": True,
                "task_id": main_task_id,
                "access_token": generate_task_access_token(main_task_id),
                "vocal_task_id": existing_dual.get("params", {}).get("vocal_task_id", ""),
                "accompaniment_task_id": existing_dual.get("params", {}).get("accompaniment_task_id", ""),
                "vocal_filename": existing_dual.get("params", {}).get("vocal_filename", ""),
                "accompaniment_filename": existing_dual.get("params", {}).get("accompaniment_filename", ""),
                "vocal_size": 0,
                "accompaniment_size": 0,
                "vocal_info": None,
                "accompaniment_info": None,
            }

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

    vocal_size = 0
    acc_size = 0

    def _cleanup_dual():
        for p in [vocal_upload_path, accompaniment_upload_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    try:
        with open(vocal_upload_path, "wb") as f:
            while True:
                chunk = await vocal_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                vocal_size += len(chunk)
                if vocal_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail=f"人声文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
                f.write(chunk)

        with open(accompaniment_upload_path, "wb") as f:
            while True:
                chunk = await accompaniment_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                acc_size += len(chunk)
                if acc_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail=f"伴奏文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
                f.write(chunk)

        total_size = vocal_size + acc_size
        try:
            disk_usage = os.statvfs(UPLOAD_DIR)
            available_bytes = disk_usage.f_bavail * disk_usage.f_frsize
            min_required = total_size * 2
            if available_bytes < min_required:
                available_mb = available_bytes // 1024 // 1024
                required_mb = min_required // 1024 // 1024
                raise HTTPException(
                    status_code=507,
                    detail=f"存储空间不足：可用 {available_mb}MB，至少需要 {required_mb}MB（文件大小的2倍）"
                )
        except OSError:
            pass
    except HTTPException:
        _cleanup_dual()
        raise

    vocal_audio_info = _get_audio_info(vocal_upload_path)
    if vocal_audio_info is None:
        _cleanup_dual()
        raise HTTPException(status_code=400, detail="无法解析人声音频文件，文件可能已损坏")

    acc_audio_info = _get_audio_info(accompaniment_upload_path)
    if acc_audio_info is None:
        _cleanup_dual()
        raise HTTPException(status_code=400, detail="无法解析伴奏音频文件，文件可能已损坏")

    create_task(vocal_task_id, f"vocal_{vocal_file.filename or 'audio'}", vocal_upload_path,
                {"audio_info": vocal_audio_info},
                vocal_hash, vocal_size)
    create_task(accompaniment_task_id, f"acc_{accompaniment_file.filename or 'audio'}", accompaniment_upload_path,
                {"audio_info": acc_audio_info},
                accompaniment_hash, acc_size)
    create_task(main_task_id, f"dual_{vocal_file.filename or 'audio'}", vocal_upload_path, {
        "vocal_task_id": vocal_task_id,
        "accompaniment_task_id": accompaniment_task_id,
        "vocal_file_hash": vocal_hash,
        "accompaniment_file_hash": accompaniment_hash,
        "vocal_filename": vocal_file.filename or "",
        "accompaniment_filename": accompaniment_file.filename or "",
    }, file_hash, vocal_size + acc_size)

    logger.info(f"[/upload-dual] main_task_id={main_task_id} vocal={vocal_task_id} acc={accompaniment_task_id} vocal_hash={vocal_hash[:12] if vocal_hash else 'none'} acc_hash={accompaniment_hash[:12] if accompaniment_hash else 'none'}")

    return {
        "task_id": main_task_id,
        "access_token": generate_task_access_token(main_task_id),
        "vocal_task_id": vocal_task_id,
        "accompaniment_task_id": accompaniment_task_id,
        "vocal_filename": vocal_file.filename,
        "accompaniment_filename": accompaniment_file.filename,
        "vocal_size": vocal_size,
        "accompaniment_size": acc_size,
        "vocal_info": vocal_audio_info,
        "accompaniment_info": acc_audio_info,
    }


_audio_files_cache: dict = {"data": None, "ts": 0}


@router.get("/audio-files")
async def list_audio_files():
    import hashlib
    import time
    from config import OUTPUT_DIR

    now = time.time()
    with _audio_files_cache_lock:
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
    with _audio_files_cache_lock:
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
    task_id = generate_task_id()
    temp_path = os.path.join(UPLOAD_DIR, f"{task_id}_training{ext}")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    file_size = 0
    try:
        with open(temp_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail=f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
                f.write(chunk)
    except HTTPException:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise

    if file_size == 0:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="文件为空，无法处理")

    audio_info = _get_audio_info(temp_path)
    if not audio_info:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="无效的音频文件")

    import io
    with open(temp_path, "rb") as f:
        file_content = f.read()
    file.file = io.BytesIO(file_content)
    saved_path = await save_training_file(file, file_hash, label, ext)

    try:
        os.remove(temp_path)
    except OSError:
        pass

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
    if not _SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(status_code=400, detail="无效的会话ID")
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

    if file_size == 0:
        try:
            os.remove(final_path)
        except OSError:
            pass
        import shutil
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="文件为空，无法处理")

    audio_info = _get_audio_info(final_path)
    if not audio_info:
        try:
            os.remove(final_path)
        except OSError:
            pass
        import shutil
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="无效的音频文件")

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
