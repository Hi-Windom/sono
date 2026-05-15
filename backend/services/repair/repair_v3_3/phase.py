import numpy as np
from scipy import signal
from .config import HOP_LENGTH, N_FFT
from services.dsp_utils import stft, istft


def _ms_diffuse(y, sr, strength):
    if strength <= 0:
        return y
    if y.ndim == 1:
        return y
    if y.shape[0] < 2:
        return y

    L = y[0].astype(np.float64)
    R = y[1].astype(np.float64)
    M = (L + R) * 0.5
    S = (L - R) * 0.5

    a_m = 0.05 + 0.2 * strength
    a_s = 0.15 + 0.4 * strength

    b_m = np.array([a_m, 1.0])
    a_m_coeff = np.array([1.0, a_m])
    M_processed = signal.lfilter(b_m, a_m_coeff, M)
    M_processed = signal.lfilter(b_m, a_m_coeff, M_processed)

    b_s = np.array([a_s, 1.0])
    a_s_coeff = np.array([1.0, a_s])
    S_processed = signal.lfilter(b_s, a_s_coeff, S)
    S_processed = signal.lfilter(b_s, a_s_coeff, S_processed)

    L_out = M_processed + S_processed
    R_out = M_processed - S_processed

    out = np.stack([L_out, R_out])
    peak = np.max(np.abs(out))
    if peak > 0.99:
        out *= 0.99 / peak

    return out.astype(y.dtype)


def _group_delay_correct(y, sr, strength):
    if strength <= 0:
        return y.copy()

    original_dtype = y.dtype
    if y.ndim == 1:
        y_in = y.astype(np.float64).reshape(1, -1)
    else:
        y_in = y.astype(np.float64)

    n = y_in.shape[1]
    S = stft(y_in, n_fft=N_FFT, hop_length=HOP_LENGTH)
    n_bins = S.shape[-2]
    n_frames = S.shape[-1]
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)

    high_mask = freqs > 8000
    high_indices = np.where(high_mask)[0]

    if len(high_indices) == 0:
        if y.ndim == 1:
            return y_in[0].astype(original_dtype)
        return y_in.astype(original_dtype)

    rng = np.random.RandomState(42)
    if S.ndim == 3:
        for ch in range(S.shape[0]):
            phase_shift = (rng.rand(len(high_indices), n_frames) - 0.5) * 2 * np.pi * strength * 0.03
            S_ch = S[ch]
            mag = np.abs(S_ch)
            phase = np.angle(S_ch)
            phase[high_indices] += phase_shift
            S[ch] = mag * np.exp(1j * phase)
    else:
        phase_shift = (rng.rand(len(high_indices), n_frames) - 0.5) * 2 * np.pi * strength * 0.03
        mag = np.abs(S)
        phase = np.angle(S)
        phase[high_indices] += phase_shift
        S = mag * np.exp(1j * phase)

    y_out = istft(S, hop_length=HOP_LENGTH, length=n)
    if y_out.ndim == 1:
        y_out = y_out.reshape(1, -1)
    if y_out.shape[0] > y_in.shape[0]:
        y_out = y_out[:y_in.shape[0]]
    if y_out.shape[1] < n:
        pad_width = ((0, 0), (0, n - y_out.shape[1]))
        y_out = np.pad(y_out, pad_width)
    elif y_out.shape[1] > n:
        y_out = y_out[:, :n]

    if y.ndim == 1:
        return y_out[0].astype(original_dtype)
    return y_out.astype(original_dtype)


def _phase_naturalize(y, sr, strength):
    if strength <= 0:
        return y.copy()

    original_dtype = y.dtype

    if y.ndim == 1:
        y_stereo = y.astype(np.float64).reshape(1, -1)
    else:
        y_stereo = y.astype(np.float64)

    if y_stereo.shape[0] >= 2:
        y_stereo = _ms_diffuse(y_stereo, sr, strength * 0.5)

    a = 0.05 + 0.2 * strength
    b_allpass = np.array([a, 1.0])
    a_allpass = np.array([1.0, a])

    if y_stereo.ndim == 1:
        y_out = signal.lfilter(b_allpass, a_allpass, y_stereo)
        y_out = signal.lfilter(b_allpass, a_allpass, y_out)
    else:
        y_out = np.zeros_like(y_stereo)
        for ch in range(y_stereo.shape[0]):
            y_out[ch] = signal.lfilter(b_allpass, a_allpass, y_stereo[ch])
            y_out[ch] = signal.lfilter(b_allpass, a_allpass, y_out[ch])

    y_out = _group_delay_correct(y_out, sr, strength * 0.3)

    if y.ndim == 1:
        return y_out[0].astype(original_dtype)
    return y_out.astype(original_dtype)