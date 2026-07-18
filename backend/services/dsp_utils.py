import numpy as np
from functools import lru_cache
import time
from collections import OrderedDict


_MAX_WINDOW_CACHE_SIZE = 64
_WINDOW_CACHE = OrderedDict()


def _get_window(window: str, n_fft: int, dtype=np.float64) -> np.ndarray:
    key = (window, n_fft, dtype)
    if key not in _WINDOW_CACHE:
        from scipy.signal import get_window
        w = get_window(window, n_fft, fftbins=True).astype(dtype)
        if len(_WINDOW_CACHE) >= _MAX_WINDOW_CACHE_SIZE:
            _WINDOW_CACHE.popitem(last=False)
        _WINDOW_CACHE[key] = w
    else:
        _WINDOW_CACHE.move_to_end(key)
    return _WINDOW_CACHE[key]


def _dct(x, **kwargs):
    from scipy.fftpack import dct
    return dct(x, **kwargs)


def _medfilt(x, **kwargs):
    from scipy.signal import medfilt
    return medfilt(x, **kwargs)


def _stride_frames(y, frame_length, hop_length):
    n_frames = 1 + (len(y) - frame_length) // hop_length
    if n_frames <= 0:
        return np.empty((0, frame_length), dtype=y.dtype)
    strides = (y.strides[0] * hop_length, y.strides[0])
    return np.lib.stride_tricks.as_strided(y, shape=(n_frames, frame_length), strides=strides)


def _get_dtype(y):
    if y.dtype == np.float32:
        return np.float32, np.complex64
    return np.float64, np.complex128


