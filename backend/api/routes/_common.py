import logging
import hmac
import hashlib

logger = logging.getLogger(__name__)

_DEFAULT_SECRET_KEY = "default-secret-key-change-in-production"


def _task_auth_enabled() -> bool:
    from config import SECRET_KEY
    return SECRET_KEY != _DEFAULT_SECRET_KEY and bool(SECRET_KEY)


def generate_task_access_token(task_id: str) -> str:
    from config import SECRET_KEY
    return hmac.new(SECRET_KEY.encode(), task_id.encode(), hashlib.sha256).hexdigest()[:16]


def verify_task_access_token(task_id: str, token: str) -> bool:
    if not _task_auth_enabled():
        return True
    if not token:
        return False
    expected = generate_task_access_token(task_id)
    return hmac.compare_digest(expected, token)


def _get_audio_info(path: str) -> dict | None:
    try:
        import soundfile as sf
        info = sf.info(path)
        return {
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "duration": info.duration,
            "num_frames": info.frames,
            "format": info.format,
            "subtype": info.subtype,
        }
    except Exception:
        pass
    try:
        import miniaudio
        info = miniaudio.get_file_info(path)
        return {
            "sample_rate": info.sample_rate,
            "channels": info.nchannels,
            "duration": info.duration,
            "num_frames": info.num_frames,
            "format": str(info.file_format),
            "sample_width": info.sample_width,
        }
    except Exception:
        return None
