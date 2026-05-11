import sys
import os
import tempfile
import numpy as np
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False
    from scipy.io import wavfile


SR = 44100
DURATION = 2.0


def generate_pure_sine(sr=SR, freq=440.0, duration=DURATION, amplitude=0.7):
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


def generate_multi_tone(sr=SR, duration=DURATION):
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    return 0.3 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 1000 * t) + 0.15 * np.sin(2 * np.pi * 3000 * t)


def generate_speech_like(sr=SR, duration=DURATION):
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    carrier = 0.5 * np.sin(2 * np.pi * 200 * t) + 0.3 * np.sin(2 * np.pi * 600 * t)
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 3 * t)) * 0.5
    envelope *= 0.5 * (1 + np.sin(2 * np.pi * 0.7 * t)) * 0.5
    return carrier * envelope


def generate_with_pops(sr=SR, duration=DURATION):
    y = generate_speech_like(sr, duration)
    pop_positions = [int(0.5 * sr), int(1.2 * sr), int(1.7 * sr)]
    for pos in pop_positions:
        if pos < len(y):
            y[pos] = 0.95
            if pos + 1 < len(y):
                y[pos + 1] = -0.85
    return y


def generate_with_clipping(sr=SR, duration=DURATION):
    y = generate_multi_tone(sr, duration) * 2.0
    return np.clip(y, -0.85, 0.85)


def generate_ai_artifact_signal(sr=SR, duration=DURATION):
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    y = 0.3 * np.sin(2 * np.pi * 200 * t) + 0.2 * np.sin(2 * np.pi * 600 * t)
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 3 * t)) * 0.5
    y *= envelope
    from services.dsp_utils import stft, istft
    n_fft = 2048
    hop_length = 512
    S = stft(y, n_fft=n_fft, hop_length=hop_length)
    freqs = np.arange(S.shape[0]) * sr / n_fft
    presence_mask = (freqs >= 2000) & (freqs <= 5000)
    S[presence_mask, :] *= 3.0
    chirp_bins = (freqs >= 6000) & (freqs <= 10000)
    for j in range(S.shape[1]):
        chirp_phase = 2 * np.pi * 50 * j / sr
        S[chirp_bins, j] *= (1 + 0.5 * np.sin(chirp_phase))
    y_out = istft(S, hop_length=hop_length, length=len(y))
    if len(y_out) < len(y):
        y_out = np.pad(y_out, (0, len(y) - len(y_out)))
    return y_out[:len(y)]


def write_temp_wav(y, sr, tmp_path):
    if y.ndim == 1:
        y_out = y
    else:
        y_out = y.T

    filepath = str(tmp_path / "test_input.wav")
    if HAS_SOUNDFILE:
        sf.write(filepath, y_out, sr, subtype="PCM_24")
    else:
        y_int = np.clip(y_out * 32767, -32768, 32767).astype(np.int16)
        wavfile.write(filepath, sr, y_int)
    return filepath


def compute_thd(signal, sr, fundamental_freq, n_harmonics=5):
    n = len(signal)
    window = np.hanning(n)
    windowed = signal * window
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    bin_width = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0

    fundamental_power = 0.0
    harmonic_power = 0.0

    for h in range(1, n_harmonics + 1):
        target_freq = fundamental_freq * h
        if target_freq >= sr / 2:
            break
        idx = np.argmin(np.abs(freqs - target_freq))
        search_range = max(1, int(5 * bin_width / (freqs[1] - freqs[0] + 1e-10)))
        start = max(0, idx - search_range)
        end = min(len(spectrum), idx + search_range + 1)
        peak_power = np.max(spectrum[start:end]) ** 2

        if h == 1:
            fundamental_power = peak_power
        else:
            harmonic_power += peak_power

    if fundamental_power < 1e-20:
        return -100.0

    thd_db = 10 * np.log10(harmonic_power / fundamental_power + 1e-20)
    return thd_db