def stft(y, n_fft=2048, hop_length=512, window='hann'):
    f_dtype, c_dtype = _get_dtype(y)
    fft_window = _get_window(window, n_fft, f_dtype)
    pad_length = n_fft // 2
    y_padded = np.pad(y, (pad_length, pad_length), mode='reflect').astype(f_dtype, copy=False)
    frames = _stride_frames(y_padded, n_fft, hop_length)
    if frames.shape[0] == 0:
        return np.empty((1 + n_fft // 2, 0), dtype=c_dtype)
    windowed = frames * fft_window
    S = np.fft.rfft(windowed, axis=1).T
    return S


def stft_chunked(y, n_fft=2048, hop_length=512, window='hann', chunk_frames=4096):
    f_dtype, c_dtype = _get_dtype(y)
    fft_window = _get_window(window, n_fft, f_dtype)
    pad_length = n_fft // 2
    y_padded = np.pad(y, (pad_length, pad_length), mode='reflect').astype(f_dtype, copy=False)
    n_frames = 1 + (len(y_padded) - n_fft) // hop_length
    if n_frames <= 0:
        return np.empty((1 + n_fft // 2, 0), dtype=c_dtype)
    n_bins = 1 + n_fft // 2
    S = np.empty((n_bins, n_frames), dtype=c_dtype)
    for start in range(0, n_frames, chunk_frames):
        end = min(start + chunk_frames, n_frames)
        starts = start * hop_length
        ends = starts + n_fft + (end - start - 1) * hop_length
        chunk_data = np.ascontiguousarray(y_padded[starts:ends])
        chunk_frames_data = _stride_frames(chunk_data, n_fft, hop_length)[:end - start]
        windowed = chunk_frames_data * fft_window
        S[:, start:end] = np.fft.rfft(windowed, axis=1).T
    return S


def istft(S, hop_length=512, length=None, window='hann'):
    n_fft = 2 * (S.shape[0] - 1)
    c_dtype = S.dtype
    f_dtype = np.float32 if c_dtype == np.complex64 else np.float64
    fft_window = _get_window(window, n_fft, f_dtype)
    n_frames = S.shape[1]
    expected_signal_len = n_fft + hop_length * (n_frames - 1)
    y = np.zeros(expected_signal_len, dtype=f_dtype)
    window_sum = np.zeros(expected_signal_len, dtype=f_dtype)
    frames = np.fft.irfft(S.T, n=n_fft, axis=1)
    windowed = frames * fft_window
    win_sq = fft_window ** 2
    frame_starts = np.arange(n_frames) * hop_length
    block = max(1, hop_length)
    for i0 in range(0, n_fft, block):
        i1 = min(i0 + block, n_fft)
        cols = np.arange(i0, i1)
        idx = frame_starts[:, None] + cols
        y[idx] += windowed[:, i0:i1]
        window_sum[idx] += win_sq[i0:i1]
    nonzero = window_sum > 1e-10
    y[nonzero] /= window_sum[nonzero]
    pad_length = n_fft // 2
    y = y[pad_length:]
    if length is not None:
        y = y[:length]
    return y


def istft_chunked(S, hop_length=512, length=None, window='hann', chunk_frames=4096):
    n_fft = 2 * (S.shape[0] - 1)
    c_dtype = S.dtype
    f_dtype = np.float32 if c_dtype == np.complex64 else np.float64
    fft_window = _get_window(window, n_fft, f_dtype)
    n_frames = S.shape[1]
    expected_signal_len = n_fft + hop_length * (n_frames - 1)
    y = np.zeros(expected_signal_len, dtype=f_dtype)
    window_sum = np.zeros(expected_signal_len, dtype=f_dtype)
    win_sq = fft_window ** 2
    block = max(1, hop_length)
    for start in range(0, n_frames, chunk_frames):
        end = min(start + chunk_frames, n_frames)
        S_chunk = S[:, start:end]
        frames = np.fft.irfft(S_chunk.T, n=n_fft, axis=1)
        windowed = frames * fft_window
        chunk_n_frames = end - start
        frame_starts = np.arange(start, end) * hop_length
        for i0 in range(0, n_fft, block):
            i1 = min(i0 + block, n_fft)
            cols = np.arange(i0, i1)
            idx = frame_starts[:, None] + cols
            y[idx] += windowed[:, i0:i1]
            window_sum[idx] += win_sq[i0:i1]
        del frames, windowed, S_chunk
    nonzero = window_sum > 1e-10
    y[nonzero] /= window_sum[nonzero]
    pad_length = n_fft // 2
    y = y[pad_length:]
    if length is not None:
        y = y[:length]
    return y


def streaming_spectral_process(y, sr, process_fn, n_fft=2048, hop_length=512,
                                chunk_seconds=10, analyze_fn=None):
    n_samples = len(y)
    chunk_samples = int(sr * chunk_seconds)
    overlap_samples = n_fft * 2

    if analyze_fn is not None:
        global_stats = analyze_fn(y, sr)
    else:
        global_stats = None

    output = np.zeros(n_samples, dtype=y.dtype)
    window_sum = np.zeros(n_samples, dtype=y.dtype)

    fade_len = min(hop_length * 8, chunk_samples // 2)
    hop_out = max(1, chunk_samples - fade_len)

    if n_samples <= chunk_samples:
        S = stft(y, n_fft=n_fft, hop_length=hop_length)
        if global_stats is not None:
            S = process_fn(S, sr, n_fft, hop_length, global_stats)
        else:
            S = process_fn(S, sr, n_fft, hop_length)
        return istft(S, hop_length=hop_length, length=n_samples)

    pos = 0
    while pos < n_samples:
        start = max(0, pos - overlap_samples)
        end = min(n_samples, pos + chunk_samples + overlap_samples)
        chunk = y[start:end]

        S = stft(chunk, n_fft=n_fft, hop_length=hop_length)
        if global_stats is not None:
            S = process_fn(S, sr, n_fft, hop_length, global_stats)
        else:
            S = process_fn(S, sr, n_fft, hop_length)

        chunk_out = istft(S, hop_length=hop_length, length=len(chunk))

        out_start = pos - start
        out_end = out_start + min(chunk_samples, n_samples - pos)
        region = chunk_out[out_start:out_end]

        region_len = len(region)
        win = np.ones(region_len, dtype=y.dtype)
        if pos > 0 and fade_len > 0:
            fl = min(fade_len, region_len)
            win[:fl] = np.linspace(0, 1, fl, dtype=y.dtype)
        remaining = n_samples - pos - region_len
        if remaining > 0 and fade_len > 0:
            fl = min(fade_len, region_len)
            win[-fl:] = np.linspace(1, 0, fl, dtype=y.dtype)

        write_start = pos
        write_end = pos + region_len
        if write_end <= n_samples:
            output[write_start:write_end] += region * win
            window_sum[write_start:write_end] += win

        del S, chunk_out, region, win
        pos += hop_out

    valid = window_sum > 1e-10
    output[valid] /= window_sum[valid]
    return output


def fft_frequencies(sr=22050, n_fft=2048):
    return np.fft.rfftfreq(n_fft, 1.0 / sr)


def spectral_flatness(S=None, y=None, n_fft=2048, hop_length=512):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    log_mag = np.log(mag + 1e-10)
    geometric_mean = np.exp(np.mean(log_mag, axis=0))
    arithmetic_mean = np.mean(mag, axis=0) + 1e-10
    flatness = geometric_mean / arithmetic_mean
    return flatness.reshape(1, -1)


def spectral_centroid(y=None, sr=22050, S=None, n_fft=2048, hop_length=512):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    freqs = fft_frequencies(sr=sr, n_fft=2 * (S.shape[0] - 1))
    centroid = np.dot(freqs, mag) / (np.sum(mag, axis=0) + 1e-10)
    return centroid.reshape(1, -1)


def spectral_bandwidth(y=None, sr=22050, S=None, n_fft=2048, hop_length=512, p=2):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    freqs = fft_frequencies(sr=sr, n_fft=2 * (S.shape[0] - 1))
    centroid = np.dot(freqs, mag) / (np.sum(mag, axis=0) + 1e-10)
    deviation = np.sum(mag * np.abs(freqs[:, np.newaxis] - centroid[np.newaxis, :]) ** p, axis=0) / (np.sum(mag, axis=0) + 1e-10)
    bandwidth = deviation ** (1.0 / p)
    return bandwidth.reshape(1, -1)


def spectral_rolloff(y=None, sr=22050, S=None, n_fft=2048, hop_length=512, roll_percent=0.85):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    freqs = fft_frequencies(sr=sr, n_fft=2 * (S.shape[0] - 1))
    total_energy = np.sum(mag, axis=0)
    cumulative_energy = np.cumsum(mag, axis=0)
    threshold = roll_percent * total_energy
    rolloff_idx = np.argmax(cumulative_energy >= threshold[np.newaxis, :], axis=0)
    rolloff = freqs[rolloff_idx]
    silent = total_energy < 1e-10
    rolloff[silent] = np.nan
    return rolloff.reshape(1, -1)


@lru_cache(maxsize=16)
def _mel_frequencies_cached(n_mels, fmin, fmax):
    mel_min = 2595.0 * np.log10(1.0 + fmin / 700.0)
    mel_max = 2595.0 * np.log10(1.0 + fmax / 700.0)
    mels = np.linspace(mel_min, mel_max, n_mels + 2)
    return 700.0 * (10.0 ** (mels / 2595.0) - 1.0)


@lru_cache(maxsize=16)
def _mel_filterbank_cached(sr, n_fft, n_mels=128, fmin=0.0, fmax=None):
    if fmax is None:
        fmax = float(sr / 2.0)
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    mel_f = _mel_frequencies_cached(n_mels, fmin, fmax)
    filterbank = np.zeros((n_mels, len(freqs)))
    freqs_arr = freqs
    for i in range(n_mels):
        lower = mel_f[i]
        center = mel_f[i + 1]
        upper = mel_f[i + 2]
        up_mask = (freqs_arr >= lower) & (freqs_arr <= center) & (center > lower)
        down_mask = (freqs_arr >= center) & (freqs_arr <= upper) & (upper > center)
        filterbank[i, up_mask] = (freqs_arr[up_mask] - lower) / (center - lower)
        filterbank[i, down_mask] = (upper - freqs_arr[down_mask]) / (upper - center)
    return filterbank


def _mel_filterbank(sr, n_fft, n_mels=128, fmin=0.0, fmax=None):
    if fmax is None:
        fmax = float(sr / 2.0)
    return _mel_filterbank_cached(float(sr), int(n_fft), int(n_mels), float(fmin), float(fmax))


def mfcc(y=None, sr=22050, S=None, n_mfcc=20, n_fft=2048, hop_length=512, n_mels=128):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    n_fft_actual = 2 * (S.shape[0] - 1)
    mel_fb = _mel_filterbank(sr, n_fft_actual, n_mels=n_mels)
    mel_spec = np.dot(mel_fb, mag)
    mel_spec = np.maximum(mel_spec, 1e-10)
    log_mel_spec = np.log(mel_spec)
    mfcc_result = _dct(log_mel_spec, axis=0, type=2, norm='ortho')[:n_mfcc]
    return mfcc_result


def delta(data, width=9, order=1):
    if width < 3 or width % 2 == 0:
        width = max(3, width if width % 2 == 1 else width + 1)
    order = max(0, int(order))
    if order == 0:
        return data.copy() if isinstance(data, np.ndarray) else data
    result = np.array(data, dtype=np.float64, copy=True)
    for _ in range(order):
        half_width = width // 2
        kernel = np.arange(-half_width, half_width + 1, dtype=np.float64)
        kernel = kernel / np.sum(np.abs(kernel))
        if result.ndim == 1:
            padded = np.pad(result, half_width, mode='edge')
            result = np.convolve(padded, kernel, mode='valid')[:len(result)]
        else:
            padded = np.pad(result, ((0, 0), (half_width, half_width)), mode='edge')
            new_result = np.zeros_like(result)
            for row in range(result.shape[0]):
                new_result[row] = np.convolve(padded[row], kernel, mode='valid')[:result.shape[1]]
            result = new_result
    return result


def rms(y=None, S=None, n_fft=2048, hop_length=512, frame_length=2048):
    if y is not None:
        if frame_length is None:
            frame_length = n_fft
        if hop_length is None:
            hop_length = frame_length // 4
        frames = _stride_frames(y, frame_length, hop_length)
        if frames.shape[0] == 0:
            return np.zeros((1, 0))
        result = np.sqrt(np.mean(frames ** 2, axis=1))
        return result.reshape(1, -1)
    elif S is not None:
        mag = np.abs(S)
        total_energy = np.sum(mag ** 2, axis=0)
        result = np.sqrt(np.mean(mag ** 2, axis=0))
        silent = total_energy < 1e-20
        result[silent] = np.nan
        return result.reshape(1, -1)
    else:
        raise ValueError("Either y or S must be provided")


def chroma_stft(y=None, sr=22050, S=None, n_fft=2048, hop_length=512, n_chroma=12):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    freqs = fft_frequencies(sr=sr, n_fft=2 * (S.shape[0] - 1))
    valid = freqs > 1e-6
    midi = 12 * np.log2(freqs[valid] / 440.0) + 69
    pitch_class = np.round(midi).astype(int) % 12
    chroma = np.zeros((n_chroma, mag.shape[1]))
    valid_mag = mag[valid]
    for pc in range(n_chroma):
        mask = pitch_class == pc
        if np.any(mask):
            chroma[pc] = np.sum(valid_mag[mask], axis=0)
    chroma_max = np.max(chroma, axis=0, keepdims=True)
    silent = (chroma_max < 1e-10).squeeze(axis=0)
    chroma_max_safe = np.maximum(chroma_max, 1e-10)
    chroma = chroma / chroma_max_safe
    chroma[:, silent] = np.nan
    return chroma


def zero_crossing_rate(y, frame_length=2048, hop_length=512):
    frames = _stride_frames(y, frame_length, hop_length)
    if frames.shape[0] == 0:
        return np.zeros((1, 0))
    signs = np.sign(frames)
    crossings = np.sum(np.abs(np.diff(signs, axis=1)) > 0, axis=1)
    result = crossings / frame_length
    return result.reshape(1, -1)


def onset_strength(y=None, sr=22050, S=None, n_fft=2048, hop_length=512):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    flux = np.maximum(mag[:, 1:] - mag[:, :-1], 0)
    strength = np.sum(flux, axis=0)
    strength = np.insert(strength, 0, 0)
    return strength


def onset_detect(onset_envelope=None, sr=22050, hop_length=512, delta=0.07, wait=10):
    if onset_envelope is None:
        raise ValueError("onset_envelope must be provided")
    if len(onset_envelope) == 0:
        return np.array([], dtype=int)
    onset_env = onset_envelope - np.mean(onset_envelope)
    std = np.std(onset_env)
    if std < 1e-10:
        return np.array([], dtype=int)
    onset_env = onset_env / std
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(onset_env, height=delta, distance=wait)
    return peaks


def beat_track(onset_envelope=None, sr=22050, hop_length=512, start_bpm=120.0):
    if onset_envelope is None:
        raise ValueError("onset_envelope must be provided")
    if len(onset_envelope) < 2:
        return start_bpm, np.array([], dtype=int)
    onset_env = onset_envelope - np.mean(onset_envelope)
    n = len(onset_env)
    n_fft = 1
    while n_fft < 2 * n:
        n_fft *= 2
    fft_env = np.fft.rfft(onset_env, n=n_fft)
    autocorr = np.fft.irfft(fft_env * np.conj(fft_env), n=n_fft)[:n]
    if np.max(autocorr) > 0:
        autocorr = autocorr / np.max(autocorr)
    min_lag = int(60.0 * sr / hop_length / 300.0)
    max_lag = int(60.0 * sr / hop_length / 30.0)
    max_lag = min(max_lag, n - 1)
    if min_lag >= max_lag:
        return start_bpm, np.array([], dtype=int)
    search_range = autocorr[min_lag:max_lag + 1]
    if len(search_range) == 0:
        return start_bpm, np.array([], dtype=int)
    best_lag = np.argmax(search_range) + min_lag
    if best_lag <= 0:
        return start_bpm, np.array([], dtype=int)
    tempo = 60.0 * sr / hop_length / best_lag
    period = best_lag
    onset_peaks = onset_detect(onset_envelope=onset_envelope, sr=sr, hop_length=hop_length)
    if len(onset_peaks) == 0:
        return tempo, np.array([], dtype=int)
    beats = []
    for start_peak in onset_peaks[:3]:
        pos = start_peak
        while pos < n:
            nearest = onset_peaks[np.argmin(np.abs(onset_peaks - pos))]
            if abs(nearest - pos) < period * 0.5:
                beats.append(nearest)
                pos = nearest + period
            else:
                beats.append(pos)
                pos += period
    beats = sorted(set(beats))
    beats = [b for b in beats if b < n]
    return tempo, np.array(beats, dtype=int)


def harmonic(y, margin=1.0):
    if y.ndim > 1:
        result = np.zeros_like(y)
        for ch in range(y.shape[0]):
            result[ch] = harmonic(y[ch], margin=margin)
        return result
    S = stft(y)
    mag = np.abs(S)
    harm_mag = _medfilt(mag, kernel_size=(1, 5))
    perc_mag = mag - harm_mag
    if margin > 1.0:
        mask = harm_mag > margin * perc_mag
    else:
        mask = harm_mag > perc_mag
    S_harm = S * mask
    y_harm = istft(S_harm, length=len(y))
    return y_harm


def hpss(y, margin=1.0):
    if y.ndim > 1:
        h_result = np.zeros_like(y)
        p_result = np.zeros_like(y)
        for ch in range(y.shape[0]):
            h, p = hpss(y[ch], margin=margin)
            h_result[ch] = h
            p_result[ch] = p
        return h_result, p_result
    S = stft(y)
    mag = np.abs(S)
    harm_mag = _medfilt(mag, kernel_size=(1, 5))
    perc_mag = _medfilt(mag, kernel_size=(5, 1))
    harm_mask = harm_mag >= perc_mag
    S_harm = S * harm_mask
    S_perc = S * (~harm_mask)
    y_harm = istft(S_harm, length=len(y))
    y_perc = istft(S_perc, length=len(y))
    return y_harm, y_perc


def pyin(y, fmin=65.0, fmax=2093.0, sr=22050, frame_length=2048, hop_length=None):
    if hop_length is None:
        hop_length = frame_length // 4
    if y.ndim > 1:
        y = y[0] if y.shape[0] == 1 else y.mean(axis=0)
    n_frames = 1 + (len(y) - frame_length) // hop_length
    f0 = np.full(n_frames, np.nan)
    voiced_flag = np.zeros(n_frames, dtype=bool)
    voiced_prob = np.zeros(n_frames, dtype=float)
    min_lag = max(2, int(sr / fmax))
    max_lag = min(frame_length // 2, int(sr / fmin))
    frames = _stride_frames(y, frame_length, hop_length)
    if frames.shape[0] == 0:
        return f0, voiced_flag, voiced_prob
    frames_centered = frames - np.mean(frames, axis=1, keepdims=True)
    rms_vals = np.sqrt(np.mean(frames_centered ** 2, axis=1))
    n_fft = 1
    while n_fft < 2 * frame_length:
        n_fft *= 2
    lags = np.arange(min_lag, max_lag + 1)
    for i in range(n_frames):
        if rms_vals[i] < 1e-6:
            continue
        frame = frames_centered[i]
        energy = np.sum(frame ** 2)
        if energy < 1e-10:
            continue
        fft_frame = np.fft.rfft(frame, n=n_fft)
        corr_full = np.fft.irfft(fft_frame * np.conj(fft_frame), n=n_fft)
        corr = corr_full[:frame_length]
        corr_norm = corr / energy
        valid_corr = corr_norm[lags]
        best_idx = np.argmax(valid_corr)
        best_corr = valid_corr[best_idx]
        best_lag = lags[best_idx]
        if best_corr > 0.3 and best_lag > 0:
            f0[i] = sr / best_lag
            voiced_flag[i] = True
            voiced_prob[i] = min(1.0, best_corr)
    f0 = np.nan_to_num(f0, nan=0.0)
    return f0, voiced_flag, voiced_prob


def note_to_hz(note):
    if isinstance(note, str):
        note_map = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
        if len(note) == 2:
            name = note[0].upper()
            octave = int(note[1])
        elif len(note) == 3 and note[1] == '#':
            name = note[0].upper()
            octave = int(note[2])
            midi = (octave + 1) * 12 + note_map[name] + 1
            return 440.0 * (2.0 ** ((midi - 69) / 12.0))
        elif len(note) == 3 and note[1] == 'b':
            name = note[0].upper()
            octave = int(note[2])
            midi = (octave + 1) * 12 + note_map[name] - 1
            return 440.0 * (2.0 ** ((midi - 69) / 12.0))
        else:
            raise ValueError(f"Invalid note: {note}")
        midi = (octave + 1) * 12 + note_map[name]
        return 440.0 * (2.0 ** ((midi - 69) / 12.0))
    else:
        return 440.0 * (2.0 ** ((note - 69) / 12.0))


def frame(y, frame_length=2048, hop_length=512):
    frames = _stride_frames(y, frame_length, hop_length)
    return frames.T


def mel_frequencies(n_mels=128, fmin=0.0, fmax=11025.0):
    """计算 mel 频率刻度（n_mels+2 个点，与缓存版本一致）"""
    return _mel_frequencies_cached(n_mels, fmin, fmax)


def mel_filterbank(sr, n_fft, n_mels=128, fmin=0.0, fmax=None):
    """构建 mel 滤波器组（与 _mel_filterbank 缓存版本一致）"""
    return _mel_filterbank(sr, n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax)


def mel_spectrogram(y=None, sr=22050, S=None, n_fft=2048, hop_length=512, n_mels=128, fmin=0.0, fmax=None):
    """计算 mel 频谱图"""
    if S is None:
        if y is None:
            raise ValueError("Either y or S must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))

    # 功率谱
    power = S ** 2

    # 构建 mel 滤波器组
    mel_basis = mel_filterbank(sr, n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax)

    # 应用 mel 滤波器
    mel_spec = np.dot(mel_basis, power)

    return mel_spec


def power_to_db(S, ref=1.0, amin=1e-10, top_db=80.0):
    """将功率谱转换为 dB 刻度"""
    S = np.asarray(S)

    # 确保最小值
    S = np.maximum(S, amin)

    # 计算 dB
    db = 10.0 * np.log10(S / ref)

    # 限制动态范围
    if top_db is not None:
        max_db = np.max(db)
        db = np.maximum(db, max_db - top_db)

    return db
