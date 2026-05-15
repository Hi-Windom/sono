# 修复三个 UI 缺陷

## 概述

修复用户报告的三个前端 UI 缺陷：
1. 预估大小和交付缓存更新不及时（需切换/刷新才能看到更新）
2. 导出下载框合并轨没有下载按钮
3. 直接访问 AB 对比页面没有更新记录

---

## 当前状态分析

### Issue 1: 缓存更新不及时

**涉及文件：**
- [RepairPage.tsx](/workspace/src/pages/RepairPage.tsx) — 主修复页面，持有 `renderCacheRefreshRef`
- [AIRepairPanel.tsx](/workspace/src/components/AIRepairPanel.tsx) — 渲染缓存列表和"可秒下"标记

**当前行为：**
- `AIRepairPanel` 在 `taskId`/`algorithmVersion`/`cacheTriggerKey` 变化时调用 `refreshRenderCache()` 获取渲染缓存列表
- `cacheTriggerKey` 仅在 `hasBeenProcessed` 变化时递增（修复完成时）
- 当后端渲染完成（用户选择规格后自动渲染），前端没有收到通知，需要手动切换页面或刷新

**已有基础设施：**
- `connectCacheWS()` 在 `backendApi.ts` 中已实现，通过 WebSocket 接收 `render_cache_updated` 事件
- `CacheManagerPage.tsx` 已使用此 WebSocket 更新交付渲染列表
- `AIRepairPanel` 通过 `onRenderCacheRefresh` 回调注册刷新函数到 `RepairPage`

### Issue 2: 合并轨没有按钮

**涉及文件：**
- [DownloadModal.tsx](/workspace/src/components/DownloadModal.tsx) — 导出下载对话框

**当前行为：**
- 合并轨区域（第 304-343 行）始终渲染（当 `dualTrackUrls && backendInfo` 时）
- 但下载按钮仅在 `dualTrackUrls.merged` 存在时显示（第 319 行）
- 合并轨信息区只显示文件名和音频格式，缺少文件大小、声道、时长等信息
- 当 `dualTrackUrls.merged` 为 undefined 时，合并轨显示信息但没有下载按钮

### Issue 3: ComparePage 没有更新记录

**涉及文件：**
- [ComparePage.tsx](/workspace/src/pages/ComparePage.tsx) — AB 对比页面

**当前行为：**
- 当 `taskId` 为空时，在 mount 时调用 `/api/v1/cache/info` 获取已完成任务列表
- 只获取一次，没有轮询或 WebSocket 订阅
- 如果修复在页面加载后完成，用户看不到新任务

---

## 修改方案

### Fix 1: 缓存实时更新

**目标：** 当后端渲染缓存完成时，前端自动刷新渲染缓存列表

**修改 [RepairPage.tsx](/workspace/src/pages/RepairPage.tsx)：**
- 在 RepairPage 中添加 `useEffect`，使用 `connectCacheWS` 连接缓存 WebSocket
- 当收到 `render_cache_updated` 事件且 `event.task_id` 匹配当前 `taskId` 时，调用 `renderCacheRefreshRef.current()`
- 组件卸载时关闭 WebSocket 连接

**修改 [AIRepairPanel.tsx](/workspace/src/components/AIRepairPanel.tsx)：**
- 无需修改，`refreshRenderCache` 已通过 `onRenderCacheRefresh` 注册，WebSocket 触发后自动刷新

### Fix 2: 合并轨下载按钮

**目标：** 合并轨始终显示下载按钮

**修改 [DownloadModal.tsx](/workspace/src/components/DownloadModal.tsx)：**
- 在合并轨信息区添加文件大小、声道、时长等详细信息（从 `backendInfo` 获取）
- 当 `dualTrackUrls.merged` 为 undefined 但 `backendDownloadUrl` 存在时，使用 `backendDownloadUrl` 作为合并轨的下载回退
- 修改条件渲染逻辑：合并轨的按钮区域始终渲染，URL 优先使用 `dualTrackUrls.merged`，回退到 `backendDownloadUrl`

### Fix 3: ComparePage 实时更新

**目标：** 直接访问 ComparePage 时，任务列表能实时更新

**修改 [ComparePage.tsx](/workspace/src/pages/ComparePage.tsx)：**
- 添加轮询机制：每 5 秒重新获取 `/api/v1/cache/info` 更新任务列表
- 使用 `useRef` 管理轮询定时器，组件卸载时清除
- 当 `taskId` 变化时重置轮询

---

## 验证步骤

1. **Fix 1 验证：** 在修复页面选择规格后，等待后端渲染完成，观察"可秒下"标记是否自动出现
2. **Fix 2 验证：** 打开双轨修复的导出对话框，确认合并轨有 WAV/MP3/复制链接按钮
3. **Fix 3 验证：** 直接访问 `/compare` 页面，在另一个标签页完成修复，观察任务列表是否自动更新