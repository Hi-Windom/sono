# WAV 音质修复计划

## 问题描述
MP3 "怪物低语"已修复，但 WAV 音质仍然不正确。44.1kHz 音频也有问题。

## 根因分析

### 已确认的 Bug

#### Bug 1: miniaudio 强制重采样到 44100Hz
- `miniaudio.decode_file()` 对所有音频强制重采样到 44100Hz
- 48kHz 音频被降采样到 44.1kHz，高频信息丢失
- 22.05kHz 音频被上采样到 44.1kHz
- 96kHz 音频被降采样到 44.1kHz
- 修复模块从 44100Hz 重采样到 48000Hz（工作采样率），导致双重重采样

#### Bug 2: miniaudio 对单声道误报 nchannels=2（已修复）
- 已通过 soundfile.info() 校正修复

#### Bug 3: MP3 编码器非连续数组（已修复）
- 已通过 np.ascontiguousarray() 修复

### 根本解决方案
**用 soundfile 替代 miniaudio 作为主要音频加载器**

soundfile 的优势：
- 正确报告声道数
- 保持原始采样率（不强制重采样）
- 更高质量的音频读取
- 已在 requirements_android.txt 中

miniaudio 的问题：
- 强制重采样到 44100Hz
- 对单声道误报 nchannels=2
- 数据精度损失

## 修改方案

### 文件: `backend/services/audio_loader.py`

**策略**: 优先使用 soundfile 加载音频，miniaudio 作为 fallback

```python
def load_audio_with_fallback(file_path, sr=None, mono=False, return_bit_depth=False):
    # 优先使用 soundfile（正确处理采样率和声道）
    try:
        import soundfile as sf
        info = sf.info(file_path)
        data, sample_rate = sf.read(file_path, dtype='float32')
        source_bit_depth = ... # 从 info.subtype 推断

        # 统一为 (channels, samples) 格式
        if data.ndim == 1:
            data = data.reshape(1, -1)
        else:
            data = data.T  # (samples, channels) → (channels, samples)

        # 声道处理
        if mono and data.shape[0] > 1:
            data = data.mean(axis=0)
        elif mono and data.shape[0] == 1:
            data = data[0]
        elif not mono and data.shape[0] == 1:
            data = data[0].reshape(1, -1)

        # 重采样
        ...

    except Exception:
        # fallback 到 miniaudio
        ...
```

### 关键注意事项
1. soundfile 返回的数据格式是 (samples, channels)，需要转置为 (channels, samples)
2. soundfile 的 dtype='float32' 参数可以直接返回 float32 数据
3. source_bit_depth 需要从 info.subtype 推断
4. miniaudio 作为 fallback 处理 soundfile 不支持的格式
5. 重采样逻辑保持不变

### source_bit_depth 推断
```python
SUBTYPE_TO_BIT_DEPTH = {
    'PCM_16': 16,
    'PCM_24': 24,
    'PCM_32': 32,
    'FLOAT': 32,
    'DOUBLE': 64,
}
source_bit_depth = SUBTYPE_TO_BIT_DEPTH.get(info.subtype, 16)
```

## 验证步骤

1. 运行 `python -m pytest backend/tests/ -v --tb=short`
2. 验证 44.1kHz 单声道/立体声加载正确
3. 验证 48kHz 单声道/立体声加载正确（不被重采样）
4. 验证修复流程输出频率正确
5. 验证 render 流程输出正确
6. 运行 `bash scripts/build_android_release.sh` 打包
