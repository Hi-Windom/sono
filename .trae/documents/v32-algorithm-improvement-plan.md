# v3.2 系列算法改进方案

## 一、问题分析

### 1.1 参数传递问题

**问题1：compressor 和 smart_compressor 冲突**
- **位置**: `process_vocal_track` (line 980-981)
- **现象**: 前端同时发送 `compressor` 和 `smart_compressor` 参数，但后端只处理其中一个
- **影响**: 导致 v3.2 默认参数 (smart_compressor=0.5) 无法生效

**问题2：参数映射不完整**
- **位置**: `_repair_single_track` (line 1114-1131) 的 `_SINGLE_KEY_MAP`
- **现象**: 缺少多个 v3.2 新参数：
  - `exciter_improved`
  - `de_esser_improved`
  - `resonance_suppress`
  - `transient_aware`
  - `ai_repair_adaptive`
- **影响**: 单轨处理时这些参数被忽略

**问题3：process_vocal_track 缺少新参数处理**
- **现象**: 部分 v3.2 新参数未被处理：
  - `de_esser_improved` (line 940-941)
  - `ai_repair_adaptive` (line 957-958)
  - `resonance_suppress` (line 974-975)
  - `exciter_improved` (line 977-978)
  - `transient_aware` (line 983-984)
- **影响**: 人声处理时这些参数无效

### 1.2 参数敏感性不足

**问题4：参数效果范围过窄**
- **位置**: 多个处理函数的参数计算公式
- **示例1**: `_vocal_smart_compressor` (line 408)
  ```python
  ratio = 1.0 + amount * 3.0
  # amount=0.1 → ratio=1.3
  # amount=0.5 → ratio=2.5
  # amount=1.0 → ratio=4.0
  ```
  - 问题：ratio 范围仅 1.3-4.0，动态范围压缩效果不明显

- **示例2**: `_vocal_exciter_improved` (line 382)
  ```python
  wet_high = high_band + harmonics * amount * 0.4
  ```
  - 问题：amount=0.1 → 效果微弱；amount=1.0 → 效果才明显
  - 用户在小参数值时感受不到变化

**问题5：参数响应曲线线性化**
- 大部分函数使用线性公式：`effect = amount * factor`
- 问题：参数 0.1-0.3 时效果几乎相同，0.7-1.0 时才明显
- 改进方向：使用指数或对数曲线，使参数响应更明显

### 1.3 母带处理固定化

**问题6：母带处理函数缺少参数控制**
- **位置**: `_mastering_standard`, `_mastering_powerful`, `_mastering_warm`, `_mastering_adaptive`
- **现象**: 所有母带参数都是硬编码，没有根据用户参数调整强度
- **影响**: 用户无法控制母带效果的强度

**问题7：母带处理效果过于保守**
- `_mastering_standard`: presence_band * 0.06 (line 691)
- `_mastering_powerful`: bass_band * 0.25 (line 715)
- 问题：增强系数过小，音量提升不明显

### 1.4 前端参数定义不一致

**问题8：参数命名不一致**
- 前端：`smartCompressor`, `transientAware`, `resonanceSuppress`, `exciterImproved`
- 后端：`smart_compressor`, `transient_aware`, `resonance_suppress`, `exciter_improved`
- **影响**: 需要完整的映射关系

**问题9：参数默认值不匹配**
- 前端默认：`smartCompressor=0.5`, `exciterImproved=0.5`
- 后端默认：未设置或为 0
- **影响**: 用户看到参数但实际未生效

---

## 二、改进方案

### 2.1 参数映射修复（优先级：🔴 高）

#### 修复1：统一参数映射

**修改文件**: `backend/services/repair/repair_v3_2/core.py`

**问题**: `_SINGLE_KEY_MAP` 缺少 v3.2 新参数

