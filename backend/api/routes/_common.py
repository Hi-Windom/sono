import logging

logger = logging.getLogger(__name__)


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
