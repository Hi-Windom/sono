import numpy as np
from services.dsp_utils import stft, istft


def time_stretch_hifi(y, sr, speed, n_fft=4096, hop_length=512):
    if speed <= 0 or abs(speed - 1.0) < 0.001:
        return y
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True
    else:
        was_mono = False
    result = []
    for ch in range(y.shape[0]):
        stretched = _phase_vocoder_stretch(y[ch], speed, n_fft, hop_length)
        result.append(stretched)
    out = np.stack(result, axis=0)
    return out[0] if was_mono else out


def _phase_vocoder_stretch(y, speed, n_fft, hop_length):
    S = stft(y, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(S)
    phase = np.angle(S)
    n_frames_in = S.shape[1]
    n_frames_out = max(1, int(n_frames_in / speed))
    phase_accum = phase[:, 0].copy()
    dphase = np.diff(np.unwrap(phase, axis=1), axis=1)
    S_out = np.zeros((S.shape[0], n_frames_out), dtype=np.complex128)
    S_out[:, 0] = S[:, 0]
    for i in range(1, n_frames_out):
        src_idx = min(int(i * speed), n_frames_in - 1)
        frac = (i * speed) - src_idx
        if src_idx < n_frames_in - 1:
            mag_interp = (1 - frac) * mag[:, src_idx] + frac * mag[:, src_idx + 1]
        else:
            mag_interp = mag[:, src_idx]
        if src_idx > 0 and src_idx <= dphase.shape[1]:
            phase_accum += dphase[:, src_idx - 1]
        S_out[:, i] = mag_interp * np.exp(1j * phase_accum)
    expected_len = int(len(y) / speed)
    y_out = istft(S_out, hop_length=hop_length, length=expected_len)
    return y_out