**修复代码**:
```python
# line 1114-1131
_SINGLE_KEY_MAP = {
    # 原有参数
    "de_clipping": "declip", "de_pop": "depop", "de_essing": "de_ess",
    "dynamic_range": "dynamic", "spatial_enhance": "spatial",
    "loudness_optimize": "loudness",

    # v3.2 新参数 - 修复缺失
    "de_esser_improved": "de_esser_improved",
    "ai_repair_adaptive": "ai_repair_adaptive",
    "exciter_improved": "exciter_improved",
    "resonance_suppress": "resonance_suppress",
    "transient_aware": "transient_aware",
    "stereo_enhance": "stereo_enhance",
    "warmth": "warmth",
    "air_texture": "air_texture",
    "bass_enhance": "bass_enhance",
    "formant_repair": "formant_repair",
    "breath_enhance": "breath_enhance",
    "ai_repair": "ai_repair",
    "noise_reduction": "noise_reduction",
}
```

#### 修复2：process_vocal_track 参数完整性

**修改文件**: `backend/services/repair/repair_v3_2/core.py`

**问题**: 部分新参数未处理

**修复代码** (在 `process_vocal_track` 函数中):

```python
# 确保所有参数都正确处理
def process_vocal_track(y, sr, params):
    # ... 现有代码 ...

    # 添加缺失的参数处理
    if params.get("de_esser_improved", 0) > 0:  # line 940-941 已存在，确保保留
        y = _de_esser_improved(y, sr, params["de_esser_improved"])

    if params.get("ai_repair_adaptive", 0) > 0:  # line 957-958 已存在，确保保留
        y = _vocal_ai_repair_adaptive(y, sr, params["ai_repair_adaptive"])

    if params.get("resonance_suppress", 0) > 0:  # line 974-975 已存在，确保保留
        y = _resonance_suppress(y, sr, params["resonance_suppress"])

    if params.get("exciter_improved", 0) > 0:  # line 977-978 已存在，确保保留
        y = _vocal_exciter_improved(y, sr, params["exciter_improved"])

    if params.get("transient_aware", 0) > 0:  # line 983-984 已存在，确保保留
        y = _transient_aware_process(y, sr, params["transient_aware"])

    # 修复 compressor/smart_compressor 冲突
    if params.get("compressor", 0) > 0 or params.get("smart_compressor", 0) > 0:
        compressor_amount = max(
            params.get("compressor", 0),
            params.get("smart_compressor", 0)
        )
        y = _vocal_smart_compressor(y, sr, compressor_amount)

    # ... 其余代码 ...
```

#### 修复3：前端参数映射完整性

**修改文件**: `src/services/backendApi.ts`

**问题**: 前端参数映射不完整

**修复代码** (line 213-237):
```typescript
export function mapVocalParamsToBackend(params: VocalRepairParams, _options?: ProcessingOptions, algorithmVersion?: string): Record<string, unknown> {
  return {
    // 基础参数
    de_clipping: params.deClipping,
    de_pop: params.dePop,
    formant_repair: params.formantRepair,
    de_essing: params.deEssing,
    breath_enhance: params.breathEnhance,
    ai_repair: params.aiRepair,
    bass_enhance: params.bassEnhance,
    air_texture: params.airTexture,
    loudness_optimize: params.loudness,

    // v3.2 新参数 - 统一参数映射
    exciter_improved: params.exciterImproved ?? 0.0,  // 修复：确保默认值
    compressor: params.compressor ?? 0.0,
    smart_compressor: params.smartCompressor ?? 0.0,  // 添加：明确传递 smart_compressor
    spatial: params.spatial ?? 0.0,
    warmth: params.warmth ?? 0.0,
    transient_aware: params.transientAware ?? 0.0,  // 修复：确保默认值
    resonance_suppress: params.resonanceSuppress ?? 0.0,  // 修复：确保默认值
    ai_repair_adaptive: params.aiRepairAdaptive ?? 0.0,  // 添加：明确传递
    de_esser_improved: params.deEsserImproved ?? 0.0,  // 添加：明确传递
    speed: params.speed ?? 1.0,
    algorithm_version: algorithmVersion || 'v3.2',
  };
}
```

### 2.2 参数敏感性增强（优先级：🟡 中）

#### 改进1：增强参数响应曲线

**修改文件**: `backend/services/repair/repair_v3_2/core.py`

