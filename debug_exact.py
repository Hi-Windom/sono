#!/usr/bin/env python3
import sys
import numpy as np
import tempfile
from pathlib import Path
import soundfile as sf

sys.path.insert(0, '/workspace/backend')

from tests.conftest import generate_speech_like, SR, compute_hf_noise
from services.repair.repair_v3_0 import repair_audio
from services.audio_repair import ALGORITHM_VERSIONS


def main():
    print("=== Debugging exact test scenario ===\n")
    
    y = generate_speech_like(sr=SR, duration=2.0)
    input_hf = compute_hf_noise(y, SR, 5000, 16000)
    print(f"Input HF: {input_hf:.2e}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = str(Path(tmpdir) / "input.wav")
        output_path = str(Path(tmpdir) / "output.wav")
        sf.write(input_path, y, SR)
        
        params = dict(ALGORITHM_VERSIONS["v3.0"]["default_params"])
        print("Running repair...")
        repair_audio(input_path, output_path, params)
        print("Done!")
        
        y_out, sr_out = sf.read(output_path)
        output_hf = compute_hf_noise(y_out, sr_out, 5000, 16000)
        if input_hf > 1e-10:
            ratio = output_hf / input_hf
        else:
            ratio = output_hf / 1e-10
        
        print(f"Output HF: {output_hf:.2e}")
        print(f"Ratio: {ratio:.1f}x")
        print(f"Output SR: {sr_out}")


if __name__ == "__main__":
    main()
