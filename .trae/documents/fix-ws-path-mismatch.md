# 修复 WebSocket 路径不匹配导致进度丢失和自动下载失败

## Summary

**根因**：前端 WebSocket 连接路径与后端路由不匹配，导致 403 Forbidden。
- 前端连接：`/api/v1/ws/progress/{taskId}`（多了 `/progress`）
- 后端路由：`/api/v1/ws/{task_id}`（[routes.py:416](file:///workspace/backend/api/routes.py#L416)）

此问题在 v2.4 合并提交（`e4e1317`）中就已存在，**不是位深优化引入的回归**。但影响链路：
1. WS 403 → 重连3次均失败 → 降级到 HTTP 轮询
2. 修复阶段的轮询可能部分工作（有 `[后端]` 前缀但延迟高），但渲染阶段 `waitRenderWithWS()` 也使用同一个断连的 `connectProgressWS`，导致渲染完成后 Promise 不 resolve → 自动下载不触发

## Current State Analysis

### 问题现象（用户报告）
1. **进度显示没有 `[后端]` 前缀** — 来自 [useAudioProcessor.ts:1374](file:///workspace/src/hooks/useAudioProcessor.ts#L1374) 的 `setProcessingStep(\`[后端] ${event.step}\`)`，仅在 WS `onProgress` 回调中设置
2. **自动下载不触发** — [useAudioProcessor.ts:1659](file:///workspace/src/hooks/useAudioProcessor.ts#L1659) 的 `renderAndDownload()` 在 backendRepairPromise fulfilled 后调用，依赖 WS/polling 的 `onComplete` 触发 Promise resolve

### 根因定位

| 组件 | 文件 | 行号 | 实际路径 |
|------|------|------|---------|
| 前端 WS 连接 | [backendApi.ts:911](file:///workspace/src/services/backendApi.ts#L911) | L911 | `/api/v1/ws/progress/${taskId}` |
| 后端 WS 路由 | [routes.py:416](file:////workspace/backend/api/routes.py#L416) | L416 | `@router.websocket("/ws/{task_id}")` |
| Vite 代理 | [vite.config.ts:134](file:///workspace/vite.config.ts#L134) | L134 | `/api` → backend, `ws: true` |

前端比后端**多了一个 `/progress` 段**，FastAPI 对无法匹配的 WebSocket 路径返回 403。

### 影响范围
- `connectProgressWS()` 被2处调用：
  1. `applySettings()` 中修复进度监听（[useAudioProcessor.ts:1368](file:///workspace/src/hooks/useAudioProcessor.ts#L1368)）
  2. `waitRenderWithWS()` 中渲染进度监听（[backendApi.ts:1149](file:///workspace/src/services/backendApi.ts#L1149)）
- 两处都受影响：修复进度 + 渲染进度均走断连的 WS

### 上次修改回顾（位深优化提交）
- ✅ `generateExportFilename()` 工具函数 — 有效改进，保留
- ✅ `processingOptionsRef` / `algorithmVersionRef` — 正确模式，保留
- ⚠️ `renderAndDownload` deps 简化为 `[audioFile]` — 无害，保留
- ❌ Bug 1 诊断错误（闭包陈旧值）— 实际是 WS 路径问题，需纠正

## Proposed Changes

### 修改 1：修复 WebSocket URL 路径（核心修复）

**文件**：`/workspace/src/services/backendApi.ts`
**行号**：L911
**内容**：
```typescript
// 修改前:
const wsUrl = `${protocol}//${wsHost}/api/v1/ws/progress/${taskId}`;

// 修改后:
const wsUrl = `${protocol}//${wsHost}/api/v1/ws/${taskId}`;
```

**原因**：对齐后端 `@router.websocket("/ws/{task_id}")` 路由（prefix `/api/v1` + 路由 `/ws/{task_id}` = `/api/v1/ws/{task_id}`）

### 修改 2：无需其他改动

以下上次提交的内容经验证无问题，全部保留：
- `generateExportFilename()` 函数及所有文件名替换
- `processingOptionsRef` / `algorithmVersionRef` 引用模式
- `renderAndDownload` 的依赖数组简化
- RepairPage.tsx / Home.tsx 中的文件名更新

## Assumptions & Decisions
1. 后端 WS 路由 `/ws/{task_id}` 是正确的唯一端点，不需要新增 `/ws/progress/` 路由
2. Vite 代理配置 (`ws: true`) 已正确转发 WebSocket 升级请求，修复路径后代理应正常工作
3. 不需要同时修改后端来兼容旧的前端路径——前端改一处即可

## Verification Steps
1. 启动 dev 环境：`bash scripts/start_dev.sh`
2. 打开浏览器控制台，上传音频文件，点击"开始修复"
3. **验证1**：控制台应显示 `[WS] 连接成功 task_id=xxx`（不再是 403）
4. **验证2**：进度文字应显示 `[后端] xxx` 格式的步骤信息
5. **验证3**：修复完成后应自动弹出下载模态框（`setShowDownloadModal(true)`）
6. **验证4**：下载文件名格式为 `新项目_v2.4a_48k_24bit_20260511_xxxxxx.wav`
7. 运行测试：`cd /workspace && python -m pytest backend/tests/test_repair_quality.py -v`
8. 打包 Android：`bash scripts/build_android_release.sh`
