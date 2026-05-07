# WebSocket 进度推送 Spec

## Why
当前前端通过 HTTP 轮询 `/api/v1/status/{taskId}` 获取任务进度，一次60秒的修复任务产生约47次 HTTP 请求。移动端（Termux）场景下，频繁轮询导致延迟高（0.8~3秒）、电量消耗大、服务端负载高。WebSocket 可将进度推送延迟降至毫秒级，请求量从47次降为1次连接。

## What Changes
- 新增后端 WebSocket 端点 `/ws/progress/{task_id}`，服务端主动推送进度
- 新增后端 WebSocket 连接管理器，维护活跃连接并在 `progress_callback` 时广播
- 前端 `backendApi.ts` 新增 `connectProgressWS()` 函数
- 前端 `useAudioProcessor.ts` 优先使用 WebSocket，连接失败时降级到 HTTP 轮询
- 移除未使用的 SSE 端点 `/api/v1/stream/{task_id}`（已有但前端从未使用）
- 保留 HTTP 轮询作为降级方案，确保向后兼容

## Impact
- 后端: `backend/api/routes.py` (新增 WS 端点, 移除 SSE), 新增 `backend/services/ws_manager.py` (连接管理器), `backend/services/task_manager.py` (progress_callback 增加 WS 推送)
- 前端: `src/services/backendApi.ts` (新增 WS 连接函数), `src/hooks/useAudioProcessor.ts` (优先 WS, 降级轮询)
- 兼容性: HTTP 轮询完全保留，WebSocket 不可用时自动降级

## ADDED Requirements

### Requirement: WebSocket 进度推送端点
系统 SHALL 提供 WebSocket 端点 `/ws/progress/{task_id}`，当任务状态变化时主动推送进度数据。

#### Scenario: 正常进度推送
- **WHEN** 前端连接到 `/ws/progress/{task_id}` 且任务正在执行
- **THEN** 服务端在每次 `progress_callback` 调用时推送 JSON 消息 `{ task_id, status, progress, step, detection_result?, repaired_detection_result?, repair_result?, error? }`
- **AND** 任务到达终态（completed/detected/error）后推送最终消息并关闭连接

#### Scenario: 任务不存在
- **WHEN** 前端连接到 `/ws/progress/{task_id}` 但 task_id 不存在
- **THEN** 服务端推送错误消息 `{ error: "任务不存在" }` 并关闭连接

#### Scenario: 连接已存在时重连
- **WHEN** 同一 task_id 有新的 WebSocket 连接建立
- **THEN** 旧连接被关闭，新连接接管推送

### Requirement: WebSocket 连接管理器
系统 SHALL 提供 `ProgressWSManager` 单例，管理所有活跃的 WebSocket 连接。

#### Scenario: 推送进度
- **WHEN** `progress_callback` 被调用
- **THEN** 管理器查找该 task_id 对应的活跃 WebSocket 连接，发送 JSON 进度消息
- **AND** 如果发送失败（连接已断开），静默移除该连接

#### Scenario: 终态清理
- **WHEN** 任务到达终态
- **THEN** 推送最终消息后关闭并移除该 task_id 的 WebSocket 连接

### Requirement: 前端 WebSocket 连接与降级
前端 SHALL 优先使用 WebSocket 获取进度，连接失败时自动降级到 HTTP 轮询。

#### Scenario: WebSocket 连接成功
- **WHEN** 前端调用 `connectProgressWS(taskId, callbacks)` 且 WebSocket 连接成功建立
- **THEN** 进度更新通过 WebSocket `onmessage` 回调传递给 `callbacks.onProgress`
- **AND** 不启动 HTTP 轮询

#### Scenario: WebSocket 连接失败
- **WHEN** 前端调用 `connectProgressWS(taskId, callbacks)` 但 WebSocket 连接失败（超时/拒绝）
- **THEN** 自动降级到 `pollProgress()` HTTP 轮询
- **AND** 控制台输出降级日志

#### Scenario: WebSocket 连接中断
- **WHEN** WebSocket 连接在任务执行期间意外断开
- **THEN** 自动尝试重连（最多3次，间隔1s/2s/4s）
- **AND** 重连失败则降级到 HTTP 轮询

#### Scenario: WebSocket 消息到达
- **WHEN** 收到 WebSocket 消息
- **THEN** 解析 JSON 并调用 `callbacks.onProgress(event)`
- **AND** 如果 `event.status` 为终态，调用 `callbacks.onComplete(event)` 并关闭连接

## MODIFIED Requirements

### Requirement: 任务进度回调
`task_manager.py` 中的 `progress_callback` SHALL 在调用 `update_task()` 的同时，通过 `ProgressWSManager` 推送进度到 WebSocket 连接。

### Requirement: 前端进度获取
`useAudioProcessor.ts` 中的 `applySettings()` 和 `runAIDetection()` SHALL 优先使用 `connectProgressWS()` 获取进度，降级时使用 `pollProgress()`。

## REMOVED Requirements

### Requirement: SSE 进度端点
**Reason**: `/api/v1/stream/{task_id}` 已存在但前端从未使用，WebSocket 方案完全替代 SSE，且更符合双向通信需求。
**Migration**: 无需迁移，该端点无消费者。
