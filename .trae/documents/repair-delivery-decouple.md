# 修复规格与交付规格解耦 + 存储预估

## Summary

1. **后端存储占用预估**：新增 `/storage/estimate` API，根据时长/采样率/位深/通道数计算预估输出文件大小
2. **修复与交付解耦**：修复始终在 working_sr 下进行（不受用户选择的采样率影响），交付时通过新的 `/render` 端点做轻量重采样+位深转换+高频增强，修改交付规格不需要重新修复
3. **96kHz 高频增强**：交付 96kHz 时，重采样后对全频段做谐波增强，让整体听感更丰富

## Current State Analysis

### 当前修复流程
```
用户选择 96kHz/24bit → 前端传 sample_rate=96000 给后端 → 后端:
1. 重采样到 working_sr (48kHz)
2. 在 working_sr 下修复
3. 重采样到 target_sr=96kHz 输出
```
问题：修改交付规格需要重新走完整修复流程，96kHz 内存顶不住，缓存键包含 sample_rate/bit_depth 导致无法复用

### 当前缓存匹配
`database.py::find_repair_cache` 用 `json.dumps(params, sort_keys=True)` 精确匹配，params 包含 sample_rate/bit_depth，修改交付规格后缓存无法命中

### 当前前端文案
AIRepairPanel: "采样率和位深在修复时应用，修改后需重新修复"

## Proposed Changes

### 1. 后端：新增 `/storage/estimate` API

**文件**: `backend/api/routes.py`

新增端点：
```python
class StorageEstimateRequest(BaseModel):
    duration: float
    channels: int = 2
    sample_rate: int = 44100
    bit_depth: int = 24

@router.post("/storage/estimate")
async def storage_estimate(request: StorageEstimateRequest):
    bytes_per_sample = request.bit_depth // 8
    data_bytes = int(request.duration * request.sample_rate * request.channels * bytes_per_sample)
    total_bytes = data_bytes + 44  # WAV header
    return {
        "estimated_output_bytes": total_bytes,
        "estimated_output_mb": round(total_bytes / (1024 * 1024), 1),
    }
```

### 2. 后端：修复函数移除 target_sr 逻辑

**文件**: 所有 `backend/services/repair/*/core.py`

修改所有修复函数：
- 移除 `target_sr = params.get("sample_rate", ...)` 和后续的重采样到 target_sr 的代码
- 修复结果始终以 working_sr 输出
- 修复结果中 `output_sample_rate` 改为 working_sr
- 保留 `bit_depth` 参数用于 WAV 写入（修复结果位深）

涉及文件：
- `backend/services/repair/repair_v2_3a/core.py` — 移除 L474-489 的 target_sr 重采样
- `backend/services/repair/repair_v2_3/core.py` — 移除对应 target_sr 重采样
- `backend/services/repair/repair_v2_2/core.py` — 移除对应 target_sr 重采样
- `backend/services/repair/repair_v2_1/core.py` — 移除对应 target_sr 重采样
- `backend/services/repair/repair_v2_0/core.py` — 移除对应 target_sr 重采样
- `backend/services/repair/audio_repair_v1_2.py` — 移除对应 target_sr 重采样
- `backend/services/repair/audio_repair_v1_1.py` — 移除对应 target_sr 重采样
- `backend/services/repair/audio_repair_v1_0.py` — 移除对应 target_sr 重采样

### 3. 后端：新增 `/render` 端点（交付渲染）

**文件**: `backend/api/routes.py`

新增端点，从已有修复结果做轻量渲染：
```python
class RenderRequest(BaseModel):
    task_id: str
    sample_rate: int = 44100
    bit_depth: int = 24

@router.post("/render")
async def render_audio(request: RenderRequest):
    # 1. 查找 task 的 output_path（修复结果）
    # 2. 加载修复后的音频
    # 3. 如果 target_sr != current_sr:
    #    - 如果上采样（如48k→96k）：重采样 + 谐波增强
    #    - 如果下采样：抗混叠滤波 + 重采样
    # 4. 位深转换
    # 5. 写入新输出文件
    # 6. 返回新的 preview/download URL
```

**文件**: 新增 `backend/services/render.py`

