# 修复计划：3个问题修复方案

## 问题1: Termux 没有 ffmpeg，MP3 下载失败

### 根因
`backend/api/routes.py` 中 `/download-mp3` 端点使用 `subprocess.run(["ffmpeg", ...])` 进行 MP3 转码，但 Termux 环境没有安装 ffmpeg。

### 修复方案
用 `lameenc` Python 库替换 ffmpeg 子进程调用。`lameenc` 是 LAME MP3 编码器的 Python 绑定，纯 pip 安装，无外部依赖，在 Linux/macOS/Windows 上都有预编译二进制包。

**修改文件：**
1. `backend/requirements.txt` — 添加 `lameenc>=1.8`
2. `backend/api/routes.py` — 重写 `/download-mp3` 端点：
   - 用 `wave` 模块读取 WAV 文件的 PCM 数据
   - 用 `lameenc.Encoder` 编码为 MP3
   - 保持原有的文件缓存逻辑（转换后存 mp3_path，下次直接返回）
   - 保持 Range 请求支持

```python
# 伪代码
import lameenc
import wave

def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    with wave.open(wav_path, 'rb') as wav:
        framerate = wav.getframerate()
        channels = wav.getnchannels()
        sampwidth = wav.getsampwidth()
        pcm_data = wav.readframes(wav.getnframes())
    
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(framerate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    
    mp3_data = encoder.encode(pcm_data)
    mp3_data += encoder.flush()
    
    with open(mp3_path, 'wb') as f:
        f.write(mp3_data)
```

---

## 问题2: 单轨修复缓存命中没生效

### 根因
`backend/database.py` 中 `find_repair_cache`（单轨缓存查找）仍然使用**严格 JSON 精确匹配**：
```python
stored_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
if stored_json == params_json:
```

但前端 `mapParamsToBackend` 传过来的参数 key 集合与数据库中存储的参数 key 集合不一致（前端有旧式 key `de_clipping`、`algorithm_version` 等，数据库存储的参数可能有额外字段）。严格精确匹配导致永远不匹配。

之前已修复了 `find_dual_repair_cache` 改用交集比较，但 `find_repair_cache` 遗漏了。

### 修复方案
对 `find_repair_cache` 应用与 `find_dual_repair_cache` 相同的交集比较逻辑。

**修改文件：**
1. `backend/database.py` — 重写 `find_repair_cache` 的参数比较部分

```python
# 修改后
repair_param_keys = {
    "de_clipping", "noise_reduction", "de_essing", "de_crackle", "de_pop",
    "harmonic_enhance", "dynamic_range", "softness", "presence_boost",
    "bass_enhance", "spatial_enhance", "transient_repair", "warmth", "clarity",
    "algorithm_version",
}
stored_subset = {k: v for k, v in parsed.items() if k in repair_param_keys}
input_subset = {k: v for k, v in params.items() if k in repair_param_keys}
common_keys = stored_subset.keys() & input_subset.keys()
if common_keys and all(stored_subset[k] == input_subset[k] for k in common_keys):
```

---

## 问题3: 预估大小和交付显示异常

### 根因
`src/utils/settingsStorage.ts` 中 `AppSettings.exportOptions` 接口定义缺少 `masteringStyle` 字段：

```typescript
exportOptions: {
    sampleRate: number;
    bitDepth: 16 | 24 | 32;
    // 缺少 masteringStyle!
};
```

`defaultSettings.exportOptions` 也没有 `masteringStyle`。当从 localStorage 加载设置时，`masteringStyle` 丢失，导致 `processingOptions` 初始化时没有 `masteringStyle`。

虽然母带风格选择器用 `(processingOptions.masteringStyle || 'standard')` 作为后备显示，但 `onOptionsChange?.({ ...processingOptions, masteringStyle: option.value })` 创建的 `processingOptions` 对象如果缺失 `masteringStyle`，传给 `renderAudio` 时就是 `undefined`，后端会用默认值 `'standard'`。

### 修复方案
**修改文件：**
1. `src/utils/settingsStorage.ts` — `exportOptions` 接口添加 `masteringStyle`，`defaultSettings.exportOptions` 添加默认值

```typescript
export interface AppSettings {
  // ...
  exportOptions: {
    sampleRate: number;
    bitDepth: 16 | 24 | 32;
    masteringStyle?: 'standard' | 'powerful' | 'warm';
  };
  // ...
}

export const defaultSettings: AppSettings = {
  // ...
  exportOptions: {
    sampleRate: 48000,
    bitDepth: 24,
    masteringStyle: 'standard',
  },
  // ...
};
```

---

## 问题4: 测试是摆设，不覆盖缓存逻辑

### 根因
现有测试只覆盖了 API 端点和修复质量，完全没有覆盖缓存查找逻辑：
- `test_dual_track_api.py` — 只测试上传/修复/状态端点
- `test_repair_quality.py` — 只测试修复质量

### 修复方案
新增 `backend/tests/test_cache_lookup.py`，测试以下场景：

1. **单轨缓存精确匹配**：相同 hash + 相同 params → 命中
2. **单轨缓存参数变化匹配**：相同 hash + 不同 params（但 repair_param_keys 相同）→ 命中
3. **单轨缓存参数变化不匹配**：相同 hash + 不同 params（repair_param_keys 不同）→ 不命中
4. **双轨缓存子集匹配**：相同 hash + 参数子集相同 → 命中
5. **双轨缓存参数缺失**：输入有额外 key、存储有额外 key → 交集比较仍能命中
6. **MP3 编码**：测试 `_wav_to_mp3` 函数输出有效 MP3 文件

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/requirements.txt` | 添加 `lameenc>=1.8` |
| `backend/api/routes.py` | 重写 `/download-mp3` 用 `lameenc` 替代 ffmpeg |
| `backend/database.py` | `find_repair_cache` 改为交集比较 |
| `src/utils/settingsStorage.ts` | `exportOptions` 添加 `masteringStyle` |
| `backend/tests/test_cache_lookup.py` | 新增缓存查找测试 |

---

## 验证步骤

1. **安装 lameenc**：`pip install lameenc`
2. **MP3 下载**：调用 `/api/v1/download-mp3/{task_id}` 确认返回有效 MP3
3. **单轨缓存**：执行修复，第二次相同参数时查看日志 `[cache-lookup] ✅ MATCH`
4. **设置持久化**：切换母带风格后刷新页面，确认风格保持
5. **运行测试**：`python -m pytest backend/tests/test_cache_lookup.py -v`
6. **构建验证**：`npm run build`
7. **Android 打包**：`bash scripts/build_android_release.sh`
8. **启动 dev**：`bash scripts/start_dev.sh`