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
from services.perf_metrics import get_perf_collector, perf_timer
from services.task_base import BaseTask
from services.message_bus import publish_ws_progress, publish_ws_final, get_message_bus

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
        _active_tasks.add(task_id)
        if len(_active_tasks) > MAX_CONCURRENT_TASKS:
            _active_tasks.discard(task_id)
            return False
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
        logger.warning(f"[waveform] soundfile生成波形峰值失败，尝试miniaudio: {e}")

    try:
        import miniaudio
        sound = miniaudio.decode_file(output_path, output_format=miniaudio.SampleFormat.FLOAT32)
        raw = np.frombuffer(sound.samples, dtype=np.float32)
        nchannels = sound.nchannels
        n_frames = sound.num_frames
        if n_frames == 0:
            return None
        if nchannels > 1:
            raw = raw.reshape(-1, nchannels).T
            mono = np.mean(raw, axis=0)
        else:
            mono = raw
        samples_per_peak = max(1, n_frames // num_peaks)
        peaks = []
        for i in range(num_peaks):
            start = i * samples_per_peak
            end = min(start + samples_per_peak, n_frames)
            if start >= end:
                break
            block = mono[start:end]
            if block.size == 0:
                break
            peaks.append([float(np.min(block)), float(np.max(block))])
        return peaks if peaks else None
    except Exception as e:
        logger.warning(f"[waveform] miniaudio生成波形峰值也失败: {e}")
        return None

_loop = None
_loop_warned = False

def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """由应用启动（lifespan）在主线程事件循环中调用，缓存正在运行的 loop。

    后台修复线程通过 _ws_send_* 用 run_coroutine_threadsafe 投递协程，
    必须投递到「正在运行」的主 loop 上，否则协程永远不会被执行
    （表现为 WebSocket 进度静默丢失，前端只能退回 HTTP 轮询）。
    """
    global _loop, _loop_warned
    _loop = loop
    _loop_warned = False

def _get_loop():
    """获取正在运行的事件循环。

    没有设置 loop 时返回 None，不兜底创建未运行的事件循环。
    调用方需要处理 None 的情况（打日志、退回轮询等）。
    """
    global _loop_warned
    if _loop is None:
        if not _loop_warned:
            logger.warning("[_get_loop] 事件循环未设置（set_event_loop 未调用），WebSocket 消息将无法发送，前端需退回 HTTP 轮询")
            _loop_warned = True
        return None
    if _loop.is_closed():
        if not _loop_warned:
            logger.warning("[_get_loop] 事件循环已关闭，WebSocket 消息将无法发送")
            _loop_warned = True
        return None
    return _loop

def _ws_send_progress(task_id: str, data: dict[str, Any]) -> None:
    try:
        publish_ws_progress(task_id, data)
    except Exception as e:
        logger.warning(f"[_ws_send_progress] 发送进度消息失败: {e}")

def _ws_send_final(task_id: str, data: dict[str, Any]) -> None:
    try:
        publish_ws_final(task_id, data)
    except Exception as e:
        logger.warning(f"[_ws_send_final] 发送最终消息失败: {e}")

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

TASK_TIMEOUTS = {
    "detect": 300,
    "repair": 600,
}

STUCK_THRESHOLD = 30

_cancelled_tasks: set[str] = set()
_cancelled_lock = threading.Lock()
_CANCEL_CLEANUP_DELAY = 3600


def _schedule_cancel_cleanup(task_id: str) -> None:
    def _cleanup():
        time.sleep(_CANCEL_CLEANUP_DELAY)
        with _cancelled_lock:
            _cancelled_tasks.discard(task_id)
        logger.debug(f"[cancel] 超时清理取消标记 task_id={task_id}")
    t = threading.Thread(target=_cleanup, daemon=True)
    t.start()


def cancel_task(task_id: str) -> bool:
    with _cancelled_lock:
        if task_id in _cancelled_tasks:
            return False
        _cancelled_tasks.add(task_id)
    _track_task_end(task_id)
    update_task(task_id, status="cancelled", step="已取消", progress=0)
    _ws_send_final(task_id, {"task_id": task_id, "status": "cancelled"})
    logger.info(f"[cancel] 任务已取消 task_id={task_id}")
    _schedule_cancel_cleanup(task_id)
    return True


class TaskCancelledError(Exception):
    pass


def generate_task_id() -> str:
    return uuid.uuid4().hex[:16]


def submit_detect_task(task_id: str, audio_path: str, detect_type: str = "original", detector_version: str = "v1.1"):
    logger.info(f"[submit_detect_task] task_id={task_id} type={detect_type} version={detector_version}")
    from services.task_executor import get_task_executor
    task = DetectTask(task_id, audio_path, detect_type, detector_version)
    get_task_executor().submit(task)


def submit_repair_task(task_id: str, audio_path: str, params: dict[str, Any]) -> None:
    logger.info(f"[submit_repair_task] task_id={task_id} params_keys={list(params.keys())}")
    update_task(task_id, params=params)
    from services.task_executor import get_task_executor
    task = RepairTask(task_id, audio_path, params, MOBILE_MODE)
    get_task_executor().submit(task)


def _handle_future_exception(future: Future[Any], task_id: str, task_type: str) -> None:
    try:
        future.result()
    except FutureTimeoutError:
        logger.error(f"[{task_type}] 任务超时 task_id={task_id}")
        update_task(task_id, status="error", error=f"任务执行超时（{TASK_TIMEOUTS.get(task_type, 300)}秒）", step="执行超时")
        _ws_send_final(task_id, {"task_id": task_id, "status": "error", "progress": 0, "step": "执行超时", "error": f"任务执行超时（{TASK_TIMEOUTS.get(task_type, 300)}秒）", "error_type": "timeout"})
        _track_task_end(task_id)
    except Exception as e:
        tb_str = traceback.format_exc()
        error_msg = f"{type(e).__name__}: {e}"
        full_error = f"{error_msg}\n{tb_str}"
        logger.error(f"[{task_type}] 任务异常 task_id={task_id}: {full_error}")
        update_task(task_id, status="error", error=full_error[:1000], step="执行异常")
        _ws_send_final(task_id, {"task_id": task_id, "status": "error", "progress": 0, "step": "执行异常", "error": error_msg, "error_type": type(e).__name__, "traceback": tb_str[:2000]})
        _track_task_end(task_id)


def _run_detect(task_id: str, audio_path: str, detect_type: str, detector_version: str) -> None:
    start_time = time.time()
    logger.info(f"[detect] 开始 task_id={task_id} type={detect_type} version={detector_version}")

    with _cancelled_lock:
        if task_id in _cancelled_tasks:
            logger.info(f"[detect] 任务已取消，跳过执行 task_id={task_id}")
            _cancelled_tasks.discard(task_id)
            _track_task_end(task_id)
            return

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

        # 检测任务复用任务记录中的 params（双轨检测时由路由写入），
        # 不能引用未定义的 params 变量，否则每次检测都会抛 NameError
        params: dict[str, Any] = (prev_task.get("params") if prev_task else None) or {}
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
    perf_collector = get_perf_collector()
    size_samples = 0
    perf_ended = False
    
    with _cancelled_lock:
        if task_id in _cancelled_tasks:
            logger.info(f"[repair] 任务已取消，跳过执行 task_id={task_id}")
            _cancelled_tasks.discard(task_id)
            _track_task_end(task_id)
            return
    
    perf_collector.start_repair(task_id)
    
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

        try:
            from services.audio_loader import load_audio_with_fallback
            y, sr = load_audio_with_fallback(audio_path, sr=None, mono=False)
            size_samples = y.shape[1] if y.ndim > 1 else len(y)
        except Exception as e:
            logger.warning(f"[repair] 预加载音频获取采样数失败 task_id={task_id}: {e}")
            size_samples = 0

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

        with perf_timer("repair_total"):
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

        perf_data = perf_collector.end_repair(task_id, size_samples, algorithm_version)
        perf_ended = True
        repair_result["perf_data"] = perf_data
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
        if not perf_ended:
            try:
                perf_collector.end_repair(task_id, size_samples, algorithm_version)
            except Exception as e:
                logger.warning(f"[repair] perf_collector.end_repair 失败 task_id={task_id}: {e}")
        _track_task_end(task_id)
        with _cancelled_lock:
            _cancelled_tasks.discard(task_id)


def get_task_status(task_id: str) -> TaskDict | None:
    return get_task(task_id)


def shutdown_executor():
    logger.info("关闭任务执行器...")
    executor.shutdown(wait=True)
    logger.info("任务执行器已关闭")


class RepairTask(BaseTask):
    def __init__(self, task_id: str, audio_path: str, params: dict[str, Any], mobile_mode: bool = False) -> None:
        super().__init__(task_id)
        self.audio_path = audio_path
        self.params = params
        self.mobile_mode = mobile_mode
        self.algorithm_version = params.get("algorithm_version", DEFAULT_VERSION)
        self._start_time = 0.0
        self._size_samples = 0
        self._perf_ended = False
        self._stop_monitor = [False]
        self._monitor_thread: threading.Thread | None = None
        self._last_progress_time = [0.0]
        self._last_progress = [-1.0]
        self._is_stuck = [False]
        self._perf_collector = get_perf_collector()

    @property
    def task_type(self) -> str:
        return "repair"

    @property
    def initial_fields(self) -> dict[str, Any]:
        return {
            "error": "",
            "repair_result": None,
            "render_filename": None,
            "render_result": None,
        }

    @property
    def processing_status(self) -> str:
        return "repairing"

    @property
    def completed_status(self) -> str:
        return "completed"

    @property
    def initial_step(self) -> str:
        return "任务已提交，等待执行..."

    @property
    def start_step(self) -> str:
        return "开始修复..."

    @property
    def done_step(self) -> str:
        elapsed = time.time() - self._start_time
        return f"修复完成 ({elapsed:.1f}s)"

    @property
    def error_step(self) -> str:
        elapsed = time.time() - self._start_time
        return f"修复失败 ({elapsed:.1f}s)"

    @property
    def cancel_step(self) -> str:
        elapsed = time.time() - self._start_time
        return f"已取消 ({elapsed:.1f}s)"

    def execute(self, progress_callback) -> dict[str, Any]:
        self._start_time = time.time()
        self._perf_collector.start_repair(self.task_id)

        if self.mobile_mode:
            version_info = ALGORITHM_VERSIONS.get(self.algorithm_version)
            if version_info and not version_info.get("mobile_compatible", True):
                error_msg = f"算法版本 {self.algorithm_version} 不支持移动端，请刷新页面后重试"
                raise ValueError(error_msg)

        logger.info(f"[RepairTask] 开始 task_id={self.task_id} version={self.algorithm_version}")

        self._last_progress_time[0] = time.time()
        self._start_stuck_monitor()

        output_filename = f"{self.task_id}_repaired.wav"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        if not os.path.exists(self.audio_path):
            raise FileNotFoundError(f"音频文件不存在: {self.audio_path}")

        file_size = os.path.getsize(self.audio_path)
        logger.info(f"[RepairTask] 音频文件 task_id={self.task_id} size={file_size/1024/1024:.2f}MB")

        try:
            from services.audio_loader import load_audio_with_fallback
            y, sr = load_audio_with_fallback(self.audio_path, sr=None, mono=False)
            self._size_samples = y.shape[1] if y.ndim > 1 else len(y)
        except Exception as e:
            logger.warning(f"[RepairTask] 预加载音频获取采样数失败 task_id={self.task_id}: {e}")
            self._size_samples = 0

        active_params = {k: v for k, v in self.params.items() if isinstance(v, (int, float)) and v > 0}
        logger.info(f"[RepairTask] 参数 task_id={self.task_id} active_params={active_params}")

        if "source_bit_depth" not in self.params:
            try:
                from services.audio_loader import load_audio_with_fallback
                _, _, src_bd = load_audio_with_fallback(self.audio_path, sr=None, mono=False, return_bit_depth=True)
                self.params["source_bit_depth"] = src_bd
            except Exception:
                self.params["source_bit_depth"] = 24

        def wrapped_progress(p: float, s: str) -> None:
            self._last_progress_time[0] = time.time()
            self._last_progress[0] = p
            if self._is_stuck[0]:
                self._is_stuck[0] = False
            progress_callback(p, s)

        with perf_timer("repair_total"):
            repair_result = repair_audio(
                self.audio_path,
                output_path,
                self.params,
                wrapped_progress,
                mobile_mode=self.mobile_mode
            )

        if os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            logger.info(f"[RepairTask] 输出文件 task_id={self.task_id} size={output_size/1024/1024:.2f}MB")
            waveform_peaks = _generate_waveform_peaks(output_path)
            if waveform_peaks:
                repair_result["waveform_peaks"] = waveform_peaks

        if repair_result.get("vocal_output_path") and os.path.exists(repair_result["vocal_output_path"]):
            vocal_task_id = self.params.get("vocal_task_id")
            if vocal_task_id:
                update_task(vocal_task_id, output_path=repair_result["vocal_output_path"], status="completed", progress=1)

        if repair_result.get("accompaniment_output_path") and os.path.exists(repair_result["accompaniment_output_path"]):
            accompaniment_task_id = self.params.get("accompaniment_task_id")
            if accompaniment_task_id:
                update_task(accompaniment_task_id, output_path=repair_result["accompaniment_output_path"], status="completed", progress=1)

        perf_data = self._perf_collector.end_repair(self.task_id, self._size_samples, self.algorithm_version)
        self._perf_ended = True
        repair_result["perf_data"] = perf_data

        elapsed = time.time() - self._start_time
        logger.info(f"[RepairTask] 完成 task_id={self.task_id} elapsed={elapsed:.1f}s issues={repair_result.get('issues_found', [])}")

        return repair_result

    def on_success(self, result: dict[str, Any]) -> dict[str, Any]:
        output_filename = f"{self.task_id}_repaired.wav"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        return {
            "output_path": output_path if os.path.exists(output_path) else None,
            "repair_result": result,
        }

    def on_error(self, error: Exception) -> dict[str, Any] | None:
        if isinstance(error, MemoryError):
            return {
                "error": str(error)[:500],
                "step": f"内存不足 ({time.time() - self._start_time:.1f}s)",
            }
        return None

    def _start_stuck_monitor(self) -> None:
        def monitor_stuck():
            while not self._stop_monitor[0]:
                time.sleep(2)
                if self._stop_monitor[0]:
                    break
                elapsed = time.time() - self._last_progress_time[0]
                if elapsed > STUCK_THRESHOLD and not self._is_stuck[0]:
                    self._is_stuck[0] = True
                    logger.warning(f"[RepairTask] 任务疑似卡住 task_id={self.task_id} elapsed={elapsed:.1f}s")
                    _ws_send_progress(self.task_id, {
                        "task_id": self.task_id,
                        "status": "repairing",
                        "progress": self._last_progress[0],
                        "step": "任务疑似卡住，请重试",
                        "stuck": True,
                        "stuck_duration": elapsed,
                    })

        self._monitor_thread = threading.Thread(target=monitor_stuck, daemon=True)
        self._monitor_thread.start()

    def cleanup(self) -> None:
        self._stop_monitor[0] = True
        if not self._perf_ended:
            try:
                self._perf_collector.end_repair(self.task_id, self._size_samples, self.algorithm_version)
            except Exception as e:
                logger.warning(f"[RepairTask] perf_collector.end_repair 失败 task_id={self.task_id}: {e}")


class DetectTask(BaseTask):
    def __init__(self, task_id: str, audio_path: str, detect_type: str = "original", detector_version: str = "v1.1") -> None:
        super().__init__(task_id)
        self.audio_path = audio_path
        self.detect_type = detect_type
        self.detector_version = detector_version
        self._start_time = 0.0
        prev_task = get_task(task_id)
        self._prev_status = prev_task["status"] if prev_task else "pending"
        self._stop_monitor = [False]
        self._monitor_thread: threading.Thread | None = None
        self._last_progress_time = [0.0]
        self._last_progress = [-1.0]
        self._is_stuck = [False]

    @property
    def task_type(self) -> str:
        return "detect"

    @property
    def initial_fields(self) -> dict[str, Any]:
        fields = {"error": ""}
        if self.detect_type == "original":
            fields["detection_result"] = None
        elif self.detect_type == "repaired":
            fields["repaired_detection_result"] = None
        return fields

    @property
    def processing_status(self) -> str:
        return "detecting"

    @property
    def completed_status(self) -> str:
        return "completed" if self._prev_status == "completed" else "detected"

    @property
    def label(self) -> str:
        return "修复后" if self.detect_type == "repaired" else "原始"

    @property
    def initial_step(self) -> str:
        return f"任务已提交，等待{self.label}检测..."

    @property
    def start_step(self) -> str:
        return f"开始{self.label}检测..."

    @property
    def done_step(self) -> str:
        elapsed = time.time() - self._start_time
        return f"{self.label}检测完成 ({elapsed:.1f}s)"

    @property
    def error_step(self) -> str:
        elapsed = time.time() - self._start_time
        return f"检测失败 ({elapsed:.1f}s)"

    @property
    def cancel_step(self) -> str:
        elapsed = time.time() - self._start_time
        return f"已取消 ({elapsed:.1f}s)"

    def execute(self, progress_callback) -> dict[str, Any]:
        self._start_time = time.time()
        logger.info(f"[DetectTask] 开始 task_id={self.task_id} type={self.detect_type} version={self.detector_version}")

        prev_task = get_task(self.task_id)
        self._prev_status = prev_task["status"] if prev_task else "pending"

        self._last_progress_time[0] = time.time()
        self._start_stuck_monitor()

        params: dict[str, Any] = (prev_task.get("params") if prev_task else None) or {}
        processing_mode = params.get("processing_mode", "single")
        if processing_mode == "dual":
            vocal_path = params.get("vocal_path", "")
            accompaniment_path = params.get("accompaniment_path", "")
            if vocal_path and not os.path.exists(vocal_path):
                raise FileNotFoundError(f"人声音频不存在: {vocal_path}")
            if accompaniment_path and not os.path.exists(accompaniment_path):
                raise FileNotFoundError(f"伴奏音频不存在: {accompaniment_path}")
            self.audio_path = vocal_path
        else:
            if not os.path.exists(self.audio_path):
                raise FileNotFoundError(f"音频文件不存在: {self.audio_path}")

        file_size = os.path.getsize(self.audio_path)
        logger.info(f"[DetectTask] 音频文件 task_id={self.task_id} size={file_size/1024/1024:.2f}MB")

        def wrapped_progress(p: float, s: str) -> None:
            self._last_progress_time[0] = time.time()
            self._last_progress[0] = p
            if self._is_stuck[0]:
                self._is_stuck[0] = False
            progress_callback(p, s)

        result = detect_ai_audio(self.audio_path, wrapped_progress, version=self.detector_version)
        result["detect_type"] = self.detect_type
        result["detector_version"] = self.detector_version

        elapsed = time.time() - self._start_time
        logger.info(f"[DetectTask] 完成 task_id={self.task_id} elapsed={elapsed:.1f}s")

        return result

    def on_success(self, result: dict[str, Any]) -> dict[str, Any]:
        if self.detect_type == "repaired":
            return {"repaired_detection_result": result}
        else:
            return {"detection_result": result}

    def _start_stuck_monitor(self) -> None:
        def monitor_stuck():
            while not self._stop_monitor[0]:
                time.sleep(2)
                if self._stop_monitor[0]:
                    break
                elapsed = time.time() - self._last_progress_time[0]
                if elapsed > STUCK_THRESHOLD and not self._is_stuck[0]:
                    self._is_stuck[0] = True
                    logger.warning(f"[DetectTask] 任务疑似卡住 task_id={self.task_id} elapsed={elapsed:.1f}s")
                    _ws_send_progress(self.task_id, {
                        "task_id": self.task_id,
                        "status": "detecting",
                        "progress": self._last_progress[0],
                        "step": "任务疑似卡住，请重试",
                        "stuck": True,
                        "stuck_duration": elapsed,
                    })

        self._monitor_thread = threading.Thread(target=monitor_stuck, daemon=True)
        self._monitor_thread.start()

    def cleanup(self) -> None:
        self._stop_monitor[0] = True


class RenderTask(BaseTask):
    def __init__(
        self,
        task_id: str,
        input_path: str,
        output_path: str,
        target_sr: int,
        bit_depth: int,
        render_filename: str,
        vocal_path: str | None = None,
        accompaniment_path: str | None = None,
        merge: bool = False,
        track_type: str = "both",
    ) -> None:
        super().__init__(task_id)
        self.input_path = input_path
        self.output_path = output_path
        self.target_sr = target_sr
        self.bit_depth = bit_depth
        self.render_filename = render_filename
        self.vocal_path = vocal_path
        self.accompaniment_path = accompaniment_path
        self.merge = merge
        self.track_type = track_type
        self._is_dual = vocal_path is not None and accompaniment_path is not None
        self._vocal_rendered = False
        self._accompaniment_rendered = False
        self._vocal_render_filename: str | None = None
        self._accompaniment_render_filename: str | None = None

    @property
    def task_type(self) -> str:
        return "render"

    @property
    def initial_fields(self) -> dict[str, Any]:
        return {
            "error": "",
            "render_result": None,
            "render_filename": None,
        }

    @property
    def processing_status(self) -> str:
        return "rendering"

    @property
    def completed_status(self) -> str:
        return "render_completed"

    @property
    def start_step(self) -> str:
        return "开始渲染..."

    @property
    def done_step(self) -> str:
        return "渲染完成"

    @property
    def error_step(self) -> str:
        return "渲染失败"

    def execute(self, progress_callback) -> dict[str, Any]:
        if self._is_dual:
            return self._execute_dual(progress_callback)
        else:
            return self._execute_single(progress_callback)

    def _execute_single(self, progress_callback) -> dict[str, Any]:
        from services.render import render_output
        from services.audio_loader import load_audio_with_fallback

        source_bit_depth = None
        try:
            _, _, src_bd = load_audio_with_fallback(self.input_path, sr=None, mono=False, return_bit_depth=True)
            source_bit_depth = src_bd
        except Exception:
            pass

        result = render_output(
            self.input_path,
            self.output_path,
            self.target_sr,
            self.bit_depth,
            progress_callback=progress_callback,
            source_bit_depth=source_bit_depth,
        )
        return result

    def _execute_dual(self, progress_callback) -> dict[str, Any]:
        import numpy as np
        import soundfile as sf
        from services.render import render_output
        from services.audio_loader import load_audio_with_fallback

        if self.track_type == "vocal":
            progress_callback(0.2, "渲染人声轨...")
            source_bit_depth = self._get_source_bit_depth(self.vocal_path)
            result = render_output(
                self.vocal_path,
                self.output_path,
                self.target_sr,
                self.bit_depth,
                progress_callback=progress_callback,
                source_bit_depth=source_bit_depth,
            )
            return result
        elif self.track_type == "accompaniment":
            progress_callback(0.2, "渲染伴奏轨...")
            source_bit_depth = self._get_source_bit_depth(self.accompaniment_path)
            result = render_output(
                self.accompaniment_path,
                self.output_path,
                self.target_sr,
                self.bit_depth,
                progress_callback=progress_callback,
                source_bit_depth=source_bit_depth,
            )
            return result

        progress_callback(0.1, "加载人声轨...")
        vocal_y, vocal_sr = load_audio_with_fallback(self.vocal_path, sr=None, mono=False)
        progress_callback(0.2, "加载伴奏轨...")
        accompaniment_y, accompaniment_sr = load_audio_with_fallback(self.accompaniment_path, sr=None, mono=False)

        progress_callback(0.3, "混音...")
        max_len = max(vocal_y.shape[1], accompaniment_y.shape[1])
        if vocal_y.shape[1] < max_len:
            vocal_y = np.pad(vocal_y, ((0, 0), (0, max_len - vocal_y.shape[1])), mode='constant')
        if accompaniment_y.shape[1] < max_len:
            accompaniment_y = np.pad(accompaniment_y, ((0, 0), (0, max_len - accompaniment_y.shape[1])), mode='constant')

        mixed = (vocal_y + accompaniment_y) / 2

        progress_callback(0.5, "渲染输出...")
        mixed = np.clip(mixed, -1.0, 1.0)
        if vocal_sr != self.target_sr:
            from scipy.signal import resample_poly
            target_len = int(mixed.shape[1] * self.target_sr / vocal_sr)
            mixed_resampled = np.zeros((mixed.shape[0], target_len), dtype=mixed.dtype)
            for ch in range(mixed.shape[0]):
                resampled = resample_poly(mixed[ch], self.target_sr, vocal_sr)
                mixed_resampled[ch, :len(resampled)] = resampled[:target_len]
            mixed = mixed_resampled
        subtype_map = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}
        subtype = subtype_map.get(self.bit_depth, "PCM_24")
        sf.write(self.output_path, mixed.T if mixed.ndim > 1 else mixed, self.target_sr, subtype=subtype)

        result = {
            "input_sample_rate": vocal_sr,
            "output_sample_rate": self.target_sr,
            "output_bit_depth": self.bit_depth,
            "channels": mixed.shape[0] if mixed.ndim > 1 else 1,
        }

        base_name = self.render_filename.rsplit(".", 1)[0]
        if base_name.endswith("_merged"):
            base_name = base_name[:-7]

        progress_callback(0.6, "渲染人声独立轨...")
        self._vocal_render_filename = f"{base_name}_vocal.wav"
        vocal_render_path = os.path.join(os.path.dirname(self.output_path), self._vocal_render_filename)
        vocal_source_bit_depth = self._get_source_bit_depth(self.vocal_path)
        try:
            render_output(self.vocal_path, vocal_render_path, self.target_sr, self.bit_depth, progress_callback=progress_callback, source_bit_depth=vocal_source_bit_depth)
            self._vocal_rendered = True
            logger.info(f"[RenderTask] 人声独立轨渲染完成: {self._vocal_render_filename}")
        except Exception as e:
            logger.warning(f"[RenderTask] 人声独立轨渲染失败: {e}")

        progress_callback(0.8, "渲染伴奏独立轨...")
        self._accompaniment_render_filename = f"{base_name}_accompaniment.wav"
        accompaniment_render_path = os.path.join(os.path.dirname(self.output_path), self._accompaniment_render_filename)
        accompaniment_source_bit_depth = self._get_source_bit_depth(self.accompaniment_path)
        try:
            render_output(self.accompaniment_path, accompaniment_render_path, self.target_sr, self.bit_depth, progress_callback=progress_callback, source_bit_depth=accompaniment_source_bit_depth)
            self._accompaniment_rendered = True
            logger.info(f"[RenderTask] 伴奏独立轨渲染完成: {self._accompaniment_render_filename}")
        except Exception as e:
            logger.warning(f"[RenderTask] 伴奏独立轨渲染失败: {e}")

        progress_callback(0.9, "完成")
        return result

    def _get_source_bit_depth(self, path: str) -> int | None:
        try:
            from services.audio_loader import load_audio_with_fallback
            _, _, src_bd = load_audio_with_fallback(path, sr=None, mono=False, return_bit_depth=True)
            return src_bd
        except Exception:
            return None

    def on_success(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "output_path": self.output_path,
            "render_filename": self.render_filename,
            "render_result": result,
        }

    def cleanup(self) -> None:
        from services.ws_manager import ws_manager
        files = [{"filename": self.render_filename, "sample_rate": self.target_sr, "bit_depth": self.bit_depth, "track_type": "both"}]
        if self._vocal_rendered and self._vocal_render_filename:
            files.append({"filename": self._vocal_render_filename, "sample_rate": self.target_sr, "bit_depth": self.bit_depth, "track_type": "vocal"})
        if self._accompaniment_rendered and self._accompaniment_render_filename:
            files.append({"filename": self._accompaniment_render_filename, "sample_rate": self.target_sr, "bit_depth": self.bit_depth, "track_type": "accompaniment"})
        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast_render_cache_update(self.task_id, files),
                loop
            )
        except Exception:
            pass
