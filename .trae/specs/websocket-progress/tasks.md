# Tasks

- [x] Task 1: 创建 WebSocket 连接管理器 `backend/services/ws_manager.py`
  - [x] 1.1: 实现 `ProgressWSManager` 单例类，维护 `{task_id: [WebSocket]}` 映射
  - [x] 1.2: 实现 `connect(task_id, websocket)` 方法，注册连接并关闭同 task_id 的旧连接
  - [x] 1.3: 实现 `disconnect(task_id, websocket)` 方法，移除连接
  - [x] 1.4: 实现 `send_progress(task_id, data)` 方法，推送进度并清理断开的连接
  - [x] 1.5: 实现 `send_final(task_id, data)` 方法，推送终态消息并关闭连接

- [x] Task 2: 添加 WebSocket 端点到 `backend/api/routes.py`
  - [x] 2.1: 新增 `/ws/progress/{task_id}` WebSocket 路由
  - [x] 2.2: 连接时验证 task_id 存在，不存在则发送错误并关闭
  - [x] 2.3: 连接成功后立即推送当前任务状态（避免首帧延迟）
  - [x] 2.4: 保持连接直到任务终态或客户端断开
  - [x] 2.5: 移除未使用的 SSE 端点 `/api/v1/stream/{task_id}`

- [x] Task 3: 修改 `backend/services/task_manager.py` 集成 WS 推送
  - [x] 3.1: 在 `_run_detect` 和 `_run_repair` 的 `progress_callback` 中增加 WS 推送调用
  - [x] 3.2: 在任务终态更新时调用 `ws_manager.send_final()`

- [x] Task 4: 前端 `backendApi.ts` 新增 WebSocket 连接函数
  - [x] 4.1: 新增 `connectProgressWS(taskId, callbacks, terminalStates)` 函数
  - [x] 4.2: 返回 `{ close(), ws }` 控制对象
  - [x] 4.3: 实现断线重连逻辑（最多3次，指数退避）
  - [x] 4.4: 重连失败时降级到 `pollProgress()` HTTP 轮询
  - [x] 4.5: 消息解析与 callbacks 分发（onProgress/onComplete/onError/onStuck/onUnstuck）

- [x] Task 5: 前端 `useAudioProcessor.ts` 集成 WebSocket
  - [x] 5.1: 修改 `applySettings()` 中的后端修复进度获取，优先使用 `connectProgressWS()`
  - [x] 5.2: 修改 `runAIDetection()` 中的检测进度获取，优先使用 `connectProgressWS()`
  - [x] 5.3: 确保组件卸载或新任务提交时关闭旧 WebSocket 连接

- [x] Task 6: 验证与测试
  - [x] 6.1: 桌面端启动服务，浏览器控制台验证 WebSocket 连接和进度推送
  - [x] 6.2: 模拟 WebSocket 连接失败，验证降级到 HTTP 轮询
  - [x] 6.3: 验证 Termux 环境下 WebSocket 可用性（uvicorn[standard] 包含 websockets 库）

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] independent of backend tasks
- [Task 5] depends on [Task 4]
- [Task 6] depends on [Task 2, Task 3, Task 5]
