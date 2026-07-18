import sys
import os
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.dsp_utils import stft, istft, delta
from services.repair.repair_v3_2.core import _vocal_ai_repair_adaptive


def benchmark_stft(signal_len=48000 * 60, n_fft=2048, hop_length=512, runs=5):
    print(f"\n=== STFT/ISTFT 性能测试 ({signal_len/48000:.1f}s 音频) ===")
    y = np.random.randn(signal_len).astype(np.float64)

    times_stft = []
    times_istft = []

    for i in range(runs):
        t0 = time.perf_counter()
        D = stft(y, n_fft=n_fft, hop_length=hop_length)
        t1 = time.perf_counter()
        times_stft.append(t1 - t0)

        t2 = time.perf_counter()
        y_recon = istft(D, hop_length=hop_length, length=signal_len)
        t3 = time.perf_counter()
        times_istft.append(t3 - t2)

    avg_stft = sum(times_stft) / len(times_stft)
    avg_istft = sum(times_istft) / len(times_istft)
    duration_s = signal_len / 48000

    print(f"  STFT 平均耗时: {avg_stft*1000:.2f}ms (xRTF: {duration_s/avg_stft:.2f}x)")
    print(f"  ISTFT 平均耗时: {avg_istft*1000:.2f}ms (xRTF: {duration_s/avg_istft:.2f}x)")
    print(f"  总耗时: {(avg_stft+avg_istft)*1000:.2f}ms")

    return avg_stft + avg_istft


def benchmark_delta(signal_len=48000 * 10, runs=20):
    print(f"\n=== Delta 特征性能测试 ({signal_len/48000:.1f}s 音频) ===")
    data = np.random.randn(20, signal_len // 100).astype(np.float64)

    times = []
    for i in range(runs):
        t0 = time.perf_counter()
        d = delta(data)
        t1 = time.perf_counter()
        times.append(t1 - t0)

    avg = sum(times) / len(times)
    print(f"  Delta 平均耗时: {avg*1000:.3f}ms")
    return avg


def benchmark_vocal_ai_repair(duration_s=30, runs=3):
    print(f"\n=== Vocal AI Repair 性能测试 ({duration_s}s 音频) ===")
    sr = 48000
    n_samples = int(sr * duration_s)
    y = np.random.randn(n_samples).astype(np.float64) * 0.1

    times = []
    for i in range(runs):
        t0 = time.perf_counter()
        result = _vocal_ai_repair_adaptive(y, sr, strength=1.0)
        t1 = time.perf_counter()
        times.append(t1 - t0)
        print(f"  第 {i+1} 次: {(t1-t0)*1000:.2f}ms")

    avg = sum(times) / len(times)
    xrtf = duration_s / avg
    print(f"  平均耗时: {avg*1000:.2f}ms")
    print(f"  实时倍率 (xRTF): {xrtf:.2f}x")
    return avg


def benchmark_memory(duration_s=60):
    print(f"\n=== 内存使用测试 ({duration_s}s 音频) ===")
    sr = 48000
    n_samples = int(sr * duration_s)

    y64 = np.random.randn(n_samples).astype(np.float64)
    y32 = y64.astype(np.float32)

    mem_64 = y64.nbytes / (1024 * 1024)
    mem_32 = y32.nbytes / (1024 * 1024)

    print(f"  float64 内存: {mem_64:.2f} MB")
    print(f"  float32 内存: {mem_32:.2f} MB")
    print(f"  节省比例: {(1 - mem_32/mem_64)*100:.1f}%")

    t0 = time.perf_counter()
    D64 = stft(y64, n_fft=2048, hop_length=512)
    t1 = time.perf_counter()
    D32 = stft(y32, n_fft=2048, hop_length=512)
    t2 = time.perf_counter()

    mem_D64 = D64.nbytes / (1024 * 1024)
    mem_D32 = D32.nbytes / (1024 * 1024)

    print(f"\n  STFT float64: {mem_D64:.2f} MB, 耗时: {(t1-t0)*1000:.2f}ms")
    print(f"  STFT float32: {mem_D32:.2f} MB, 耗时: {(t2-t1)*1000:.2f}ms")
    print(f"  STFT 内存节省: {(1 - mem_D32/mem_D64)*100:.1f}%")
    print(f"  STFT 速度提升: {(t1-t0)/(t2-t1)*100:.1f}%")


def main():
    print("=" * 60)
    print("DSP 性能基准测试")
    print("=" * 60)

    try:
        benchmark_stft(signal_len=48000 * 30, runs=5)
    except Exception as e:
        print(f"  STFT 测试失败: {e}")

    try:
        benchmark_delta(runs=20)
    except Exception as e:
        print(f"  Delta 测试失败: {e}")

    try:
        benchmark_memory(duration_s=60)
    except Exception as e:
        print(f"  内存测试失败: {e}")

    try:
        benchmark_vocal_ai_repair(duration_s=10, runs=3)
    except Exception as e:
        print(f"  Vocal AI Repair 测试失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
