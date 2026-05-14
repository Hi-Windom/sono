# 双轨模式三问题修复计划

## 摘要

修复双轨模式中的三个问题：
1. 算法列表错误显示不支持双轨的算法（v1.x/v2.x）
2. 预估大小和渲染交付不生效（`fetchMemoryInfo`/`fetchStorageEstimate` 用了单轨的 `duration`/`channels` 而非双轨的 `effectiveDuration`/`effectiveChannels`）
3. 切换单轨时不应清除双轨状态（`clearDualTrack()` 清空了所有数据）

## 当前状态分析

### Issue 1: 算法列表错误显示

- **根因**: [AIRepairPanel.tsx:164](file:///workspace/src/components/AIRepairPanel.tsx#L164) — `const filteredAlgorithms = availableAlgorithms;` — 完全不过滤
- **期望行为**: 双轨模式下只显示 v3+ 算法（v3.0, v3.0a, v3.1, v3.1a）
- **判断依据**: 算法名称以 `v3` 开头即为支持双轨（与后端设计一致，v3+ 才有独立的人声/伴奏效果器参数）

### Issue 2: 预估大小和渲染交付不生效

- **根因**: [AIRepairPanel.tsx:175-201](file:///workspace/src/components/AIRepairPanel.tsx#L175-L201) — `fetchMemoryInfo` 和 `fetchStorageEstimate` 使用 `duration`/`channels` props（来自单轨上下文，可能为 0），而非 `effectiveDuration`/`effectiveChannels`（已正确计算双轨的有效时长和通道数）
- **currentEstimate 和 allEstimates** 已正确使用 `effectiveDuration`/`effectiveChannels`（line 282-318），所以前端计算是准的，但后端 API 查询参数错误导致返回空
- **渲染缓存刷新** 依赖 `taskId`，双轨修复前 `taskId` 为 null，但 `persistedRenderCaches` 已通过 Issue 3b 传入。然而 `refreshRenderCache` 在 `taskId` 为 null 时直接返回空数组并覆盖了 persisted 值。需要特殊处理。

### Issue 3: 切换单轨不应清除双轨状态

- **根因**: [RepairPage.tsx:270-281](file:///workspace/src/pages/RepairPage.tsx#L270-L281) — `handleSwitchToSingleTrack` 调用 `sessionActions.clearDualTrack()`，它同时设置了 `isDualTrackMode: false` 并清空了所有双轨数据
- **期望行为**: 切换单轨只改变模式标志，不丢失双轨文件/元数据/渲染缓存等状态，以便用户切回双轨时恢复

## 修改计划

### 修改 1: repairSessionStore.ts — 新增 `disableDualTrackMode` 方法

**文件**: `/workspace/src/store/repairSessionStore.ts`

- 新增 `disableDualTrackMode` action：只设置 `isDualTrackMode: false`，不清除任何数据
- `clearDualTrack` 保持不变（用于真正需要清除时）

### 修改 2: AIRepairPanel.tsx — 算法过滤 + 预估 API 参数修正 + 渲染缓存初始化保护

**文件**: `/workspace/src/components/AIRepairPanel.tsx`

**2a. 算法过滤** (line 164):
```typescript
const filteredAlgorithms = useMemo(() => {
  if (isDualTrackMode) {
    return availableAlgorithms.filter(a => a.name.startsWith('v3'));
  }
  return availableAlgorithms;
}, [isDualTrackMode, availableAlgorithms]);
```

**2b. 预估 API 参数修正** (lines 175-201):
将 `fetchMemoryInfo` 和 `fetchStorageEstimate` 的 `duration`/`channels` 参数替换为 `effectiveDuration`/`effectiveChannels`，并在依赖数组中加入 `effectiveDuration`/`effectiveChannels`：

```typescript
// fetchMemoryInfo 的 useEffect (line 175-187)
const fetchDuration = effectiveDuration > 0 ? effectiveDuration : 300;
const fetchChannels = effectiveChannels > 0 ? effectiveChannels : 2;
// ... 依赖数组: [effectiveDuration, effectiveChannels, ...]

// fetchStorageEstimate 的 useEffect (line 189-201)  
const fetchDuration = effectiveDuration > 0 ? effectiveDuration : 300;
const fetchChannels = effectiveChannels > 0 ? effectiveChannels : 2;
// ... 依赖数组: [effectiveDuration, effectiveChannels, ...]
```

**2c. 渲染缓存初始化保护** (lines 203-225):
`refreshRenderCache` 在 `taskId` 为 null 时不应清空已持久化的渲染缓存：

```typescript
const refreshRenderCache = useCallback(async () => {
  if (!taskId || !backendAvailable) {
    // 不清空：保持 persistedRenderCaches 的值
    return;
  }
  // ... 其余不变
}, [taskId, backendAvailable]);
```

对应的 `useEffect`（line 215-225）也需要保护：
```typescript
useEffect(() => {
  if (!taskId || !backendAvailable) {
    return; // 不清空 renderCaches
  }
  // ... 其余不变
}, [taskId, backendAvailable, algorithmVersion, refreshRenderCache, cacheTriggerKey]);
```

### 修改 3: RepairPage.tsx — 切换单轨不清理双轨状态

**文件**: `/workspace/src/pages/RepairPage.tsx`

**3a. `handleSwitchToSingleTrack`** (lines 270-281):
将 `sessionActions.clearDualTrack()` 替换为仅清除本地 React state 和停止轮询，同时使用 `sessionActions.setDualTrackMode(false)` 仅关闭模式标志：

```typescript
const handleSwitchToSingleTrack = useCallback(() => {
  // 仅切换模式标志，保留双轨数据以便切回
  sessionActions.setDualTrackMode(false);
  // 清除临时运行时状态
  setDualTrackTaskId(null);
  setDualTrackVocalTaskId(null);
  setDualTrackAccompanimentTaskId(null);
  setDualTrackDownloadUrl(null);
  setDualTrackRepairResult(null);
  stopDualTrackPolling();
}, [stopDualTrackPolling, sessionActions]);
```

注意：不再清除 `setDualTrackFilesSelected(false)`，保留 `dualTrackVocalFile`/`dualTrackAccompanimentFile` 等运行时 File 对象（刷新后由 store 恢复）。

**3b. 双轨模式切换按钮** (lines 608-636):
单轨按钮的 `onClick` 中需要将 `handleSwitchToSingleTrack` 改为仅调用模式切换。当前逻辑：点击单轨按钮时如果当前是双轨模式则调用 `handleSwitchToSingleTrack`。修改后 `handleSwitchToSingleTrack` 不再清数据，所以可以直接保留这个调用。

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `src/store/repairSessionStore.ts` | 新增 `disableDualTrackMode` action（或复用 `setDualTrackMode(false)`，因为 `setDualTrackMode` 已经只改标志） |
| `src/components/AIRepairPanel.tsx` | 2a: `filteredAlgorithms` 加 `useMemo` 过滤 v3+；2b: `fetchMemoryInfo`/`fetchStorageEstimate` 用 `effectiveDuration`/`effectiveChannels`；2c: `refreshRenderCache` 不覆盖持久化缓存 |
| `src/pages/RepairPage.tsx` | `handleSwitchToSingleTrack` 不再调 `clearDualTrack()`，只停轮询 + 清临时 taskId state |

## 验证

1. TypeScript 编译 `npx tsc --noEmit` 零错误
2. 双轨模式下算法下拉框只显示 v3.0/v3.0a/v3.1/v3.1a
3. 双轨上传后，预估大小区域正常显示数值
4. 双轨修复后，渲染交付列表正常显示
5. 切换到单轨 → 再切回双轨 → 文件/元数据/参数/渲染缓存仍在
6. 打包 `bash scripts/build_android_release.sh` 成功