import numpy as np
import librosa
from pydub import AudioSegment


def load_audio_with_fallback(file_path: str, sr=None, mono=False) -> tuple:
    try:
        y, sample_rate = librosa.load(file_path, sr=sr, mono=mono)
        return y, sample_rate
    except Exception as e:
        pass

    audio = AudioSegment.from_file(file_path)

    if mono:
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        samples = samples / 32768.0
        if audio.channels == 2:
            samples = samples.reshape(-1, 2).mean(axis=1)
        samples = samples.astype(np.float32)
    else:
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        samples = samples / 32768.0
        if audio.channels == 1:
            samples = samples.astype(np.float32)
        else:
            samples = samples.reshape(-1, audio.channels).T.astype(np.float32)

    target_sr = sr if sr is not None else audio.frame_rate

    if audio.frame_rate != target_sr:
        if samples.ndim == 1:
            num_samples = int(len(samples) * target_sr / audio.frame_rate)
            indices = np.linspace(0, len(samples) - 1, num_samples)
            samples = np.interp(indices, np.arange(len(samples)), samples).astype(np.float32)
        else:
            resampled = np.zeros((samples.shape[0], int(samples.shape[1] * target_sr / audio.frame_rate)), dtype=np.float32)
            for ch in range(samples.shape[0]):
                indices = np.linspace(0, len(samples[ch]) - 1, resampled.shape[1])
                resampled[ch] = np.interp(indices, np.arange(len(samples[ch])), samples[ch])
            samples = resampled

    return samples, target_sr
