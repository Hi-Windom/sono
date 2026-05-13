# 双轨架构修复计划

## 概述

双轨模式目前存在三个主要问题：预估大小不显示、渲染缓存卡片不显示、缓存命中不工作。经过对前后端代码的全面分析，发现这些问题源于双轨流程与单轨基础设施的耦合方式存在缺陷。

---

## 现状分析

### 双轨数据流

```
用户选择文件 → handleDualTrackUpload → uploadDualAudio (POST /upload-dual)
    ↓
dualTrackTaskId, dualTrackVocalInfo, dualTrackAccompanimentInfo 被设置
    ↓
用户点击修复 → handleDualTrackRepair → repairDualAudio (POST /repair-dual) → submit_repair_task → _run_repair
    ↓
startDualTrackPolling (WS 监听 repair 完成)
    ↓
WS onComplete → setTaskId(dualTrackTaskId) → renderAndDownload() → setCacheTriggerKey(k+1)
    ↓
AIRepairPanel 的 cacheTriggerKey 变化 → refreshRenderCache(dualTrackTaskId)
```

### 根因分析

#### 问题 1：预估大小不显示

**关键代码链：**
- [AIRepairPanel.tsx:L147-L152](file:///workspace/src/components/AIRepairPanel.tsx#L147-L152) — `effectiveDuration` 计算
- [AIRepairPanel.tsx:L312-L337](file:///workspace/src/components/AIRepairPanel.tsx#L312-L337) — `allEstimates` 依赖 `effectiveDuration`
- [AIRepairPanel.tsx:L593](file:///workspace/src/components/AIRepairPanel.tsx#L593) — 显示条件 `allEstimates.length > 0 || isDualTrackMode`
- [AIRepairPanel.tsx:L597](file:///workspace/src/components/AIRepairPanel.tsx#L597) — 实际估值渲染条件 `allEstimates.length > 0`

**根因：**
`effectiveDuration` 在双轨模式下依赖 `dualTrackVocalInfo` 和 `dualTrackAccompanimentInfo` 两者都非空。如果其中任何一个为 `null`（例如后端 `get_audio_info` 返回 `None`），`effectiveDuration` 会回退到 `duration`（单轨 duration），而双轨模式下单轨 `duration` 为 0，导致 `allEstimates` 返回空数组。

虽然 `isDualTrackMode` 为 true 时占位格会显示（"—"），但实际估值数字不显示。

**修复方向：** 当音频信息为空时，使用合理的默认值或直接从上传文件获取。

#### 问题 2：渲染缓存卡片不显示

**关键代码链：**
- [AIRepairPanel.tsx:L204-L211](file:///workspace/src/components/AIRepairPanel.tsx#L204-L211) — `refreshRenderCache` 使用 `taskId`
- [AIRepairPanel.tsx:L213-L223](file:///workspace/src/components/AIRepairPanel.tsx#L213-L223) — effect 依赖 `cacheTriggerKey` + `taskId`
- [AIRepairPanel.tsx:L600-L604](file:///workspace/src/components/AIRepairPanel.tsx#L600-L604) — 缓存匹配逻辑
- [RepairPage.tsx:L879](file:///workspace/src/components/RepairPage.tsx#L879) — `taskId={isDualTrackMode ? dualTrackTaskId : taskId}`

**根因：**
1. `renderAndDownload` 函数来自 `useAudioProcessor` hook，其 `taskIdRef.current` 由 `setTaskId(taskId)` 设置。但在 `startDualTrackPolling.onComplete` 中调用 `renderAndDownload()` 时，`taskIdRef.current` 已经被 `setTaskId(dualTrackTaskId)` 正确设置。这个路径理论上正确。

2. **潜在问题**：`renderAndDownload` 的依赖数组只有 `[audioFile]`。在双轨模式下 `audioFile` 为 `null`，导致 `renderAndDownload` 的闭包中 `audioFile?.name` 为 `undefined`。这不影响功能但文件名生成不正确。

3. **核心问题**：`renderAndDownload` 完成后 `setCacheTriggerKey(k => k + 1)` 确实会触发 `refreshRenderCache`。但 `refreshRenderCache` 是一个 `useCallback`，其依赖 `[taskId, backendAvailable]`。如果 `taskId`（即 `dualTrackTaskId`）在渲染完成前后没有变化，这个回调不会被重建，但 effect 仍然会因为 `cacheTriggerKey` 变化而触发执行 `refreshRenderCache`。这里存在闭包捕获的 taskId 可能是旧值的问题。

**修复方向：** 在双轨渲染完成后，显式调用 `refreshRenderCache` 而不是依赖 `cacheTriggerKey` 的副作用链。同时确保 `taskId` 在 AIRepairPanel 中的传播是可靠的。

#### 问题 3：缓存命中不工作

**关键代码链：**
- [RepairPage.tsx:L385-L408](file:///workspace/src/pages/RepairPage.tsx#L385-L408) — `lookupDualRepairCache` 调用
- [backendApi.ts:L791-L815](file:///workspace/src/services/backendApi.ts#L791-L815) — `lookupDualRepairCache` 函数
- [database.py:L209-L278](file:///workspace/backend/database.py#L209-L278) — `find_dual_repair_cache`
- [routes.py:L454-L461](file:///workspace/backend/api/routes.py#L454-L461) — 上传时主任务的 params 不含 `processing_mode='dual'`

**根因：**
`find_dual_repair_cache` 查询 `processing_mode='dual'` 的任务。但上传端点创建的主任务 **没有** 设置 `processing_mode='dual'`（只在修复端点的 params 中设置了）。缓存查找时使用的是上传时生成的 hash，但数据库中的任务 params 可能不匹配。

**修复方向：**
1. 上传端点在主任务 params 中添加 `processing_mode='dual'`
2. 完善 `find_dual_repair_cache` 的查询逻辑，确保能匹配到已修复的任务
3. 前端缓存查找后，如果找到缓存但 `task_id` 为空，需要正确处理

#### 问题 4：架构耦合问题

**关键耦合点：**
- `renderAndDownload` 来自 `useAudioProcessor`，依赖 `audioFile`、`taskIdRef` 等单轨状态
- `startDualTrackPolling` 的依赖数组包含 `renderAndDownload`、`setTaskId` 等
- AIRepairPanel 的 `taskId` prop 在双轨/单轨间切换
- `effectiveDuration` 回退到 `duration`（单轨 duration）

---

## 修复方案

### 修复 1：预估大小 - 确保 `effectiveDuration` 在双轨模式下始终有效

**文件：** [AIRepairPanel.tsx](file:///workspace/src/components/AIRepairPanel.tsx)

**修改内容：**
- 在 `effectiveDuration` 计算中，当 `isDualTrackMode` 为 true 但 `dualTrackVocalInfo`/`dualTrackAccompanimentInfo` 为空时，使用 `props.duration` 作为后备（而非当前的回退到单轨 `duration`）
- 如果 `props.duration` 也为 0，使用默认值 300 秒
- 同时确保 `effectiveChannels` 同理处理

```typescript
// 修改前
const effectiveDuration = useMemo(() => {
  if (isDualTrackMode && dualTrackVocalInfo && dualTrackAccompanimentInfo) {
    return Math.max(dualTrackVocalInfo.duration, dualTrackAccompanimentInfo.duration);
  }
  return duration;
}, [...]);

// 修改后
const effectiveDuration = useMemo(() => {
  if (isDualTrackMode) {
    if (dualTrackVocalInfo && dualTrackAccompanimentInfo) {
      return Math.max(dualTrackVocalInfo.duration, dualTrackAccompanimentInfo.duration);
    }
    return duration > 0 ? duration : 300;
  }
  return duration;
}, [...]);
```

### 修复 2：渲染缓存 - 在双轨模式下直接调用 `refreshRenderCache`

**文件：** [RepairPage.tsx](file:///workspace/src/pages/RepairPage.tsx)

**修改内容：**
- 在 `startDualTrackPolling.onComplete` 中，`renderAndDownload()` 完成后，除了 `setCacheTriggerKey`，还要通过 `renderCacheRefreshRef` 直接触发缓存刷新
- 确保 `renderCacheRefreshRef.current` 在 AIRepairPanel 挂载时被正确注册（已通过 `onRenderCacheRefresh={handleRegisterCacheRefresh}` 实现）

```typescript
// 在 onComplete 中添加
await renderAndDownload();
// 直接刷新渲染缓存
if (renderCacheRefreshRef.current) {
  await renderCacheRefreshRef.current();
}
setCacheTriggerKey(k => k + 1);
```

**文件：** [AIRepairPanel.tsx](file:///workspace/src/components/AIRepairPanel.tsx)

**修改内容：**
- 增加 `refreshRenderCache` 的 effect 依赖项，确保 `taskId` 变化时能正确重新获取缓存
- 修复 `refreshRenderCache` 的 `useCallback` 依赖数组，确保 `taskId` 变化时回调被正确重建
- 在双轨模式下，增加一个额外的 `useEffect` 监听 `dualTrackTaskId` 变化（通过 props 的 `taskId` 间接传递）

### 修复 3：缓存命中 - 上传时在主任务 params 中添加 `processing_mode='dual'`

**文件：** [routes.py](file:///workspace/backend/api/routes.py)

**修改内容：**
- 在 `/upload-dual` 端点创建主任务时，添加 `"processing_mode": "dual"` 到 params

```python
# 修改前 (L454-L461)
create_task(main_task_id, f"dual_{vocal_file.filename or 'audio'}", vocal_upload_path, {
    "vocal_task_id": vocal_task_id,
    "accompaniment_task_id": accompaniment_task_id,
    ...
}, file_hash, len(vocal_content) + len(accompaniment_content))

# 修改后
create_task(main_task_id, f"dual_{vocal_file.filename or 'audio'}", vocal_upload_path, {
    "processing_mode": "dual",
    "vocal_task_id": vocal_task_id,
    "accompaniment_task_id": accompaniment_task_id,
    ...
}, file_hash, len(vocal_content) + len(accompaniment_content))
```

### 修复 4：完善 `find_dual_repair_cache` 查询

**文件：** [database.py](file:///workspace/backend/database.py)

**修改内容：**
- 确保 `find_dual_repair_cache` 能正确处理 `processing_mode` 存储在 params 字段中的情况
- 添加更多的查询条件匹配（如 vocal_file_hash, accompaniment_file_hash 的位置是否在 params 或顶层）

### 修复 5：增加完整的双轨日志和错误处理

**文件：** [RepairPage.tsx](file:///workspace/src/pages/RepairPage.tsx), [AIRepairPanel.tsx](file:///workspace/src/components/AIRepairPanel.tsx)

**修改内容：**
- 在 `handleDualTrackUpload` 成功后，添加日志记录 `dualTrackVocalInfo` 和 `dualTrackAccompanimentInfo` 的值
- 在 `startDualTrackPolling.onComplete` 中，添加每一步的关键日志
- 在 `refreshRenderCache` 中添加日志，记录 taskId 和缓存结果
- 在 `effectiveDuration` 计算中添加日志（开发模式）

### 修复 6：AIRepairPanel 修复闭包问题

**文件：** [AIRepairPanel.tsx](file:///workspace/src/components/AIRepairPanel.tsx)

**修改内容：**
- 将 `refreshRenderCache` 改为使用 ref 模式，避免闭包捕获过时的 `taskId`
- 或确保 `taskId` 变化时，`refreshRenderCache` 被正确重建

---

## 涉及文件

| 文件 | 修改内容 |
|------|---------|
| `src/components/AIRepairPanel.tsx` | 修复 `effectiveDuration` 回退逻辑；修复 `refreshRenderCache` 闭包问题；增加日志 |
| `src/pages/RepairPage.tsx` | 在 `startDualTrackPolling.onComplete` 中直接调用 `refreshRenderCache`；增加日志 |
| `backend/api/routes.py` | 上传端点添加 `processing_mode='dual'` |
| `backend/database.py` | 完善 `find_dual_repair_cache` 查询逻辑 |

---

## 验证步骤

1. **手动测试：**
   - 启动 dev 服务
   - 进入修复页面，切换到双轨模式
   - 上传人声和伴奏文件
   - 确认 AIRepairPanel 显示预估大小（而非 "—"）
   - 点击"双轨修复"，等待修复 + 渲染完成
   - 确认预估大小表格中显示绿色圆点（缓存命中）
   - 刷新页面，重新上传相同文件
   - 确认缓存命中提示弹出

2. **日志验证：**
   - 在浏览器 console 中查看双轨相关日志
   - 确认 `effectiveDuration` 值正确
   - 确认 `refreshRenderCache` 被正确调用
   - 确认 `renderCache` 数据正确返回

---

## 假设与决策

1. **定向修复而非重构**：用户选择了"定向修复"方案，因此不做大规模架构重构
2. **最小改动原则**：每处修改只针对具体问题，不引入额外变更
3. **兼容性**：所有修改向后兼容，不影响现有单轨功能