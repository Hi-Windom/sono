import asyncio
import uuid
import os
import traceback
import logging
import time
import functools
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from database import create_task, update_task, get_task
from services.ai_detector import detect_ai_audio
from services.audio_repair import repair_audio
from config import MAX_WORKERS, OUTPUT_DIR

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

TASK_TIMEOUTS = {
    "detect": 300,
    "repair": 600,
}


def generate_task_id() -> str:
    return uuid.uuid4().hex[:16]


def submit_detect_task(task_id: str, audio_path: str, detect_type: str = "original", detector_version: str = "v1.1"):
    logger.info(f"[submit_detect_task] task_id={task_id} type={detect_type} version={detector_version}")
    future = executor.submit(_run_detect, task_id, audio_path, detect_type, detector_version)
    future.add_done_callback(lambda f: _handle_future_exception(f, task_id, "detect"))


def submit_repair_task(task_id: str, audio_path: str, params: dict):
    logger.info(f"[submit_repair_task] task_id={task_id} params_keys={list(params.keys())}")
    future = executor.submit(_run_repair, task_id, audio_path, params)
    future.add_done_callback(lambda f: _handle_future_exception(f, task_id, "repair"))


def _handle_future_exception(future, task_id: str, task_type: str):
    try:
        future.result()
    except FutureTimeoutError:
        logger.error(f"[{task_type}] 任务超时 task_id={task_id}")
        update_task(task_id, status="error", error=f"任务执行超时（{TASK_TIMEOUTS.get(task_type, 300)}秒）", step="执行超时")
    except Exception as e:
        logger.error(f"[{task_type}] 任务异常 task_id={task_id}: {e}")
        update_task(task_id, status="error", error=f"任务执行异常: {str(e)}", step="执行异常")


def _run_detect(task_id: str, audio_path: str, detect_type: str, detector_version: str):
    start_time = time.time()
    logger.info(f"[detect] 开始 task_id={task_id} type={detect_type} version={detector_version}")

    try:
        prev_task = get_task(task_id)
        prev_status = prev_task["status"] if prev_task else "pending"

        label = "修复后" if detect_type == "repaired" else "原始"
        update_task(task_id, status="detecting", progress=0, step=f"开始{label}检测...")

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        file_size = os.path.getsize(audio_path)
        logger.info(f"[detect] 音频文件 task_id={task_id} size={file_size/1024/1024:.2f}MB")

        def progress_callback(p, s):
            elapsed = time.time() - start_time
            update_task(task_id, progress=p, step=s)

        result = detect_ai_audio(audio_path, progress_callback, version=detector_version)
        result["detect_type"] = detect_type

        elapsed = time.time() - start_time
        final_status = "completed" if prev_status == "completed" else "detected"

        if detect_type == "repaired":
            update_task(task_id, status=final_status, progress=1, step=f"修复后检测完成 ({elapsed:.1f}s)", repaired_detection_result=result)
        else:
            update_task(task_id, status=final_status, progress=1, step=f"原始检测完成 ({elapsed:.1f}s)", detection_result=result)

        logger.info(f"[detect] 完成 task_id={task_id} elapsed={elapsed:.1f}s")

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[detect] 失败 task_id={task_id} elapsed={elapsed:.1f}s: {error_msg}")
        update_task(task_id, status="error", error=error_msg[:500], step=f"检测失败 ({elapsed:.1f}s)")
        raise


def _run_repair(task_id: str, audio_path: str, params: dict):
    start_time = time.time()
    algorithm_version = params.get("algorithm_version", "v1.1")
    logger.info(f"[repair] 开始 task_id={task_id} version={algorithm_version}")

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

        def progress_callback(p, s):
            elapsed = time.time() - start_time
            update_task(task_id, progress=p, step=s)

        repair_result = repair_audio(
            audio_path,
            output_path,
            params,
            progress_callback
        )

        elapsed = time.time() - start_time

        if os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            logger.info(f"[repair] 输出文件 task_id={task_id} size={output_size/1024/1024:.2f}MB")

        update_task(
            task_id,
            status="completed",
            progress=1,
            step=f"修复完成 ({elapsed:.1f}s)",
            output_path=output_path if os.path.exists(output_path) else None,
            repair_result=repair_result
        )

        logger.info(f"[repair] 完成 task_id={task_id} elapsed={elapsed:.1f}s issues={repair_result.get('issues_found', [])}")

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[repair] 失败 task_id={task_id} elapsed={elapsed:.1f}s: {error_msg}")
        update_task(task_id, status="error", error=error_msg[:500], step=f"修复失败 ({elapsed:.1f}s)")
        raise


def get_task_status(task_id: str) -> dict | None:
    return get_task(task_id)


def shutdown_executor():
    logger.info("关闭任务执行器...")
    executor.shutdown(wait=True)
    logger.info("任务执行器已关闭")
