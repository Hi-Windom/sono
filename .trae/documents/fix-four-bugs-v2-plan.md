# 修复计划：4个Bug修复方案 v2

## 当前状态分析

### Bug 1: MP3 下载转换失败（MPEGMode is not defined）
**状态：已修复 ✅**
- `src/utils/mp3Encoder.ts` 和 `src/workers/mp3EncoderWorker.ts` 已删除
- `package.json` 中 `lamejs` 依赖已移除
- 后端新增 `GET /api/v1/download-mp3/{task_id}` 端点，使用 ffmpeg 转码
- `DownloadModal.tsx` 中 `handleDownloadMp3` 已改为调用后端端点
- **无需额外操作**

### Bug 2: ComparePage 直接访问没有更新记录
**状态：代码逻辑正确，但需验证**
- 后端 `/api/v1/cache/info` 返回所有任务（不按 `output_exists` 过滤）
- 前端 `fetchTaskList` 在无 taskId 时获取所有任务并展示
- 过期任务显示"文件已过期"（黄色），可点击任务显示"已修复"（绿色）
- WebSocket 持久连接（ref-based，不关闭）
- **潜在问题**：`fetchTaskList` 使用 `useCallback([], [])`，`useEffect` 依赖 `[taskId, fetchTaskList]`。当直接访问（无 taskId）时，`taskId` 为 `''`（falsy），effect 应正常触发。需确认是否有其他竞态条件。

### Bug 3: 双轨修复缓存命中依旧没生效 ⚠️
**状态：发现根因，需要修复**
- `find_dual_repair_cache` 使用子集匹配（`stored_subset == input_subset`）
- 但输入参数和存储参数的 key 集合不一致：
  - **输入参数**（来自 `mapParamsToBackend`）：使用旧式 key（`de_clipping`, `noise_reduction` 等）+ `algorithm_version`
  - **存储参数**（来自数据库）：使用新式 key（`vocal_declip`, `inst_loudness`, `mastering_style` 等）
  - `repair_param_keys` 包含 `algorithm_version` 但输入有而存储没有 → 不匹配
  - `repair_param_keys` 包含 `mastering_style` 但存储有而输入没有 → 不匹配
- **根因**：严格相等比较要求两边 key 集合完全一致，但实际两边 key 集合不同
- **修复方案**：改为交集比较（只比较两边都有的 key）

### Bug 4: 移动端 v3.1a 母带风格
**状态：部分修复，仍有遗漏**
- `default_params` 中 `mastering_style` 已改为 `"standard"` ✅
- 但 v3.1a 的"快速处理"预设模式仍为 `"mastering_style": "none"` ❌
- **修复方案**：将"快速处理"模式的 `mastering_style` 改为 `"standard"`

---

## 需要修改的文件

### 1. `backend/database.py` — 双轨缓存匹配修复

**问题**：`find_dual_repair_cache` 使用 `stored_subset == input_subset` 严格相等比较，但两边 key 集合不同（输入有 `algorithm_version` 而存储没有，存储有 `mastering_style` 而输入没有）。

**修复**：将严格相等比较改为交集比较，只比较两边都有的 key。

```python
# 修改前
if stored_subset == input_subset:

# 修改后
common_keys = stored_subset.keys() & input_subset.keys()
if all(stored_subset[k] == input_subset[k] for k in common_keys):
```

同时移除 `algorithm_version`、`sample_rate`、`bit_depth` 从 `repair_param_keys`（这些是元参数，不应作为修复参数匹配依据）。

### 2. `backend/services/audio_repair.py` — v3.1a 快速处理母带风格

**问题**：v3.1a "快速处理"预设模式的 `mastering_style` 为 `"none"`。

**修复**：将 `"mastering_style": "none"` 改为 `"mastering_style": "standard"`。

### 3. `src/pages/ComparePage.tsx` — 验证任务列表加载

**问题**：需确认直接访问时任务列表能正确加载。

**修复**：增加 `useEffect` 的健壮性，确保在组件挂载时无论 `taskId` 状态如何都能获取任务列表。同时添加 `original_exists` 到 `CacheTask` 接口，确保前端能正确判断文件状态。

---

## 验证步骤

1. **MP3 下载**：在 DownloadModal 中点击 MP3 下载按钮，确认后端 ffmpeg 转码成功，文件可正常下载
2. **ComparePage**：直接访问 `/compare` 页面，确认能看到所有历史修复任务（包括已过期的）
3. **双轨缓存**：执行双轨修复，确认第二次相同参数时能命中缓存（查看后端日志 `[cache-lookup-dual]`）
4. **v3.1a 母带**：选择 v3.1a "快速处理"模式，确认 `mastering_style` 为 `"standard"` 而非 `"none"`
5. **构建验证**：`npm run build` 通过
6. **Android 打包**：`bash scripts/build_android_release.sh` 通过