import numpy as np
from scipy.signal import get_window, medfilt
from scipy.fftpack import dct


def stft(y, n_fft=2048, hop_length=512, window='hann'):
    fft_window = get_window(window, n_fft, fftbins=True)
    pad_length = n_fft // 2
    y_padded = np.pad(y, (pad_length, pad_length), mode='reflect')
    n_frames = 1 + (len(y_padded) - n_fft) // hop_length
    S = np.empty((1 + n_fft // 2, n_frames), dtype=np.complex128)
    for i in range(n_frames):
        frame = y_padded[i * hop_length:i * hop_length + n_fft]
        S[:, i] = np.fft.rfft(frame * fft_window)
    return S


def istft(S, hop_length=512, length=None, window='hann'):
    n_fft = 2 * (S.shape[0] - 1)
    fft_window = get_window(window, n_fft, fftbins=True)
    expected_signal_len = n_fft + hop_length * (S.shape[1] - 1)
    y = np.zeros(expected_signal_len)
    window_sum = np.zeros(expected_signal_len)
    for i in range(S.shape[1]):
        frame = np.fft.irfft(S[:, i], n=n_fft)
        start = i * hop_length
        y[start:start + n_fft] += frame * fft_window
        window_sum[start:start + n_fft] += fft_window ** 2
    nonzero = window_sum > 1e-10
    y[nonzero] /= window_sum[nonzero]
    pad_length = n_fft // 2
    y = y[pad_length:]
    if length is not None:
        y = y[:length]
    return y


def fft_frequencies(sr=22050, n_fft=2048):
    return np.fft.rfftfreq(n_fft, 1.0 / sr)


def spectral_flatness(S=None, y=None, n_fft=2048, hop_length=512):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    geometric_mean = np.exp(np.mean(np.log(mag + 1e-10), axis=0))
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
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)
    return centroid.reshape(1, -1)


def spectral_bandwidth(y=None, sr=22050, S=None, n_fft=2048, hop_length=512, p=2):
    if S is None:
        if y is None:
            raise ValueError("Either S or y must be provided")
        S = np.abs(stft(y, n_fft=n_fft, hop_length=hop_length))
    mag = np.abs(S)
    freqs = fft_frequencies(sr=sr, n_fft=2 * (S.shape[0] - 1))
    centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-10)
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
    return rolloff.reshape(1, -1)


def _mel_frequencies(n_mels, fmin, fmax):
    def hz_to_mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel_to_hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    mel_min = hz_to_mel(fmin)
    mel_max = hz_to_mel(fmax)
    mels = np.linspace(mel_min, mel_max, n_mels + 2)
    return mel_to_hz(mels)


def _mel_filterbank(sr, n_fft, n_mels=128, fmin=0.0, fmax=None):
    if fmax is None:
        fmax = sr / 2.0
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)
    mel_f = _mel_frequencies(n_mels, fmin, fmax)
    filterbank = np.zeros((n_mels, len(freqs)))
    for i in range(n_mels):
        lower = mel_f[i]
        center = mel_f[i + 1]
        upper = mel_f[i + 2]
        for j, f in enumerate(freqs):
            if lower <= f <= center and center > lower:
                filterbank[i, j] = (f - lower) / (center - lower)
            elif center <= f <= upper and upper > center:
                filterbank[i, j] = (upper - f) / (upper - center)
    return filterbank


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
    mfcc_result = dct(log_mel_spec, axis=0, type=2, norm='ortho')[:n_mels]
    return mfcc_result


def delta(data, width=9, order=1):
    if width < 3 or width % 2 == 0:
        width = max(3, width if width % 2 == 1 else width + 1)
    half_width = width // 2
    result = np.zeros_like(data)
    if data.ndim == 1:
        padded = np.pad(data, half_width, mode='edge')
        for i in range(len(data)):
            window = padded[i:i + width]
            result[i] = np.mean(np.diff(window))
    else:
        for row in range(data.shape[0]):
            padded = np.pad(data[row], half_width, mode='edge')
            for i in range(data.shape[1]):
                window = padded[i:i + width]
                result[row, i] = np.mean(np.diff(window))
    if order > 1:
        return delta(result, width=width, order=order - 1)
    return result


