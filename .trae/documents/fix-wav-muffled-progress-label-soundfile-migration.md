# 修复计划：WAV闷声 + 单轨进度显示 + soundfile替代miniaudio

## 问题1：WAV输出很闷

### 根因分析

**两个叠加的根因**：

**根因A：miniaudio 强制重采样到 44100Hz**
- `audio_loader.py` 使用 miniaudio 解码所有音频，miniaudio 会将 48kHz 音频降采样到 44100Hz
- 22050Hz 以上的高频信息被不可逆地丢失
- 在 MOBILE_MODE 下 `working_sr = sr`（即保持 44100Hz），不上采样到 48kHz
- 即使桌面端，miniaudio 也会把 48kHz 音频降到 44100Hz，然后 v2.4 再上采样到 48kHz——但高频已经丢了

**根因B：v3.x 双轨算法被错误用于单轨输入**
- v3.x 的 `repair_audio` 中 `vocal_path = params.get("vocal_path", input_path)` 和 `accompaniment_path = params.get("accompaniment_path", input_path)`
- 当单轨输入走 v3.x 时，**同一个文件被加载两次，分别作为"人声"和"伴奏"处理，然后混音叠加**
- 这导致：信号被处理两次 + 混音叠加 = 严重失真/闷声
- 进度显示"处理人声轨"正是因为 v3.x 确实在按双轨流程处理

### 修复方案

**修复根因A：soundfile 优先加载**
- `audio_loader.py`：WAV/FLAC/OGG 用 soundfile 加载（保留原始采样率和声道数），MP3/AAC 用 miniaudio fallback
- `routes.py`：`miniaudio.get_file_info()` 替换为 `sf.info()` + miniaudio fallback

**修复根因B：单轨模式禁止 v3.x**
- `audio_repair.py`：单轨模式自动降级 v3.x → v2.4/v2.4a
- 前端：单轨模式下 v3.x 选项灰显

---

## 问题2：单轨处理进度显示"处理人声轨"

### 根因

单轨输入走了 v3.x 双轨算法路径。v3.x 的 `repair_audio` 会：
1. 加载同一个文件两次（作为 vocal_path 和 accompaniment_path）
2. 显示 "v3.1 处理人声轨..." 和 "v3.1 处理伴奏轨..."
3. 分别处理后混音叠加

这不仅是进度显示错误，更是**音质问题**——同一信号被处理两次再叠加。

### 修复方案

在 `audio_repair.py` 入口校验：单轨模式不允许使用 v3.x，自动降级为 v2.4（桌面端）或 v2.4a（移动端）。

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
- soundfile 保留原始采样率（miniaudio 强制 44100Hz）
- soundfile 正确报告声道数（miniaudio 单声道误报 2 声道）
- soundfile 安装更简单（`pkg install libsndfile` vs `pkg install rust` + 编译）

**策略**：soundfile 为主加载器，miniaudio 仅作 MP3/AAC fallback。

---

## 实施步骤

### Step 1: 改造 audio_loader.py — soundfile 优先，miniaudio fallback

文件：`backend/services/audio_loader.py`

```python
def load_audio_with_fallback(file_path, sr=None, mono=False, return_bit_depth=False):
    # 1. 先尝试 soundfile（WAV/FLAC/OGG，保留原始采样率）
    try:
        return _load_with_soundfile(file_path, sr, mono, return_bit_depth)
    except Exception:
        pass
    # 2. Fallback 到 miniaudio（MP3/AAC 等）
    return _load_with_miniaudio(file_path, sr, mono, return_bit_depth)
```

`_load_with_soundfile()` 实现：
- 使用 `sf.read()` 加载，返回 (data, sr)
- data 形状：单声道 (n_samples,) → reshape 为 (1, n_samples)；立体声 (n_samples, 2) → 转置为 (2, n_samples)
- 保留原始采样率，不强制重采样
- 如果调用者指定了 sr 且与原始不同，使用 scipy 的 resample_poly 重采样
- `return_bit_depth` 时从 `sf.info().subtype` 提取位深

`_load_with_miniaudio()` 实现：现有逻辑不变

### Step 2: 替换 routes.py 中的 miniaudio.get_file_info()

文件：`backend/api/routes.py`

新增辅助函数 `get_audio_info(path)`：
```python
def get_audio_info(path):
    try:
        import soundfile as sf
        info = sf.info(path)
        return {
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "duration": info.duration,
            "num_frames": info.frames,
            "format": info.format,
            "subtype": info.subtype,
        }
    except Exception:
        pass
    try:
        import miniaudio
        info = miniaudio.get_file_info(path)
        return {
            "sample_rate": info.sample_rate,
            "channels": info.nchannels,
            "duration": info.duration,
            "num_frames": info.num_frames,
            "format": str(info.file_format),
            "sample_width": info.sample_width,
        }
    except Exception:
        return None
```

替换所有 `miniaudio.get_file_info()` 调用点（约 5 处）。

### Step 3: 单轨模式算法版本校验

文件：`backend/services/audio_repair.py`

在 `repair_audio()` 入口增加：
```python
def repair_audio(input_path, output_path, params, progress_callback=None, mobile_mode=False):
    version = params.get("algorithm_version", DEFAULT_VERSION)
    processing_mode = params.get("processing_mode", "single")
    
    # 单轨模式不允许使用 v3.x 双轨算法
    if processing_mode == "single" and version.startswith("v3."):
        version = "v2.4a" if mobile_mode else "v2.4"
        logger.warning(f"单轨模式不支持 {params.get('algorithm_version')}，自动降级为 {version}")
        params = {**params, "algorithm_version": version}
    
    # ... 原有逻辑
```

### Step 4: 更新 setup_android.sh

文件：`deploy/setup_android.sh`

在依赖安装部分增加 `pkg install libsndfile`。

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
| `backend/services/audio_repair.py` | 单轨模式 v3.x 自动降级 |
| `deploy/setup_android.sh` | 增加 `pkg install libsndfile` |

## 假设与决策

1. **soundfile 在 Termux 可用**：需 `pkg install libsndfile`，setup_android.sh 需更新
2. **miniaudio 保留**：MP3/AAC 等格式仍需 miniaudio，不删除依赖
3. **v3.x 不适用于单轨**：v3.x 设计为双轨算法，单轨输入会被当作人声+伴奏双重处理，导致失真
4. **WAV 闷声主因**：miniaudio 强制重采样到 44100Hz 丢失高频 + v3.x 双重处理叠加
