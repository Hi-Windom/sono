import logging

logger = logging.getLogger(__name__)

FLOAT32_THRESHOLD_SAMPLES = 10 * 60 * 48000

def get_available_memory_bytes():
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    try:
        import psutil
        return psutil.virtual_memory().available
    except ImportError:
        pass
    return None

def should_use_float32(n_samples, n_channels):
    return n_samples * n_channels > FLOAT32_THRESHOLD_SAMPLES

def estimate_repair_memory_bytes(n_samples, n_channels, sr, working_sr, algorithm_version=None):
    upsampled_samples = int(n_samples * working_sr / sr)
    use_f32 = should_use_float32(n_samples, n_channels)
    elem_size = 4 if use_f32 else 8
    audio_bytes = n_channels * upsampled_samples * elem_size

    chunk_stft_bytes = 1025 * (working_sr * 10 // 512 + 1) * 16

    peak_temp = upsampled_samples * elem_size + chunk_stft_bytes

    if algorithm_version in ("v2.2", "v2.3"):
        peak_temp += upsampled_samples * elem_size * 0.5
    elif algorithm_version in ("v2.2a", "v2.3a"):
        peak_temp += upsampled_samples * elem_size * 0.15
    elif algorithm_version in ("v1.0", "v1.1", "v1.2"):
        peak_temp += upsampled_samples * elem_size * 0.3

    python_overhead = 1.3
    safety = 1.2
    total = (audio_bytes + peak_temp) * python_overhead * safety
    return int(total)

def check_memory_before_repair(n_samples, n_channels, sr, working_sr, safety_margin=0.3):
    available = get_available_memory_bytes()
    if available is None:
        logger.warning("[memory_guard] 无法获取可用内存，跳过检查")
        return working_sr
    estimated = estimate_repair_memory_bytes(n_samples, n_channels, sr, working_sr)
    safe_limit = available * (1.0 - safety_margin)
    if estimated <= safe_limit:
        logger.info(f"[memory_guard] 内存检查通过: 预估 {estimated/1024/1024:.0f}MB, 可用 {available/1024/1024:.0f}MB, 工作采样率 {working_sr}Hz")
        return working_sr
    logger.error(
        f"[memory_guard] 内存不足: 预估 {estimated/1024/1024:.0f}MB > 安全上限 {safe_limit/1024/1024:.0f}MB (可用 {available/1024/1024:.0f}MB × {(1-safety_margin)*100:.0f}%), "
        f"音频参数: n_samples={n_samples}, channels={n_channels}, sr={sr}, working_sr={working_sr}"
    )
    raise MemoryError(
        f"可用内存不足，无法处理此音频。"
        f"预估需要 {estimated/1024/1024:.0f}MB，当前可用 {available/1024/1024:.0f}MB。"
        f"请尝试更短的音频或关闭其他程序释放内存。"
    )
