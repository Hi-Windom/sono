import os
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from config import UPLOAD_DIR, OUTPUT_DIR
from database import (
    get_db,
    get_task,
    find_task_by_hash,
    find_repair_cache,
    find_dual_repair_cache,
    get_analysis_cache,
    save_analysis_cache,
    get_all_analysis_cache,
    delete_analysis_cache,
    clear_all_analysis_cache,
    _format_timestamp,
)
from services.param_maps import flatten_vocal_params, flatten_inst_params
from services.task_manager import _generate_waveform_peaks
from ._common import _get_audio_info

logger = logging.getLogger(__name__)

router = APIRouter()


class AnalysisCacheRequest(BaseModel):
    quick_hash: str
    file_name: str = ""
    file_size: int = 0
    wav_info: str = ""
    analysis: str = ""


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


_DELIVERY_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def _is_valid_audio_file(filepath: str) -> tuple[bool, str]:
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


@router.get("/render-cache/{task_id}")
async def get_render_cache(task_id: str):
    task = get_task(task_id)
    if not task:
        return {"caches": []}

    algo_version = task.get("params", {}).get("algorithm_version", "")

    caches = []
    if os.path.isdir(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            if not fname.startswith(f"{task_id}_rendered_") or not fname.endswith(".wav"):
                continue
            base = fname.replace(".wav", "")
            parts = base.split("_rendered_")
            if len(parts) != 2:
                continue
            suffix = parts[1]
            segments = suffix.split("_")
            try:
                track_type = "both"
                is_merged = False

                if len(segments) >= 4:
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
                    sr = int(segments[-2])
                    bd = int(segments[-1])
                    file_algo_ver = "_".join(segments[:-2])
                elif len(segments) == 2:
                    sr = int(segments[0])
                    bd = int(segments[1])
                    file_algo_ver = ""
                else:
                    continue

                fpath = os.path.join(OUTPUT_DIR, fname)
                mtime = os.path.getmtime(fpath)
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
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    if "_rendered_" not in filename:
        raise HTTPException(status_code=400, detail="不是渲染缓存文件")
    released = os.path.getsize(file_path)
    os.remove(file_path)
    return {"released_bytes": released, "filename": filename}


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


@router.get("/analysis-cache/{quick_hash}")
async def get_analysis_cache_endpoint(quick_hash: str):
    cached = get_analysis_cache(quick_hash)
    if not cached:
        return {"found": False}
    return {"found": True, "data": cached}


@router.post("/analysis-cache")
async def save_analysis_cache_endpoint(request: AnalysisCacheRequest):
    save_analysis_cache(request.quick_hash, request.file_name, request.file_size, request.wav_info, request.analysis)
    return {"status": "ok"}


@router.get("/analysis-cache-list")
async def list_analysis_cache():
    entries = get_all_analysis_cache()
    return {"entries": entries, "count": len(entries)}


@router.delete("/analysis-cache/{quick_hash}")
async def delete_analysis_cache_endpoint(quick_hash: str):
    delete_analysis_cache(quick_hash)
    return {"status": "ok"}


@router.post("/analysis-cache-clear")
async def clear_analysis_cache():
    count = clear_all_analysis_cache()
    return {"deleted_count": count}


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

    cached = get_analysis_cache(file_hash)
    if cached and cached.get("waveform_peaks"):
        try:
            return {"peaks": json.loads(cached["waveform_peaks"])}
        except Exception:
            pass

    original_path = task.get("original_path", "")
    if not original_path or not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    peaks = _generate_waveform_peaks(original_path)
    if not peaks:
        raise HTTPException(status_code=500, detail="波形生成失败")

    if cached:
        conn = get_db()
        conn.execute("UPDATE analysis_cache SET waveform_peaks = ? WHERE quick_hash = ?", (json.dumps(peaks), file_hash))
        conn.commit()
        conn.close()
    else:
        save_analysis_cache(file_hash, task.get("original_filename", ""), task.get("file_size", 0), "", "", waveform_peaks=json.dumps(peaks))

    return {"peaks": peaks}


@router.get("/cache/info")
async def get_cache_info():
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


@router.post("/cache/lookup")
async def lookup_repair_cache(req: RepairCacheLookupRequest):
    cached = find_repair_cache(req.file_hash, req.params)
    if not cached:
        return {"found": False}
    repair_result = cached.get("repair_result")

    if repair_result and not repair_result.get("waveform_peaks"):
        output_path = cached.get("output_path", "")
        if output_path and os.path.exists(output_path):
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


@router.post("/cache/clean-invalid")
async def clean_invalid_cache():
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
