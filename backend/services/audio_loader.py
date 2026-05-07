import numpy as np
import librosa
from scipy import signal as scipy_signal
from pydub import AudioSegment


def _resample_pydub(samples: np.ndarray, orig_sr: int, target_sr: int, channels: int) -> np.ndarray:
    if channels > 1:
        samples = samples.T
    audio = AudioSegment(
        samples=samples.tobytes(),
        sample_width=2,
        frame_rate=orig_sr,
        channels=channels
    )
    audio = audio.set_frame_rate(target_sr)
    arr = np.array(audio.get_array_of_samples())
    if audio.channels > 1:
        arr = arr.reshape(-1, audio.channels).T
    else:
        arr = arr
    return arr


def load_audio_with_fallback(file_path: str, sr=None, mono=False) -> tuple:
    try:
        y, sample_rate = librosa.load(file_path, sr=sr, mono=mono)
        return y, sample_rate
    except Exception:
        audio = AudioSegment.from_file(file_path)

        if mono:
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples = samples / 32768.0
            if audio.channels == 2:
                samples = samples.reshape(-1, 2).mean(axis=1)
        else:
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples = samples / 32768.0
            if audio.channels == 1:
                pass
            else:
                samples = samples.reshape(-1, audio.channels).T

        target_sr = sr if sr is not None else audio.frame_rate

        if audio.frame_rate != target_sr:
            if samples.ndim == 1:
                num_samples = int(len(samples) * target_sr / audio.frame_rate)
                indices = np.linspace(0, len(samples) - 1, num_samples)
                samples = np.interp(indices, np.arange(len(samples)), samples)
            else:
                resampled = np.zeros((samples.shape[0], int(samples.shape[1] * target_sr / audio.frame_rate)))
                for ch in range(samples.shape[0]):
                    indices = np.linspace(0, len(samples[ch]) - 1, resampled.shape[1])
                    resampled[ch] = np.interp(indices, np.arange(len(samples[ch])), samples[ch])
                samples = resampled

        return samples, target_sr
