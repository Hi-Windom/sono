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

def get_total_memory_bytes():
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    try:
        import psutil
        return psutil.virtual_memory().total
    except ImportError:
        pass
    return None

def estimate_repair_memory_bytes(n_samples, n_channels, sr, working_sr, algorithm_version=None):
    upsampled_samples = int(n_samples * working_sr / sr)
    use_f32 = should_use_float32(n_samples, n_channels)
    elem_size = 4 if use_f32 else 8
    audio_bytes = n_channels * upsampled_samples * elem_size

    n_fft = 2048
    hop_length = 512
    n_frames = upsampled_samples // hop_length + 1
    has_streaming = algorithm_version in ("v2.2", "v2.3", "v2.3a", "v2.4", "v2.4a", "v3.0", "v3.0a", "v3.1", "v3.1a", "v3.2", "v3.2+", "v3.2a", "v3.2a+")

    if has_streaming:
        stft_bytes = (n_fft // 2 + 1) * (working_sr * 10 // hop_length + 1) * 16
    else:
        stft_bytes = (n_fft // 2 + 1) * n_frames * 16

    peak_temp = upsampled_samples * elem_size + stft_bytes

    if algorithm_version in ("v2.2", "v2.3", "v2.4"):
        peak_temp += upsampled_samples * elem_size * 0.5
    elif algorithm_version in ("v2.2a", "v2.3a", "v2.4a"):
        peak_temp += upsampled_samples * elem_size * 0.15
    elif algorithm_version == "v3.0":
        peak_temp += upsampled_samples * elem_size * 1.0
    elif algorithm_version == "v3.0a":
        peak_temp += upsampled_samples * elem_size * 0.5
    elif algorithm_version == "v3.1":
        peak_temp += upsampled_samples * elem_size * 1.2
    elif algorithm_version == "v3.1a":
        peak_temp += upsampled_samples * elem_size * 0.6
    elif algorithm_version == "v3.2":
        peak_temp += upsampled_samples * elem_size * 0.3
    elif algorithm_version == "v3.2+":
        peak_temp += upsampled_samples * elem_size * 0.6
    elif algorithm_version == "v3.2a":
        peak_temp += upsampled_samples * elem_size * 0.2
    elif algorithm_version == "v3.2a+":
        peak_temp += upsampled_samples * elem_size * 3.0
    elif algorithm_version in ("v1.0", "v1.1", "v1.2"):
        peak_temp += upsampled_samples * elem_size * 0.3
    elif algorithm_version in ("v2.0", "v2.1"):
        peak_temp += upsampled_samples * elem_size * 0.2

    python_overhead = 1.3
    safety = 1.2
    total = (audio_bytes + peak_temp) * python_overhead * safety
    return int(total)

def check_memory_before_repair(n_samples, n_channels, sr, working_sr, safety_margin=0.0, algorithm_version=None):
    available = get_available_memory_bytes()
    if available is None:
        logger.warning("[memory_guard] 无法获取可用内存，跳过检查")
        return working_sr
    estimated = estimate_repair_memory_bytes(n_samples, n_channels, sr, working_sr, algorithm_version=algorithm_version)
    if estimated <= available:
        logger.info(f"[memory_guard] 内存检查通过: 预估 {estimated/1024/1024:.0f}MB, 可用 {available/1024/1024:.0f}MB, 工作采样率 {working_sr}Hz")
        return working_sr
    logger.error(
        f"[memory_guard] 内存不足: 预估 {estimated/1024/1024:.0f}MB > 可用 {available/1024/1024:.0f}MB, "
        f"音频参数: n_samples={n_samples}, channels={n_channels}, sr={sr}, working_sr={working_sr}"
    )
    raise MemoryError(
        f"可用内存不足，无法处理此音频。"
        f"预估需要 {estimated/1024/1024:.0f}MB，当前可用 {available/1024/1024:.0f}MB。"
        f"请尝试更短的音频或关闭其他程序释放内存。"
    )
