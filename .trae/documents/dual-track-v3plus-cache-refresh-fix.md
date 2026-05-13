# 双轨模式 3 项修复计划

## 现状分析

### Issue 1: v3+算法支持双轨模式 — 遗漏的UI提示

**根因**: 之前的修改已移除 `filteredAlgorithms` 过滤和算法回退 `useEffect`，但还有两处 UI 文本仍然提示「仅支持 v3.0/v3.0a」：

1. [AIRepairPanel.tsx:L369-L375](file:///workspace/src/components/AIRepairPanel.tsx#L369-L375): `双轨模式仅支持 v3.0/v3.0a 算法` — 已过时，需移除或改为通用提示
2. [RepairPage.tsx:L619](file:///workspace/src/pages/RepairPage.tsx#L619): `双轨上传 (v3.0)` — 按钮文字仍标注 v3.0

**修改方案**: 
- 移除 `双轨模式仅支持 v3.0/v3.0a 算法` 提示（或改为 `v3+算法支持双轨模式`）
- 按钮文字 `双轨上传 (v3.0)` → `双轨上传`

### Issue 2: 双轨模式修复缓存没有正确命中

**根因**: 后端已完整实现 `find_dual_repair_cache` ([database.py:L209-L278](file:///workspace/backend/database.py#L209-L278)) 和 `/cache/lookup-dual` 端点 ([routes.py:L2161-L2176](file:///workspace/backend/api/routes.py#L2161-L2176))，前端也有 `lookupDualRepairCache` 函数 ([backendApi.ts:L791-L808](file:///workspace/src/services/backendApi.ts#L791-L808))。但 `handleDualTrackRepair` ([RepairPage.tsx:L350-L407](file:///workspace/src/pages/RepairPage.tsx#L350-L407)) **从未调用** `lookupDualRepairCache`，直接提交修复请求，导致即使有完全匹配的缓存也重新修复。

对比单轨模式：`useAudioProcessor.ts` 的 `applySettings` 函数在修复前会先调用 `lookupRepairCache`，命中则展示 `RepairCacheModal`。

**修改方案**:

1. **在 `handleDualTrackRepair` 中增加缓存查询**：
   - 修复前先调用 `lookupDualRepairCache(vocalHash, accHash, backendParams)`
   - 命中时设置 `dualCacheHitInfo` state 并展示 `RepairCacheModal`
   - 用户选择使用缓存 → 直接恢复 `repair_result`、设置 `dualTrackTaskId`
   - 用户选择重新修复 → 走现有流程

2. **扩展 `RepairCacheModal` 支持双轨模式**：
   - 新增 `isDualTrack` prop 控制 UI 文案
   - 新增 `onUseDualCache` 回调处理双轨缓存恢复

### Issue 3: 刷新后双轨模式预估大小和交付更新失效

**根因**: 页面刷新后：
- `isDualTrackMode` → 从 localStorage 恢复 ✅
- `dualTrackVocalFileHash` / `dualTrackAccompanimentFileHash` → 从 localStorage 恢复 ✅
- `dualTrackTaskId` / `dualTrackVocalTaskId` / `dualTrackAccompanimentTaskId` → **React state，刷新丢失** ❌

AIRepairPanel 接收的 `taskId` 为 `isDualTrackMode ? dualTrackTaskId : taskId`，刷新后 `dualTrackTaskId` 为 null，导致：
- `fetchRenderCache(taskId)` 因 taskId 为 null 而返回空 → 交付更新失效
- `fetchMemoryInfo(taskId)` 因 taskId 为 null 而无法估算 → 预估大小失效

**修改方案**:

1. **将 `dualTrackTaskId` 持久化到 `repairSessionStore`**：
   - 新增 `dualTrackTaskId` 字段到 store
   - 在 `handleDualTrackUpload` 和 `handleDualTrackRepair`（`repairDualFromHash` 分支）中调用 `sessionActions.setDualTrackTaskId(id)`

2. **刷新后恢复验证**：
   - 页面加载时，如果 `isDualTrackMode` 且 `dualTrackTaskId` 存在，通过 `get_task` API 验证任务是否仍然有效
   - 如果任务无效（被清理），清除持久化的 taskId

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `src/components/AIRepairPanel.tsx` | Issue 1: 移除过时的双轨算法限制提示 |
| `src/pages/RepairPage.tsx` | Issue 1: 按钮文字更新；Issue 2: handleDualTrackRepair 增加缓存查询；Issue 3: 持久化 dualTrackTaskId |
| `src/store/repairSessionStore.ts` | Issue 3: 新增 dualTrackTaskId 字段和 setter |
| `src/components/RepairCacheModal.tsx` | Issue 2: 新增 isDualTrack + onUseDualCache 支持 |

---

## 验证步骤

1. `bash scripts/start_dev.sh` 启动 dev 服务器
2. **Issue 1**: 切换到双轨模式 → 确认算法下拉框包含 v3.0/v3.0a/v3.1/v3.1a → 确认不再显示"仅支持 v3.0/v3.0a"提示 → 确认按钮显示"双轨上传"（不带 v3.0）
3. **Issue 2**: 上传双轨文件 → 选择 v3.1 → 修复 → 修复完成后 → 重新点击修复 → 确认弹出缓存命中提示
4. **Issue 3**: 双轨模式上传文件 → 修复 → 刷新页面 → 确认预估大小和交付缓存正常显示
5. `bash scripts/build_android_release.sh` 打包验证