def compute_scale_adjusted_snr(original, processed):
    orig = original.astype(np.float64).flatten()
    proc = processed.astype(np.float64).flatten()

    min_len = min(len(orig), len(proc))
    orig = orig[:min_len]
    proc = proc[:min_len]

    orig_rms = np.sqrt(np.mean(orig ** 2))
    if orig_rms < 1e-10:
        return 100.0

    scale = np.dot(proc, orig) / (np.dot(orig, orig) + 1e-20)
    scaled_orig = orig * scale
    noise = proc - scaled_orig
    noise_rms = np.sqrt(np.mean(noise ** 2))

    if noise_rms < 1e-10:
        return 100.0

    snr = 20 * np.log10(orig_rms / noise_rms)
    return snr


def compute_hf_noise(signal, sr, low_hz=5000, high_hz=16000):
    from scipy.signal import butter, sosfilt

    y = signal.astype(np.float64).flatten()
    nyq = sr / 2
    if high_hz >= nyq:
        high_hz = nyq * 0.95
    low_norm = low_hz / nyq
    high_norm = high_hz / nyq

    if low_norm >= 1.0 or high_norm >= 1.0 or low_norm >= high_norm:
        return 0.0

    sos = butter(4, [low_norm, high_norm], btype="band", output="sos")
    filtered = sosfilt(sos, y)
    return np.sqrt(np.mean(filtered ** 2))


def count_flat_top_samples(signal, threshold=1e-8):
    y = signal.astype(np.float64).flatten()
    if len(y) < 2:
        return 0
    diffs = np.abs(np.diff(y))
    flat = diffs < threshold
    return int(np.sum(flat))


def compute_per_step_snr(input_signal, step_fn, *args):
    inp = input_signal.astype(np.float64)
    out = step_fn(inp, *args)
    if out is None:
        return -100.0
    out = out.astype(np.float64)
    return compute_scale_adjusted_snr(inp, out)


def benchmark_step(step_fn, *args, repeat=3):
    import time
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        step_fn(*args)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    return min(times)


ACTIVE_VERSIONS = ["v2.0", "v2.1", "v2.2", "v2.2a", "v2.3", "v2.3a", "v2.4", "v2.4a"]


@pytest.fixture(params=ACTIVE_VERSIONS)
def repair_version(request):
    return request.param


@pytest.fixture
def repair_fn(repair_version):
    import unittest.mock as mock

    with mock.patch.dict(os.environ, {"MOBILE_MODE": "0"}):
        with mock.patch("config.MOBILE_MODE", False):
            if repair_version == "v2.0":
                from services.repair.repair_v2_0 import repair_audio as fn
            elif repair_version == "v2.1":
                from services.repair.repair_v2_1 import repair_audio as fn
            elif repair_version == "v2.2":
                from services.repair.repair_v2_2 import repair_audio as fn
            elif repair_version == "v2.2a":
                from services.repair.repair_v2_2a import repair_audio as fn
            elif repair_version == "v2.3":
                from services.repair.repair_v2_3 import repair_audio as fn
            elif repair_version == "v2.3a":
                from services.repair.repair_v2_3a import repair_audio as fn
            elif repair_version == "v2.4":
                from services.repair.repair_v2_4 import repair_audio as fn
            elif repair_version == "v2.4a":
                from services.repair.repair_v2_4a import repair_audio as fn
            else:
                pytest.skip(f"Unknown version: {repair_version}")
            yield fn


@pytest.fixture
def default_params(repair_version):
    from services.audio_repair import ALGORITHM_VERSIONS
    return dict(ALGORITHM_VERSIONS[repair_version]["default_params"])


@pytest.fixture
def tmp_wav_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def pure_sine():
    return generate_pure_sine()


@pytest.fixture
def multi_tone():
    return generate_multi_tone()


@pytest.fixture
def speech_like():
    return generate_speech_like()


@pytest.fixture
def signal_with_pops():
    return generate_with_pops()


@pytest.fixture
def signal_with_clipping():
    return generate_with_clipping()


@pytest.fixture
def ai_artifact_signal():
    return generate_ai_artifact_signal()
