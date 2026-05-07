import numpy as np


def load_audio_with_fallback(file_path: str, sr=None, mono=False) -> tuple:
    try:
        import miniaudio

        sound = miniaudio.read_file(file_path)

        nchannels = sound.nchannels
        sample_rate = sound.sample_rate

        if sound.sample_format == miniaudio.SampleFormat.FLOAT32:
            raw = np.frombuffer(sound.samples, dtype=np.float32)
        elif sound.sample_format == miniaudio.SampleFormat.SIGNED16:
            raw = np.frombuffer(sound.samples, dtype=np.int16).astype(np.float32) / 32768.0
        elif sound.sample_format == miniaudio.SampleFormat.SIGNED32:
            raw = np.frombuffer(sound.samples, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raw = np.frombuffer(sound.samples, dtype=np.int16).astype(np.float32) / 32768.0

        if nchannels > 1:
            raw = raw.reshape(-1, nchannels).T
        else:
            raw = raw.reshape(1, -1)

        if mono and raw.shape[0] > 1:
            raw = raw.mean(axis=0)
        elif mono and raw.shape[0] == 1:
            raw = raw[0]
        elif not mono and raw.shape[0] == 1:
            raw = raw[0].reshape(1, -1)

        target_sr = sr if sr is not None else sample_rate
        if sample_rate != target_sr:
            if raw.ndim == 1:
                num_samples = int(len(raw) * target_sr / sample_rate)
                indices = np.linspace(0, len(raw) - 1, num_samples)
                raw = np.interp(indices, np.arange(len(raw)), raw).astype(np.float32)
            else:
                resampled = np.zeros((raw.shape[0], int(raw.shape[1] * target_sr / sample_rate)), dtype=np.float32)
                for ch in range(raw.shape[0]):
                    indices = np.linspace(0, len(raw[ch]) - 1, resampled.shape[1])
                    resampled[ch] = np.interp(indices, np.arange(len(raw[ch])), raw[ch])
                raw = resampled
            sample_rate = target_sr

        return raw, sample_rate

    except Exception:
        pass

    try:
        import librosa
        y, sample_rate = librosa.load(file_path, sr=sr, mono=mono)
        return y, sample_rate
    except Exception:
        raise RuntimeError(f"Failed to load audio file: {file_path}")
