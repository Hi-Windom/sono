# 修复双轨缓存失效和 96kHz 倍速问题

## Bug 1: 双轨修复缓存命中失效

### 根因分析

双轨修复的缓存流程：
1. 前端 `mapVocalParamsToBackend` 发送的 vocal params 包含 `smart_compressor`, `transient_aware`, `resonance_suppress`, `ai_repair_adaptive`, `exciter_improved`, `de_esser_improved` 等键
2. 后端 `repair_dual_audio_endpoint` / `repair_dual_from_hash` 中的 `_VOCAL_KEY_MAP` **缺少这些键的映射**，导致这些参数在存储时被丢弃
3. 缓存查询 `lookup_dual_repair_cache` 中的 `_VOCAL_KEY_MAP` 同样缺少这些键
4. `find_dual_repair_cache` 中的 `repair_param_keys` 也缺少这些键

**结果**：vocal/accompaniment 参数的关键部分未被正确存储和比较，导致缓存匹配逻辑不完整。

### 修复步骤

#### 步骤 1.1: 补充 `_VOCAL_KEY_MAP` 缺失的映射

在以下三个位置补充缺失的 vocal 键映射：
- `repair_dual_audio_endpoint` (routes.py ~L749)
- `repair_dual_from_hash` (routes.py ~L868)
- `lookup_dual_repair_cache` (routes.py ~L2341)

需要新增的映射：
```python
"smart_compressor": "vocal_smart_compressor",
"transient_aware": "vocal_transient_aware",
"resonance_suppress": "vocal_resonance_suppress",
"ai_repair_adaptive": "vocal_ai_repair_adaptive",
"exciter_improved": "vocal_exciter_improved",
"de_esser_improved": "vocal_de_esser_improved",
```

#### 步骤 1.2: 补充 `_INST_KEY_MAP` 缺失的映射

同样在三个位置补充缺失的 instrument 键映射：
```python
"exciter": "inst_exciter",
"compressor": "inst_compressor",
"de_esser_advanced": "inst_de_esser_advanced",
"ai_repair_enhanced": "inst_ai_repair_enhanced",
"ai_repair_enhanced_lite": "inst_ai_repair_enhanced_lite",
"exciter_lite": "inst_exciter_lite",
"compressor_lite": "inst_compressor_lite",
"transient": "inst_transient",
"resonance": "inst_resonance",
"bass_enhance": "inst_bass_enhance",
"air_texture": "inst_air_texture",
"clarity": "inst_clarity",
```

#### 步骤 1.3: 补充 `repair_param_keys` 缺失的键

在 `find_dual_repair_cache` (database.py ~L280) 中补充：
```python
"vocal_smart_compressor", "vocal_transient_aware", "vocal_resonance_suppress",
"vocal_ai_repair_adaptive", "vocal_exciter_improved", "vocal_de_esser_improved",
"inst_exciter", "inst_compressor", "inst_de_esser_advanced",
"inst_ai_repair_enhanced", "inst_ai_repair_enhanced_lite",
"inst_exciter_lite", "inst_compressor_lite",
"inst_transient", "inst_resonance", "inst_bass_enhance",
"inst_air_texture", "inst_clarity",
```

---

## Bug 2: 96kHz 交付音频被错误 2 倍速处理

### 根因分析

在 `_run_render_dual` (routes.py ~L1129-1148) 中，当 `track_type == "both"`（混音模式）时：

1. 加载人声和伴奏（原始 SR，如 48kHz）
2. 混音：`mixed = (vocal_y + accompaniment_y) / 2`
3. **直接写入**：`sf.write(output_path, mixed.T, target_sr, subtype=subtype)`

**问题**：混音后的音频数据仍然是原始采样率（如 48kHz），但 WAV 头标记为 `target_sr`（如 96kHz）。播放器按 96kHz 播放，时长减半，听起来像 2 倍速。

### 修复步骤

#### 步骤 2.1: 混音后重采样到 target_sr

在 `_run_render_dual` 的混音分支中，在 `sf.write` 之前添加重采样逻辑：

```python
# 混音后重采样到 target_sr
if vocal_sr != target_sr:
    from scipy.signal import resample_poly
    target_len = int(mixed.shape[1] * target_sr / vocal_sr)
    mixed_resampled = np.zeros((mixed.shape[0], target_len))
    for ch in range(mixed.shape[0]):
        resampled = resample_poly(mixed[ch], target_sr, vocal_sr)
        mixed_resampled[ch, :len(resampled)] = resampled[:target_len]
    mixed = mixed_resampled
```

---

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `backend/api/routes.py` | 3 处补充 `_VOCAL_KEY_MAP` 和 `_INST_KEY_MAP`；修复 `_run_render_dual` 混音重采样 |
| `backend/database.py` | 补充 `find_dual_repair_cache` 的 `repair_param_keys` |

## 验证方法

1. 双轨缓存：执行双轨修复后，修改参数再执行，应命中缓存（参数相同时）或不命中（参数不同时）
2. 96kHz 交付：双轨修复后，以 96kHz 交付，下载的音频时长应正确，不应有 2 倍速效果