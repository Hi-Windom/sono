import os
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import OUTPUT_DIR
from database import get_task, update_task
from services.task_manager import executor, _track_task_start, _track_task_end, TaskCancelledError, _cancelled_lock

logger = logging.getLogger(__name__)

router = APIRouter()


class RenderRequest(BaseModel):
    task_id: str
    sample_rate: int = 44100
    bit_depth: int = 24
    merge: bool = False
    track_type: str = "both"


def _run_render(task_id, input_path, output_path, target_sr, bit_depth, render_filename):
    from services.render import render_output
    from services.task_manager import _ws_send_progress, _ws_send_final, _cancelled_lock, TaskCancelledError

    with _cancelled_lock:
        if task_id in _cancelled_tasks:
            logger.info(f"[render] 任务已取消，跳过执行 task_id={task_id}")
            _cancelled_tasks.discard(task_id)
            _track_task_end(task_id)
            return

    source_bit_depth = None
    try:
        from services.audio_loader import load_audio_with_fallback
        _, _, src_bd = load_audio_with_fallback(input_path, sr=None, mono=False, return_bit_depth=True)
        source_bit_depth = src_bd
    except Exception:
        pass

    def progress_callback(pct, step):
        with _cancelled_lock:
            if task_id in _cancelled_tasks:
                raise TaskCancelledError(f"任务已取消: {task_id}")
        update_task(task_id, progress=pct, step=step)
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "rendering",
            "progress": pct,
            "step": step,
        })

    try:
        update_task(task_id, status="rendering", progress=0, step="开始渲染...")
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
    except TaskCancelledError:
        logger.info(f"[render] 任务已取消 task_id={task_id}")
        _ws_send_final(task_id, {"task_id": task_id, "status": "cancelled", "progress": 0, "step": "已取消"})
    except Exception as e:
        logger.error(f"[render] 渲染失败 task_id={task_id}: {e}")
        update_task(task_id, status="error", error=str(e), step="渲染失败")
        _ws_send_final(task_id, {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
            "step": "渲染失败",
        })
        raise
    finally:
        _track_task_end(task_id)
        with _cancelled_lock:
            _cancelled_tasks.discard(task_id)


def _run_render_dual(task_id, vocal_path, accompaniment_path, output_path, target_sr, bit_depth, render_filename, merge=False, track_type="both"):
    from services.render import render_output
    from services.task_manager import _ws_send_progress, _ws_send_final, _cancelled_lock, TaskCancelledError
    import numpy as np
    import soundfile as sf

    with _cancelled_lock:
        if task_id in _cancelled_tasks:
            logger.info(f"[render_dual] 任务已取消，跳过执行 task_id={task_id}")
            _cancelled_tasks.discard(task_id)
            _track_task_end(task_id)
            return

    vocal_rendered = False
    accompaniment_rendered = False
    vocal_render_filename = None
    accompaniment_render_filename = None

    def progress_callback(pct, step):
        with _cancelled_lock:
            if task_id in _cancelled_tasks:
                raise TaskCancelledError(f"任务已取消: {task_id}")
        update_task(task_id, progress=pct, step=step)
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "rendering",
            "progress": pct,
            "step": step,
        })

    try:
        update_task(task_id, status="rendering", progress=0, step="开始渲染...")
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
    except TaskCancelledError:
        logger.info(f"[render_dual] 任务已取消 task_id={task_id}")
        _ws_send_final(task_id, {"task_id": task_id, "status": "cancelled", "progress": 0, "step": "已取消"})
    except Exception as e:
        logger.error(f"[render_dual] 渲染失败 task_id={task_id}: {e}")
        update_task(task_id, status="error", error=str(e), step="渲染失败")
        _ws_send_final(task_id, {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
            "step": "渲染失败",
        })
        raise
    finally:
        _track_task_end(task_id)
        with _cancelled_lock:
            _cancelled_tasks.discard(task_id)


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

    from services.task_manager import RenderTask
    from services.task_executor import get_task_executor

    if is_dual_track:
        render_task = RenderTask(
            task_id=request.task_id,
            input_path="",
            output_path=render_path,
            target_sr=request.sample_rate,
            bit_depth=request.bit_depth,
            render_filename=render_filename,
            vocal_path=vocal_output_path,
            accompaniment_path=accompaniment_output_path,
            merge=request.merge,
            track_type=request.track_type,
        )
    else:
        render_task = RenderTask(
            task_id=request.task_id,
            input_path=output_path,
            output_path=render_path,
            target_sr=request.sample_rate,
            bit_depth=request.bit_depth,
            render_filename=render_filename,
        )

    get_task_executor().submit(render_task)

    return {"task_id": request.task_id, "status": "rendering"}
