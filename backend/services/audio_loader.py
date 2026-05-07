import numpy as np
import librosa
import soundfile as sf


def load_audio_with_fallback(file_path: str, sr=None, mono=False) -> tuple:
    try:
        y, sample_rate = librosa.load(file_path, sr=sr, mono=mono)
        return y, sample_rate
    except Exception:
        pass

    try:
        import miniaudio

        sound = miniaudio.decode_file(file_path, output_format=miniaudio.SampleFormat.FLOAT32)
        samples = sound.samples.T if sound.channels > 1 else sound.samples.reshape(1, -1)
        sample_rate = sound.sample_rate

        if mono and samples.shape[0] > 1:
            samples = samples.mean(axis=0)
        elif mono and samples.shape[0] == 1:
            samples = samples[0]
        elif not mono and samples.shape[0] == 1:
            samples = samples[0].reshape(1, -1)

        target_sr = sr if sr is not None else sample_rate
        if sample_rate != target_sr:
            if samples.ndim == 1:
                num_samples = int(len(samples) * target_sr / sample_rate)
                indices = np.linspace(0, len(samples) - 1, num_samples)
                samples = np.interp(indices, np.arange(len(samples)), samples).astype(np.float32)
            else:
                resampled = np.zeros((samples.shape[0], int(samples.shape[1] * target_sr / sample_rate)), dtype=np.float32)
                for ch in range(samples.shape[0]):
                    indices = np.linspace(0, len(samples[ch]) - 1, resampled.shape[1])
                    resampled[ch] = np.interp(indices, np.arange(len(samples[ch])), samples[ch])
                samples = resampled
            sample_rate = target_sr

        return samples, sample_rate

    except Exception:
        raise RuntimeError(f"Failed to load audio file: {file_path}")
