# Bug 审查与修复计划

## 发现的 Bug 清单

### BUG-1 [严重] v3.x 单轨修复参数名与前端不匹配，多个处理步骤被静默跳过

**根因**：前端 `mapParamsToBackend` 发送 `de_clipping`、`de_pop`、`de_essing`、`dynamic_range`、`spatial_enhance` 等参数名，但 v3.x 的 `_repair_single_track` 检查的是 `declip`、`depop`、`de_ess`、`dynamic`、`spatial`。双轨模式有 `_VOCAL_KEY_MAP`/`_INST_KEY_MAP` 做映射，但单轨模式没有映射步骤。

**影响**：v3.x 单轨模式下，declip、depop、de_ess、dynamic、spatial 等步骤永远不会执行（`params.get("declip", 0)` 始终返回 0，因为实际 key 是 `de_clipping`）。

**修复方案**：在 v3.x 的 `_repair_single_track` 函数中添加参数名映射，与双轨模式一致。

**涉及文件**：
- `backend/services/repair/repair_v3_0/core.py` — `_repair_single_track`
- `backend/services/repair/repair_v3_0a/core.py` — `_repair_single_track`
- `backend/services/repair/repair_v3_1/core.py` — `_repair_single_track`
- `backend/services/repair/repair_v3_1a/core.py` — `_repair_single_track`

---

### BUG-2 [严重] routes.py `upload_dual_audio` 调用 `get_audio_info` 而非 `_get_audio_info`

**根因**：`routes.py:504-505` 调用了 `get_audio_info`（async API 端点函数，接受 file_hash 参数），而非 `_get_audio_info`（本地辅助函数，接受文件路径参数）。

**影响**：双轨上传接口返回的 `vocal_info` 和 `accompaniment_info` 始终为空或报错，因为将文件路径当作 hash 去查找任务。

**修复方案**：改为 `_get_audio_info(vocal_upload_path)` 和 `_get_audio_info(accompaniment_upload_path)`。

**涉及文件**：
- `backend/api/routes.py:504-505`

---

### BUG-3 [严重] `applySettings` 缺少 `algorithmVersion` 依赖，可能使用过期算法版本

**根因**：`useAudioProcessor.ts:1343` 的 `applySettings` useCallback 依赖数组为 `[audioBuffer, audioFile, params, processingOptions, loadAudioFromUrl, wavInfo]`，不包含 `algorithmVersion` 和 `availableAlgorithms`，但函数内部使用了这两个值。

**影响**：用户切换算法版本后（如果 `defaultParams` 为 undefined 导致 `setParams` 未被调用），`applySettings` 闭包中的 `algorithmVersion` 仍是旧值，导致用旧版本发起修复请求。

**修复方案**：将 `algorithmVersion` 和 `availableAlgorithms` 加入依赖数组。

**涉及文件**：
- `src/hooks/useAudioProcessor.ts:1343`

---

### BUG-4 [严重] `applyAlgorithmVersion` 未清除旧版本修复状态

**根因**：`useAudioProcessor.ts:244-263` 的 `applyAlgorithmVersion` 只清除了 `renderDownloadUrl`，未清除 `cacheHitInfo`、`backendProcessedBuffer`、`repairResult`、`hasBeenProcessed`、`backendPreviewUrl` 等。

**影响**：切换算法版本后，UI 仍显示旧版本的修复结果，播放的仍是旧版本音频，但文件名标注新版本。这是数据完整性 bug。

**修复方案**：在 `applyAlgorithmVersion` 中添加完整的状态清理。

**涉及文件**：
- `src/hooks/useAudioProcessor.ts:244-263`

---

### BUG-5 [中等] `renderAudio` 未传递 `algorithmVersion` 给后端

**根因**：`backendApi.ts:1640-1666` 的 `renderAudio` 函数不接收 `algorithmVersion` 参数。后端渲染端点从 task_params 中获取 `algorithm_version`（routes.py:1009），所以文件名中的版本是正确的。但前端渲染缓存查找时按 `algorithm_version` 匹配（useAudioProcessor.ts:1821），如果用户切换版本后未重新修复，缓存查找会 miss（因为 task 中存的还是旧版本），这是正确行为。

**实际影响**：影响有限，因为渲染缓存查找逻辑是正确的（版本不匹配会 miss 并重新渲染）。但传递 `algorithmVersion` 可以让后端做额外校验。

**修复方案**：在 `renderAudio` 函数中增加 `algorithmVersion` 参数，并在请求体中传递。后端可选择性使用。

