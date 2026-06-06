# 修复计划：WAV闷声 + 单轨进度显示 + soundfile替代miniaudio

## 问题1：WAV输出很闷

### 根因分析

**根因A：miniaudio 强制重采样到 44100Hz**
- `audio_loader.py` 使用 miniaudio 解码所有音频，miniaudio 会将 48kHz 音频降采样到 44100Hz
- 22050Hz 以上的高频信息被不可逆地丢失
- 即使桌面端 v2.4 再上采样到 48kHz，高频已经丢了

**根因B：v3.x 双轨算法缺少单轨模式支持**
- v3.x 的 `repair_audio` 中 `vocal_path = params.get("vocal_path", input_path)` 和 `accompaniment_path = params.get("accompaniment_path", input_path)`
- **关键 bug**：`processing_mode` 默认值是 `"dual"`（`params.get("processing_mode", "dual")`），而单轨请求 `/repair` 根本不传 `processing_mode`
- 所以单轨请求也默认走了双轨模式：同一文件被加载两次，分别作为"人声"和"伴奏"处理，然后混音叠加
- 这导致：信号被处理两次 + 混音叠加 = 严重失真/闷声

### 修复方案

**修复根因A：soundfile 优先加载**（见问题3）

**修复根因B：v3.x 增加单轨模式支持**
- v3.x 的 `repair_audio` 入口检测 `processing_mode`
- 单轨模式：只加载一次音频，使用统一的处理流程，不进行双轨分离和混音
- 双轨模式：保持现有逻辑不变
- **同时修复 `processing_mode` 默认值**：改为 `"single"`（因为单轨请求不传此参数）

---

## 问题2：单轨处理进度显示"处理人声轨"

### 根因

v3.x 缺少单轨模式。`processing_mode` 默认值为 `"dual"`，导致单轨请求也走双轨流程，显示"处理人声轨"。

### 修复方案

1. v3.x 增加单轨模式分支
2. 单轨时进度消息改为 `"v3.1 处理音频..."` 而非 `"处理人声轨..."`
3. 修复 `processing_mode` 默认值为 `"single"`

---

## 问题3：soundfile 在 Termux 能否完全替代 miniaudio？

### 结论：**部分替代**

| 格式 | soundfile | miniaudio |
|------|-----------|-----------|
| WAV | ✅ | ✅ |
| FLAC | ✅ | ✅ |
| OGG | ✅ | ✅ |
| MP3 | ❌ | ✅ |
| AAC/M4A | ❌ | ✅ |

**关键优势**：
- soundfile 保留原始采样率（miniaudio 强制 44100Hz）——**解决闷声的根因A**
- soundfile 正确报告声道数（miniaudio 单声道误报 2 声道）
- soundfile 安装更简单（`pkg install libsndfile` vs `pkg install rust` + 编译）

**策略**：soundfile 为主加载器，miniaudio 仅作 MP3/AAC fallback。

---

## 实施步骤

### Step 1: 改造 audio_loader.py — soundfile 优先，miniaudio fallback

文件：`backend/services/audio_loader.py`

重构为两个内部函数 + 一个统一入口：

