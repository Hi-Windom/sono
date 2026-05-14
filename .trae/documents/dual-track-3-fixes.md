# 双轨模式三问题修复计划 (v2)

## 摘要

修复双轨模式中的三个问题：
1. 算法列表错误显示不支持双轨的算法 — 后端算法声明 `supports_dual_track` 字段，前端据此过滤
2. 预估大小不生效 + 渲染交付不生效 — API 参数修正 + 后端主动查询渲染缓存 + WebSocket 推送通知
3. 切换单轨时不应清除双轨状态

---

## Issue 1: 算法列表错误显示不支持双轨的算法

### 根因
[AIRepairPanel.tsx:164](file:///workspace/src/components/AIRepairPanel.tsx#L164) — `const filteredAlgorithms = availableAlgorithms;` 完全不过滤。双轨模式下显示了 v1.x/v2.x 等不支持的算法。

### 修复方案：后端声明 + 前端过滤

**Step 1 — 后端**: 在 `ALGORITHM_VERSIONS` 中为每个算法添加 `supports_dual_track` 字段
- v3.0, v3.0a, v3.1, v3.1a → `True`（有独立人声/伴奏效果器）
- 其余全部 → `False`

**文件**: `backend/services/audio_repair.py`

```python
# 在每个算法字典中添加：
"supports_dual_track": True,   # v3.x 系列
"supports_dual_track": False,  # v1.x/v2.x 系列
```

**Step 2 — 后端 API**: 在 `get_available_versions()` 输出中包含 `supportsDualTrack`

```python
version_data = {
    ...
    "supportsDualTrack": v.get("supports_dual_track", False),
}
```

**Step 3 — 前端类型**: 在 `AlgorithmVersion` 接口中添加字段

**文件**: `src/services/backendApi.ts`
```typescript
export interface AlgorithmVersion {
  ...
  supportsDualTrack?: boolean;
}
```

**Step 4 — 前端过滤**: 在 `AIRepairPanel.tsx` 中根据 `supportsDualTrack` 过滤

```typescript
const filteredAlgorithms = useMemo(() => {
  if (isDualTrackMode) {
    return availableAlgorithms.filter(a => a.supportsDualTrack === true);
  }
  return availableAlgorithms;
}, [isDualTrackMode, availableAlgorithms]);
```

---

## Issue 2: 预估大小不生效 + 渲染交付不生效

### 根因分析

**2a. 预估大小**: [AIRepairPanel.tsx:175-201](file:///workspace/src/components/AIRepairPanel.tsx#L175-L201) — `fetchMemoryInfo`/`fetchStorageEstimate` 使用 `duration`/`channels` props（来自单轨上下文，可能为 0），而非已正确计算的 `effectiveDuration`/`effectiveChannels`。

**2b. 渲染交付**:
- 页面刷新后 `dualTrackTaskId` 丢失，无法调用 `fetchRenderCache(taskId)`
- 当前只从 localStorage 恢复 `persistedRenderCaches`，但这是静态快照，不会更新
- 后端已有 `broadcast_render_cache_update` WebSocket 推送（[ws_manager.py:74-80](file:///workspace/backend/services/ws_manager.py#L74-L80)），渲染完成后会广播 `render_cache_updated` 事件
- 前端 `RepairPage` 未监听此事件（只有 `CacheManagerPage` 在监听）

### 修复方案

**2a. API 参数修正**

**文件**: `src/components/AIRepairPanel.tsx`

将两个 useEffect 中的 `duration`/`channels` 替换为 `effectiveDuration`/`effectiveChannels`：

```typescript
// fetchMemoryInfo useEffect
useEffect(() => {
  if (!backendAvailable) { setMemoryInfo(null); return; }
  const fetchDuration = effectiveDuration > 0 ? effectiveDuration : 300;
  const fetchChannels = effectiveChannels > 0 ? effectiveChannels : 2;
  if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current);
  memoryFetchRef.current = setTimeout(() => {
    fetchMemoryInfo(fetchDuration, fetchChannels, processingOptions.sampleRate, algorithmVersion).then(setMemoryInfo);
  }, 300);
  return () => { if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current); };
}, [effectiveDuration, effectiveChannels, processingOptions.sampleRate, algorithmVersion, backendAvailable]);

// fetchStorageEstimate useEffect
useEffect(() => {
  if (!backendAvailable) { setStorageEstimate(null); return; }
  const fetchDuration = effectiveDuration > 0 ? effectiveDuration : 300;
  const fetchChannels = effectiveChannels > 0 ? effectiveChannels : 2;
  if (storageFetchRef.current) clearTimeout(storageFetchRef.current);
  storageFetchRef.current = setTimeout(() => {
    fetchStorageEstimate(fetchDuration, fetchChannels, processingOptions.sampleRate, processingOptions.bitDepth).then(setStorageEstimate);
  }, 300);
  return () => { if (storageFetchRef.current) clearTimeout(storageFetchRef.current); };
}, [effectiveDuration, effectiveChannels, processingOptions.sampleRate, processingOptions.bitDepth, backendAvailable]);
```

**2b. 渲染缓存初始化保护**

`refreshRenderCache` 在 `taskId` 为 null 时不应清空已有缓存（覆盖 persisted 值）：

```typescript
const refreshRenderCache = useCallback(async () => {
  if (!taskId || !backendAvailable) {
    return; // 不清空，保持 persistedRenderCaches
  }
  const caches = await fetchRenderCache(taskId);
  setRenderCaches(caches);
  onRenderCachesLoaded?.(caches);
}, [taskId, backendAvailable]);

// 对应 useEffect
useEffect(() => {
  if (!taskId || !backendAvailable) {
    return; // 不清空 renderCaches
  }
  if (cacheCheckRef.current) clearTimeout(cacheCheckRef.current);
  cacheCheckRef.current = setTimeout(refreshRenderCache, 500);
  return () => { if (cacheCheckRef.current) clearTimeout(cacheCheckRef.current); };
}, [taskId, backendAvailable, algorithmVersion, refreshRenderCache, cacheTriggerKey]);
```

**2c. 刷新后主动查询渲染缓存**

**文件**: `src/pages/RepairPage.tsx`

在 mount 时，如果双轨有文件哈希但无 taskId，通过 `lookupDualRepairCache` 查找 repair 任务 → 获取 taskId → 查询渲染缓存：

```typescript
// 新增 useEffect：刷新后恢复双轨渲染缓存
useEffect(() => {
  if (!isDualTrackMode || !dualTrackVocalFileHash || !dualTrackAccompanimentFileHash) return;
  if (dualTrackTaskId) return; // 已有 taskId，AIRepairPanel 会自动查询
  
  let cancelled = false;
  (async () => {
    try {
      const mainParams = mapParamsToBackend(params, processingOptions, algorithmVersion);
      const vParams = mapVocalParamsToBackend(dualTrackVocalParams, processingOptions, algorithmVersion);
      const aParams = mapInstrumentParamsToBackend(dualTrackAccompanimentParams, processingOptions, algorithmVersion);
      const cacheResult = await lookupDualRepairCache(dualTrackVocalFileHash, dualTrackAccompanimentFileHash, {
        params: mainParams,
        vocal_params: vParams,
        accompaniment_params: aParams,
        mix_ratio: mixRatio,
      });
      if (cancelled) return;
      if (cacheResult.found && cacheResult.task_id) {
        setDualTrackTaskId(cacheResult.task_id);
        setTaskId(cacheResult.task_id);
        // taskId 设置后 AIRepairPanel 的 refreshRenderCache 会自动触发
      }
    } catch {}
  })();
  return () => { cancelled = true; };
}, [isDualTrackMode, dualTrackVocalFileHash, dualTrackAccompanimentFileHash, dualTrackTaskId]);
```

**2d. WebSocket 推送监听渲染缓存更新**

在 `RepairPage` mount 时连接 `connectCacheWS`，收到 `render_cache_updated` 事件后刷新渲染缓存：

```typescript
// 新增：监听渲染缓存 WebSocket 推送
useEffect(() => {
  if (!isDualTrackMode) return;
  
  const wsControl = connectCacheWS((event) => {
    if (event.task_id === dualTrackTaskId) {
      // 收到后端推送的新渲染缓存，刷新
      setCacheTriggerKey(k => k + 1);
    }
  });
  
  return () => wsControl.close();
}, [isDualTrackMode, dualTrackTaskId]);
```

需要在 `RepairPage.tsx` 中 import `connectCacheWS` 和 `CacheUpdateEvent`。

---

## Issue 3: 切换单轨不应清除双轨状态

### 根因
[RepairPage.tsx:270-281](file:///workspace/src/pages/RepairPage.tsx#L270-L281) — `handleSwitchToSingleTrack` 调用 `sessionActions.clearDualTrack()`，同时清空了 `isDualTrackMode: false` 和所有双轨数据。

### 修复方案

**Step 1**: `repairSessionStore` 已有 `setDualTrackMode` action（只改模式标志，不清理数据），无需新增方法。

**Step 2**: 修改 `handleSwitchToSingleTrack`，不再调用 `clearDualTrack()`：

**文件**: `src/pages/RepairPage.tsx`

```typescript
const handleSwitchToSingleTrack = useCallback(() => {
  sessionActions.setDualTrackMode(false);
  setDualTrackTaskId(null);
  setDualTrackVocalTaskId(null);
  setDualTrackAccompanimentTaskId(null);
  setDualTrackDownloadUrl(null);
  setDualTrackRepairResult(null);
  stopDualTrackPolling();
}, [stopDualTrackPolling, sessionActions]);
```

注意：不再调用 `clearDualTrack()`、不再清除 `dualTrackFilesSelected`、`dualTrackVocalFile`/`dualTrackAccompanimentFile`。store 中的文件哈希、文件名、元数据、渲染缓存保持不变。

**Step 3**: 切回双轨模式时恢复 UI 状态。当前逻辑：点击双轨按钮 → `sessionActions.setDualTrackMode(true)`。由于 store 中的文件哈希等数据还在，`dualTrackHasFiles` 会自动变为 true（`dualTrackHasFiles = dualTrackFilesSelected || (!!dualTrackVocalFileHash && !!dualTrackAccompanimentFileHash)`），文件卡片会自动显示。但 `dualTrackFilesSelected` 在切换时不再清除，所以也会保持 true。

---

## 修改文件清单

| 文件 | 改动内容 |
|------|---------|
| `backend/services/audio_repair.py` | 为所有算法添加 `supports_dual_track` 字段；`get_available_versions` 输出中包含 `supportsDualTrack` |
| `src/services/backendApi.ts` | `AlgorithmVersion` 接口添加 `supportsDualTrack?: boolean`；导出 `connectCacheWS`、`CacheUpdateEvent` |
| `src/components/AIRepairPanel.tsx` | `filteredAlgorithms` 过滤双轨不支持的算法；`fetchMemoryInfo`/`fetchStorageEstimate` 用 `effectiveDuration`/`effectiveChannels`；`refreshRenderCache` 不清空 persisted 缓存 |
| `src/pages/RepairPage.tsx` | `handleSwitchToSingleTrack` 不清除双轨数据；新增 mount 时查询渲染缓存 useEffect；新增 WebSocket 监听 `render_cache_updated` |

## 验证

1. TypeScript 编译 `npx tsc --noEmit` 零错误
2. 双轨模式下算法下拉框只显示 v3.0/v3.0a/v3.1/v3.1a
3. 双轨上传后，预估大小区域正常显示数值
4. 双轨修复后，渲染交付列表正常显示
5. 刷新页面后，渲染交付自动从后端查询恢复
6. 新渲染完成后，前端收到 WebSocket 推送并自动刷新交付列表
7. 切换到单轨 → 切回双轨 → 文件/元数据/参数/渲染缓存均在
8. 打包 `bash scripts/build_android_release.sh` 成功