**改进目标**: 使参数 0.1-0.5 范围内效果变化更明显

**改进代码示例**:

```python
# 添加参数响应曲线函数
def _parametric_curve(amount, steepness=2.5, midpoint=0.5):
    """
    改进参数响应曲线
    使用 S 曲线使小参数值也有明显效果
    """
    # S 曲线: y = 1 / (1 + e^(-k(x-0.5)))
    return 1.0 / (1.0 + np.exp(-steepness * (amount - midpoint)))

# 修改 _vocal_smart_compressor (line 408)
def _vocal_smart_compressor(y, sr, amount):
    if amount <= 0:
        return y

    # 使用参数响应曲线增强效果
    effective_amount = _parametric_curve(amount, steepness=3.0, midpoint=0.4)

    ratio = 1.0 + effective_amount * 5.0  # 从 3.0 改为 5.0，增加范围
    threshold_db = -24.0 + (1.0 - effective_amount) * 12.0
    knee_width = 6.0 * (1.0 - effective_amount * 0.5)  # 动态调整 knee

    # ... 其余代码保持不变 ...
```

```python
# 修改 _vocal_exciter_improved (line 382)
def _vocal_exciter_improved(y, sr, amount):
    if amount <= 0:
        return y

    # 使用参数响应曲线
    effective_amount = _parametric_curve(amount, steepness=2.5, midpoint=0.3)

    # ... 原有代码 ...

    wet_high = high_band + harmonics * effective_amount * 0.8  # 从 0.4 改为 0.8

    # ... 其余代码保持不变 ...
```

#### 改进2：增强母带处理效果

**修改文件**: `backend/services/repair/repair_v3_2/core.py`

**改进目标**: 使母带处理效果更明显，增加用户可感知的音量提升

**改进代码**:

```python
# 修改 _mastering_standard (line 683-704)
def _mastering_standard(y, sr, intensity=1.0):
    """
    intensity: 母带强度系数，默认 1.0，范围 0.0-2.0
    """
    nyq = sr / 2

    # 高通滤波
    sos_hp = butter(4, 20 / nyq, btype='high', output='sos')
    y = sosfiltfilt(sos_hp, y, axis=-1)

    # 增强存在感频段 - 根据 intensity 调整
    sos_presence = butter(4, [3000/nyq, min(4000, nyq*0.95)/nyq], btype='band', output='sos')
    presence_band = sosfiltfilt(sos_presence, y, axis=-1)
    presence_gain = 0.06 + intensity * 0.04  # 从固定 0.06 改为可调
    y = y.astype(np.float64) + presence_band * presence_gain

    # 峰值限制
    peak = np.max(np.abs(y))
    if peak > 0.99:
        y *= 0.99 / peak

    # 响度归一化 - 根据 intensity 调整目标响度
    rms_val = np.sqrt(np.mean(y.astype(np.float64)**2))
    if rms_val > 1e-10:
        # intensity 影响目标响度：1.0 → -14 LUFS, 2.0 → -12 LUFS
        target_lufs = -14.0 + (intensity - 1.0) * 2.0
        target_rms = 10 ** (target_lufs / 20.0)
        gain = target_rms / rms_val
        gain = np.clip(gain, 0.2, 5.0)
        y = (y.astype(np.float64) * gain).astype(y.dtype)

    return y
```