渲染核心逻辑：
```python
def render_output(input_path, output_path, target_sr, bit_depth, progress_callback=None):
    y, sr = load_audio_with_fallback(input_path)
    
    if target_sr != sr:
        if target_sr > sr:
            # 上采样：重采样 + 谐波增强
            y = _upsample_with_harmonics(y, sr, target_sr)
        else:
            # 下采样：抗混叠滤波 + 重采样
            y = _downsample(y, sr, target_sr)
        sr = target_sr
    
    # 位深转换 + WAV 写出
    _write_wav(output_path, y, sr, bit_depth)
```

谐波增强实现（上采样时）：
```python
def _upsample_with_harmonics(y, sr, target_sr):
    # 1. 高质量重采样到 target_sr
    y_up = resample_poly(y, target_sr, sr)
    
    # 2. 谐波增强：对信号生成2次/3次谐波并混入
    #    使用 waveshaping 产生自然泛音
    #    增益控制：谐波量与原始信号成反比，避免过度染色
    y_enhanced = _harmonic_enhance(y_up, target_sr, amount=0.15)
    
    return y_enhanced
```

### 4. 后端：缓存键移除交付规格

**文件**: `backend/services/backendApi.ts` → `mapParamsToBackend`

从修复参数中移除 `sample_rate` 和 `bit_depth`：
```typescript
export function mapParamsToBackend(params: AIRepairParams, options: ProcessingOptions, algorithmVersion?: string): Record<string, unknown> {
  return {
    de_clipping: params.deClipping,
    // ... 其他修复参数
    algorithm_version: algorithmVersion || 'v2.0',
    // 不再传 sample_rate 和 bit_depth
  };
}
```

**文件**: `backend/api/routes.py` → `lookup_repair_cache`

缓存匹配时忽略 sample_rate/bit_depth 差异（因为修复参数中已不含这两个字段，自然就不匹配了）。

### 5. 前端：交付规格 UI 改造

**文件**: `src/components/AIRepairPanel.tsx`

- 文案从"采样率和位深在修复时应用，修改后需重新修复"改为"交付规格，修改后即时渲染无需重新修复"
- 采样率/位深区域标题从"处理选项"改为"交付规格"
- 添加存储预估显示（调用 `/storage/estimate`）

**文件**: `src/services/backendApi.ts`

- 新增 `StorageEstimateResult` 接口
- 新增 `fetchStorageEstimate()` 函数
- 新增 `renderAudio()` 函数（调用 `/render`）
- `mapParamsToBackend` 移除 sample_rate/bit_depth

**文件**: `src/hooks/useAudioProcessor.ts`

- 新增 `renderOutput()` 方法：修改交付规格后调用 `/render`
- 修复完成后自动根据当前交付规格渲染
- 处理缓存恢复冲突：恢复会话时，如果已有修复结果但交付规格不同，自动触发渲染

**文件**: `src/components/DownloadButton.tsx`

- 导出信息中显示实际渲染后的采样率/位深

### 6. 前端：存储预估显示

**文件**: `src/components/AIRepairPanel.tsx`

在交付规格区域显示预估文件大小，与内存预估类似但独立：
- 调用 `/storage/estimate` 获取预估大小
- 在采样率/位深选择器下方显示

## Assumptions & Decisions

1. **修复缓存不含交付规格**：修改采样率/位深后可直接复用已有修复结果
2. **独立 `/storage/estimate` API**：与内存预估解耦
3. **新 `/render` 端点**：交付渲染独立于修复流程
4. **96kHz 高频增强**：使用 waveshaping 谐波增强，amount=0.15，轻量处理
5. **修复结果始终以 working_sr 输出**：所有算法版本移除 target_sr 重采样逻辑
6. **缓存恢复冲突**：恢复会话时检测交付规格差异，自动触发渲染

## Verification Steps

1. 修复后修改交付规格（如 48kHz→96kHz），验证不需要重新修复
2. 96kHz 输出确实包含高频内容（频谱分析验证）
3. 存储预估与实际输出大小误差 < 1%
4. 缓存恢复后修改交付规格能正常渲染
5. 移动端 96kHz 渲染不会 OOM（渲染只做重采样，不做完整修复）
6. 运行 `python -m pytest backend/tests/test_repair_quality.py -v` 确保修复质量不受影响
