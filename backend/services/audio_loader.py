import numpy as np


_SUBTYPE_BIT_DEPTH = {
    "PCM_S8": 8,
    "PCM_16": 16,
    "PCM_24": 24,
    "PCM_32": 32,
    "FLOAT": 32,
    "DOUBLE": 64,
    "MPEG_LAYER_III": 0,
    "VORBIS": 16,
    "ALAC_16": 16,
    "ALAC_20": 20,
    "ALAC_24": 24,
    "ALAC_32": 32,
}


def _load_with_soundfile(file_path: str, sr=None, mono=False, return_bit_depth=False) -> tuple:
    import soundfile as sf

    info = sf.info(file_path)
    data, sr_orig = sf.read(file_path, dtype='float32')

    if data.ndim == 1:
        raw = data.reshape(1, -1)
    else:
        raw = data.T

    sample_rate = sr_orig
    source_bit_depth = _SUBTYPE_BIT_DEPTH.get(info.subtype, 16)

    if mono and raw.shape[0] > 1:
        raw = raw.mean(axis=0)
    elif mono and raw.shape[0] == 1:
        raw = raw[0]
    elif not mono and raw.shape[0] == 1:
        raw = raw[0].reshape(1, -1)

    target_sr = sr if sr is not None else sample_rate
    if sample_rate != target_sr:
        from scipy.signal import resample_poly
        if raw.ndim == 1:
            num_samples = int(len(raw) * target_sr / sample_rate)
            raw = resample_poly(raw, target_sr, sample_rate)[:num_samples].astype(np.float32)
        else:
            resampled = np.zeros((raw.shape[0], int(raw.shape[1] * target_sr / sample_rate)), dtype=np.float32)
            for ch in range(raw.shape[0]):
                r = resample_poly(raw[ch], target_sr, sample_rate)
                resampled[ch, :len(r)] = r[:resampled.shape[1]]
            raw = resampled
        sample_rate = target_sr

    if return_bit_depth:
        return raw, sample_rate, source_bit_depth
    return raw, sample_rate


def _load_with_miniaudio(file_path: str, sr=None, mono=False, return_bit_depth=False) -> tuple:
    import miniaudio

    sound = miniaudio.decode_file(file_path, output_format=miniaudio.SampleFormat.FLOAT32)

    nchannels = sound.nchannels
    sample_rate = sound.sample_rate
    source_bit_depth = sound.sample_width * 8

    raw = np.frombuffer(sound.samples, dtype=np.float32).copy()

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

    if return_bit_depth:
        return raw, sample_rate, source_bit_depth
    return raw, sample_rate


def load_audio_with_fallback(file_path: str, sr=None, mono=False, return_bit_depth=False) -> tuple:
    try:
        return _load_with_soundfile(file_path, sr, mono, return_bit_depth)
    except Exception:
        pass
    return _load_with_miniaudio(file_path, sr, mono, return_bit_depth)