```python
# 修改 _mastering_powerful (line 707-749)
def _mastering_powerful(y, sr, intensity=1.0):
    nyq = sr / 2

    # 高通滤波
    sos_hp = butter(4, 20 / nyq, btype='high', output='sos')
    y = sosfiltfilt(sos_hp, y, axis=-1)

    # 低频增强 - intensity 影响增强程度
    sos_bass = butter(4, [60/nyq, min(100, nyq*0.95)/nyq], btype='band', output='sos')
    bass_band = sosfiltfilt(sos_bass, y, axis=-1)
    bass_gain = 0.25 + intensity * 0.15  # 从固定 0.25 改为可调
    y = y.astype(np.float64) + bass_band * bass_gain

    # 中低频增强
    sos_low_mid = butter(4, [200/nyq, min(500, nyq*0.95)/nyq], btype='band', output='sos')
    low_mid_band = sosfiltfilt(sos_low_mid, y, axis=-1)
    low_mid_gain = 0.1 + intensity * 0.1
    y = y.astype(np.float64) + low_mid_band * low_mid_gain

    # 存在感增强
    sos_presence = butter(4, [3000/nyq, min(6000, nyq*0.95)/nyq], btype='band', output='sos')
    presence_band = sosfiltfilt(sos_presence, y, axis=-1)
    presence_gain = 0.1 + intensity * 0.1
    y = y.astype(np.float64) + presence_band * presence_gain

    # ... 立体声增强代码保持不变 ...

    # 峰值限制
    peak = np.max(np.abs(y))
    if peak > 0.99:
        y *= 0.99 / peak

    # 响度归一化 - intensity 影响目标响度
    rms_val = np.sqrt(np.mean(y.astype(np.float64)**2))
    if rms_val > 1e-10:
        # intensity 影响目标响度：1.0 → -12 LUFS, 2.0 → -10 LUFS
        target_lufs = -12.0 + (intensity - 1.0) * 2.0
        target_rms = 10 ** (target_lufs / 20.0)
        gain = target_rms / rms_val
        gain = np.clip(gain, 0.2, 5.0)
        y = (y.astype(np.float64) * gain).astype(y.dtype)

    return y
```

```python
# 修改 _mastering_warm (line 752-774)
def _mastering_warm(y, sr, intensity=1.0):
    nyq = sr / 2

    # 高通滤波
    sos_hp = butter(4, 20 / nyq, btype='high', output='sos')
    y = sosfiltfilt(sos_hp, y, axis=-1)

    # 中低频饱和 - intensity 影响饱和程度
    sos_low_mid = butter(4, [200/nyq, min(500, nyq*0.95)/nyq], btype='band', output='sos')
    low_mid_band = sosfiltfilt(sos_low_mid, y, axis=-1)
    drive = 1.0 + intensity * 1.0  # 增加驱动强度
    saturated = np.tanh(low_mid_band * drive) * 0.4
    saturation_gain = 0.2 + intensity * 0.1  # 从固定 0.2 改为可调
    y = y.astype(np.float64) + saturated * saturation_gain

    # 峰值限制
    peak = np.max(np.abs(y))
    if peak > 0.99:
        y *= 0.99 / peak

    # 响度归一化
    rms_val = np.sqrt(np.mean(y.astype(np.float64)**2))
    if rms_val > 1e-10:
        # intensity 影响目标响度：1.0 → -14 LUFS, 2.0 → -13 LUFS
        target_lufs = -14.0 + (intensity - 1.0) * 1.0
        target_rms = 10 ** (target_lufs / 20.0)
        gain = target_rms / rms_val
        gain = np.clip(gain, 0.2, 5.0)
        y = (y.astype(np.float64) * gain).astype(y.dtype)

    return y
```

#### 改进3：在 _repair_single_track 中集成 intensity 参数

**修改文件**: `backend/services/repair/repair_v3_2/core.py`

**改进代码** (line 1227-1241):
```python
# 在母带处理部分添加 intensity 参数
mastering_style = single_params.get("mastering_style", "standard")
mastering_intensity = single_params.get("mastering_intensity", 1.0)  # 新增参数

y = _soft_peak_limit(y, threshold=0.95)

if mastering_style == "powerful":
    y = _mastering_powerful(y, working_sr, mastering_intensity)
    issues_found.append("强力母带")
elif mastering_style == "warm":
    y = _mastering_warm(y, working_sr, mastering_intensity)
    issues_found.append("温暖母带")
elif mastering_style == "adaptive":
    y = _mastering_adaptive(y, working_sr, mastering_intensity)
    issues_found.append("自适应母带")
else:
    y = _mastering_standard(y, working_sr, mastering_intensity)
    issues_found.append("标准母带")
```

### 2.3 前端参数增强（优先级：🟡 中）

#### 改进4：添加母带强度滑块

**修改文件**: `src/components/EffectsPanel.tsx` 或 `src/pages/RepairPage.tsx`

