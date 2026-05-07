# 消除 librosa 依赖计划

## 问题分析

当前 Android/Termux 部署中 librosa 的依赖链存在严重问题：

1. **librosa 依赖 scikit-learn** → Termux 无法编译 scikit-learn，必须用 `--no-deps` 强制安装
2. **librosa 依赖 soxr** → 需要创建 stub 模块用 scipy.signal.resample_poly 替代
3. **librosa 依赖 numba** → 需要创建 stub 模块让 JIT 装饰器变成空操作
4. **noisereduce 依赖 scikit-learn** → 无法安装，降噪只能用降级算法
5. **pedalboard 需要 C++ 扩展** → 无法安装，v1.1/v1.2 只能用 scipy 降级算法

这些 stub 和 `--no-deps` hack 让部署脆弱且不可靠。

## Termux 可用性确认

**scipy 和 numpy 在 Termux 上完全可用**：
- 通过 `pkg install python-numpy python-scipy` 预编译安装
- setup_android.sh 已有此步骤，部署日志确认 `scipy 1.17.1 OK`
- dsp_utils.py 只依赖 `numpy.fft.rfft/irfft` + `scipy.signal.get_window/medfilt` + `scipy.fftpack.dct`，全部可用

## 用户决策

1. **audio_loader.py 兜底**：直接移除 librosa 兜底，只用 miniaudio
2. **training/feature_extractor.py**：保留 librosa（仅桌面端训练使用）
3. **兼容层**：创建 `services/librosa_compat.py` 封装层，内部固定用 dsp_utils 实现，完全不依赖 librosa

## librosa 使用情况分类

### A类：STFT/ISTFT（7个文件）
| 文件 | 调用 |
|------|------|
| repair_v2_0/spectral_group_a.py | `librosa.stft()`, `librosa.istft()`, `librosa.fft_frequencies()` |
| repair_v2_0/spectral_group_b.py | `librosa.stft()`, `librosa.istft()`, `librosa.fft_frequencies()` |
| repair_v2_1/spectral_group_a.py | `librosa.stft()`, `librosa.istft()`, `librosa.fft_frequencies()` |
| repair_v2_1/spectral_group_b.py | `librosa.stft()`, `librosa.istft()`, `librosa.fft_frequencies()` |
| audio_repair_v1_0.py | `librosa.stft()`, `librosa.istft()`, `librosa.fft_frequencies()` |
| audio_repair_v1_1.py | `librosa.stft()`, `librosa.istft()`, `librosa.fft_frequencies()` |
| audio_repair_v1_2.py | `librosa.stft()`, `librosa.istft()`, `librosa.fft_frequencies()` |

### B类：高级特征提取（3个检测器文件）
| 文件 | 调用 |
|------|------|
| detectors/ai_detector_v1_0.py | `spectral_flatness`, `spectral_centroid`, `mfcc`, `delta`, `rms`, `pyin`, `onset_strength`, `beat_track`, `spectral_rolloff`, `effects.harmonic`, `util.frame` |
| detectors/ai_detector_v1_1.py | 同上 + `spectral_bandwidth`, `chroma_stft`, `zero_crossing_rate`, `onset_detect`, `effects.hpss` |
| detectors/ai_detector_v1_2.py | 同 v1_1 |

### C类：仅 import（3个文件）
| 文件 | 说明 |
|------|------|
| repair_v2_0/core.py | `import librosa` 但实际不直接使用 |
| repair_v2_1/core.py | `import librosa` 但实际不直接使用 |
| main.py | `import librosa` 仅用于 check_dependencies() |

### D类：保留 librosa（1个文件）
| 文件 | 说明 |
|------|------|
| training/feature_extractor.py | 仅桌面端训练使用，保留 librosa |

## 架构设计

```
services/
├── dsp_utils.py          # 底层 DSP 实现（stft, istft, 特征提取等）
├── librosa_compat.py     # 兼容层封装，统一 import 入口
└── audio_loader.py       # 音频加载（只用 miniaudio）
```

### `dsp_utils.py` - 底层实现

纯 numpy + scipy 实现，零 librosa 依赖：

| 函数 | 实现方式 |
|------|---------|
| `stft(y, n_fft, hop_length, window)` | 手写：np.pad + np.fft.rfft + 窗函数，与 librosa 行为一致 |
| `istft(S, hop_length, length, window)` | 手写：重叠相加 + 窗归一化，与 librosa 行为一致 |
| `fft_frequencies(sr, n_fft)` | `np.fft.rfftfreq(n_fft, 1/sr)` |
| `spectral_flatness(S)` | 几何均值/算术均值 |
| `spectral_centroid(y, sr, S)` | `np.sum(freqs * mag) / np.sum(mag)` |
| `spectral_bandwidth(y, sr, S)` | 频谱质心扩展 |
| `spectral_rolloff(y, sr, S)` | 累积能量阈值 |
| `mfcc(y, sr, S, n_mfcc)` | mel 滤波器组 + scipy.fftpack.dct |
| `delta(data)` | 中心差分 |
| `rms(y)` | 滑窗 RMS |
| `chroma_stft(y, sr, S)` | 色度映射 |
| `zero_crossing_rate(y)` | `np.diff(np.sign(y))` |
| `onset_strength(y, sr)` | 频谱通量 |
| `onset_detect(onset_envelope, sr)` | 峰值检测 |
| `beat_track(onset_envelope, sr)` | 自相关 |
| `harmonic(y)` | medfilt 谐波分离 |
| `hpss(y)` | medfilt HPSS |
| `pyin(y, fmin, fmax, sr)` | 自相关音高检测 |
| `note_to_hz(note)` | MIDI 频率转换 |
| `frame(y, frame_length, hop_length)` | 滑窗切片 |

