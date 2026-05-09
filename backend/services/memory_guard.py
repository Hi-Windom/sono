import logging

logger = logging.getLogger(__name__)

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

def estimate_repair_memory_bytes(n_samples, n_channels, sr, working_sr):
    upsampled_samples = int(n_samples * working_sr / sr)
    audio_bytes = n_channels * upsampled_samples * 8
    n_fft = 2048
    hop = 512
    n_frames = upsampled_samples // hop + 1
    stft_bytes = (n_fft // 2 + 1) * n_frames * 16
    peak_multiplier = 2.5
    total = (audio_bytes * 3 + stft_bytes * 2) * peak_multiplier
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
