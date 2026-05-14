import importlib
import sys
from pathlib import Path

import pytest

REQUIREMENTS_FILE = Path(__file__).resolve().parent.parent / "requirements_android.txt"

OPTIONAL_PACKAGES = {
    "noisereduce",
    "pedalboard",
    "lameenc",
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


def test_psutil_available():
    import psutil
    mem = psutil.virtual_memory()
    assert mem.total > 0


def test_lame_cli_available():
    import shutil
    lame_path = shutil.which("lame")
    assert lame_path is not None, "lame CLI not found in PATH"
    import subprocess
    result = subprocess.run([lame_path, "--version"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "LAME" in result.stdout