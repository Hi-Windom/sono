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
- `find_dual_repair_cache` 使用 `stored_subset == input_subset` 严格相等比较
- 但输入参数和存储参数的 key 集合不一致：
  - **输入参数**（来自 `mapParamsToBackend`）：使用旧式 key（`de_clipping`, `noise_reduction` 等）+ `algorithm_version`
  - **存储参数**（来自数据库）：使用新式 key（`vocal_declip`, `inst_loudness`, `mastering_style` 等）
  - `repair_param_keys` 包含 `algorithm_version` → 输入有但存储没有 → 不匹配
  - `repair_param_keys` 包含 `mastering_style` → 存储有但输入没有 → 不匹配
- **根因**：严格相等比较要求两边 key 集合完全一致，但实际两边 key 集合不同
- **修复方案**：改为交集比较（只比较两边都有的 key），移除 `algorithm_version`/`sample_rate`/`bit_depth` 从 `repair_param_keys`

### Bug 4: 移动端 v3.1a 也要有母带风格 ⚠️
**状态：发现根因，需要修复**

经过全面代码搜索发现：**整个前端（桌面端+移动端）都没有母带风格选择器 UI！**

- `ProcessingOptions` 接口定义了 `masteringStyle?: 'standard' | 'powerful' | 'warm'`（`backendApi.ts:63`）
- 但 `defaultProcessingOptions` 没有包含 `masteringStyle`（`useAudioProcessor.ts:54-57`）
- AIRepairPanel 的"交付规格"区域只有采样率和位深选择器，**没有母带风格选择器**
- `renderAudio` 调用时 `masteringStyle` 始终为 `undefined`，后端默认用 `'standard'`
- 用户无法在前端选择母带风格（标准/强力/温暖）

**需要**：在 AIRepairPanel 的"交付规格"区域添加母带风格选择器

---

## 需要修改的文件

### 1. `backend/database.py` — 双轨缓存匹配修复

**问题**：`find_dual_repair_cache` 使用 `stored_subset == input_subset` 严格相等比较，但两边 key 集合不同。

**修复**：将严格相等比较改为交集比较，只比较两边都有的 key。

```python
# 修改前
if stored_subset == input_subset:

# 修改后
common_keys = stored_subset.keys() & input_subset.keys()
if common_keys and all(stored_subset[k] == input_subset[k] for k in common_keys):
```

同时从 `repair_param_keys` 中移除 `algorithm_version`、`sample_rate`、`bit_depth`（这些是元参数，存储侧不一定有，不应作为修复参数匹配依据）。

### 2. `backend/services/audio_repair.py` — v3.1a 快速处理母带风格

**问题**：v3.1a "快速处理"预设模式的 `mastering_style` 为 `"none"`。

**修复**：将 `"mastering_style": "none"` 改为 `"mastering_style": "standard"`。

### 3. `src/components/AIRepairPanel.tsx` — 新增母带风格选择器 ⭐

**问题**：前端完全没有母带风格选择 UI，用户无法选择标准/强力/温暖母带风格。

**修复**：在"交付规格"区域的采样率和位深选择器下方，新增母带风格选择器：

```tsx
{/* 母带风格选择器 */}
<div className="mt-3">
  <label className="text-gray-400 text-xs mb-2 block">母带风格</label>
  <div className="flex gap-2">
    {masteringOptions.map((option) => {
      const isSelected = (processingOptions.masteringStyle || 'standard') === option.value;
      return (
        <button key={option.value} onClick={() => onOptionsChange?.({ ...processingOptions, masteringStyle: option.value })}
          className={`flex-1 py-1.5 px-2 rounded-lg text-xs transition-all ${isSelected ? 'bg-secondary/30 text-white border border-secondary/50' : 'bg-primary/30 text-gray-400 border border-gray-700 hover:border-secondary/30'}`}
        >
          {option.label}
        </button>
      );
    })}
  </div>
</div>
```

母带风格选项：
- `standard` → 标准母带（推荐）
- `powerful` → 强力母带
- `warm` → 温暖母带

### 4. `src/hooks/useAudioProcessor.ts` — 默认母带风格

**问题**：`defaultProcessingOptions` 没有包含 `masteringStyle`。

**修复**：添加默认母带风格为 `'standard'`。

```typescript
export const defaultProcessingOptions: ProcessingOptions = {
  sampleRate: 48000,
  bitDepth: 24,
  masteringStyle: 'standard',
};
```

### 5. `src/pages/ComparePage.tsx` — 验证任务列表加载

**问题**：需确认直接访问时任务列表能正确加载。

**修复**：增加 `useEffect` 的健壮性，确保在组件挂载时无论 `taskId` 状态如何都能获取任务列表。同时添加 `original_exists` 到 `CacheTask` 接口。

---

## 验证步骤

1. **MP3 下载**：在 DownloadModal 中点击 MP3 下载按钮，确认后端 ffmpeg 转码成功，文件可正常下载
2. **ComparePage**：直接访问 `/compare` 页面，确认能看到所有历史修复任务（包括已过期的）
3. **双轨缓存**：执行双轨修复，确认第二次相同参数时能命中缓存（查看后端日志 `[cache-lookup-dual]`）
4. **母带风格 UI**：AIRepairPanel 的"交付规格"区域显示母带风格选择器（标准/强力/温暖），切换后渲染输出应用对应风格
5. **构建验证**：`npm run build` 通过
6. **Android 打包**：`bash scripts/build_android_release.sh` 通过