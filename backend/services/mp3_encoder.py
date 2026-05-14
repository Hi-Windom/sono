import ctypes
import ctypes.util
import logging
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

_lib = None
_lib_version = None


def _setup_signatures():
    _lib.lame_init.restype = ctypes.c_void_p
    _lib.lame_init.argtypes = []

    _lib.lame_set_num_channels.restype = ctypes.c_int
    _lib.lame_set_num_channels.argtypes = [ctypes.c_void_p, ctypes.c_int]

    _lib.lame_set_in_samplerate.restype = ctypes.c_int
    _lib.lame_set_in_samplerate.argtypes = [ctypes.c_void_p, ctypes.c_int]

    _lib.lame_set_brate.restype = ctypes.c_int
    _lib.lame_set_brate.argtypes = [ctypes.c_void_p, ctypes.c_int]

    _lib.lame_set_quality.restype = ctypes.c_int
    _lib.lame_set_quality.argtypes = [ctypes.c_void_p, ctypes.c_int]

    _lib.lame_set_VBR.restype = ctypes.c_int
    _lib.lame_set_VBR.argtypes = [ctypes.c_void_p, ctypes.c_int]

    _lib.lame_init_params.restype = ctypes.c_int
    _lib.lame_init_params.argtypes = [ctypes.c_void_p]

    _lib.lame_encode_buffer.restype = ctypes.c_int
    _lib.lame_encode_buffer.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_short),
        ctypes.POINTER(ctypes.c_short),
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]

    _lib.lame_encode_flush.restype = ctypes.c_int
    _lib.lame_encode_flush.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
    ]

    _lib.lame_close.restype = ctypes.c_int
    _lib.lame_close.argtypes = [ctypes.c_void_p]

    _lib.get_lame_version.restype = ctypes.c_char_p
    _lib.get_lame_version.argtypes = []


def _load_lib() -> bool:
    global _lib, _lib_version
    try:
        path = ctypes.util.find_library("mp3lame")
        if not path:
            logger.warning("libmp3lame not found in system library path")
            return False
        _lib = ctypes.cdll.LoadLibrary(path)
        _setup_signatures()
        _lib_version = _lib.get_lame_version().decode()
        logger.info("libmp3lame %s loaded from %s", _lib_version, path)
        return True
    except Exception as e:
        logger.warning("failed to load libmp3lame: %s", e)
        return False


def is_available() -> bool:
    return _lib is not None


def get_version() -> str:
    if _lib_version:
        return _lib_version
    return "不可用"


def encode_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    if _lib is None:
        if not _load_lib():
            raise RuntimeError("libmp3lame 未安装，MP3编码不可用")

    wav_path = Path(wav_path)
    mp3_path = Path(mp3_path)

    if not wav_path.exists():
        raise FileNotFoundError(f"WAV文件不存在: {wav_path}")

    data, sr = sf.read(str(wav_path))
    if data.size == 0:
        raise ValueError("WAV文件为空")

    if data.ndim == 1:
        channels = 1
    else:
        channels = data.shape[1]

    if sr not in (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000):
        raise ValueError(f"不支持的采样率 {sr}Hz")

    if data.dtype != np.int16:
        if np.issubdtype(data.dtype, np.floating):
            data = (data * 32767).clip(-32768, 32767).astype(np.int16)
        else:
            data = data.astype(np.int16)

    lame = _lib.lame_init()
    try:
        _lib.lame_set_num_channels(lame, channels)
        _lib.lame_set_in_samplerate(lame, sr)
        _lib.lame_set_brate(lame, bitrate)
        _lib.lame_set_quality(lame, 2)
        _lib.lame_set_VBR(lame, 0)
        _lib.lame_init_params(lame)

        mp3_bytes = bytearray()
        if channels == 1:
            pcm = np.ascontiguousarray(data).ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            nsamples = len(data)
            buf_size = nsamples * 5 // 4 + 7200
            buf = ctypes.create_string_buffer(buf_size)
            encoded = _lib.lame_encode_buffer(lame, pcm, pcm, nsamples, buf, buf_size)
        else:
            pcm_left = np.ascontiguousarray(data[:, 0]).ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            pcm_right = np.ascontiguousarray(data[:, 1]).ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            nsamples = len(data)
            buf_size = nsamples * 5 // 4 + 7200
            buf = ctypes.create_string_buffer(buf_size)
            encoded = _lib.lame_encode_buffer(lame, pcm_left, pcm_right, nsamples, buf, buf_size)

        if encoded < 0:
            raise RuntimeError(f"MP3编码失败 (lame return code: {encoded})")

        if encoded > 0:
            mp3_bytes.extend(buf[:encoded])

        flush_buf = ctypes.create_string_buffer(8192)
        flushed = _lib.lame_encode_flush(lame, flush_buf, len(flush_buf))

        if flushed < 0:
            raise RuntimeError(f"MP3刷新编码失败 (lame return code: {flushed})")

        if flushed > 0:
            mp3_bytes.extend(flush_buf[:flushed])

        total = encoded + flushed
        logger.info("MP3编码完成: %d 样本 -> %d bytes (%d encoded + %d flushed)", nsamples, total, encoded, flushed)

        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(mp3_path), 'wb') as f:
            f.write(mp3_bytes)
    finally:
        _lib.lame_close(lame)

    if not mp3_path.exists() or mp3_path.stat().st_size == 0:
        raise RuntimeError("MP3编码输出为空")


_load_lib()