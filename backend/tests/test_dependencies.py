import importlib
import sys
from pathlib import Path

import pytest

REQUIREMENTS_FILE = Path(__file__).resolve().parent.parent / "requirements_android.txt"

OPTIONAL_PACKAGES = {
    "noisereduce",
    "pedalboard",
}

EXTRA_VALIDATIONS = {
    "lameenc": lambda mod: hasattr(mod, "Encoder"),
    "soundfile": lambda mod: hasattr(mod, "read") and callable(mod.read),
}


def _parse_requirements(path: Path):
    packages = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pkg = line.split(">=")[0].split("<")[0].split("==")[0].strip()
            import_name = pkg.replace("-", "_").split("[")[0]
            packages.append(import_name)
    return packages


def test_android_requirements_all_importable():
    required = _parse_requirements(REQUIREMENTS_FILE)
    assert required, f"Failed to parse requirements from {REQUIREMENTS_FILE}"

    failures = []
    for pkg in required:
        is_optional = pkg in OPTIONAL_PACKAGES
        try:
            mod = importlib.import_module(pkg)
            if pkg in EXTRA_VALIDATIONS:
                assert EXTRA_VALIDATIONS[pkg](mod), f"{pkg} extra validation failed"
        except (ImportError, AssertionError, Exception) as e:
            if is_optional:
                continue
            failures.append(f"{pkg}: {e}")

    if failures:
        pytest.fail(f"Missing required dependencies:\n" + "\n".join(failures))


def test_lameenc_encoder_usable():
    lameenc = importlib.import_module("lameenc")
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(44100)
    encoder.set_channels(1)
    encoder.set_quality(2)


def test_soundfile_read_write():
    import numpy as np
    import soundfile as sf
    import tempfile

    data = np.zeros(100, dtype=np.float32)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        sf.write(tmp.name, data, 44100)
        read_data, read_sr = sf.read(tmp.name)
        assert read_sr == 44100
        assert len(read_data) == 100
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def test_miniaudio_load():
    import miniaudio


def _aligned_corr(ref, dec, max_lag=3000):
    import numpy as np
    n = min(len(ref), len(dec))
    ref_seg = ref[:n]
    dec_seg = dec[:n]
    corr_full = np.correlate(ref_seg, dec_seg, mode='full')
    best_idx = np.argmax(np.abs(corr_full))
    best_lag = best_idx - (n - 1)
    if abs(best_lag) > max_lag:
        return 0.0
    if best_lag >= 0:
        a = ref_seg[best_lag:]
        b = dec_seg[:len(a)]
    else:
        b = dec_seg[-best_lag:]
        a = ref_seg[:len(b)]
    if len(a) < 100:
        return 0.0
    return abs(np.corrcoef(a, b)[0, 1])


def _mp3_roundtrip_corr(original, sr, channels_label):
    import tempfile, soundfile as sf, numpy as np
    from services.mp3_encoder import encode_mp3
    import scipy.io.wavfile as wavfile
    import subprocess

    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    try:
        sf.write(wav.name, original, sr, subtype="PCM_16")
        encode_mp3(wav.name, mp3.name, bitrate=128)
        with open(mp3.name, "rb") as f:
            raw = f.read()
        assert len(raw) > 0, "MP3 output is empty"
        has_sync = any(raw[i] == 0xff and (raw[i+1] & 0xe0) == 0xe0 for i in range(min(200, len(raw)-1)))
        assert has_sync, "No MPEG frame sync found in output"

        subprocess.run(["lame", "--decode", mp3.name, wav.name + "_decoded.wav"], capture_output=True)
        sr_dec, data_dec = wavfile.read(wav.name + "_decoded.wav")
        data_dec_float = data_dec.astype(np.float64) / 32768.0

        if original.ndim == 1:
            return _aligned_corr(original, data_dec_float)
        else:
            corrs = []
            for ch in range(original.shape[1]):
                ref_ch = original[:, ch]
                dec_ch = data_dec_float[:, ch] if data_dec_float.ndim > 1 else data_dec_float
                corrs.append(_aligned_corr(ref_ch, dec_ch))
            return min(corrs)
    finally:
        import os
        os.unlink(wav.name)
        os.unlink(mp3.name)
        decoded_path = wav.name + "_decoded.wav"
        if os.path.exists(decoded_path):
            os.unlink(decoded_path)


def test_libmp3lame_available():
    from services.mp3_encoder import is_available, get_version
    assert is_available(), "libmp3lame not available via ctypes"
    version = get_version()
    assert isinstance(version, str) and len(version) > 0
    import numpy as np
    sr = 44100
    t = np.linspace(0, 1.0, int(sr * 1.0), endpoint=False)

    mono = np.sin(2 * np.pi * 440 * t) * 0.3
    corr_mono = _mp3_roundtrip_corr(mono, sr, "mono")
    assert corr_mono > 0.95, f"Mono MP3 quality too low: |corr|={corr_mono:.4f}"

    left = np.sin(2 * np.pi * 440 * t) * 0.3
    right = np.sin(2 * np.pi * 880 * t) * 0.3
    stereo = np.column_stack([left, right])
    corr_stereo = _mp3_roundtrip_corr(stereo, sr, "stereo")
    assert corr_stereo > 0.90, f"Stereo MP3 quality too low: |corr|={corr_stereo:.4f}"