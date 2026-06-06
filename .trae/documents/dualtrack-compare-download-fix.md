# 双轨播放页对比 + 下载交付 + 状态恢复 修复计划

## 问题分析

用户反馈 3 个核心问题：

### 问题 1：ComparePage 没有显示人声/伴奏/合并切换 UI

**根因**：ComparePage 有两个 useEffect 存在竞态：

```js
// useEffect A: taskId 变化时重置 dualTrackMode
useEffect(() => { setDualTrackMode(null); }, [taskId]);

// useEffect B: isDualTrackTask 变化时设置 dualTrackMode
useEffect(() => {
  if (isDualTrackTask && dualTrackMode === null) setDualTrackMode('merged');
  else if (!isDualTrackTask && dualTrackMode !== null) setDualTrackMode(null);
}, [isDualTrackTask, dualTrackMode]);
```

当 `taskId` 变化 → useEffect A 将 `dualTrackMode` 设为 `null` → `taskInfo` 异步加载 → `isDualTrackTask` 变为 `true` → useEffect B 设 `dualTrackMode = 'merged'`。理论上可以工作，但 `isDualTrackTask` 依赖 `dualTrackSubIds`，而 `dualTrackSubIds` 依赖 `taskInfo`。如果 `taskInfo` 的 params 解析失败（JSON 字符串格式问题），`dualTrackSubIds` 为空，`isDualTrackTask` 为 false，UI 永远不显示。

**关键问题**：URL 带 `mode=dual` 时 `isDualTrackTask = true`，但 `dualTrackSubIds` 可能为空（params 解析失败），导致 `effectiveTaskId` 回退到主任务 ID，人声/伴奏切换后无法播放单独轨道。

### 问题 2：ComparePage 不应该有下载功能

**用户明确要求**：ComparePage 仅做 AB 对比播放，下载功能统一在 RepairPage 的 AIRepairPanel 渲染缓存区域完成。

**当前错误**：我在 ComparePage 中添加了简陋的 `handleRenderAndDownload` + "下载修复结果"按钮，需要删除。

### 问题 3：前端状态恢复不带双轨

**当前问题**：单轨模式通过 `sessionDB`（IndexedDB）保存 File 对象 + fileHash + taskId，页面刷新后从后端下载原始音频恢复。但双轨模式完全没有这个机制：
- `isDualTrackMode` 刷新后丢失
- 双轨文件名丢失
- 双轨参数已保存但模式开关丢失

**用户要求**：和单轨一致，用 fileHash 恢复显示文件名，不恢复 task。

## 修改方案

### 修改 1：ComparePage 双轨切换 UI 可靠显示

**文件**：`/workspace/src/pages/ComparePage.tsx`

1. **移除竞态 useEffect**：删除 `useEffect(() => { setDualTrackMode(null); }, [taskId])`
2. **合并 dualTrackMode 初始化逻辑**：在 `isDualTrackTask` 的 useMemo 中直接处理，或用单一 useEffect
3. **增强 dualTrackSubIds 解析**：增加 `processing_mode === 'dual'` 检查，以及从 URL searchParams 读取 sub-task IDs 的后备方案
4. **删除简陋下载代码**：删除 `isRenderLoading`、`renderError`、`handleRenderAndDownload`、"下载修复结果"按钮

### 修改 2：RepairPage 双轨状态恢复（与单轨一致）

**文件**：`/workspace/src/pages/RepairPage.tsx`，`/workspace/src/utils/settingsStorage.ts`

单轨恢复流程：`sessionDB` 保存 File + fileHash + taskId → 刷新后 `useAudioProcessor` 的 useEffect 从后端下载原始音频恢复 File 对象。

