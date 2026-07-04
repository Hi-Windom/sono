import subprocess
import numpy as np
import soundfile as sf

# Decode MP3 to PCM using miniaudio
result = subprocess.run([
    'python3', '-c', '''
import miniaudio
y, sr = miniaudio.load_wav("/workspace/backend/storage/training/4f51ca5161ac4f09_新项目 (1).mp3")
print(f"SR: {sr}")
print(f"Shape: {y.shape}")
print(f"Sample width: {y.itemsize}")
'''
], capture_output=True, text=True, timeout=30)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