```python
import numpy as np

_SUBTYPE_BIT_DEPTH = {
    "PCM_16": 16, "PCM_24": 24, "PCM_32": 32, "PCM_S8": 8,
    "FLOAT": 32, "DOUBLE": 64,
    "MPEG_LAYER_III": 0,
}

def _load_with_soundfile(file_path, sr, mono, return_bit_depth):
    import soundfile as sf
    info = sf.info(file_path)
    data, sr_orig = sf.read(file_path, dtype='float32')
    # data: 单声道 (n_samples,) 或立体声 (n_samples, n_channels)
    # 统一转为 (n_channels, n_samples) 格式
    if data.ndim == 1:
        raw = data.reshape(1, -1)
    else:
        raw = data.T  # (n_channels, n_samples)

    sample_rate = sr_orig
    source_bit_depth = _SUBTYPE_BIT_DEPTH.get(info.subtype, 16)

    # mono 处理
    if mono and raw.shape[0] > 1:
        raw = raw.mean(axis=0)
    elif mono and raw.shape[0] == 1:
        raw = raw[0]
    elif not mono and raw.shape[0] == 1:
        raw = raw[0].reshape(1, -1)

    # 重采样（如果调用者指定了目标采样率）
    target_sr = sr if sr is not None else sample_rate
    if sample_rate != target_sr:
        from scipy.signal import resample_poly
        if raw.ndim == 1:
            num_samples = int(len(raw) * target_sr / sample_rate)
            raw = resample_poly(raw, target_sr, sample_rate)[:num_samples].astype(np.float32)
        else:
            resampled = np.zeros((raw.shape[0], int(raw.shape[1] * target_sr / sample_rate)), dtype=np.float32)
            for ch in range(raw.shape[0]):
                r = resample_poly(raw[ch], target_sr, sample_rate)
                resampled[ch, :len(r)] = r[:resampled.shape[1]]
            raw = resampled
        sample_rate = target_sr

    if return_bit_depth:
        return raw, sample_rate, source_bit_depth
    return raw, sample_rate


def _load_with_miniaudio(file_path, sr, mono, return_bit_depth):
    import miniaudio
    # 现有逻辑不变（强制 44100Hz，声道误报等）
    sound = miniaudio.decode_file(file_path, output_format=miniaudio.SampleFormat.FLOAT32)
    nchannels = sound.nchannels
    sample_rate = sound.sample_rate
    source_bit_depth = sound.sample_width * 8
    raw = np.frombuffer(sound.samples, dtype=np.float32).copy()
    if nchannels > 1:
        raw = raw.reshape(-1, nchannels).T
    else:
        raw = raw.reshape(1, -1)
    # ... mono 和重采样逻辑不变 ...
    if return_bit_depth:
        return raw, sample_rate, source_bit_depth
    return raw, sample_rate


def load_audio_with_fallback(file_path, sr=None, mono=False, return_bit_depth=False):
    # 1. 先尝试 soundfile（WAV/FLAC/OGG，保留原始采样率）
    try:
        return _load_with_soundfile(file_path, sr, mono, return_bit_depth)
    except Exception:
        pass
    # 2. Fallback 到 miniaudio（MP3/AAC 等）
    return _load_with_miniaudio(file_path, sr, mono, return_bit_depth)
```

### Step 2: 替换 routes.py 中的 miniaudio.get_file_info()

文件：`backend/api/routes.py`

新增辅助函数 `get_audio_info(path)`，替换所有 `miniaudio.get_file_info()` 调用点（约 5 处）：
- L399: 单轨上传接口
- L461: 双轨上传接口
- L490: 双轨上传接口（伴奏）
- L2079: 文件信息接口
- L2437: 按哈希查文件信息接口

### Step 3: v3.x 增加单轨模式支持

涉及 4 个文件，每个文件的 `repair_audio()` 入口增加单轨模式分支：

**3a. 修复 `processing_mode` 默认值**

当前 bug：`params.get("processing_mode", "dual")` → 单轨请求默认走了双轨模式
修复：`params.get("processing_mode", "single")` → 默认单轨，只有双轨请求显式传 `"dual"`

**3b. v3.1 / v3.0（桌面版）单轨模式**

