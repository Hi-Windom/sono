# 架构优化 Phase 1：统一任务生命周期 - Verification Checklist

## BaseTask & TaskExecutor
- [ ] `BaseTask` 是抽象基类，不能直接实例化
- [ ] `BaseTask.execute()` 是抽象方法，子类必须实现
- [ ] `BaseTask.cancel()` 可重写，默认设置取消标志
- [ ] `BaseTask.cleanup()` 可重写，默认空实现
- [ ] `TaskExecutor.submit()` 同步设置初始状态（pending + progress=0）
- [ ] `TaskExecutor` 正确管理并发计数（_track_task_start/_track_task_end）
- [ ] 并发超过限制时拒绝任务并正确设置 error 状态
- [ ] 任务失败时 _active_tasks 计数正确清理
- [ ] 任务取消时 _cancelled_tasks 正确清理
- [ ] finally 块确保所有资源清理

## 状态流转
- [ ] 正常完成：pending → processing → completed
- [ ] 执行失败：pending → processing → error
- [ ] 执行中取消：pending → processing → cancelled
- [ ] 未开始就取消：pending → cancelled
- [ ] 每个状态变更都更新数据库
- [ ] 每个状态变更都有日志
- [ ] progress_callback 在 processing 阶段正常调用

## WebSocket 消息
- [ ] 任务开始时发送 initial progress
- [ ] 执行期间发送 progress 消息
- [ ] 正常完成时发送 final completed 消息
- [ ] 失败时发送 final error 消息
- [ ] 取消时发送 final cancelled 消息
- [ ] 消息发送失败不影响任务执行

## 取消机制
- [ ] pending 状态取消：不执行，直接标记 cancelled
- [ ] processing 状态取消：通过 progress_callback 检查取消标志并抛出 TaskCancelledError
- [ ] 取消后 _cancelled_tasks 集合正确清理
- [ ] 取消后 _active_tasks 计数正确清理
- [ ] 重复取消返回 False，不重复处理

## 任务迁移正确性
### Repair 任务
- [ ] `submit_repair_task` 行为与重构前一致
- [ ] `cancel_task` 对 repair 任务有效
- [ ] 单轨修复正常工作
- [ ] 双轨修复正常工作
- [ ] 修复结果正确写入数据库
- [ ] 所有 repair 相关测试通过

### Detect 任务
- [ ] `submit_detect_task` 行为与重构前一致
- [ ] `cancel_task` 对 detect 任务有效
- [ ] 检测结果正确写入数据库
- [ ] 所有 detect 相关测试通过

### Render 任务
- [ ] 渲染提交接口行为与重构前一致
- [ ] `cancel_task` 对 render 任务有效
- [ ] 单轨渲染正常工作
- [ ] 双轨渲染正常工作
- [ ] 渲染结果正确写入数据库
- [ ] 所有 render 相关测试通过

## 一致性测试
- [ ] TaskConformanceTest 基类包含 10+ 个测试场景
- [ ] RepairTask 通过一致性测试
- [ ] DetectTask 通过一致性测试
- [ ] RenderTask 通过一致性测试
- [ ] 新任务类型可以轻松继承并获得测试

## 代码质量
- [ ] 任务管理相关代码减少 30%+
- [ ] 没有重复的 try/except/finally 模式
- [ ] 所有状态流转集中在 TaskExecutor
- [ ] 兼容层（旧 API）保持向后兼容
- [ ] 代码结构清晰，易于添加新任务类型

## 测试通过
- [ ] 所有回归测试通过
- [ ] 所有 API 测试通过
- [ ] 所有严重 bug 测试通过
- [ ] 没有引入新的依赖
- [ ] 性能没有明显退化
