import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import soundfile as sf


def make_wav_bytes(y=None, sr=44100, duration=1.0, freq=440.0, amplitude=0.5, channels=1, subtype="PCM_16"):
    if y is None:
        n_samples = int(sr * duration)
        t = np.arange(n_samples, dtype=np.float64) / sr
        y = amplitude * np.sin(2 * np.pi * freq * t)

    y = np.asarray(y, dtype=np.float64)

    if y.ndim == 1:
        if channels > 1:
            y = np.column_stack([y] * channels)
    else:
        if y.shape[1] != channels:
            if channels == 1:
                y = y[:, 0]
            else:
                if y.shape[1] == 1:
                    y = np.column_stack([y[:, 0]] * channels)

    if subtype in ("PCM_16", "PCM_24", "PCM_32"):
        max_val = 1.0
        if np.max(np.abs(y)) > 1.0:
            max_val = np.max(np.abs(y))
        y = y / max_val * (1.0 - 1e-6)

    import io
    buf = io.BytesIO()
    sf.write(buf, y, sr, subtype=subtype, format="WAV")
    return buf.getvalue()


def make_mp3_bytes(sr=44100, duration=1.0, freq=440.0, amplitude=0.5, channels=1, bitrate=128):
    wav_bytes = make_wav_bytes(sr=sr, duration=duration, freq=freq, amplitude=amplitude, channels=channels)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
        f.write(wav_bytes)
    mp3_path = wav_path.replace(".wav", ".mp3")
    try:
        from services.mp3_encoder import encode_mp3
        encode_mp3(wav_path, mp3_path, bitrate=bitrate)
        with open(mp3_path, "rb") as f:
            return f.read()
    finally:
        for p in [wav_path, mp3_path]:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def make_large_audio_bytes(size_mb=10, sr=44100, freq=440.0, amplitude=0.5, channels=1, fmt="mp3", bitrate=128):
    target_bytes = size_mb * 1024 * 1024
    if fmt == "wav":
        bytes_per_sample = 2
        bytes_per_second = sr * channels * bytes_per_sample
        duration = target_bytes / bytes_per_second
        return make_wav_bytes(sr=sr, duration=duration, freq=freq, amplitude=amplitude, channels=channels)
    else:
        bytes_per_second = bitrate * 1024 / 8
        duration = target_bytes / bytes_per_second
        return make_mp3_bytes(sr=sr, duration=duration, freq=freq, amplitude=amplitude, channels=channels, bitrate=bitrate)


def upload_file(client, file_bytes, filename="test.wav", content_type="audio/wav", file_hash=""):
    data = {}
    if file_hash:
        data["file_hash"] = file_hash
    return client.post(
        "/api/v1/upload",
        files={"file": (filename, file_bytes, content_type)},
        data=data if data else None,
    )