**涉及文件**：
- `src/services/backendApi.ts:1640-1666`
- `src/hooks/useAudioProcessor.ts:1848`

---

### BUG-6 [中等] `forceRenderRef` 在 `applySettings` 后永不重置

**根因**：`useAudioProcessor.ts:1312` 设置 `forceRenderRef.current = true`，但在 `renderAndDownload` 成功完成后从未重置为 `false`。只有 `handleUseRepairCache`（第1962行）会重置它。

**影响**：首次修复后的所有 `renderAndDownload` 调用都会跳过渲染缓存检查（第1819行），每次都重新渲染，浪费后端资源。

**修复方案**：在 `renderAndDownload` 成功完成后重置 `forceRenderRef.current = false`。

**涉及文件**：
- `src/hooks/useAudioProcessor.ts:1878`

---

### BUG-7 [中等] `find_repair_cache` 的 `repair_param_keys` 缺少 v3.x 参数名

**根因**：`database.py:206-211` 的 `repair_param_keys` 只有 v2.x 时代的参数名（`de_clipping`、`de_essing` 等），缺少 v3.x 使用的参数名（`declip`、`de_ess`、`formant_repair`、`mastering_style` 等）。

**影响**：v3.x 单轨任务的缓存匹配时，v3.x 特有参数不在比较集合中，导致参数不同但缓存误命中。

**修复方案**：将 v3.x 参数名加入 `repair_param_keys`。

**涉及文件**：
- `backend/database.py:206-211`

---

### BUG-8 [低] 死代码 `_hf_protect`/`_spectral_hf_gate` 残留

**根因**：所有 v3.x 版本中 `_hf_protect` 和 `_spectral_hf_gate` 函数已定义但从未被调用。

**影响**：无运行时影响，但有误用风险。

**修复方案**：删除这些死代码函数。

**涉及文件**：
- `backend/services/repair/repair_v3_0/core.py`
- `backend/services/repair/repair_v3_0a/core.py`
- `backend/services/repair/repair_v3_1/core.py`
- `backend/services/repair/repair_v3_1a/core.py`

---

## 修复优先级

| 优先级 | Bug | 说明 |
|--------|-----|------|
| P0 | BUG-1 | v3.x 单轨修复核心功能失效 |
| P0 | BUG-2 | 双轨上传返回错误信息 |
| P0 | BUG-3 | 算法版本切换后修复请求可能用错版本 |
| P1 | BUG-4 | 版本切换后 UI 显示不一致 |
| P1 | BUG-7 | 缓存匹配参数不完整 |
| P2 | BUG-5 | 渲染请求未传版本（影响有限） |
| P2 | BUG-6 | forceRenderRef 不重置（性能浪费） |
| P3 | BUG-8 | 死代码清理 |

## 实施步骤

### Step 1: 修复 BUG-1 — v3.x 单轨参数名映射
在所有 v3.x 的 `_repair_single_track` 函数开头添加参数名映射：
```python
_SINGLE_KEY_MAP = {
    "de_clipping": "declip",
    "de_pop": "depop",
    "de_essing": "de_ess",
    "dynamic_range": "dynamic",
    "spatial_enhance": "spatial",
    "loudness_optimize": "loudness",
}
single_params = dict(params)
for src_key, dst_key in _SINGLE_KEY_MAP.items():
    if src_key in single_params and dst_key not in single_params:
        single_params[dst_key] = single_params[src_key]
```

### Step 2: 修复 BUG-2 — routes.py 函数调用错误
将 `get_audio_info` 改为 `_get_audio_info`。

### Step 3: 修复 BUG-3 — applySettings 依赖数组
添加 `algorithmVersion` 和 `availableAlgorithms` 到依赖数组。

### Step 4: 修复 BUG-4 — applyAlgorithmVersion 状态清理
添加完整的状态清理逻辑。

### Step 5: 修复 BUG-7 — 缓存 repair_param_keys 补全
添加 v3.x 参数名到 `repair_param_keys`。

### Step 6: 修复 BUG-5 — renderAudio 传递版本
在 `renderAudio` 函数中增加 `algorithmVersion` 参数。

### Step 7: 修复 BUG-6 — forceRenderRef 重置
在 `renderAndDownload` 成功完成后重置 `forceRenderRef.current = false`。

### Step 8: 修复 BUG-8 — 删除死代码
删除所有 v3.x 中的 `_hf_protect` 和 `_spectral_hf_gate` 函数定义。

### Step 9: 运行测试 + 打包
运行所有测试确认修复正确，然后打包 Android 发布包。
