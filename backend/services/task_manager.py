from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import numpy as np
from typing import Any

from config import MAX_WORKERS, MAX_CONCURRENT_TASKS, MOBILE_MODE, OUTPUT_DIR
from database import TaskDict, create_task, get_task, update_task
from services.ai_detector import detect_ai_audio
from services.audio_repair import ALGORITHM_VERSIONS, DEFAULT_VERSION, repair_audio
from services.memory_guard import get_available_memory_bytes
from services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

WAVEFORM_PEAKS_COUNT = 2000

_active_tasks: set[str] = set()
_active_tasks_lock = threading.Lock()

MIN_MEMORY_FOR_TASK = 512 * 1024 * 1024


def get_active_task_count() -> int:
    with _active_tasks_lock:
        return len(_active_tasks)


def get_active_tasks() -> list[str]:
    with _active_tasks_lock:
        return list(_active_tasks)


def can_accept_task() -> tuple[bool, str]:
    active = get_active_task_count()
    if active >= MAX_CONCURRENT_TASKS:
        return False, f"系统繁忙（{active}/{MAX_CONCURRENT_TASKS} 任务运行中），请稍后重试"
    available_mem = get_available_memory_bytes()
    if available_mem is not None and available_mem < MIN_MEMORY_FOR_TASK:
        mem_mb = available_mem / 1024 / 1024
        return False, f"系统内存不足（仅剩 {mem_mb:.0f}MB），请稍后重试"
    return True, ""


def _track_task_start(task_id: str) -> bool:
    with _active_tasks_lock:
        if len(_active_tasks) >= MAX_CONCURRENT_TASKS:
            return False
        _active_tasks.add(task_id)
        return True


def _track_task_end(task_id: str) -> None:
    with _active_tasks_lock:
        _active_tasks.discard(task_id)


