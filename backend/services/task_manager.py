import asyncio
import uuid
import os
import traceback
import logging
from concurrent.futures import ThreadPoolExecutor
from database import create_task, update_task, get_task
from services.ai_detector import detect_ai_audio
from services.audio_repair import repair_audio
from config import MAX_WORKERS, OUTPUT_DIR

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

def generate_task_id() -> str:
    return uuid.uuid4().hex[:16]

def submit_detect_task(task_id: str, audio_path: str, detect_type: str = "original", detector_version: str = "v1.1"):
    executor.submit(_run_detect, task_id, audio_path, detect_type, detector_version)

def submit_repair_task(task_id: str, audio_path: str, params: dict):
    executor.submit(_run_repair, task_id, audio_path, params)

def _run_detect(task_id: str, audio_path: str, detect_type: str = "original", detector_version: str = "v1.1"):
    try:
        prev_task = get_task(task_id)
        prev_status = prev_task["status"] if prev_task else "pending"

        label = "修复后" if detect_type == "repaired" else "原始"
        # 只更新状态和进度，不覆盖步骤（步骤由 API 端点设置）
        update_task(task_id, status="detecting", progress=0)
        result = detect_ai_audio(audio_path, lambda p, s: update_task(
            task_id, progress=p, step=s
        ), version=detector_version)
        result["detect_type"] = detect_type

        final_status = "completed" if prev_status == "completed" else "detected"
        if detect_type == "repaired":
            update_task(task_id, status=final_status, progress=1, step="修复后检测完成", repaired_detection_result=result)
        else:
            update_task(task_id, status=final_status, progress=1, step="原始检测完成", detection_result=result)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"检测失败 task_id={task_id}: {error_msg}")
        update_task(task_id, status="error", error=error_msg, step="检测失败")

def _run_repair(task_id: str, audio_path: str, params: dict):
    try:
        output_filename = f"{task_id}_repaired.wav"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        update_task(task_id, status="repairing", progress=0, step="开始修复...")

        repair_result = repair_audio(
            audio_path,
            output_path,
            params,
            lambda p, s: update_task(task_id, progress=p, step=s)
        )

        update_task(
            task_id,
            status="completed",
            progress=1,
            step="修复完成",
            output_path=output_path,
            repair_result=repair_result
        )
    except Exception as e:
        update_task(task_id, status="error", error=str(e), step="修复失败")

def get_task_status(task_id: str) -> dict | None:
    return get_task(task_id)
