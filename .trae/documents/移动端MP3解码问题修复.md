# 移动端 MP3 解码问题修复计划

## 问题分析

### 当前状态
- 所有音频检测算法（v1.0/v1.1/v1.2）和修复算法（v2.0/v2.1）使用 `librosa.load()` 加载音频
- librosa 在 Termux 上依赖 audioread，但无法找到可用的 MP3 解码器
- `pydub>=0.25` 已在 requirements_android.txt 中，但代码没有使用它
- 用户提到"比ffmpeg轻量、名字带123的库" - 这应该是指 **pydub**（它内部使用 mpg123 解码 MP3）

### 问题位置
以下文件使用 `librosa.load()` 加载音频：

**检测算法：**
- `services/detectors/ai_detector_v1_0.py` (第6行)
- `services/detectors/ai_detector_v1_1.py` (第153行)
- `services/detectors/ai_detector_v1_2.py` (第146行)

**修复算法：**
- `services/repair/repair_v2_0/core.py` (第25行)
- `services/repair/repair_v2_1/core.py` (第25行)
- `services/repair/audio_repair_v1_0.py` (第9行)
- `services/repair/audio_repair_v1_1.py` (第15行)
- `services/repair/audio_repair_v1_2.py` (第16行)

## 解决方案

### 方案：创建通用的音频加载工具函数

创建一个统一的音频加载函数，在 librosa 失败时使用 pydub 作为 fallback：

```python
# services/audio_loader.py
import numpy as np
import librosa
from pydub import AudioSegment

def load_audio_with_fallback(file_path: str, sr=None, mono=False) -> tuple:
    """
    加载音频文件，优先使用 librosa，失败时使用 pydub 作为 fallback
    """
    try:
        # 优先使用 librosa
        y, sample_rate = librosa.load(file_path, sr=sr, mono=mono)
        return y, sample_rate
    except Exception as e:
        # 如果 librosa 失败（如 Termux 上 MP3 解码失败），使用 pydub
        audio = AudioSegment.from_file(file_path)

        if mono:
            samples = np.array(audio.get_array_of_samples())
            if audio.channels == 2:
                # 转换为单声道：左右声道平均
                samples = samples.reshape(-1, 2).mean(axis=1)
        else:
            if audio.channels == 1:
                samples = np.array(audio.get_array_of_samples())
            else:
                # 转换为 (channels, samples) 格式
                samples = np.array(audio.get_array_of_samples()).reshape(-1, audio.channels).T

        # 重采样到目标采样率
        if sr is not None and audio.frame_rate != sr:
            samples = _resample(samples, audio.frame_rate, sr, audio.channels)

        return samples, audio.frame_rate
```

### 实施步骤

1. **创建 `services/audio_loader.py`** - 统一的音频加载工具

2. **更新检测算法** - 替换 `librosa.load()` 为 `load_audio_with_fallback()`:
   - `services/detectors/ai_detector_v1_0.py`
   - `services/detectors/ai_detector_v1_1.py`
   - `services/detectors/ai_detector_v1_2.py`

3. **更新修复算法** - 替换 `librosa.load()` 为 `load_audio_with_fallback()`:
   - `services/repair/repair_v2_0/core.py`
   - `services/repair/repair_v2_1/core.py`
   - `services/repair/audio_repair_v1_0.py`
   - `services/repair/audio_repair_v1_1.py`
   - `services/repair/audio_repair_v1_2.py`

4. **更新 requirements_android.txt** - 确保 pydub 依赖正确：
   ```
   pydub>=0.25,<0.26
   numpy>=2,<3
   scipy>=1,<2
   soundfile>=0.13,<0.14
   ```

## 修改详情

### 新建文件

**`/workspace/backend/services/audio_loader.py`**:
- 导入 librosa 和 pydub.AudioSegment
- 实现 `load_audio_with_fallback(file_path, sr=None, mono=False)` 函数
- librosa 优先，失败时使用 pydub
- pydub 处理单声道/立体声转换和重采样

### 修改文件列表

| 文件 | 修改行号 | 修改内容 |
|------|---------|---------|
| `services/detectors/ai_detector_v1_0.py` | 第6行 | `import librosa` → `from services.audio_loader import load_audio_with_fallback` |
| `services/detectors/ai_detector_v1_0.py` | 第10行 | `librosa.load()` → `load_audio_with_fallback()` |
| `services/detectors/ai_detector_v1_1.py` | 第3行 | 添加 `from services.audio_loader import load_audio_with_fallback` |
| `services/detectors/ai_detector_v1_1.py` | 第153行 | `librosa.load()` → `load_audio_with_fallback()` |
| `services/detectors/ai_detector_v1_2.py` | 第2行 | 添加 `from services.audio_loader import load_audio_with_fallback` |
| `services/detectors/ai_detector_v1_2.py` | 第146行 | `librosa.load()` → `load_audio_with_fallback()` |
| `services/repair/repair_v2_0/core.py` | 第2行 | 添加 `from services.audio_loader import load_audio_with_fallback` |
| `services/repair/repair_v2_0/core.py` | 第25行 | `librosa.load()` → `load_audio_with_fallback()` |
| `services/repair/repair_v2_1/core.py` | 第2行 | 添加 `from services.audio_loader import load_audio_with_fallback` |
| `services/repair/repair_v2_1/core.py` | 第25行 | `librosa.load()` → `load_audio_with_fallback()` |
| `services/repair/audio_repair_v1_0.py` | 第1行 | 添加 `from services.audio_loader import load_audio_with_fallback` |
| `services/repair/audio_repair_v1_0.py` | 第9行 | `librosa.load()` → `load_audio_with_fallback()` |
| `services/repair/audio_repair_v1_1.py` | 第1行 | 添加 `from services.audio_loader import load_audio_with_fallback` |
| `services/repair/audio_repair_v1_1.py` | 第15行 | `librosa.load()` → `load_audio_with_fallback()` |
| `services/repair/audio_repair_v1_2.py` | 第1行 | 添加 `from services.audio_loader import load_audio_with_fallback` |
| `services/repair/audio_repair_v1_2.py` | 第16行 | `librosa.load()` → `load_audio_with_fallback()` |

## 验证步骤

1. 在 Termux 环境中测试 MP3 文件上传和修复
2. 确认检测算法可以处理 MP3 文件
3. 确认修复算法可以处理 MP3 文件
4. 验证 WAV/FLAC 等其他格式仍然正常工作

## 假设

- pydub 0.25.x 在 Termux 上可以正常工作（因为它使用纯 Python + mpg123 C库）
- MP3 文件本身是有效的（不是损坏的文件）