def _generate_waveform_peaks(output_path: str, num_peaks: int = WAVEFORM_PEAKS_COUNT) -> list[list[float]] | None:
    try:
        import soundfile as sf
        with sf.SoundFile(output_path) as f:
            n_frames = f.frames
            if n_frames == 0:
                return None
            samples_per_peak = max(1, n_frames // num_peaks)
            peaks = []
            for _ in range(num_peaks):
                remaining = n_frames - f.tell()
                if remaining <= 0:
                    break
                to_read = min(samples_per_peak, remaining)
                block = f.read(to_read, dtype='float32')
                if block.size == 0:
                    break
                if block.ndim == 1:
                    peaks.append([float(np.min(block)), float(np.max(block))])
                else:
                    mono = np.mean(block, axis=1)
                    peaks.append([float(np.min(mono)), float(np.max(mono))])
            return peaks if peaks else None
    except Exception as e:
        logger.warning(f"[waveform] 生成波形峰值失败: {e}")
        return None

_loop = None

def _get_loop():
    global _loop
    if _loop is None:
        try:
            _loop = asyncio.get_event_loop()
        except RuntimeError:
            _loop = asyncio.new_event_loop()
    if _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop

def _ws_send_progress(task_id: str, data: dict[str, Any]) -> None:
    try:
        asyncio.run_coroutine_threadsafe(ws_manager.send_progress(task_id, data), _get_loop())
    except Exception:
        pass

def _ws_send_final(task_id: str, data: dict[str, Any]) -> None:
    try:
        asyncio.run_coroutine_threadsafe(ws_manager.send_final(task_id, data), _get_loop())
    except Exception:
        pass

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

TASK_TIMEOUTS = {
    "detect": 300,
    "repair": 600,
}

STUCK_THRESHOLD = 60

_cancelled_tasks: set[str] = set()
_cancelled_lock = threading.Lock()


def cancel_task(task_id: str) -> bool:
    with _cancelled_lock:
        if task_id in _cancelled_tasks:
            return False
        _cancelled_tasks.add(task_id)
    update_task(task_id, status="cancelled", step="已取消", progress=0)
    logger.info(f"[cancel] 任务已取消 task_id={task_id}")
    return True


class TaskCancelledError(Exception):
    pass


def generate_task_id() -> str:
    return uuid.uuid4().hex[:16]


def submit_detect_task(task_id: str, audio_path: str, detect_type: str = "original", detector_version: str = "v1.1"):
    logger.info(f"[submit_detect_task] task_id={task_id} type={detect_type} version={detector_version}")
    if not _track_task_start(task_id):
        active = get_active_task_count()
        logger.warning(f"[submit_detect_task] 拒绝任务 task_id={task_id}: 系统繁忙 ({active}/{MAX_CONCURRENT_TASKS})")
        update_task(task_id, status="error", error=f"系统繁忙（{active}/{MAX_CONCURRENT_TASKS} 任务运行中），请稍后重试", step="系统繁忙")
        return
    future = executor.submit(_run_detect, task_id, audio_path, detect_type, detector_version)
    future.add_done_callback(lambda f: _handle_future_exception(f, task_id, "detect"))


def submit_repair_task(task_id: str, audio_path: str, params: dict[str, Any]) -> None:
    logger.info(f"[submit_repair_task] task_id={task_id} params_keys={list(params.keys())}")
    update_task(task_id, params=params)
    if not _track_task_start(task_id):
        active = get_active_task_count()
        logger.warning(f"[submit_repair_task] 拒绝任务 task_id={task_id}: 系统繁忙 ({active}/{MAX_CONCURRENT_TASKS})")
        update_task(task_id, status="error", error=f"系统繁忙（{active}/{MAX_CONCURRENT_TASKS} 任务运行中），请稍后重试", step="系统繁忙")
        return
    future = executor.submit(_run_repair, task_id, audio_path, params, MOBILE_MODE)
    future.add_done_callback(lambda f: _handle_future_exception(f, task_id, "repair"))


def _handle_future_exception(future: Future[Any], task_id: str, task_type: str) -> None:
    try:
        future.result()
    except FutureTimeoutError:
        logger.error(f"[{task_type}] 任务超时 task_id={task_id}")
        update_task(task_id, status="error", error=f"任务执行超时（{TASK_TIMEOUTS.get(task_type, 300)}秒）", step="执行超时")
    except Exception as e:
        logger.error(f"[{task_type}] 任务异常 task_id={task_id}: {e}")
        update_task(task_id, status="error", error=f"任务执行异常: {str(e)}", step="执行异常")


def _run_detect(task_id: str, audio_path: str, detect_type: str, detector_version: str) -> None:
    start_time = time.time()
    logger.info(f"[detect] 开始 task_id={task_id} type={detect_type} version={detector_version}")

    last_progress_time = [time.time()]
    last_progress = [-1.0]
    is_stuck = [False]
    stop_monitor = [False]

    def monitor_stuck():
        while not stop_monitor[0]:
            time.sleep(2)
            if stop_monitor[0]:
                break
            elapsed = time.time() - last_progress_time[0]
            if elapsed > STUCK_THRESHOLD and not is_stuck[0]:
                is_stuck[0] = True
                logger.warning(f"[detect] 任务疑似卡住 task_id={task_id} elapsed={elapsed:.1f}s")
                _ws_send_progress(task_id, {
                    "task_id": task_id,
                    "status": "detecting",
                    "progress": last_progress[0],
                    "step": f"任务疑似卡住，请重试",
                    "stuck": True,
                    "stuck_duration": elapsed,
                })

    monitor_thread = threading.Thread(target=monitor_stuck, daemon=True)
    monitor_thread.start()

    try:
        prev_task = get_task(task_id)
        prev_status = prev_task["status"] if prev_task else "pending"

        label = "修复后" if detect_type == "repaired" else "原始"
        update_task(task_id, status="detecting", progress=0, step=f"开始{label}检测...")

        processing_mode = params.get("processing_mode", "single")
        if processing_mode == "dual":
            vocal_path = params.get("vocal_path", "")
            accompaniment_path = params.get("accompaniment_path", "")
            if vocal_path and not os.path.exists(vocal_path):
                raise FileNotFoundError(f"人声音频不存在: {vocal_path}")
            if accompaniment_path and not os.path.exists(accompaniment_path):
                raise FileNotFoundError(f"伴奏音频不存在: {accompaniment_path}")
            audio_path = vocal_path
        else:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        file_size = os.path.getsize(audio_path)
        logger.info(f"[detect] 音频文件 task_id={task_id} size={file_size/1024/1024:.2f}MB")

        def progress_callback(p, s):
            with _cancelled_lock:
                if task_id in _cancelled_tasks:
                    raise TaskCancelledError(f"任务已取消: {task_id}")
            elapsed = time.time() - start_time
            last_progress_time[0] = time.time()
            last_progress[0] = p
            if is_stuck[0]:
                is_stuck[0] = False
            update_task(task_id, progress=p, step=s)
            _ws_send_progress(task_id, {"task_id": task_id, "status": "detecting", "progress": p, "step": s})

        result = detect_ai_audio(audio_path, progress_callback, version=detector_version)
        result["detect_type"] = detect_type
        result["detector_version"] = detector_version

        elapsed = time.time() - start_time
        final_status = "completed" if prev_status == "completed" else "detected"

        if detect_type == "repaired":
            update_task(task_id, status=final_status, progress=1, step=f"修复后检测完成 ({elapsed:.1f}s)", repaired_detection_result=result)
            _ws_send_final(task_id, {"task_id": task_id, "status": final_status, "progress": 1, "step": f"修复后检测完成 ({elapsed:.1f}s)", "repaired_detection_result": result})
        else:
            update_task(task_id, status=final_status, progress=1, step=f"原始检测完成 ({elapsed:.1f}s)", detection_result=result)
            _ws_send_final(task_id, {"task_id": task_id, "status": final_status, "progress": 1, "step": f"原始检测完成 ({elapsed:.1f}s)", "detection_result": result})

        logger.info(f"[detect] 完成 task_id={task_id} elapsed={elapsed:.1f}s")

    except TaskCancelledError:
        elapsed = time.time() - start_time
        logger.info(f"[detect] 已取消 task_id={task_id} elapsed={elapsed:.1f}s")
        _ws_send_final(task_id, {"task_id": task_id, "status": "cancelled", "progress": 0, "step": f"已取消 ({elapsed:.1f}s)"})
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[detect] 失败 task_id={task_id} elapsed={elapsed:.1f}s: {error_msg}")
        update_task(task_id, status="error", error=error_msg[:500], step=f"检测失败 ({elapsed:.1f}s)")
        _ws_send_final(task_id, {"task_id": task_id, "status": "error", "progress": 0, "step": f"检测失败 ({elapsed:.1f}s)", "error": f"{type(e).__name__}: {e}"})
        raise
    finally:
        stop_monitor[0] = True
        _track_task_end(task_id)
        with _cancelled_lock:
            _cancelled_tasks.discard(task_id)


def _run_repair(task_id: str, audio_path: str, params: dict[str, Any], mobile_mode: bool = False) -> None:
    start_time = time.time()
    algorithm_version = params.get("algorithm_version", DEFAULT_VERSION)
    
    if mobile_mode:
        version_info = ALGORITHM_VERSIONS.get(algorithm_version)
        if version_info and not version_info.get("mobile_compatible", True):
            error_msg = f"算法版本 {algorithm_version} 不支持移动端，请刷新页面后重试"
            elapsed = time.time() - start_time
            update_task(task_id, status="error", error=error_msg, step=f"不支持的版本 ({elapsed:.1f}s)")
            _ws_send_final(task_id, {"task_id": task_id, "status": "error", "progress": 0, "step": f"不支持的版本 ({elapsed:.1f}s)", "error": error_msg})
            raise ValueError(error_msg)
    
    logger.info(f"[repair] 开始 task_id={task_id} version={algorithm_version}")

    last_progress_time = [time.time()]
    last_progress = [-1.0]
    is_stuck = [False]
    stop_monitor = [False]

    def monitor_stuck():
        while not stop_monitor[0]:
            time.sleep(2)
            if stop_monitor[0]:
                break
            elapsed = time.time() - last_progress_time[0]
            if elapsed > STUCK_THRESHOLD and not is_stuck[0]:
                is_stuck[0] = True
                logger.warning(f"[repair] 任务疑似卡住 task_id={task_id} elapsed={elapsed:.1f}s")
                _ws_send_progress(task_id, {
                    "task_id": task_id,
                    "status": "repairing",
                    "progress": last_progress[0],
                    "step": f"任务疑似卡住，请重试",
                    "stuck": True,
                    "stuck_duration": elapsed,
                })

    monitor_thread = threading.Thread(target=monitor_stuck, daemon=True)
    monitor_thread.start()

    try:
        output_filename = f"{task_id}_repaired.wav"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        update_task(task_id, status="repairing", progress=0, step="开始修复...")

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        file_size = os.path.getsize(audio_path)
        logger.info(f"[repair] 音频文件 task_id={task_id} size={file_size/1024/1024:.2f}MB")

        active_params = {k: v for k, v in params.items() if isinstance(v, (int, float)) and v > 0}
        logger.info(f"[repair] 参数 task_id={task_id} active_params={active_params}")

        if "source_bit_depth" not in params:
            try:
                from services.audio_loader import load_audio_with_fallback
                _, _, src_bd = load_audio_with_fallback(audio_path, sr=None, mono=False, return_bit_depth=True)
                params["source_bit_depth"] = src_bd
            except Exception:
                params["source_bit_depth"] = 24

        def progress_callback(p, s):
            with _cancelled_lock:
                if task_id in _cancelled_tasks:
                    raise TaskCancelledError(f"任务已取消: {task_id}")
            elapsed = time.time() - start_time
            last_progress_time[0] = time.time()
            last_progress[0] = p
            if is_stuck[0]:
                is_stuck[0] = False
            update_task(task_id, progress=p, step=s)
            _ws_send_progress(task_id, {"task_id": task_id, "status": "repairing", "progress": p, "step": s})

        repair_result = repair_audio(
            audio_path,
            output_path,
            params,
            progress_callback,
            mobile_mode=mobile_mode
        )

        elapsed = time.time() - start_time

        if os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            logger.info(f"[repair] 输出文件 task_id={task_id} size={output_size/1024/1024:.2f}MB")
            waveform_peaks = _generate_waveform_peaks(output_path)
            if waveform_peaks:
                repair_result["waveform_peaks"] = waveform_peaks

        update_task(
            task_id,
            status="completed",
            progress=1,
            step=f"修复完成 ({elapsed:.1f}s)",
            output_path=output_path if os.path.exists(output_path) else None,
            repair_result=repair_result
        )

        if repair_result.get("vocal_output_path") and os.path.exists(repair_result["vocal_output_path"]):
            vocal_task_id = params.get("vocal_task_id")
            if vocal_task_id:
                update_task(vocal_task_id, output_path=repair_result["vocal_output_path"], status="completed", progress=1)

        if repair_result.get("accompaniment_output_path") and os.path.exists(repair_result["accompaniment_output_path"]):
            accompaniment_task_id = params.get("accompaniment_task_id")
            if accompaniment_task_id:
                update_task(accompaniment_task_id, output_path=repair_result["accompaniment_output_path"], status="completed", progress=1)
        _ws_send_final(task_id, {"task_id": task_id, "status": "completed", "progress": 1, "step": f"修复完成 ({elapsed:.1f}s)", "repair_result": repair_result})

        logger.info(f"[repair] 完成 task_id={task_id} elapsed={elapsed:.1f}s issues={repair_result.get('issues_found', [])}")

    except TaskCancelledError:
        elapsed = time.time() - start_time
        logger.info(f"[repair] 已取消 task_id={task_id} elapsed={elapsed:.1f}s")
        _ws_send_final(task_id, {"task_id": task_id, "status": "cancelled", "progress": 0, "step": f"已取消 ({elapsed:.1f}s)"})
    except MemoryError as e:
        elapsed = time.time() - start_time
        error_msg = str(e)
        logger.error(f"[repair] 内存不足 task_id={task_id} elapsed={elapsed:.1f}s: {error_msg}")
        update_task(task_id, status="error", error=error_msg[:500], step=f"内存不足 ({elapsed:.1f}s)")
        _ws_send_final(task_id, {"task_id": task_id, "status": "error", "progress": 0, "step": f"内存不足", "error": error_msg})
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[repair] 失败 task_id={task_id} elapsed={elapsed:.1f}s: {error_msg}")
        update_task(task_id, status="error", error=error_msg[:500], step=f"修复失败 ({elapsed:.1f}s)")
        _ws_send_final(task_id, {"task_id": task_id, "status": "error", "progress": 0, "step": f"修复失败 ({elapsed:.1f}s)", "error": f"{type(e).__name__}: {e}"})
        raise
    finally:
        stop_monitor[0] = True
        _track_task_end(task_id)


def get_task_status(task_id: str) -> TaskDict | None:
    return get_task(task_id)


def shutdown_executor():
    logger.info("关闭任务执行器...")
    executor.shutdown(wait=True)
    logger.info("任务执行器已关闭")
