import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_ffmpeg_path = None
_ffmpeg_version = None


def _detect_ffmpeg() -> bool:
    global _ffmpeg_path, _ffmpeg_version
    try:
        path = shutil.which("ffmpeg")
        if not path:
            logger.warning("ffmpeg not found in PATH")
            return False
        _ffmpeg_path = path
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        first_line = result.stdout.strip().split("\n")[0] if result.stdout else ""
        if "ffmpeg" in first_line.lower():
            parts = first_line.split()
            _ffmpeg_version = parts[2] if len(parts) >= 3 else "unknown"
            logger.info("ffmpeg %s found at %s", _ffmpeg_version, path)
            return True
        logger.warning("ffmpeg -version output unexpected: %s", first_line[:100])
        return False
    except Exception as e:
        logger.warning("failed to detect ffmpeg: %s", e)
        return False


def is_available() -> bool:
    return _ffmpeg_path is not None


def get_version() -> str:
    if _ffmpeg_version:
        return _ffmpeg_version
    return "不可用"


def encode_m4a(wav_path: str, m4a_path: str):
    if _ffmpeg_path is None:
        raise RuntimeError("ffmpeg 未安装，M4A/ALAC 编码不可用")

    wav_path = Path(wav_path)
    m4a_path = Path(m4a_path)

    if not wav_path.exists():
        raise FileNotFoundError(f"WAV文件不存在: {wav_path}")

    if wav_path.stat().st_size == 0:
        raise ValueError("WAV文件为空")

    m4a_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _ffmpeg_path,
        "-y",
        "-i", str(wav_path),
        "-c:a", "alac",
        "-movflags", "+faststart",
        str(m4a_path),
    ]

    logger.info("M4A编码: %s -> %s", wav_path.name, m4a_path.name)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("M4A编码超时（600秒）")

    if result.returncode != 0:
        stderr_preview = result.stderr[-500:] if result.stderr else ""
        raise RuntimeError(f"ffmpeg M4A编码失败 (code {result.returncode}): {stderr_preview}")

    if not m4a_path.exists() or m4a_path.stat().st_size == 0:
        raise RuntimeError("M4A编码输出为空")

    wav_size = wav_path.stat().st_size
    m4a_size = m4a_path.stat().st_size
    ratio = m4a_size / wav_size if wav_size > 0 else 0
    logger.info(
        "M4A编码完成: %d -> %d bytes (压缩率 %.1f%%)",
        wav_size, m4a_size, ratio * 100,
    )


_detect_ffmpeg()