双轨恢复流程（对标单轨）：
1. **settingsStorage 增加**：`isDualTrackMode`（boolean）、`dualTrackVocalFileName`、`dualTrackAccompanimentFileName`、`dualTrackVocalFileHash`、`dualTrackAccompanimentFileHash`
2. **RepairPage 初始化**：从 localStorage 读取 `isDualTrackMode`，如果是双轨模式，读取文件名和 fileHash
3. **文件名恢复显示**：有 fileHash 时通过 `/api/v1/audio-info/{fileHash}` 获取文件信息，在 UI 上显示文件名（标注"已上传"）
4. **不恢复 task**：用户明确说 task 不恢复，刷新后需要重新上传和修复
5. **保存时机**：上传成功后保存 fileHash 和 fileName 到 localStorage

### 修改 3：RepairPage 双轨下载交付（复用单轨渲染缓存流程）

**文件**：`/workspace/src/pages/RepairPage.tsx`，`/workspace/src/components/AIRepairPanel.tsx`

当前单轨的下载交付流程：
1. 修复完成 → `renderAndDownload()` 自动触发渲染
2. AIRepairPanel 显示渲染缓存列表（`renderCaches`），可秒下
3. 点击秒下 → `handleRenderCacheDownload()` → 设置 `renderDownloadUrl` + `instantDownloadInfo` → 打开 `DownloadModal`

双轨需要复用这个流程：
1. 双轨修复完成后，调用 `renderAndDownload()` 渲染主任务（合并结果）
2. AIRepairPanel 的渲染缓存区域对双轨任务同样生效
3. 不需要额外的下载按钮

## 具体实现步骤

### Step 1: ComparePage — 修复双轨切换 UI + 删除下载代码

1. 删除 `useEffect(() => { setDualTrackMode(null); }, [taskId])`
2. 修改 `isDualTrackTask` 的 useMemo：增加 `processing_mode === 'dual'` 检查
3. 修改 `dualTrackMode` 初始化：在 `isDualTrackTask` 变化时统一处理（不再依赖两个 useEffect 竞态）
4. 增强 `dualTrackSubIds` 解析：增加对 `processing_mode` 的检查，如果 params 中有 `processing_mode === 'dual'` 但没有 `vocal_task_id`，尝试从 `/tracks/{taskId}` API 获取
5. 删除 `isRenderLoading`、`renderError` 状态
6. 删除 `handleRenderAndDownload` 函数
7. 删除"下载修复结果"按钮区域

### Step 2: settingsStorage — 增加双轨状态字段

1. `AppSettings` 接口增加：`isDualTrackMode: boolean`、`dualTrackVocalFileName: string`、`dualTrackAccompanimentFileName: string`、`dualTrackVocalFileHash: string`、`dualTrackAccompanimentFileHash: string`
2. `defaultSettings` 增加默认值
3. `loadSettings` 增加合并逻辑

### Step 3: RepairPage — 双轨状态恢复

1. 初始化 `isDualTrackMode` 从 localStorage 读取
2. 初始化文件名显示状态：`dualTrackVocalFileName`、`dualTrackAccompanimentFileName`
3. 上传成功后保存 fileHash + fileName 到 localStorage
4. 如果有文件名但没有 File 对象，在 UI 上显示文件名（标注"已上传，可直接修复"或"需重新上传"）
5. 双轨模式切换时保存 `isDualTrackMode` 到 localStorage

### Step 4: RepairPage — 双轨修复完成后触发渲染

1. 双轨修复完成后（`startDualTrackPolling` 中 status === 'completed'），调用 `renderAndDownload()` 触发渲染
2. 确保 AIRepairPanel 的渲染缓存区域对双轨任务同样生效（传入正确的 taskId）

### Step 5: 构建验证

1. `npm run build`
2. 验证 dist 产物包含新代码
3. `bash scripts/build_android_release.sh`
4. 验证 tar.gz 包含新代码

## 验证标准

1. ComparePage：双轨任务 URL 带 `mode=dual` 时，人声/伴奏/合并 3 个切换按钮可见且可点击
2. ComparePage：切换人声/伴奏时，音频源切换到对应子任务的 original/repaired
3. ComparePage：无下载按钮，下载回修复页
4. RepairPage：刷新页面后双轨模式开关保持、文件名显示
5. RepairPage：双轨修复完成后自动触发渲染，AIRepairPanel 渲染缓存可秒下
