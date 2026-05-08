# 卡住警告组件新增取消按钮

## 概述

在任务卡住警告组件中新增"取消"按钮，通知后端取消任务并重置前端状态。

## 当前状态

- 卡住警告组件位于 `RepairPage.tsx` L277-315
- 现有按钮：`重试`（重新执行检测/修复）和 `忽略并继续等待`
- 后端任务通过 `ThreadPoolExecutor` 执行，有 `progress_callback` 周期性回调
- 后端无 `/cancel/{task_id}` 端点
- 前端无 `cancelCurrentTask` 函数

## 修改方案

### 修改1：后端新增取消机制
**文件**: `backend/services/task_manager.py`

1. 新增全局取消集合 `_cancelled_tasks: set[str] = set()`（线程安全）
2. 新增 `cancel_task(task_id)` 函数：
   - 将 task_id 加入 `_cancelled_tasks`
   - 更新数据库状态为 `"cancelled"`
   - 通过 WebSocket 发送 cancelled 最终消息
3. 在 `_run_detect` 和 `_run_repair` 的 `progress_callback` 中检查取消标志：
   - 如果 task_id 在 `_cancelled_tasks` 中 → 抛出 `CancelledError`
   - 异常被外层 except 捕获，状态设为 error/cancelled

**文件**: `backend/api/routes.py`

4. 新增 `POST /cancel/{task_id}` 端点，调用 `task_manager.cancel_task(task_id)`

### 修改2：前端新增 cancelCurrentTask 函数
**文件**: `src/hooks/useAudioProcessor.ts`

新增 `cancelCurrentTask` 回调函数：
1. 调用后端 `POST /api/v1/cancel/{taskId}` 通知后端取消
2. 调用 `closeWS()` 关闭 WebSocket
3. 调用 `resetStuckState()` 清除卡住状态
4. 调用 `setIsProcessing(false)` / `setProcessingStep('')` / `setProcessingProgress(0)` 清除处理状态

导出给 RepairPage 使用。

### 修改3：RepairPage 卡住警告组件新增取消按钮
**文件**: `src/pages/RepairPage.tsx`

在现有按钮区域新增"取消"按钮：
- 样式：红色系（表示终止操作）
- 点击后调用 `cancelCurrentTask()`
- 文案："取消任务"

### 修改4：前端 API 层
**文件**: `src/services/backendApi.ts`

新增 `cancelTask(taskId)` 函数，调用 `POST ${API_BASE}/cancel/${taskId}`。

## 验证步骤

1. 触发任务卡住
2. 点击"取消"按钮
3. 确认：前端状态清除、后端任务停止、WebSocket 断开
4. 运行 `bash scripts/build_android_release.sh` 重新打包