def rms(y=None, S=None, n_fft=2048, hop_length=512, frame_length=2048):
    if y is not None:
        if frame_length is None:
            frame_length = n_fft
        if hop_length is None:
            hop_length = frame_length // 4
        n_frames = 1 + (len(y) - frame_length) // hop_length
        result = np.zeros(n_frames)
        for i in range(n_frames):
            frame = y[i * hop_length:i * hop_length + frame_length]
            result[i] = np.sqrt(np.mean(frame ** 2))
        return result.reshape(1, -1)
    elif S is not None:
        mag = np.abs(S)
        result = np.sqrt(np.mean(mag ** 2, axis=0))
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
    chroma = np.zeros((n_chroma, mag.shape[1]))
    for i, f in enumerate(freqs):
        if f < 1e-6:
            continue
        midi = 12 * np.log2(f / 440.0) + 69
        pitch_class = int(round(midi)) % 12
        chroma[pitch_class] += mag[i]
    chroma_max = np.max(chroma, axis=0, keepdims=True) + 1e-10
    chroma = chroma / chroma_max
    return chroma


def zero_crossing_rate(y, frame_length=2048, hop_length=512):
    n_frames = 1 + (len(y) - frame_length) // hop_length
    result = np.zeros(n_frames)
    for i in range(n_frames):
        frame = y[i * hop_length:i * hop_length + frame_length]
        signs = np.sign(frame)
        crossings = np.sum(np.abs(np.diff(signs)) > 0)
        result[i] = crossings / len(frame)
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
    threshold = delta
    peaks = []
    for i in range(1, len(onset_env) - 1):
        if onset_env[i] > threshold and onset_env[i] > onset_env[i - 1] and onset_env[i] >= onset_env[i + 1]:
            if len(peaks) == 0 or i - peaks[-1] >= wait:
                peaks.append(i)
    return np.array(peaks, dtype=int)


def beat_track(onset_envelope=None, sr=22050, hop_length=512, start_bpm=120.0):
    if onset_envelope is None:
        raise ValueError("onset_envelope must be provided")
    if len(onset_envelope) < 2:
        return start_bpm, np.array([], dtype=int)
    onset_env = onset_envelope - np.mean(onset_envelope)
    n = len(onset_env)
    autocorr = np.correlate(onset_env, onset_env, mode='full')
    autocorr = autocorr[n - 1:]
    min_lag = int(60.0 * sr / hop_length / 300.0)
    max_lag = int(60.0 * sr / hop_length / 30.0)
    max_lag = min(max_lag, n - 1)
    if min_lag >= max_lag:
        return start_bpm, np.array([], dtype=int)
    search_range = autocorr[min_lag:max_lag + 1]
    if len(search_range) == 0:
        return start_bpm, np.array([], dtype=int)
    best_lag = np.argmax(search_range) + min_lag
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
    harm_mag = medfilt(mag, kernel_size=(1, 5))
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
    harm_mag = medfilt(mag, kernel_size=(1, 5))
    perc_mag = medfilt(mag, kernel_size=(5, 1))
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
    for i in range(n_frames):
        frame = y[i * hop_length:i * hop_length + frame_length]
        frame = frame - np.mean(frame)
        rms_val = np.sqrt(np.mean(frame ** 2))
        if rms_val < 1e-6:
            continue
        best_lag = 0
        best_corr = 0
        corr = np.correlate(frame, frame, mode='full')
        corr = corr[len(frame) - 1:]
        energy = np.sum(frame ** 2)
        if energy < 1e-10:
            continue
        for lag in range(min_lag, max_lag + 1):
            if lag >= len(corr):
                break
            c = corr[lag] / energy
            if c > best_corr:
                best_corr = c
                best_lag = lag
        if best_corr > 0.3 and best_lag > 0:
            f0[i] = sr / best_lag
            voiced_flag[i] = True
            voiced_prob[i] = min(1.0, best_corr)
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
    n_frames = 1 + (len(y) - frame_length) // hop_length
    if n_frames <= 0:
        return np.empty((frame_length, 0))
    result = np.empty((frame_length, n_frames))
    for i in range(n_frames):
        result[:, i] = y[i * hop_length:i * hop_length + frame_length]
    return result
