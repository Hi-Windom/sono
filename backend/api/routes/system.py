import os
import asyncio
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from config import MOBILE_MODE, DEPLOY_TIME_FILE
from services.task_manager import get_active_task_count, get_active_tasks, can_accept_task, executor
from services.audio_repair import get_available_versions
from services.ai_detector import get_detector_versions
from services.memory_guard import get_available_memory_bytes, estimate_repair_memory_bytes, should_use_float32, get_total_memory_bytes
from database import get_queue_status, get_task

logger = logging.getLogger(__name__)

router = APIRouter()


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
    if request.algorithm_version == "v2.2a":
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

    def _supports_streaming(version: str) -> bool:
        try:
            if version.startswith('v'):
                version = version[1:]
            import re
            match = re.match(r'(\d+)\.(\d+)', version)
            if match:
                major = int(match.group(1))
                minor = int(match.group(2))
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

    from config import UPLOAD_DIR, OUTPUT_DIR, DECODED_DIR
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


@router.get("/queue-status")
async def get_queue():
    return get_queue_status()


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
            "test_loudness_norm_snr": ("per_step", "SNR", "Loudness Norm 步骤 SNR > 60 dB"),
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