### `librosa_compat.py` - 兼容层

```python
from services.dsp_utils import (
    stft, istft, fft_frequencies,
    spectral_flatness, spectral_centroid, spectral_bandwidth,
    spectral_rolloff, mfcc, delta, rms,
    chroma_stft, zero_crossing_rate,
    onset_strength, onset_detect, beat_track,
    harmonic, hpss, pyin, note_to_hz, frame
)
```

各文件只需 `from services.librosa_compat import stft, istft, fft_frequencies` 等，无需关心底层实现。

### STFT/ISTFT 实现细节

手写实现确保与 librosa 行为完全一致：

```python
def stft(y, n_fft=2048, hop_length=512, window='hann'):
    fft_window = scipy.signal.get_window(window, n_fft, fftbins=True)
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
    fft_window = scipy.signal.get_window(window, n_fft, fftbins=True)
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
```

## 实施步骤

### 步骤1：创建 `services/dsp_utils.py`
- 实现所有 DSP 函数（stft, istft, fft_frequencies, 特征提取等）
- 每个函数的输入/输出签名与 librosa 对应函数一致
- 只依赖 numpy 和 scipy

### 步骤2：创建 `services/librosa_compat.py`
- 从 dsp_utils 导入所有函数并重新导出
- 各文件通过此模块导入，统一入口

### 步骤3：替换修复算法中的 librosa（A类，7个文件）
- `repair_v2_0/spectral_group_a.py` → `from services.librosa_compat import stft, istft, fft_frequencies`
- `repair_v2_0/spectral_group_b.py` → 同上
- `repair_v2_1/spectral_group_a.py` → 同上
- `repair_v2_1/spectral_group_b.py` → 同上
- `audio_repair_v1_0.py` → 同上
- `audio_repair_v1_1.py` → 同上
- `audio_repair_v1_2.py` → 同上

### 步骤4：替换检测器中的 librosa（B类，3个文件）
- `detectors/ai_detector_v1_0.py` → `from services.librosa_compat import ...`
- `detectors/ai_detector_v1_1.py` → 同上
- `detectors/ai_detector_v1_2.py` → 同上

### 步骤5：清理残留 import（C类，3个文件）
- `repair_v2_0/core.py` → 删除 `import librosa`
- `repair_v2_1/core.py` → 删除 `import librosa`
- `main.py` → 将 `import librosa` 改为 `import miniaudio`

### 步骤6：更新 audio_loader.py
- 删除 librosa 兜底分支
- miniaudio 失败时直接抛出 RuntimeError

### 步骤7：更新依赖文件
- `requirements.txt` → 删除 `librosa>=0.10,<0.11`，删除 `soxr>=0.5,<0.6`
- `requirements_android.txt` → 删除 librosa 相关依赖（joblib, decorator, lazy_loader, msgpack, platformdirs, pooch, audioread）

### 步骤8：更新部署脚本
- `deploy/setup_android.sh` → 删除 librosa `--no-deps` 安装步骤、删除 soxr stub 创建步骤、删除 numba stub 创建步骤、删除 soxr/numba 验证步骤
- 删除 `backend/numba.py` stub 文件

### 步骤9：验证
- grep 确认 `import librosa` 在 backend 目录中仅出现在 `training/feature_extractor.py`
- grep 确认 `librosa.` 调用在 backend 目录中仅出现在 `training/feature_extractor.py`
- 确认 requirements.txt 和 requirements_android.txt 无 librosa/soxr/numba

## 风险与注意事项

1. **STFT 精度**：手写 STFT/ISTFT 必须与 librosa 行为一致（窗函数、padding、重叠相加），否则修复算法的频谱操作会出错。这是最关键的部分。

2. **MFCC 实现精度**：librosa 的 MFCC 使用了 mel 滤波器组 + DCT，手写实现需要确保 mel 滤波器组与 librosa 的 Slaney 标准一致。但检测器对 MFCC 精度要求不高（用于启发式评分），小偏差可接受。

3. **pyin 替代**：librosa.pyin 是复杂的概率性音高检测算法。替代方案用自相关法（简单但精度较低），对检测器来说足够。

4. **HPSS 替代**：librosa.effects.hpss 使用中值滤波分离谐波/冲击，scipy.signal.medfilt 可直接替代。

5. **training/feature_extractor.py 保留 librosa**：此文件仅桌面端训练使用，保留 librosa 不影响移动部署。但需注意桌面端 requirements.txt 也删除了 librosa，所以训练时需手动 `pip install librosa`。

## 预期收益

- **消除 librosa 依赖**：不再需要 `--no-deps` hack
- **消除 soxr stub**：不再需要伪造 soxr 模块
- **消除 numba stub**：不再需要伪造 numba 模块
- **消除 scikit-learn 依赖链**：librosa → scikit-learn 的依赖链完全断开
- **部署脚本大幅简化**：setup_android.sh 减少 ~40 行 hack 代码
- **桌面端也受益**：requirements.txt 减少 librosa/soxr 两个依赖
- **requirements_android.txt 大幅精简**：删除 joblib, decorator, lazy_loader, msgpack, platformdirs, pooch, audioread 等 librosa 传递依赖
