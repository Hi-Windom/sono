import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from urllib.parse import quote

from config import OUTPUT_DIR, DECODED_DIR
from database import get_task, find_task_by_hash, update_task
from services.task_manager import executor

logger = logging.getLogger(__name__)

router = APIRouter()


def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    from services.mp3_encoder import encode_mp3
    encode_mp3(wav_path, mp3_path, bitrate)


def _find_rendered_merged(task_id: str) -> str | None:
    if not os.path.isdir(OUTPUT_DIR):
        return None
    prefix = f"{task_id}_rendered_"
    for fname in os.listdir(OUTPUT_DIR):
        if fname.startswith(prefix) and fname.endswith("_merged.wav"):
            return os.path.join(OUTPUT_DIR, fname)
    return None


def _merge_wavs(vocal_path: str, acc_path: str, output_path: str):
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
        mtime = os.path.getmtime(file_path)
        ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
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

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")
    logger.info(f"[DOWNLOAD] File size: {file_size}, Range header: {range_header}")
    encoded_name = quote(download_name)
    ascii_name = download_name.encode("ascii", "ignore").decode("ascii") or "audio.wav"
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'

    if range_header:
        range_match = __import__("re").match(r"bytes=(\d+)-(\d*)", range_header)
        logger.info(f"[DOWNLOAD] Range matched: {range_match is not None}")
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            logger.info(f"[DOWNLOAD] Range: start={start}, end={end}")
            if start >= file_size:
                logger.warning(f"[DOWNLOAD] Invalid range: start={start} >= file_size={file_size}")
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

    logger.info(f"[DOWNLOAD] Returning 200 OK with full file, disposition={disposition}")
    def iter_full_file():
        with open(file_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    return StreamingResponse(
        iter_full_file(),
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
    )


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

    if temp_wav and os.path.exists(temp_wav):
        os.unlink(temp_wav)

    file_size = os.path.getsize(mp3_path)
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
    return StreamingResponse(
        iter_full_file_and_cleanup(),
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
    )


@router.get("/download-m4a/{task_id}")
async def download_m4a(task_id: str, request: Request):
    from services.m4a_encoder import encode_m4a, is_available as m4a_available

    if not m4a_available():
        raise HTTPException(status_code=501, detail="ffmpeg 未安装，M4A/ALAC 编码不可用")

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

    m4a_path = os.path.join(OUTPUT_DIR, f"{task_id}_repaired.m4a")
    if not os.path.exists(m4a_path):
        try:
            encode_m4a(wav_path, m4a_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=f"M4A编码失败: {e}")
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"音频格式不支持: {e}")
        except Exception as e:
            logger.error(f"[DOWNLOAD-M4A] 转码失败 task_id={task_id}: {e}")
            raise HTTPException(status_code=500, detail=f"M4A转码失败: {e}")

    if temp_wav and os.path.exists(temp_wav):
        os.unlink(temp_wav)

    file_size = os.path.getsize(m4a_path)
    download_name = f"{task_id}.m4a"
    task = get_task(task_id)
    if task and task.get("original_filename"):
        original_basename = os.path.splitext(task["original_filename"])[0]
        speed = task.get("params", {}).get("speed", 1.0)
        speed_tag = f"{speed}x_" if speed and speed != 1.0 else ""
        download_name = f"{original_basename}_{speed_tag}repaired.m4a"
    encoded_name = quote(download_name)
    ascii_name = download_name.encode("ascii", "ignore").decode("ascii") or "audio.m4a"
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'
    range_header = request.headers.get("range")
    if range_header:
        range_match = __import__("re").match(r"bytes=(\d+)-(\d*)", range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            if start >= file_size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
            end = min(end, file_size - 1)
            chunk_size = end - start + 1
            def iter_file():
                with open(m4a_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_size = min(8192, remaining)
                        data = f.read(read_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type="audio/mp4",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(chunk_size),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": disposition,
                },
            )
    def iter_full_file():
        with open(m4a_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data
    return StreamingResponse(
        iter_full_file(),
        media_type="audio/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
    )


@router.get("/download-mp3-file/{filename}")
async def download_mp3_file(filename: str, request: Request):
    if not filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="仅支持 .wav 源文件")

    wav_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(wav_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    base_name = filename[:-4]
    mp3_path = os.path.join(OUTPUT_DIR, f"{base_name}.mp3")
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
            logger.error(f"[DOWNLOAD-MP3-FILE] 转码失败 filename={filename}: {e}")
            raise HTTPException(status_code=500, detail=f"MP3转码失败: {e}")

    file_size = os.path.getsize(mp3_path)
    download_name = f"{base_name}.mp3"
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

    def iter_full_file():
        with open(mp3_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    return StreamingResponse(
        iter_full_file(),
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
    )


@router.get("/download-m4a-file/{filename}")
async def download_m4a_file(filename: str, request: Request):
    from services.m4a_encoder import encode_m4a, is_available as m4a_available

    if not m4a_available():
        raise HTTPException(status_code=501, detail="ffmpeg 未安装，M4A/ALAC 编码不可用")

    if not filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="仅支持 .wav 源文件")

    wav_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(wav_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    base_name = filename[:-4]
    m4a_path = os.path.join(OUTPUT_DIR, f"{base_name}.m4a")
    if not os.path.exists(m4a_path):
        try:
            encode_m4a(wav_path, m4a_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=f"M4A编码失败: {e}")
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"音频格式不支持: {e}")
        except Exception as e:
            logger.error(f"[DOWNLOAD-M4A-FILE] 转码失败 filename={filename}: {e}")
            raise HTTPException(status_code=500, detail=f"M4A转码失败: {e}")

    file_size = os.path.getsize(m4a_path)
    download_name = f"{base_name}.m4a"
    encoded_name = quote(download_name)
    ascii_name = download_name.encode("ascii", "ignore").decode("ascii") or "audio.m4a"
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'

    range_header = request.headers.get("range")
    if range_header:
        range_match = __import__("re").match(r"bytes=(\d+)-(\d*)", range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            if start >= file_size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
            end = min(end, file_size - 1)
            chunk_size = end - start + 1
            def iter_file():
                with open(m4a_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_size = min(8192, remaining)
                        data = f.read(read_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type="audio/mp4",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(chunk_size),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": disposition,
                },
            )

    def iter_full_file():
        with open(m4a_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    return StreamingResponse(
        iter_full_file(),
        media_type="audio/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": disposition,
        },
    )


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


@router.get("/decoded-wav/{file_hash}")
async def get_decoded_wav(file_hash: str, request: Request):
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
    decoded_path = os.path.join(DECODED_DIR, f"{file_hash}.wav")
    if not os.path.exists(decoded_path):
        raise HTTPException(status_code=404, detail="解码缓存不存在")
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
            update_task(task_id, original_path=decoded_path)
            if original_path != decoded_path and os.path.exists(original_path):
                os.remove(original_path)
                logger.info(f"已删除原始文件: {original_path}")
        except Exception as e:
            logger.warning(f"解码WAV缓存创建失败: {e}")

    executor.submit(_convert_to_wav)
    return {"status": "ok", "message": "正在后台创建解码缓存"}
