# 双轨模式 3 项修复计划

## 现状分析

### Issue 1: v3+算法支持双轨模式 — 遗漏的UI提示

之前已移除 `filteredAlgorithms` 过滤和算法回退 `useEffect`，但还有两处 UI 文本仍提示「仅支持 v3.0/v3.0a」：

1. [AIRepairPanel.tsx:L369-L375](file:///workspace/src/components/AIRepairPanel.tsx#L369-L375): `双轨模式仅支持 v3.0/v3.0a 算法`
2. [RepairPage.tsx:L619](file:///workspace/src/pages/RepairPage.tsx#L619): `双轨上传 (v3.0)`

**修改**: 移除过时提示 + 按钮文字改为 `双轨上传`

### Issue 2: 双轨模式修复缓存没有正确命中

**根因**: 后端 `find_dual_repair_cache` ([database.py:L209](file:///workspace/backend/database.py#L209)) 和 `/cache/lookup-dual` 端点 ([routes.py:L2161](file:///workspace/backend/api/routes.py#L2161)) 完整实现，前端 `lookupDualRepairCache` ([backendApi.ts:L791](file:///workspace/src/services/backendApi.ts#L791)) 已定义但**从未被调用**。

单轨模式：`useAudioProcessor.ts` 的 `applySettings` 在修复前调用 `lookupRepairCache`，命中则展示 `RepairCacheModal`。双轨模式：`handleDualTrackRepair` 直接提交修复，跳过缓存查询。

**修改**:
1. `handleDualTrackRepair` 修复前先调用 `lookupDualRepairCache`
2. 命中时展示 `RepairCacheModal`（新增 `isDualTrack` + `onUseDualCache` 支持）
3. 用户可选择使用缓存或重新修复

### Issue 3: 刷新后双轨模式预估大小和交付更新失效

**根因分析**:

| 数据 | 刷新后状态 | 影响 |
|------|-----------|------|
| `isDualTrackMode` | ✅ localStorage 恢复 | 双轨UI正常显示 |
| `dualTrackVocalFileHash` / `dualTrackAccompanimentFileHash` | ✅ localStorage 恢复 | 可基于hash查找原始任务 |
| `dualTrackVocalInfo` / `dualTrackAccompanimentInfo` | ❌ React state，丢失 | duration/channels 为 0 → 预估使用fallback值(300s/2ch) |
| `dualTrackTaskId` | ❌ React state，丢失 | renderCaches 无taskId可查 → 交付列表为空 |
| `renderCaches` | ❌ React state，丢失 | 即使 taskId 可用也无法恢复 |

**设计原则**（用户明确要求）：
- 预估大小和交付更新不应当依赖 task
- 上传 task 和修复 task 完全独立
- 前端恢复后使用新的修复 task（通过 `repairDualFromHash` 创建）

**修改**:

**3a. 持久化文件元数据**（预估大小恢复）

在 `repairSessionStore` 中新增 `dualTrackVocalInfo` / `dualTrackAccompanimentInfo`（`sample_rate`/`channels`/`duration`）。这是**文件元数据**，不是 task 状态。上传/替换文件时同步写入 store → 刷新后从 localStorage 恢复 → `fetchMemoryInfo`/`fetchStorageEstimate` 正常调用。

**3b. 持久化交付缓存**（渲染缓存恢复）

在 `repairSessionStore` 中新增 `dualTrackRenderCaches: RenderCacheEntry[]` 字段。不持久化 taskId，直接持久化缓存条目本身（含 filename/size/sample_rate/bit_depth/track_type/algorithm_version）。刷新后直接展示已缓存的交付列表。

流程：
- AIRepairPanel 的 `onRenderCachesLoaded` → 同步写入 `sessionActions.setDualTrackRenderCaches(caches)`
- 刷新后 → `RepairPage` 从 store 读取 → 通过新 prop `persistedRenderCaches` 传给 AIRepairPanel
- AIRepairPanel 初始化时合并 `persistedRenderCaches` + 后端实时数据
- 用户点击修复 → `repairDualFromHash` 创建新 task → 修复+渲染完成后新缓存覆盖旧缓存

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `src/store/repairSessionStore.ts` | Issue 3: 新增 `dualTrackVocalInfo` / `dualTrackAccompanimentInfo` / `dualTrackRenderCaches` 持久化字段 + setters |
| `src/pages/RepairPage.tsx` | Issue 1: 按钮文字；Issue 2: handleDualTrackRepair 缓存查询；Issue 3: 上传时持久化文件元数据，刷新后恢复渲染缓存 |
| `src/components/AIRepairPanel.tsx` | Issue 1: 移除过时提示；Issue 3: 新增 `persistedRenderCaches` prop |
| `src/components/RepairCacheModal.tsx` | Issue 2: 新增 isDualTrack + onUseDualCache 支持 |

---

## 验证步骤

1. `bash scripts/start_dev.sh` 启动 dev 服务器
2. **Issue 1**: 切换双轨模式 → 算法下拉框包含全部 v3+ → 无"仅支持 v3.0"提示 → 按钮"双轨上传"
3. **Issue 2**: 上传双轨文件 → 修复 → 再次点击修复 → 弹出缓存命中提示
4. **Issue 3**: 上传双轨文件 → 修复 → 渲染完成 → 刷新页面 → **预估大小正常显示** + **交付缓存列表正常显示** → 点击修复 → 新修复完成且缓存更新
5. `bash scripts/build_android_release.sh` 打包验证