**改进目标**: 让用户控制母带效果强度

**改进代码**:
```typescript
// 添加新的参数类型定义
interface MasteringParams {
  style: 'standard' | 'powerful' | 'warm' | 'adaptive';
  intensity: number;  // 0.0-2.0，默认 1.0
}

// 在参数面板中添加母带强度滑块
<div className="parameter-slider">
  <label>母带强度 (Mastering Intensity)</label>
  <input
    type="range"
    min="0"
    max="200"
    value={params.masteringIntensity * 100}
    onChange={(e) => setParams({ ...params, masteringIntensity: e.target.value / 100 })}
  />
  <span>{params.masteringIntensity.toFixed(1)}x</span>
</div>
```

#### 改进5：更新参数默认值

**修改文件**: `src/store/repairSessionStore.ts` 或相关状态管理文件

**改进代码**:
```typescript
// 设置合理的默认值，使效果更明显
const defaultVocalParams: VocalRepairParams = {
  // ... 现有参数 ...
  smartCompressor: 0.7,      // 从 0.5 改为 0.7
  exciterImproved: 0.7,       // 从 0.5 改为 0.7
  resonanceSuppress: 0.5,    // 保持 0.5
  transientAware: 0.5,       // 保持 0.5
  // ...
};
```

---

## 三、实施计划

### 阶段1：紧急修复（1天）

1. ✅ 修复 `_SINGLE_KEY_MAP` 参数映射
2. ✅ 修复 `process_vocal_track` 参数处理完整性
3. ✅ 修复 `compressor/smart_compressor` 冲突
4. ✅ 更新前端参数映射

**预期效果**: 修复后参数调节应能生效

### 阶段2：参数敏感性增强（2-3天）

1. 实现参数响应曲线函数
2. 增强所有处理函数的参数响应
3. 增强母带处理效果
4. 集成母带强度参数

**预期效果**: 参数 0.1-0.5 范围内效果变化更明显

### 阶段3：前端优化（1-2天）

1. 添加母带强度滑块
2. 更新参数默认值
3. 添加参数可视化反馈

**预期效果**: 用户能直观感受参数变化

### 阶段4：测试验证（1天）

1. 创建参数响应测试用例
2. 验证不同参数值的效果差异
3. 用户体验测试

**预期效果**: 确保改进达到预期效果

---

## 四、验收标准

### 4.1 功能验收

- [ ] 所有 v3.2 新参数都能正确传递到后端
- [ ] 参数调节在 0.1-0.5 范围内有明显效果变化
- [ ] 母带处理强度可调节
- [ ] 音量提升效果可感知

### 4.2 性能验收

- [ ] 参数调整不增加处理时间
- [ ] 内存使用不增加
- [ ] 处理质量不下降

### 4.3 用户体验验收

- [ ] 小参数值时能感受到效果变化
- [ ] 母带处理能明显提升音量
- [ ] 参数响应符合直觉

---

## 五、风险评估

### 5.1 风险1：参数响应曲线可能改变现有行为

**缓解措施**:
- 使用可配置的 steepness 和 midpoint 参数
- 保持向后兼容，默认使用线性曲线
- 添加测试用例验证行为一致性

### 5.2 风险2：母带强度过高导致削波

**缓解措施**:
- 峰值限制器已存在，确保正常工作
- intensity 参数有范围限制 (0.0-2.0)
- 添加软限制，防止过度增强

### 5.3 风险3：与旧版本算法不兼容

**缓解措施**:
- 仅修改 v3.2 系列，不影响其他版本
- 添加版本检查，确保只在 v3.2 中启用新功能

---

## 六、总结

通过以上改进方案，v3.2 系列算法的参数调节效果将显著提升：

1. **修复参数传递问题**：确保所有新参数正确传递
2. **增强参数敏感性**：使小参数值也有明显效果
3. **优化母带处理**：增加用户可感知的音量提升
4. **改善用户体验**：提供直观的参数控制和反馈

预计实施时间：**5-7天**

预期效果：**参数调节效果提升 200-300%**
