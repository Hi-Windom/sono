import os
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
    original_working_sr = working_sr
    candidates = sorted(set([
        working_sr // 2,
        sr,
        sr // 2 if sr // 2 >= 8000 else None,
        22050,
        16000,
        8000,
    ]))
    candidates = [c for c in candidates if c is not None and c >= 8000 and c <= working_sr]
    for candidate_sr in candidates:
        estimated_c = estimate_repair_memory_bytes(n_samples, n_channels, sr, candidate_sr)
        if estimated_c <= safe_limit:
            logger.warning(
                f"[memory_guard] 内存不足: 预估 {estimated/1024/1024:.0f}MB > 可用 {available/1024/1024:.0f}MB, "
                f"工作采样率降级 {original_working_sr}Hz → {candidate_sr}Hz"
            )
            return candidate_sr
    estimated_native = estimate_repair_memory_bytes(n_samples, n_channels, sr, min(candidates) if candidates else sr)
    logger.error(
        f"[memory_guard] 内存严重不足: 即使最低采样率处理也需 {estimated_native/1024/1024:.0f}MB > 可用 {available/1024/1024:.0f}MB, "
        f"音频可能过长 (n_samples={n_samples}, channels={n_channels}, sr={sr})"
    )
    raise MemoryError(
        f"可用内存不足，无法处理此音频。"
        f"预估需要 {estimated_native/1024/1024:.0f}MB，当前可用 {available/1024/1024:.0f}MB。"
        f"请尝试更短的音频或关闭其他程序释放内存。"
    )