`_repair_single_track()` 实现：
```python
def _repair_single_track(input_path, output_path, params, progress_callback):
    # 加载音频（一次）
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)
    was_mono = y.shape[0] == 1 and params.get("was_mono", False)

    original_sr = sr
    original_duration = round(y.shape[1] / sr, 2)
    working_sr = DESKTOP_WORKING_SR  # 48000

    # 内存检查 + 重采样（与双轨模式相同）
    ...

    issues_found = ["单轨处理"]

    # 处理步骤：合并人声+伴奏的精华步骤
    # 使用 v3.x 已有的处理函数，但只处理一次
    if progress_callback:
        progress_callback(0.10, "v3.1 处理音频...")

    # 1. 基础修复
    if params.get("de_clipping", 0) > 0:
        y = _tanh_declip(y, params["de_clipping"])
    if params.get("de_pop", 0) > 0:
        y = _diff_clamp_depop(y, sr, params["de_pop"])

    # 2. 频谱处理（使用 v2.4 的模块，与双轨人声处理共享）
    if params.get("noise_reduction", 0) > 0:
        y = apply_spectral_group_a(y, sr, params, N_FFT, HOP_LENGTH, issues_found, "generic")
    if params.get("de_essing", 0) > 0:
        y = _apply_vocal_de_ess(y, sr, params["de_essing"])
    if params.get("ai_repair", 0) > 0:
        y = apply_hifi_ai_repair(y, sr, params["ai_repair"], {})

    # 3. 响度归一化
    y = _adaptive_loudness_normalize(y, sr, -14.0)

    # 4. 增强
    if params.get("dynamic_range", 0) > 0:
        y = apply_hifi_multiband_compress(y, sr, params["dynamic_range"], "generic", {})
    if params.get("bass_enhance", 0) > 0:
        y = _harmonic_bass_enhance(y, sr, params["bass_enhance"], "generic")
    if params.get("clarity", 0) > 0:
        y = _air_texture_reconstruct(y, sr, params["clarity"], "generic")

    # 5. 立体声增强（如果是立体声）
    if y.shape[0] == 2 and params.get("stereo_width", 0) > 0:
        y = apply_stereo_width_v3(y, sr, params["stereo_width"])

    # 6. 峰值限制 + 导出
    y = _soft_peak_limit(y, threshold=0.9)
    y = _spectral_hf_gate(y, sr)
    y = _hf_protect(y, sr)

    # 导出 WAV
    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype="PCM_24")

    return {
        "issues_found": issues_found,
        "original_sample_rate": original_sr,
        "output_sample_rate": working_sr,
        "output_bit_depth": params.get("bit_depth", 24),
        "duration": original_duration,
        "channels": y.shape[0] if y.ndim > 1 else 1,
        "algorithm_version": "v3.1",
        "processing_mode": "single",
    }
```

**3c. v3.1a / v3.0a（移动版/轻量版）单轨模式**

类似实现，但使用轻量版处理函数（`_simple_declip`、`_spectral_denoise` 等），`working_sr = MOBILE_WORKING_SR`。

### Step 4: 更新 setup_android.sh

文件：`deploy/setup_android.sh`

在系统依赖安装列表中增加 `libsndfile`：
```bash
for pkg in python clang make pkg-config libc++ libffi openssl curl ca-certificates \
    python-numpy python-scipy rust lame libsndfile; do
```

### Step 5: 验证和测试

- `pytest backend/tests/test_repair_quality.py -v`
- `pytest backend/tests/test_dependencies.py -v`
- 确认 soundfile 在当前环境可用
- 打包 `bash scripts/build_android_release.sh`

---

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `backend/services/audio_loader.py` | soundfile 优先加载，miniaudio fallback |
| `backend/api/routes.py` | `get_audio_info()` 替换 `miniaudio.get_file_info()` |
| `backend/services/repair/repair_v3_0/core.py` | 增加单轨模式 `_repair_single_track()`，修复 processing_mode 默认值 |
| `backend/services/repair/repair_v3_0a/core.py` | 增加单轨模式 `_repair_single_track()`，修复 processing_mode 默认值 |
| `backend/services/repair/repair_v3_1/core.py` | 增加单轨模式 `_repair_single_track()`，修复 processing_mode 默认值 |
| `backend/services/repair/repair_v3_1a/core.py` | 增加单轨模式 `_repair_single_track()`，修复 processing_mode 默认值 |
| `deploy/setup_android.sh` | 增加 `libsndfile` 到系统依赖 |

## 假设与决策

1. **soundfile 在 Termux 可用**：需 `pkg install libsndfile`，setup_android.sh 需更新
2. **miniaudio 保留**：MP3/AAC 等格式仍需 miniaudio，不删除依赖
3. **v3.x 单轨模式**：v3.x 是 v2.4 的升级版，理应支持单轨模式。单轨时使用统一的处理流程（合并人声+伴奏处理的精华步骤），不进行双轨分离和混音
4. **WAV 闷声主因**：miniaudio 强制重采样到 44100Hz 丢失高频 + v3.x 缺少单轨模式导致双重处理叠加
5. **processing_mode 默认值修复**：从 `"dual"` 改为 `"single"`，因为单轨请求不传此参数
